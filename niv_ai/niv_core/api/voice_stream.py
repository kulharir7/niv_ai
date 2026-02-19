"""
Streaming Voice API — Real-time voice responses with clause-level TTS chunking.

Flow:
  Browser STT text → LLM streaming → clause chunking → Edge TTS per chunk
  → frappe.realtime push → frontend audio queue → gapless playback

Achieves ~1.5s first-audio latency vs ~12s in sequential mode.
"""
import json
import base64
import os
import re
import uuid
import asyncio
import hashlib
import time
import threading
import queue as queue_module
from typing import List, Optional

import frappe
from frappe import _

from niv_ai.niv_core.utils import get_niv_settings
from niv_ai.niv_core.api._helpers import (
    validate_conversation,
    save_user_message,
    save_assistant_message,
    auto_title,
)
from niv_ai.niv_core.api.voice import clean_text_for_tts

try:
    from niv_ai.niv_core.utils.rate_limiter import check_rate_limit
    from niv_ai.niv_core.utils.logger import log_api_call
except ImportError:
    check_rate_limit = lambda *a, **kw: None
    log_api_call = lambda *a, **kw: None


# ─── Constants ───────────────────────────────────────────────────────────

# Minimum words before a clause break triggers TTS generation.
# Prevents very short fragments like "Ha," from becoming standalone audio.
MIN_CLAUSE_WORDS = 3

# Maximum characters per TTS chunk — prevents excessively long single chunks.
MAX_CHUNK_CHARS = 200

# Sentence-ending punctuation (full stops, question marks, etc.)
SENTENCE_ENDS = frozenset({".", "?", "!", "।", "。"})

# Clause-breaking punctuation (commas, semicolons, etc.)
# Note: । (Devanagari danda) is in SENTENCE_ENDS only — it's a full stop in Hindi.
CLAUSE_BREAKS = frozenset({",", ";", ":", "—", "–"})

# Common filler phrases pre-cached for instant playback.
# Maps language → list of (trigger_context, phrase) tuples.
FILLER_PHRASES = {
    "tool_start": "Ek second, check kar raha hoon...",
    "tool_start_en": "Let me check that for you...",
    "thinking": "Sochta hoon...",
    "error": "Maaf kijiye, kuch galat ho gaya.",
}

# Redis key prefix for cached TTS audio
CACHE_KEY_PREFIX = "niv_voice_cache:"
CACHE_TTL_SECONDS = 3600  # 1 hour


# ─── Clause-level Smart Chunker ─────────────────────────────────────────

class ClauseChunker:
    """Accumulates streaming tokens and yields complete clauses for TTS.

    Strategy:
      1. Tokens arrive one-by-one from LLM stream.
      2. Buffer them until a clause boundary is detected.
      3. Yield the clause only if it has >= MIN_CLAUSE_WORDS words.
      4. If the clause is too short, keep buffering until the next break.
      5. On flush (stream end), yield whatever remains.

    Clause boundaries (in priority order):
      - Sentence enders: . ? ! । 。
      - Clause breakers: , ; : — –   (only if buffer >= MIN_CLAUSE_WORDS)

    Special handling:
      - Markdown/code blocks are stripped (not spoken).
      - Numbers with decimals (3.14) don't trigger sentence break.
      - Abbreviations (Dr. Mr. etc.) don't trigger break.
    """

    # Abbreviations that use period but aren't sentence endings
    _ABBREVS = frozenset({
        "dr", "mr", "mrs", "ms", "prof", "sr", "jr", "st", "vs",
        "etc", "inc", "ltd", "corp", "dept", "govt", "approx",
        "no", "vol", "ref", "fig", "sec",
    })

    def __init__(self):
        self._buffer: str = ""
        self._in_code_block: bool = False
        self._backtick_count: int = 0
        self._first_chunk: bool = True

    def feed(self, token: str) -> List[str]:
        """Feed a token, return list of ready clauses (0 or more)."""
        clauses: List[str] = []

        for char in token:
            # Track code block fences (``` ... ```)
            if char == "`":
                self._backtick_count += 1
                if self._backtick_count == 3:
                    self._in_code_block = not self._in_code_block
                    self._backtick_count = 0
                continue
            else:
                self._backtick_count = 0

            # Skip content inside code blocks
            if self._in_code_block:
                continue

            self._buffer += char

            # Check for clause boundary
            if char in SENTENCE_ENDS:
                if self._is_real_sentence_end():
                    clause = self._try_yield()
                    if clause:
                        clauses.append(clause)

            elif char in CLAUSE_BREAKS:
                # Only break at clauses if we have enough words
                if self._word_count() >= MIN_CLAUSE_WORDS:
                    clause = self._try_yield()
                    if clause:
                        clauses.append(clause)

            # Force break if buffer is too long (prevents memory buildup)
            elif len(self._buffer) > MAX_CHUNK_CHARS:
                # Find last space to break at word boundary
                last_space = self._buffer.rfind(" ", 0, MAX_CHUNK_CHARS)
                if last_space > 0:
                    clause = self._buffer[:last_space].strip()
                    self._buffer = self._buffer[last_space:].lstrip()
                    if clause:
                        clauses.append(clause)

        return clauses

    def flush(self) -> Optional[str]:
        """Flush remaining buffer. Call when stream ends.
        Uses full TTS cleaning (from voice.py) for the final chunk."""
        if self._buffer.strip():
            clause = clean_text_for_tts(self._buffer)
            self._buffer = ""
            return clause if clause else None
        return None

    def _is_real_sentence_end(self) -> bool:
        """Check if the period is a real sentence end (not abbreviation/decimal)."""
        buf = self._buffer.rstrip()
        if not buf.endswith("."):
            return True  # Non-period punctuation is always a real end

        # Check for decimal numbers: "3.14", "50.5"
        if len(buf) >= 2 and buf[-2].isdigit():
            return False

        # Check for abbreviations: "Dr.", "Mr.", etc.
        # Find the word before the period
        words = buf.split()
        if words:
            last_word = words[-1].rstrip(".").lower()
            if last_word in self._ABBREVS:
                return False

        return True

    def _word_count(self) -> int:
        """Count words in current buffer."""
        return len(self._buffer.split())

    def _try_yield(self) -> Optional[str]:
        """Try to yield the buffer as a clause.
        First chunk uses lower threshold (1 word) for faster first audio."""
        clause = self._clean(self._buffer)
        self._buffer = ""
        min_words = 1 if self._first_chunk else MIN_CLAUSE_WORDS
        if clause and len(clause.split()) >= min_words:
            self._first_chunk = False
            return clause
        elif clause:
            # Too short — put it back
            self._buffer = clause + " "
            return None
        return None

    def _clean(self, text: str) -> str:
        """Clean text for TTS — remove markdown artifacts."""
        t = text.strip()
        # Remove markdown bold/italic markers
        t = re.sub(r"\*\*\*(.+?)\*\*\*", r"\1", t)
        t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
        t = re.sub(r"\*(.+?)\*", r"\1", t)
        t = re.sub(r"__(.+?)__", r"\1", t)
        t = re.sub(r"_(.+?)_", r"\1", t)
        # Remove heading markers
        t = re.sub(r"^#{1,6}\s+", "", t)
        # Remove list markers
        t = re.sub(r"^[\s]*[-*+]\s+", "", t)
        t = re.sub(r"^[\s]*\d+\.\s+", "", t)
        # Remove inline code
        t = re.sub(r"`[^`]+`", "", t)
        # Remove URLs
        t = re.sub(r"https?://\S+", "", t)
        # Remove markdown links [text](url) → text
        t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
        # Remove HTML tags
        t = re.sub(r"<[^>]+>", "", t)
        # Collapse whitespace
        t = re.sub(r"\s{2,}", " ", t)
        return t.strip()


# ─── TTS Engine (Edge TTS, async, per-chunk) ────────────────────────────

def _detect_language(text: str) -> str:
    """Detect if text is Hindi or English based on character analysis."""
    hindi_chars = sum(1 for c in text if "\u0900" <= c <= "\u097F")
    total_alpha = sum(1 for c in text if c.isalpha()) or 1
    hindi_ratio = hindi_chars / total_alpha

    # Also check for Romanized Hindi keywords
    # Note: "main" excluded — ambiguous (English "main" vs Hindi "I")
    hindi_words = {
        "kya", "hai", "haan", "nahi", "aap", "kaise", "mera",
        "tera", "yeh", "woh", "kaisa", "kitna", "kaha", "kyun", "abhi",
        "acha", "theek", "bahut", "zyada", "kam", "bada", "chhota",
        "mujhe", "humara", "tumhara", "bhai", "dost", "paisa",
    }
    words = set(text.lower().split())
    romanized_hindi = len(words & hindi_words)

    if hindi_ratio > 0.3 or romanized_hindi >= 2:
        return "hi"
    return "en"


def _get_edge_voice(language: str) -> str:
    """Get the appropriate Edge TTS voice for the language."""
    voices = {
        "hi": "hi-IN-SwaraNeural",
        "en": "en-US-JennyNeural",
    }
    return voices.get(language, voices["en"])


def _compute_cache_key(text: str, voice: str) -> str:
    """Generate a Redis cache key for a TTS audio chunk."""
    content_hash = hashlib.md5(f"{text}:{voice}".encode()).hexdigest()
    return f"{CACHE_KEY_PREFIX}{content_hash}"


def _get_cached_audio(cache_key: str) -> Optional[str]:
    """Retrieve cached TTS audio (base64) from Redis."""
    try:
        cached = frappe.cache().get_value(cache_key)
        if cached:
            return cached
    except Exception:
        pass
    return None


def _set_cached_audio(cache_key: str, audio_base64: str):
    """Store TTS audio (base64) in Redis with TTL."""
    try:
        frappe.cache().set_value(cache_key, audio_base64, expires_in_sec=CACHE_TTL_SECONDS)
    except Exception:
        pass


def _generate_tts_chunk(text: str, voice: str) -> Optional[dict]:
    """Generate TTS audio for a single text chunk using Edge TTS.

    Returns dict with base64-encoded audio and metadata, or None on failure.
    Uses Redis caching to avoid regenerating identical chunks.
    """
    if not text or not text.strip():
        return None

    # Check cache first
    cache_key = _compute_cache_key(text, voice)
    cached = _get_cached_audio(cache_key)
    if cached:
        return {
            "audio_base64": cached,
            "text": text,
            "voice": voice,
            "cached": True,
            "format": "mp3",
        }

    try:
        import edge_tts
    except ImportError:
        frappe.logger().warning("edge_tts not installed — cannot generate streaming TTS")
        return None

    output_path = os.path.join(
        frappe.get_site_path("private", "files"),
        f"niv_stream_tts_{uuid.uuid4().hex[:12]}.mp3",
    )

    try:
        # Run Edge TTS (async → sync bridge)
        async def _gen():
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_path)

        # Safe async execution — reuse thread-local loop if available
        _loop = getattr(_generate_tts_chunk, "_loop", None)
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
            _generate_tts_chunk._loop = _loop
        try:
            _loop.run_until_complete(_gen())
        except RuntimeError:
            # Fallback: create fresh loop
            _loop = asyncio.new_event_loop()
            _generate_tts_chunk._loop = _loop
            _loop.run_until_complete(_gen())

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            return None

        # Read and encode
        with open(output_path, "rb") as f:
            audio_bytes = f.read()

        audio_base64 = base64.b64encode(audio_bytes).decode("ascii")

        # Cache for future use
        _set_cached_audio(cache_key, audio_base64)

        # Clean up temp file
        try:
            os.unlink(output_path)
        except Exception:
            pass

        return {
            "audio_base64": audio_base64,
            "text": text,
            "voice": voice,
            "cached": False,
            "format": "mp3",
        }

    except Exception as e:
        frappe.logger().warning(f"Edge TTS chunk failed for '{text[:50]}...': {e}")
        # Clean up on failure
        try:
            if os.path.exists(output_path):
                os.unlink(output_path)
        except Exception:
            pass
        return None


# ─── Pre-cache Common Phrases ───────────────────────────────────────────

def _ensure_filler_cache():
    """Pre-generate and cache filler phrases on first use."""
    for key, phrase in FILLER_PHRASES.items():
        # Explicit language mapping — _en suffix = English, otherwise detect
        if key.endswith("_en"):
            lang = "en"
        else:
            lang = _detect_language(phrase)
        voice = _get_edge_voice(lang)
        cache_key = _compute_cache_key(phrase, voice)
        if not _get_cached_audio(cache_key):
            result = _generate_tts_chunk(phrase, voice)
            if result:
                frappe.logger().info(f"Pre-cached filler phrase: '{phrase}' ({voice})")


def _safe_ensure_filler_cache(site_name):
    """Thread-safe filler cache warmup — runs in background thread."""
    try:
        frappe.init(site=site_name)
        frappe.connect()
        _ensure_filler_cache()
    except Exception:
        pass
    finally:
        try:
            frappe.db.close()
        except Exception:
            pass


# ─── Main Streaming Voice Endpoint ──────────────────────────────────────

@frappe.whitelist(methods=["GET", "POST"])
def stream_voice_chat(**kwargs):
    """Stream voice chat — accepts text, streams audio chunks back via SSE.

    Input (POST JSON):
        text: str               — User's spoken text (from browser STT)
        conversation_id: str    — Conversation ID (auto-created if empty)
        voice: str              — Optional override for TTS voice

    Response: SSE stream with events:
        audio_chunk  — Base64-encoded audio chunk + text
        text_chunk   — Text-only chunk (for display)
        tool_call    — Tool being called
        tool_result  — Tool result
        filler       — Filler audio during tool execution
        done         — Stream complete with full response text
        error        — Error message
    """
    check_rate_limit()
    log_api_call("stream_voice_chat")

    # Parse input
    try:
        data = frappe.request.get_json(silent=True) or {}
    except Exception:
        data = {}

    text = (data.get("text") or frappe.form_dict.get("text") or "").strip()
    conversation_id = data.get("conversation_id") or frappe.form_dict.get("conversation_id") or ""
    voice_override = data.get("voice") or frappe.form_dict.get("voice") or ""

    if not text:
        frappe.throw(_("No text provided"))

    user = frappe.session.user

    # Auto-create conversation if needed
    if not conversation_id:
        conv = frappe.get_doc({
            "doctype": "Niv Conversation",
            "user": user,
            "title": text[:50],
            "channel": "webchat",
        })
        conv.insert(ignore_permissions=True)
        frappe.db.commit()
        conversation_id = conv.name

    validate_conversation(conversation_id, user)
    save_user_message(conversation_id, text, dedup=True)

    # Get LLM settings
    settings = get_niv_settings()
    provider = settings.default_provider
    model = settings.default_model

    # Capture site for re-init inside generator
    _site_name = frappe.local.site

    def generate():
        """SSE generator — streams audio chunks as LLM generates text.

        Architecture (Producer-Consumer):
          Main thread: LLM stream → chunker → text clauses → tts_queue
          TTS thread:  tts_queue → Edge TTS (parallel) → output_queue
          Generator:   output_queue → yield SSE events

        This ensures LLM streaming is NEVER blocked by TTS generation.
        The TTS thread runs independently, generating audio while LLM
        continues producing tokens. Result: true parallel pipeline.
        """
        full_response = ""
        tool_calls_data = []
        chunk_index = 0
        voice = voice_override or ""
        voice_detected = False

        # Thread-safe queues for producer-consumer pipeline
        # tts_queue: main thread puts (clause_text, index) → TTS thread consumes
        # output_queue: TTS thread puts SSE bytes → generator yields them
        tts_queue = queue_module.Queue(maxsize=20)
        output_queue = queue_module.Queue(maxsize=50)
        tts_thread_done = threading.Event()

        def detect_voice(clause_text):
            """Auto-detect language and set voice on first clause."""
            nonlocal voice, voice_detected
            if not voice_detected:
                lang = _detect_language(clause_text)
                if not voice:
                    voice = _get_edge_voice(lang)
                voice_detected = True

        def tts_worker():
            """TTS worker thread — consumes clauses, generates audio, pushes to output.

            Runs in background. Generates Edge TTS for each clause independently.
            IMPORTANT: Must init its own Frappe context — threads don't inherit it.
            """
            try:
                # Each thread needs its own Frappe context for DB/cache access
                frappe.init(site=_site_name)
                frappe.connect()

                while True:
                    item = tts_queue.get(timeout=60)
                    if item is None:  # Poison pill — shutdown signal
                        break

                    item_type = item.get("type", "")

                    if item_type == "clause":
                        clause_text = item["text"]
                        idx = item["index"]
                        chunk_voice = item["voice"]

                        # Ensure DB alive for cache access
                        try:
                            frappe.db.sql("SELECT 1")
                        except Exception:
                            try:
                                frappe.db.connect()
                            except Exception:
                                frappe.init(site=_site_name)
                                frappe.connect()

                        tts_result = _generate_tts_chunk(clause_text, chunk_voice)

                        if tts_result:
                            output_queue.put(_sse({
                                "type": "audio_chunk",
                                "index": idx,
                                "text": clause_text,
                                "audio_base64": tts_result["audio_base64"],
                                "format": tts_result["format"],
                                "cached": tts_result.get("cached", False),
                            }))
                        else:
                            # TTS failed — send text so frontend uses browser TTS
                            output_queue.put(_sse({
                                "type": "text_chunk",
                                "index": idx,
                                "text": clause_text,
                            }))

                    elif item_type == "filler":
                        phrase = item["text"]
                        idx = item["index"]
                        filler_voice = item["voice"]

                        tts_result = _generate_tts_chunk(phrase, filler_voice)
                        if tts_result:
                            output_queue.put(_sse({
                                "type": "filler",
                                "index": idx,
                                "text": phrase,
                                "audio_base64": tts_result["audio_base64"],
                                "format": tts_result["format"],
                            }))

                    elif item_type == "passthrough":
                        # Non-TTS events (tool_call, tool_result, etc.) — pass directly
                        output_queue.put(item["data"])

            except queue_module.Empty:
                pass
            except Exception as e:
                output_queue.put(_sse({
                    "type": "error",
                    "content": f"TTS worker error: {str(e)[:200]}",
                }))
            finally:
                tts_thread_done.set()
                # Clean up thread's DB connection
                try:
                    frappe.db.close()
                except Exception:
                    pass

        try:
            # Re-init Frappe context inside generator
            frappe.init(site=_site_name)
            frappe.connect()

            # Ensure private/files directory exists
            files_dir = frappe.get_site_path("private", "files")
            os.makedirs(files_dir, exist_ok=True)

            # Pre-cache filler phrases in background thread (non-blocking)
            # Don't let this delay the LLM call
            _filler_thread = threading.Thread(
                target=lambda: _safe_ensure_filler_cache(_site_name),
                daemon=True,
                name="niv-filler-warmup",
            )
            _filler_thread.start()

            from niv_ai.niv_core.langchain.agent import stream_agent
            from niv_ai.niv_core.langchain.tools import (
                set_dev_mode as _set_dev_mode,
                set_active_dev_conversation,
            )

            set_active_dev_conversation(conversation_id)

            # Start TTS worker thread
            tts_thread = threading.Thread(target=tts_worker, daemon=True, name="niv-tts-worker")
            tts_thread.start()

            # Initialize chunker
            chunker = ClauseChunker()
            last_db_check = time.time()

            def ensure_db():
                nonlocal last_db_check
                if time.time() - last_db_check > 10:  # Check every 10s (streaming is fast)
                    try:
                        frappe.db.sql("SELECT 1")
                    except Exception:
                        try:
                            frappe.db.connect()
                        except Exception:
                            frappe.init(site=_site_name)
                            frappe.connect()
                    last_db_check = time.time()

            def submit_clause(clause_text):
                """Submit a clause for TTS generation (non-blocking)."""
                nonlocal chunk_index
                detect_voice(clause_text)
                chunk_index += 1
                tts_queue.put({
                    "type": "clause",
                    "text": clause_text,
                    "index": chunk_index,
                    "voice": voice,
                })

            def submit_filler(filler_key):
                """Submit a filler phrase for TTS (non-blocking)."""
                nonlocal chunk_index
                phrase = FILLER_PHRASES.get(filler_key, "")
                if not phrase:
                    return
                lang = _detect_language(phrase)
                filler_voice = _get_edge_voice(lang)
                chunk_index += 1
                tts_queue.put({
                    "type": "filler",
                    "text": phrase,
                    "index": chunk_index,
                    "voice": filler_voice,
                })

            def passthrough(sse_data):
                """Send non-TTS event through the pipeline (non-blocking)."""
                tts_queue.put({"type": "passthrough", "data": sse_data})

            def drain_output():
                """Yield all ready SSE events from the output queue (non-blocking)."""
                events = []
                while not output_queue.empty():
                    try:
                        events.append(output_queue.get_nowait())
                    except queue_module.Empty:
                        break
                return events

            # Send conversation ID
            yield _sse({
                "type": "init",
                "conversation_id": conversation_id,
            })

            # Stream from LLM — main thread stays fast, TTS runs in background
            tool_active = False

            for event in stream_agent(
                message=text,
                conversation_id=conversation_id,
                provider_name=provider,
                model=model,
                user=user,
                dev_mode=False,
            ):
                ensure_db()

                # Drain any ready TTS audio chunks first (non-blocking)
                for sse_bytes in drain_output():
                    yield sse_bytes

                event_type = event.get("type", "")

                if event_type == "token":
                    content = event.get("content", "")
                    if not content:
                        continue

                    full_response += content
                    tool_active = False

                    # Feed tokens to chunker — clauses go to TTS thread
                    clauses = chunker.feed(content)
                    for clause in clauses:
                        if clause.strip():
                            submit_clause(clause)

                elif event_type == "tool_call":
                    tool_name = event.get("tool", "")
                    tool_args = event.get("arguments", {})
                    tool_calls_data.append({
                        "tool": tool_name,
                        "arguments": tool_args,
                    })

                    # Pass tool_call event through (instant, no TTS needed)
                    yield _sse({
                        "type": "tool_call",
                        "tool": tool_name,
                        "arguments": tool_args,
                    })

                    # Submit filler audio (TTS thread generates while tool runs)
                    if not tool_active:
                        tool_active = True
                        filler_lang = _detect_language(text)
                        filler_key = "tool_start" if filler_lang == "hi" else "tool_start_en"
                        submit_filler(filler_key)

                elif event_type == "tool_result":
                    tool_active = False
                    yield _sse({
                        "type": "tool_result",
                        "tool": event.get("tool", ""),
                        "result": str(event.get("result", ""))[:500],
                    })

                elif event_type == "error":
                    error_content = event.get("content", "Something went wrong.")
                    full_response = error_content
                    submit_filler("error")

                elif event_type == "thought":
                    yield _sse({
                        "type": "thought",
                        "content": event.get("content", ""),
                    })

            # Flush remaining buffer
            remaining = chunker.flush()
            if remaining and remaining.strip():
                submit_clause(remaining)

            # Signal TTS thread to finish and wait for it
            tts_queue.put(None)  # Poison pill
            tts_thread.join(timeout=30)

            # Drain remaining TTS output
            for sse_bytes in drain_output():
                yield sse_bytes

            # Wait a bit more for any last TTS chunks
            deadline = time.time() + 15
            while not tts_thread_done.is_set() and time.time() < deadline:
                time.sleep(0.1)
                for sse_bytes in drain_output():
                    yield sse_bytes

            # Final drain
            for sse_bytes in drain_output():
                yield sse_bytes

            # Reconnect DB before saving
            try:
                frappe.db.sql("SELECT 1")
            except Exception:
                try:
                    frappe.db.connect()
                except Exception:
                    frappe.init(site=_site_name)
                    frappe.connect()

            # Save assistant message
            if full_response.strip():
                clean_response = re.sub(
                    r"\[\[THOUGHT\]\].*?\[\[/THOUGHT\]\]", "", full_response, flags=re.DOTALL
                ).strip()
                save_assistant_message(conversation_id, clean_response, tool_calls_data)
                auto_title(conversation_id, text)

            # Done event
            yield _sse({
                "type": "done",
                "conversation_id": conversation_id,
                "full_text": full_response,
                "chunks_sent": chunk_index,
            })

        except Exception as e:
            frappe.log_error(f"Stream voice error: {e}", "Niv AI Voice Stream")
            yield _sse({
                "type": "error",
                "content": "Voice chat failed. Please try again.",
            })

        finally:
            # Ensure TTS thread shuts down
            try:
                tts_queue.put(None)
            except Exception:
                pass
            try:
                set_active_dev_conversation("")
            except Exception:
                pass

    from werkzeug.wrappers import Response
    return Response(
        generate(),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ─── Realtime Push (alternative to SSE — for frappe.realtime) ────────────

@frappe.whitelist(methods=["POST"])
def stream_voice_realtime(**kwargs):
    """Stream voice chat using frappe.realtime (Socket.IO) for audio delivery.

    Same logic as stream_voice_chat but pushes audio chunks via
    frappe.publish_realtime instead of SSE. This enables true push
    to the browser without the client holding an open HTTP connection.

    Input (POST JSON):
        text: str
        conversation_id: str
        voice: str (optional)

    Audio chunks are pushed as frappe.realtime events:
        niv_voice_chunk → { type, index, text, audio_base64, format }
    """
    check_rate_limit()
    log_api_call("stream_voice_realtime")

    try:
        data = frappe.request.get_json(silent=True) or {}
    except Exception:
        data = {}

    text = (data.get("text") or frappe.form_dict.get("text") or "").strip()
    conversation_id = data.get("conversation_id") or frappe.form_dict.get("conversation_id") or ""
    voice_override = data.get("voice") or frappe.form_dict.get("voice") or ""

    if not text:
        frappe.throw(_("No text provided"))

    user = frappe.session.user

    # Auto-create conversation
    if not conversation_id:
        conv = frappe.get_doc({
            "doctype": "Niv Conversation",
            "user": user,
            "title": text[:50],
            "channel": "webchat",
        })
        conv.insert(ignore_permissions=True)
        frappe.db.commit()
        conversation_id = conv.name

    validate_conversation(conversation_id, user)
    save_user_message(conversation_id, text, dedup=True)

    # Enqueue background job — returns immediately to client
    frappe.enqueue(
        _run_voice_stream_background,
        queue="default",
        timeout=120,
        now=frappe.conf.developer_mode,
        text=text,
        conversation_id=conversation_id,
        voice_override=voice_override,
        user=user,
    )

    return {
        "status": "started",
        "conversation_id": conversation_id,
        "event_name": "niv_voice_chunk",
    }


def _run_voice_stream_background(
    text: str,
    conversation_id: str,
    voice_override: str,
    user: str,
):
    """Background job: streams LLM → TTS → realtime push.

    Runs inside frappe.enqueue, pushes audio chunks to the user's
    browser via frappe.publish_realtime.
    """
    settings = get_niv_settings()
    provider = settings.default_provider
    model = settings.default_model

    full_response = ""
    tool_calls_data = []
    chunk_index = 0
    voice = voice_override or ""
    voice_detected = False

    # Ensure private/files directory exists
    files_dir = frappe.get_site_path("private", "files")
    os.makedirs(files_dir, exist_ok=True)

    # Pre-cache fillers
    try:
        _ensure_filler_cache()
    except Exception:
        pass

    def publish(event_data: dict):
        """Push event to user's browser via Socket.IO."""
        frappe.publish_realtime(
            event="niv_voice_chunk",
            message=event_data,
            user=user,
            after_commit=False,
        )

    def detect_voice_if_needed(clause_text):
        nonlocal voice, voice_detected
        if not voice_detected:
            lang = _detect_language(clause_text)
            if not voice:
                voice = _get_edge_voice(lang)
            voice_detected = True

    def send_chunk(clause_text):
        nonlocal chunk_index
        detect_voice_if_needed(clause_text)

        tts_result = _generate_tts_chunk(clause_text, voice)
        chunk_index += 1

        if tts_result:
            publish({
                "type": "audio_chunk",
                "index": chunk_index,
                "text": clause_text,
                "audio_base64": tts_result["audio_base64"],
                "format": tts_result["format"],
                "cached": tts_result.get("cached", False),
            })
        else:
            publish({
                "type": "text_chunk",
                "index": chunk_index,
                "text": clause_text,
            })

    def send_filler(filler_key):
        nonlocal chunk_index
        phrase = FILLER_PHRASES.get(filler_key, "")
        if not phrase:
            return

        lang = _detect_language(phrase)
        filler_voice = _get_edge_voice(lang)
        tts_result = _generate_tts_chunk(phrase, filler_voice)

        if tts_result:
            chunk_index += 1
            publish({
                "type": "filler",
                "index": chunk_index,
                "text": phrase,
                "audio_base64": tts_result["audio_base64"],
                "format": tts_result["format"],
            })

    # Notify client that stream is starting
    publish({"type": "init", "conversation_id": conversation_id})

    try:
        from niv_ai.niv_core.langchain.agent import stream_agent
        from niv_ai.niv_core.langchain.tools import (
            set_dev_mode as _set_dev_mode,
            set_active_dev_conversation,
        )

        set_active_dev_conversation(conversation_id)

        chunker = ClauseChunker()
        tool_active = False

        for event in stream_agent(
            message=text,
            conversation_id=conversation_id,
            provider_name=provider,
            model=model,
            user=user,
            dev_mode=False,
        ):
            event_type = event.get("type", "")

            if event_type == "token":
                content = event.get("content", "")
                if not content:
                    continue

                full_response += content
                tool_active = False

                clauses = chunker.feed(content)
                for clause in clauses:
                    if clause.strip():
                        send_chunk(clause)

            elif event_type == "tool_call":
                tool_name = event.get("tool", "")
                tool_args = event.get("arguments", {})
                tool_calls_data.append({"tool": tool_name, "arguments": tool_args})

                publish({
                    "type": "tool_call",
                    "tool": tool_name,
                    "arguments": tool_args,
                })

                if not tool_active:
                    tool_active = True
                    filler_lang = _detect_language(text)
                    filler_key = "tool_start" if filler_lang == "hi" else "tool_start_en"
                    send_filler(filler_key)

            elif event_type == "tool_result":
                tool_active = False
                publish({
                    "type": "tool_result",
                    "tool": event.get("tool", ""),
                    "result": str(event.get("result", ""))[:500],
                })

            elif event_type == "error":
                full_response = event.get("content", "Something went wrong.")
                send_filler("error")

            elif event_type == "thought":
                publish({
                    "type": "thought",
                    "content": event.get("content", ""),
                })

        # Flush remaining
        remaining = chunker.flush()
        if remaining and remaining.strip():
            send_chunk(remaining)

        # Save message
        if full_response.strip():
            clean_response = re.sub(
                r"\[\[THOUGHT\]\].*?\[\[/THOUGHT\]\]", "", full_response, flags=re.DOTALL
            ).strip()
            try:
                frappe.db.sql("SELECT 1")
            except Exception:
                frappe.db.connect()
            save_assistant_message(conversation_id, clean_response, tool_calls_data)
            auto_title(conversation_id, text)

        # Done
        publish({
            "type": "done",
            "conversation_id": conversation_id,
            "full_text": full_response,
            "chunks_sent": chunk_index,
        })

    except Exception as e:
        frappe.log_error(f"Voice stream background error: {e}", "Niv AI Voice Stream")
        publish({
            "type": "error",
            "content": "Voice chat failed. Please try again.",
        })

    finally:
        try:
            set_active_dev_conversation("")
        except Exception:
            pass


# ─── SSE Helper ──────────────────────────────────────────────────────────

def _sse(data: dict) -> bytes:
    """Format a dict as an SSE event line."""
    return f"data: {json.dumps(data, default=str)}\n\n".encode("utf-8")
