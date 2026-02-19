import frappe
import requests
import json
import os
import re
import uuid
import subprocess
import tempfile

try:
    from niv_ai.niv_core.utils.rate_limiter import check_rate_limit
    from niv_ai.niv_core.utils.error_handler import handle_errors
    from niv_ai.niv_core.utils.logger import log_api_call
except ImportError:
    check_rate_limit = lambda *a, **kw: None
    handle_errors = lambda f: f
    log_api_call = lambda *a, **kw: None


# ─── Text Cleaning for TTS ──────────────────────────────────────────────

def clean_text_for_tts(text):
    """Strip markdown, code, HTML, URLs etc. to produce clean spoken text."""
    if not text:
        return ""

    t = text

    # Remove thinking/reasoning blocks (all formats)
    t = re.sub(r'<think>[\s\S]*?</think>', '', t)
    t = re.sub(r'<reasoning>[\s\S]*?</reasoning>', '', t)
    t = re.sub(r'\[\[THOUGHT\]\][\s\S]*?\[\[/THOUGHT\]\]', '', t)
    t = re.sub(r'\[\[THINKING\]\][\s\S]*?\[\[/THINKING\]\]', '', t)
    t = re.sub(r'(?m)^Thought:.*$', '', t)
    t = re.sub(r'(?m)^Action:.*$', '', t)
    t = re.sub(r'(?m)^Action Input:.*$', '', t)
    t = re.sub(r'(?m)^Observation:.*$', '', t)

    # Remove code blocks entirely (``` ... ```) — replace with "code block"
    t = re.sub(r'```[\s\S]*?```', ' code block ', t)

    # Inline code: keep the text inside backticks
    t = re.sub(r'`([^`]+)`', r'\1', t)

    # Detect error stack traces
    t = re.sub(
        r'(?:Traceback \(most recent call last\):[\s\S]*?(?:\n\S|\Z))',
        ' There was an error. ',
        t,
    )
    t = re.sub(r'(?m)^[ \t]*(?:at |File "|Exception|Error:|Caused by:).*$', '', t)

    # Remove HTML tags
    t = re.sub(r'<[^>]+>', '', t)

    # Convert markdown links [text](url) → text
    t = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', t)

    # Remove bare URLs
    t = re.sub(r'https?://\S+', '', t)

    # Remove markdown images ![alt](url)
    t = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', t)

    # Convert markdown tables to spoken format
    # Remove separator rows (|---|---|)
    t = re.sub(r'(?m)^\|[-:\s|]+\|$', '', t)
    # Convert table rows: | col1 | col2 | → col1, col2.
    def _table_row_to_speech(m):
        cells = [c.strip() for c in m.group(0).strip('|').split('|') if c.strip()]
        # Skip if all cells are just dashes (separator)
        if all(re.match(r'^[-:]+$', c) for c in cells):
            return ''
        return ', '.join(cells) + '.'
    t = re.sub(r'(?m)^\|.+\|$', _table_row_to_speech, t)

    # Headings: # Title → Title.
    t = re.sub(r'(?m)^#{1,6}\s+(.*)', r'\1.', t)

    # Bold / italic
    t = re.sub(r'\*\*\*(.+?)\*\*\*', r'\1', t)
    t = re.sub(r'\*\*(.+?)\*\*', r'\1', t)
    t = re.sub(r'\*(.+?)\*', r'\1', t)
    t = re.sub(r'__(.+?)__', r'\1', t)
    t = re.sub(r'_(.+?)_', r'\1', t)
    t = re.sub(r'~~(.+?)~~', r'\1', t)

    # Blockquotes
    t = re.sub(r'(?m)^>\s?', '', t)

    # List markers
    t = re.sub(r'(?m)^[\s]*[-*+]\s+', '', t)
    t = re.sub(r'(?m)^[\s]*\d+\.\s+', '', t)

    # Horizontal rules
    t = re.sub(r'(?m)^[-*=]{3,}\s*$', '', t)

    # Emoji shortcodes :emoji_name:
    t = re.sub(r':([a-zA-Z0-9_+-]+):', r'\1', t)

    # Remove Unicode emoji (flags, symbols, faces, etc.)
    t = re.sub(
        r'[\U0001F600-\U0001F64F'   # emoticons
        r'\U0001F300-\U0001F5FF'    # symbols & pictographs
        r'\U0001F680-\U0001F6FF'    # transport & map
        r'\U0001F1E0-\U0001F1FF'    # flags
        r'\U0001F900-\U0001F9FF'    # supplemental symbols
        r'\U0001FA00-\U0001FA6F'    # chess symbols
        r'\U0001FA70-\U0001FAFF'    # symbols extended-A
        r'\U00002702-\U000027B0'    # dingbats
        r'\U0000FE00-\U0000FE0F'    # variation selectors
        r'\U0000200D'               # zero width joiner
        r'\U000020E3'               # combining enclosing keycap
        r'\U00002600-\U000026FF'    # misc symbols
        r'\U00002300-\U000023FF'    # misc technical
        r'\U0000200B-\U0000200F'    # zero-width chars
        r'\U000025A0-\U000025FF'    # geometric shapes
        r']+', '', t
    )

    # Remove remaining special characters that TTS reads aloud
    t = re.sub(r'@{2,}', '', t)  # @@@@
    t = re.sub(r'"{2,}', '', t)  # """"
    t = re.sub(r'#{2,}', '', t)  # ####
    t = re.sub(r'\*{2,}', '', t)  # ****
    t = re.sub(r'_{2,}', '', t)  # ____
    t = re.sub(r'={2,}', '', t)  # ====
    t = re.sub(r'~{2,}', '', t)  # ~~~~
    t = re.sub(r'\|', '', t)  # pipe characters from tables
    t = re.sub(r'[{}\[\]<>\\]', '', t)  # braces, brackets, backslash
    t = re.sub(r'&(?:amp|lt|gt|quot|apos);', '', t)  # HTML entities

    # Clean punctuation that TTS reads aloud
    t = re.sub(r'/{2,}', ' ', t)      # // or ///
    t = re.sub(r'/(?=\s)', ' ', t)    # trailing slash
    t = re.sub(r'-{2,}', ', ', t)     # -- or --- → pause
    t = re.sub(r',{2,}', ',', t)      # ,,,, → single comma
    t = re.sub(r'!{2,}', '!', t)      # !!!! → single !
    t = re.sub(r'\?{2,}', '?', t)     # ???? → single ?
    t = re.sub(r'\.{3,}', '.', t)     # ... → single .
    t = re.sub(r'[""„"]+', '', t)     # fancy quotes
    t = re.sub(r"[''‚']+", '', t)     # fancy single quotes
    t = re.sub(r'[→←↑↓•·►▶▸‣⁃]', '', t)  # arrows, bullets
    t = re.sub(r'[─━═│┃┌┐└┘├┤┬┴┼╔╗╚╝╠╣╦╩╬]', '', t)  # box drawing chars
    t = re.sub(r'[\U0001F300-\U0001F9FF]', '', t)  # emoji

    # Collapse whitespace
    t = re.sub(r'\n{2,}', '. ', t)
    t = re.sub(r'\n', ' ', t)
    t = re.sub(r'\s{2,}', ' ', t)

    # Clean up punctuation artifacts
    t = re.sub(r'\.(\s*\.)+', '.', t)
    t = re.sub(r',(\s*,)+', ',', t)
    t = re.sub(r'^\s*[,.:;!?]\s*', '', t)  # leading punctuation

    return t.strip()


# ─── SSML Generation (Phase 2) ──────────────────────────────────────────

def _escape_ssml(text):
    """Escape special XML characters for SSML"""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&apos;")
    return text


def _detect_sentiment(text):
    """Simple rule-based sentiment detection for prosody adjustment.
    Returns: 'happy', 'sad', 'error', 'question', 'data', 'neutral'
    """
    text_lower = text.lower()

    # Error/apology patterns
    error_words = ["sorry", "unfortunately", "error", "failed", "issue", "problem",
                   "apologize", "couldn't", "can't", "unable", "mistake", "wrong",
                   "maaf", "galat", "samasya"]
    if any(w in text_lower for w in error_words):
        return "error"

    # Question detection
    if text.rstrip().endswith("?"):
        return "question"

    # Data/numbers heavy text
    number_count = len(re.findall(r'\d+', text))
    word_count = max(len(text.split()), 1)
    if number_count / word_count > 0.3:
        return "data"

    # Happy/excited patterns
    happy_words = ["great", "excellent", "awesome", "wonderful", "fantastic",
                   "congratulations", "perfect", "amazing", "success", "happy",
                   "bahut accha", "badhai", "shaandar", "zabardast"]
    if any(w in text_lower for w in happy_words) or text.count("!") >= 2:
        return "happy"

    # Sad/negative
    sad_words = ["sad", "disappointed", "loss", "difficult", "hard time",
                 "dukh", "mushkil"]
    if any(w in text_lower for w in sad_words):
        return "sad"

    return "neutral"


def _get_prosody_params(sentiment):
    """Return SSML prosody rate and pitch based on sentiment."""
    params = {
        "happy": {"rate": "+8%", "pitch": "+5%"},
        "sad": {"rate": "-8%", "pitch": "-5%"},
        "error": {"rate": "-10%", "pitch": "-8%"},
        "question": {"rate": "+0%", "pitch": "+3%"},
        "data": {"rate": "-5%", "pitch": "+0%"},
        "neutral": {"rate": "+0%", "pitch": "+0%"},
    }
    return params.get(sentiment, params["neutral"])


def _add_ssml_breaks_and_emphasis(text):
    """Add SSML breaks between sentences/paragraphs and emphasis markup.
    Input is already clean text (no markdown). Output is SSML fragment (no outer tags).
    """
    # Split into paragraphs first
    paragraphs = re.split(r'\n\s*\n|\.\s+(?=[A-Z])', text)
    if len(paragraphs) <= 1:
        paragraphs = [text]

    ssml_parts = []

    for para_idx, para in enumerate(paragraphs):
        para = para.strip()
        if not para:
            continue

        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', para)

        for sent_idx, sentence in enumerate(sentences):
            sentence = sentence.strip()
            if not sentence:
                continue

            escaped = _escape_ssml(sentence)

            # Handle numbers with say-as for currency
            escaped = re.sub(
                r'(?:₹|Rs\.?|INR)\s*(\d[\d,]*\.?\d*)',
                r'<say-as interpret-as="currency" language="en-IN">\1 INR</say-as>',
                escaped
            )
            # Large numbers
            escaped = re.sub(
                r'(\d{1,3}(?:,\d{3})+)',
                r'<say-as interpret-as="cardinal">\1</say-as>',
                escaped
            )
            # Dates like 2024-01-15
            escaped = re.sub(
                r'(\d{4})-(\d{2})-(\d{2})',
                r'<say-as interpret-as="date" format="ymd">\1\2\3</say-as>',
                escaped
            )

            # Exclamation → emphasis
            if sentence.rstrip().endswith("!"):
                escaped = '<emphasis level="moderate">' + escaped + '</emphasis>'

            ssml_parts.append(escaped)

            # Add break between sentences
            if sent_idx < len(sentences) - 1:
                ssml_parts.append('<break time="300ms"/>')

        # Add longer break between paragraphs
        if para_idx < len(paragraphs) - 1:
            ssml_parts.append('<break time="600ms"/>')

    return " ".join(ssml_parts)


def _text_to_ssml(text, voice):
    """Convert plain text to full SSML with prosody, breaks, emphasis.

    Args:
        text: Clean text (already stripped of markdown)
        voice: Edge TTS voice name (e.g. en-IN-NeerjaExpressiveNeural)

    Returns:
        SSML string ready for edge_tts.Communicate()
    """
    if not text or not text.strip():
        return None

    # Detect sentiment for prosody
    sentiment = _detect_sentiment(text)
    prosody = _get_prosody_params(sentiment)

    # Determine language from voice name
    if voice and voice.startswith("hi-"):
        lang = "hi-IN"
    else:
        lang = "en-IN"

    # Build SSML body with breaks and emphasis
    ssml_body = _add_ssml_breaks_and_emphasis(text)

    ssml = (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="{lang}">'
        '<voice name="{voice}">'
        '<prosody rate="{rate}" pitch="{pitch}">'
        '{body}'
        '</prosody>'
        '</voice>'
        '</speak>'
    ).format(
        lang=lang,
        voice=voice,
        rate=prosody["rate"],
        pitch=prosody["pitch"],
        body=ssml_body,
    )

    return ssml


# ─── Config ──────────────────────────────────────────────────────────────

def _get_voice_config():
    """Get voice API configuration from Niv Settings"""
    settings = frappe.get_single("Niv Settings")
    api_key = settings.get_password("voice_api_key") if settings.voice_api_key else None
    base_url = settings.voice_base_url or "https://api.openai.com/v1"
    default_voice = settings.default_voice or "hi_IN-priyamvada-medium"
    tts_model = settings.tts_model or "tts-1"

    stt_engine = getattr(settings, "stt_engine", "") or "auto"
    tts_engine = getattr(settings, "tts_engine", "") or "auto"
    tts_language = getattr(settings, "tts_language", "") or "en"
    tts_voice = getattr(settings, "tts_voice", "") or default_voice
    enable_voice = getattr(settings, "enable_voice", 1)

    if not api_key:
        provider_name = settings.default_provider
        if provider_name:
            try:
                provider = frappe.get_doc("Niv AI Provider", provider_name)
                api_key = provider.get_password("api_key")
                if not base_url or base_url == "https://api.openai.com/v1":
                    base_url = provider.base_url or "https://api.openai.com/v1"
            except Exception:
                pass

    provider_type = "openai"
    if base_url and "mistral" in base_url.lower():
        provider_type = "mistral"
    elif base_url and "anthropic" in base_url.lower():
        provider_type = "anthropic"

    # ElevenLabs config
    elevenlabs_api_key = None
    elevenlabs_voice_en = ""
    elevenlabs_voice_hi = ""
    try:
        elevenlabs_api_key = settings.get_password("elevenlabs_api_key") if getattr(settings, "elevenlabs_api_key", None) else None
        elevenlabs_voice_en = getattr(settings, "elevenlabs_voice_en", "") or ""
        elevenlabs_voice_hi = getattr(settings, "elevenlabs_voice_hi", "") or ""
    except Exception:
        pass

    return {
        "api_key": api_key,
        "base_url": base_url.rstrip("/") if base_url else "",
        "default_voice": default_voice,
        "tts_model": tts_model,
        "provider_type": provider_type,
        "stt_engine": stt_engine,
        "tts_engine": tts_engine,
        "tts_language": tts_language,
        "tts_voice": tts_voice,
        "enable_voice": enable_voice,
        "elevenlabs_api_key": elevenlabs_api_key,
        "elevenlabs_voice_en": elevenlabs_voice_en,
        "elevenlabs_voice_hi": elevenlabs_voice_hi,
    }


# ─── Piper TTS ───────────────────────────────────────────────────────────

def _is_piper_available():
    """Check if piper-tts is installed"""
    try:
        import piper
        return True
    except ImportError:
        return False


def _get_piper_model_path(voice_name):
    """Get or download piper voice model. Returns (model_path, config_path)"""
    models_dir = os.path.join(frappe.get_site_path(), "private", "piper_models")
    os.makedirs(models_dir, exist_ok=True)

    model_path = os.path.join(models_dir, f"{voice_name}.onnx")
    config_path = os.path.join(models_dir, f"{voice_name}.onnx.json")

    if os.path.exists(model_path) and os.path.exists(config_path):
        return model_path, config_path

    base_url = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
    parts = voice_name.split("-")
    if len(parts) >= 3:
        lang_region = parts[0]
        name = "-".join(parts[1:-1])
        quality = parts[-1]
        lang = lang_region.split("_")[0]
    else:
        frappe.throw(f"Invalid voice name format: {voice_name}. Expected: lang_REGION-name-quality")
        return None, None

    model_url = f"{base_url}/{lang}/{lang_region}/{name}/{quality}/{voice_name}.onnx"
    config_url = f"{base_url}/{lang}/{lang_region}/{name}/{quality}/{voice_name}.onnx.json"

    try:
        frappe.logger().info(f"Downloading Piper voice model: {voice_name}")
        resp = requests.get(model_url, stream=True, timeout=120)
        resp.raise_for_status()
        with open(model_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        resp = requests.get(config_url, timeout=30)
        resp.raise_for_status()
        with open(config_path, "wb") as f:
            f.write(resp.content)

        frappe.logger().info(f"Piper voice model downloaded: {voice_name}")
        return model_path, config_path

    except Exception as e:
        for p in [model_path, config_path]:
            if os.path.exists(p):
                os.unlink(p)
        frappe.throw(f"Failed to download Piper voice model '{voice_name}': {e}")
        return None, None


def _is_piper_voice_name(name):
    """Check if a voice name looks like a Piper voice"""
    if not name:
        return False
    return bool(re.match(r'^[a-z]{2}_[A-Z]{2}-\w+-\w+$', name))


def _tts_piper(text, voice_name=None):
    """Generate speech using Piper TTS (local, free, fast)"""
    try:
        from piper import PiperVoice
    except ImportError:
        return None

    if not voice_name or not _is_piper_voice_name(voice_name):
        voice_name = "en_US-lessac-medium"

    try:
        import wave

        model_path, config_path = _get_piper_model_path(voice_name)
        if not model_path:
            return None

        voice = PiperVoice.load(model_path, config_path=config_path)

        out_path = os.path.join(tempfile.gettempdir(), f"niv_tts_{uuid.uuid4().hex[:8]}.wav")

        with wave.open(out_path, "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)

        with open(out_path, "rb") as f:
            audio_data = f.read()

        try:
            os.unlink(out_path)
        except Exception:
            pass

        filename = f"niv_tts_{uuid.uuid4().hex[:8]}.wav"
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": filename,
            "content": audio_data,
            "is_private": 1,
            "folder": "Home",
        })
        file_doc.insert(ignore_permissions=True)
        frappe.db.commit()

        return {"audio_url": file_doc.file_url, "engine": "piper"}

    except Exception as e:
        frappe.logger().warning(f"Piper TTS failed: {e}")
        return None


# ─── ElevenLabs TTS ──────────────────────────────────────────────────────

def _tts_elevenlabs(text, voice_id=None, config=None):
    """Generate speech using ElevenLabs API (human-like, multilingual, Hindi+English).
    
    Requires elevenlabs_api_key in Niv Settings.
    Default voice: Rachel (21m00Tcm4TlvDq8ikWAM) — natural female English.
    For Hindi: use a multilingual voice or Hindi-specific voice.
    """
    if not config:
        config = _get_voice_config()
    
    api_key = config.get("elevenlabs_api_key")
    if not api_key:
        return None
    
    # Default voices
    if not voice_id:
        lang = _detect_language(text)
        if lang == "hi":
            voice_id = config.get("elevenlabs_voice_hi") or "21m00Tcm4TlvDq8ikWAM"
        else:
            voice_id = config.get("elevenlabs_voice_en") or "21m00Tcm4TlvDq8ikWAM"
    
    try:
        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                    "style": 0.0,
                    "use_speaker_boost": True,
                },
            },
            timeout=30,
        )
        
        if resp.status_code != 200:
            frappe.logger().warning(f"ElevenLabs TTS failed ({resp.status_code}): {resp.text[:200]}")
            return None
        
        output_dir = frappe.get_site_path("public", "files")
        filename = "tts_11labs_{0}.mp3".format(uuid.uuid4().hex[:12])
        output_path = os.path.join(output_dir, filename)
        
        with open(output_path, "wb") as f:
            f.write(resp.content)
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return {
                "audio_url": "/files/{0}".format(filename),
                "engine": "elevenlabs",
                "voice": voice_id,
            }
    except Exception as e:
        frappe.logger().warning(f"ElevenLabs TTS error: {e}")
    
    return None


# ─── OpenAI TTS ──────────────────────────────────────────────────────────

def _tts_openai(text, voice, model, response_format, config):
    """Generate speech using OpenAI-compatible API"""
    if _is_piper_voice_name(voice):
        voice = "alloy"

    response = requests.post(
        f"{config['base_url']}/audio/speech",
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "input": text,
            "voice": voice,
            "response_format": response_format,
        },
        timeout=60,
    )

    if response.status_code != 200:
        frappe.throw(f"TTS API error ({response.status_code}): {response.text[:300]}")

    filename = f"niv_tts_{uuid.uuid4().hex[:8]}.{response_format}"
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": filename,
        "content": response.content,
        "is_private": 1,
        "folder": "Home/Niv AI",
    })
    file_doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {"audio_url": file_doc.file_url, "engine": "openai"}


# ─── Language Detection ──────────────────────────────────────────────────

def _detect_language(text):
    """Detect if text is Hindi or English"""
    has_devanagari = any(ord(c) >= 0x0900 and ord(c) <= 0x097F for c in text)
    if has_devanagari:
        return "hi"

    hindi_words = [
        "kya", "hai", "haan", "nahi", "aap", "main", "kaise", "mera", "tera",
        "kitna", "kitne", "kab", "kahan", "kaun", "kyun", "karo", "karna",
        "dikhao", "batao", "bolo", "suno", "dekho", "jao", "aao", "lo", "do",
        "accha", "theek", "bahut", "abhi", "yahan", "wahan", "isko", "usko",
        "mujhe", "tumhe", "humko", "unko", "sabhi", "koi", "kuch", "sab"
    ]
    text_lower = text.lower()
    hindi_count = sum(1 for w in hindi_words if w in text_lower.split())
    if hindi_count >= 2:
        return "hi"

    return "en"


# ─── Edge TTS (with SSML support) ───────────────────────────────────────

def _tts_edge(text, voice=None, use_ssml=False):
    """Edge TTS — Microsoft Azure neural voices, free, unlimited, human-like.
    
    Phase 2: Now supports SSML with natural pauses, prosody, emphasis.
    Falls back to plain text if SSML fails.
    """
    try:
        import edge_tts
        import asyncio
    except ImportError:
        return None

    # Handle "auto" or no voice - detect language
    if not voice or voice == "auto":
        lang = _detect_language(text)
        if lang == "hi":
            voice = "hi-IN-SwaraNeural"
        else:
            voice = "en-IN-NeerjaExpressiveNeural"

    try:
        output_dir = frappe.get_site_path("public", "files")
        filename = "tts_edge_{0}.mp3".format(uuid.uuid4().hex[:12])
        output_path = os.path.join(output_dir, filename)

        # Build SSML or use plain text
        ssml_text = None
        if use_ssml:
            try:
                ssml_text = _text_to_ssml(text, voice)
            except Exception as e:
                frappe.logger().warning("SSML generation failed, using plain text: {0}".format(e))
                ssml_text = None

        async def _generate():
            if ssml_text:
                # When using SSML, pass it as the text parameter
                # Edge TTS handles SSML when text starts with <speak>
                communicate = edge_tts.Communicate(ssml_text, voice)
            else:
                communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_path)

        # Run async
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    pool.submit(asyncio.run, _generate()).result(timeout=30)
            else:
                loop.run_until_complete(_generate())
        except RuntimeError:
            asyncio.run(_generate())

        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            audio_url = "/files/{0}".format(filename)
            frappe.logger().info("Edge TTS: generated {0} with voice {1} (ssml={2})".format(
                filename, voice, bool(ssml_text)))
            return {
                "audio_url": audio_url,
                "engine": "edge",
                "voice": voice,
                "text": text,
            }

        # If SSML failed to produce output, retry without SSML
        if ssml_text and use_ssml:
            frappe.logger().warning("Edge TTS SSML produced empty file, retrying plain text")
            return _tts_edge(text, voice, use_ssml=False)

    except Exception as e:
        frappe.logger().warning("Edge TTS failed: {0}".format(str(e)))
        # If SSML caused the error, retry without it
        if ssml_text and use_ssml:
            frappe.logger().info("Retrying Edge TTS without SSML")
            try:
                return _tts_edge(text, voice, use_ssml=False)
            except Exception:
                pass

    return None


# ─── Public APIs ─────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=False)
def text_to_speech(text, voice=None, model=None, response_format="wav", engine=None):
    """
    Convert text to speech. Tries engines in order:
    1. Edge TTS (free, human-like, Microsoft Azure neural voices) — now with SSML
    2. Piper TTS (free, local, offline fallback)
    3. OpenAI-compatible API
    4. Returns engine='browser' signal for client-side fallback
    """
    check_rate_limit()
    log_api_call("text_to_speech")

    if not text or not text.strip():
        frappe.throw("No text provided for TTS")

    # Clean markdown/code/HTML for natural speech
    text = clean_text_for_tts(text)
    if not text:
        return {"audio_url": None, "engine": "browser", "text": ""}

    config = _get_voice_config()

    # ── Try ElevenLabs first (most human-like, multilingual, Hindi+English) ──
    if engine in (None, "auto", "elevenlabs") and config.get("elevenlabs_api_key"):
        result = _tts_elevenlabs(text, config=config)
        if result:
            return result

    # ── Try Edge TTS (free, human-like) ──
    if engine in (None, "auto", "edge"):
        edge_voice = voice if (voice and "Neural" in str(voice)) else None
        result = _tts_edge(text, edge_voice)
        if result:
            return result

    # ── Try Piper TTS (free, local, offline fallback) ──
    if engine in (None, "auto", "piper"):
        piper_voice = voice or config.get("default_voice") or "en_US-lessac-medium"
        result = _tts_piper(text, piper_voice)
        if result:
            return result

    # ── Try OpenAI-compatible API ──
    if engine in (None, "auto", "openai") and config.get("api_key"):
        if config.get("provider_type") == "mistral":
            frappe.logger().info("Skipping OpenAI TTS: Mistral does not support /audio/speech")
        else:
            openai_voice = voice if (voice and not _is_piper_voice_name(voice)) else "alloy"
            return _tts_openai(text, openai_voice, model or config["tts_model"], response_format, config)

    # ── Fallback: tell client to use browser TTS ──
    return {"audio_url": None, "engine": "browser", "text": text}


@frappe.whitelist(allow_guest=False)
def stream_tts(text, voice=None):
    """Generate TTS for a single sentence/chunk. Used by streaming voice mode.
    
    This is optimized for low latency — short text segments get fast audio.
    Returns audio_url immediately.
    """
    check_rate_limit()

    if not text or not text.strip():
        return {"audio_url": None}

    # Full cleaning — same as text_to_speech for consistency
    text = clean_text_for_tts(text)

    if not text.strip():
        return {"audio_url": None}

    # Resolve voice based on language parameter or text detection
    stt_language = frappe.form_dict.get("language", "")
    
    if not voice or voice == "auto":
        # Use STT-detected language if available, otherwise detect from text
        lang = stt_language or _detect_language(text)
        if lang in ("hi", "hindi"):
            voice = "hi-IN-SwaraNeural"  # Edge TTS for Hindi (Piper has no Hindi)
        else:
            voice = "en-IN-NeerjaExpressiveNeural"

    # Check configured TTS engine
    settings = frappe.get_single("Niv Settings")
    tts_engine = getattr(settings, "tts_engine", "") or "auto"
    config = _get_voice_config()

    # ── Try ElevenLabs first (most human-like) ──
    if tts_engine in ("auto", "elevenlabs") and config.get("elevenlabs_api_key"):
        result = _tts_elevenlabs(text, config=config)
        if result:
            return result

    # ── Try Piper first if configured (English only - no Hindi model) ──
    detected_lang = stt_language or _detect_language(text)
    if tts_engine == "piper" and detected_lang not in ("hi", "hindi"):
        piper_voice = "en_US-lessac-medium"
        result = _tts_piper(text, piper_voice)
        if result:
            return result

    # ── Edge TTS (free, human-like) ──
    if tts_engine in ("auto", "edge"):
        try:
            import edge_tts
            import asyncio
        except ImportError:
            return {"audio_url": None, "engine": "browser", "text": text}

        try:
            output_dir = frappe.get_site_path("public", "files")
            filename = "tts_stream_{0}.mp3".format(uuid.uuid4().hex[:12])
            output_path = os.path.join(output_dir, filename)

            # Build simple SSML for just this sentence
            ssml = None
            try:
                ssml = _text_to_ssml(text, voice)
            except Exception:
                ssml = None

            async def _generate():
                if ssml:
                    communicate = edge_tts.Communicate(ssml, voice)
                else:
                    communicate = edge_tts.Communicate(text, voice)
                await communicate.save(output_path)

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        pool.submit(asyncio.run, _generate()).result(timeout=15)
                else:
                    loop.run_until_complete(_generate())
            except RuntimeError:
                asyncio.run(_generate())

            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return {
                    "audio_url": "/files/{0}".format(filename),
                    "engine": "edge",
                    "voice": voice,
                }
        except Exception as e:
            frappe.logger().warning("stream_tts Edge failed: {0}".format(str(e)))

    # ── Piper fallback (if not tried yet) ──
    if tts_engine not in ("piper",):
        piper_voice = "en_US-lessac-medium"
        result = _tts_piper(text, piper_voice)
        if result:
            return result

    # Fallback
    return {"audio_url": None, "engine": "browser", "text": text}


# ─── Faster-Whisper STT (Free, Local) ────────────────────────────────────

_whisper_model = None

def _get_whisper_model():
    """Get or load Whisper model (lazy loading, cached)"""
    global _whisper_model
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
            frappe.logger().info("Faster-Whisper model loaded: base")
        except Exception as e:
            frappe.logger().warning(f"Failed to load Whisper model: {e}")
            return None
    return _whisper_model


def _stt_whisper(audio_path):
    """Transcribe audio using Faster-Whisper (local, free, offline)"""
    model = _get_whisper_model()
    if not model:
        return None

    try:
        segments, info = model.transcribe(audio_path, beam_size=5)
        text = " ".join([segment.text for segment in segments])
        frappe.logger().info(f"Whisper STT: {info.language} ({info.language_probability:.0%}) - {len(text)} chars")
        return {"text": text.strip(), "language": info.language, "engine": "whisper-local"}
    except Exception as e:
        frappe.logger().warning(f"Whisper STT failed: {e}")
        return None


@frappe.whitelist(allow_guest=False)
def speech_to_text(audio_file, engine=None):
    """Transcribe audio. Tries Faster-Whisper first, then API."""
    check_rate_limit()
    log_api_call("speech_to_text")

    if not audio_file:
        frappe.throw("No audio file provided")

    config = _get_voice_config()
    stt_engine = engine or config.get("stt_engine", "auto")

    file_path = frappe.get_site_path("private" if "/private/" in audio_file else "public",
                                      "files", os.path.basename(audio_file))
    if not os.path.exists(file_path):
        file_path = frappe.get_site_path(audio_file.lstrip("/"))
    if not os.path.exists(file_path):
        frappe.throw(f"Audio file not found: {audio_file}")

    # ── Try Mistral Voxtral STT first (fast, multilingual, Hindi+English) ──
    if stt_engine in ("auto", "voxtral", "mistral", "api") and config.get("api_key"):
        provider_type = config.get("provider_type", "openai")
        if provider_type == "mistral":
            stt_model = "voxtral-mini-latest"
        else:
            stt_model = "whisper-1"

        data = {"model": stt_model}
        lang = config.get("tts_language", "")
        if lang:
            data["language"] = lang

        try:
            with open(file_path, "rb") as f:
                resp = requests.post(
                    f"{config['base_url']}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {config['api_key']}"},
                    files={"file": (os.path.basename(audio_file), f, "audio/webm")},
                    data=data,
                    timeout=60,
                )

            if resp.status_code == 200:
                result = resp.json()
                text = result.get("text", "")
                if text.strip():
                    return {"text": text, "engine": f"voxtral ({stt_model})", "language": result.get("language", "")}
            else:
                frappe.logger().warning(f"Voxtral STT failed ({resp.status_code}): {resp.text[:200]}")
        except Exception as e:
            frappe.logger().warning(f"Voxtral STT error: {e}")

    # ── Fallback: Local Faster-Whisper ──
    if stt_engine in ("auto", "whisper", "whisper-local"):
        result = _stt_whisper(file_path)
        if result:
            return result

    frappe.throw("No STT available. Configure Mistral API key or install faster-whisper.")




@frappe.whitelist(allow_guest=False)
def stt_from_base64(**kwargs):
    """Server-side STT from base64 audio. Returns transcript text.
    
    Phase 3: Primary STT endpoint - replaces browser Web Speech API.
    Uses Faster-Whisper locally (free, accurate, multilingual).
    """
    import base64
    
    check_rate_limit()
    
    audio_base64 = frappe.form_dict.get("audio_base64", "")
    if not audio_base64:
        return {"text": "", "error": "No audio data"}
    
    try:
        audio_bytes = base64.b64decode(audio_base64)
        
        # Save to temp file for Whisper
        tmp = tempfile.NamedTemporaryFile(suffix=".webm", delete=False)
        tmp.write(audio_bytes)
        tmp.close()
        
        # Try Voxtral/API STT first (fast, accurate, Hindi+English)
        config = _get_voice_config()
        if config.get("api_key"):
            provider_type = config.get("provider_type", "openai")
            stt_model = "voxtral-mini-latest" if provider_type == "mistral" else "whisper-1"
            
            try:
                with open(tmp.name, "rb") as f:
                    resp = requests.post(
                        f"{config['base_url']}/audio/transcriptions",
                        headers={"Authorization": f"Bearer {config['api_key']}"},
                        files={"file": ("audio.webm", f, "audio/webm")},
                        data={"model": stt_model},
                        timeout=30,
                    )
                
                if resp.status_code == 200:
                    api_result = resp.json()
                    text = api_result.get("text", "")
                    if text.strip():
                        try:
                            os.unlink(tmp.name)
                        except Exception:
                            pass
                        return {
                            "text": text,
                            "language": api_result.get("language", ""),
                            "engine": f"voxtral ({stt_model})",
                        }
                else:
                    frappe.logger().warning(f"Voxtral STT failed ({resp.status_code}): {resp.text[:200]}")
            except Exception as e:
                frappe.logger().warning(f"Voxtral STT error: {e}")
        
        # Fallback: Local Faster-Whisper
        result = _stt_whisper(tmp.name)
        
        if result and result.get("text"):
            try:
                os.unlink(tmp.name)
            except Exception:
                pass
            return {
                "text": result["text"],
                "language": result.get("language", ""),
                "engine": "whisper-local",
            }
        
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
        
        return {"text": "", "error": "STT failed - no engine available"}
        
    except Exception as e:
        frappe.logger().warning(f"stt_from_base64 error: {e}")
        return {"text": "", "error": str(e)}


@frappe.whitelist(allow_guest=False)
def voice_chat(conversation_id, audio_file, voice=None):
    """Combined voice chat: STT → Chat → TTS in one call."""
    check_rate_limit()
    log_api_call("voice_chat", conversation_id=conversation_id)

    if not conversation_id:
        frappe.throw("No conversation_id provided")
    if not audio_file:
        frappe.throw("No audio file provided")

    config = _get_voice_config()
    voice = voice or config["default_voice"]

    stt_result = speech_to_text(audio_file)
    user_text = stt_result.get("text", "").strip()

    if not user_text:
        return {
            "text": "",
            "response": "I couldn't understand what you said. Please try again.",
            "audio_url": None,
        }

    from niv_ai.niv_core.api.chat import send_message
    chat_result = send_message(conversation_id=conversation_id, message=user_text)
    response_text = chat_result.get("response", "") or chat_result.get("message", "")

    audio_url = None
    if response_text:
        tts_result = text_to_speech(text=response_text, voice=voice)
        audio_url = tts_result.get("audio_url")

    try:
        _cleanup_file(audio_file)
    except Exception:
        pass

    return {
        "text": user_text,
        "response": response_text,
        "audio_url": audio_url,
        "message_id": chat_result.get("message_id"),
        "tokens": {
            "input": chat_result.get("input_tokens", 0),
            "output": chat_result.get("output_tokens", 0),
            "total": chat_result.get("total_tokens", 0),
        },
    }


@frappe.whitelist(allow_guest=False)
def voice_chat_base64(**kwargs):
    """Voice chat using base64-encoded audio — bypasses upload_file API."""
    import base64

    audio_base64 = frappe.form_dict.get("audio_base64", "")
    conversation_id = frappe.form_dict.get("conversation_id", "")
    browser_transcript = frappe.form_dict.get("browser_transcript", "")

    if not conversation_id:
        try:
            conv = frappe.get_doc({
                "doctype": "Niv Conversation",
                "user": frappe.session.user,
                "title": "Voice Chat",
                "channel": "webchat",
            })
            conv.insert(ignore_permissions=True)
            frappe.db.commit()
            conversation_id = conv.name
        except Exception as e:
            frappe.throw("Failed to create conversation: " + str(e))

    user_text = browser_transcript

    if audio_base64 and not user_text:
        try:
            audio_bytes = base64.b64decode(audio_base64)
            tmp = tempfile.NamedTemporaryFile(suffix=".webm", delete=False)
            tmp.write(audio_bytes)
            tmp.close()

            from frappe.utils.file_manager import save_file
            file_doc = save_file(
                "voice_input.webm", audio_bytes, "Niv Conversation",
                conversation_id, folder="Home/Niv AI", is_private=1
            )
            file_url = file_doc.file_url

            stt_result = speech_to_text(file_url)
            user_text = stt_result.get("text", "")

            os.unlink(tmp.name)
            try:
                _cleanup_file(file_url)
            except Exception:
                pass
        except Exception as e:
            frappe.log_error("voice_chat_base64 STT error: " + str(e))
            if not user_text:
                user_text = browser_transcript or ""

    if not user_text:
        return {
            "text": "",
            "response": "I couldn't hear anything. Please try again.",
            "audio_url": None,
            "conversation_id": conversation_id,
            "tokens": {"input": 0, "output": 0, "total": 0},
        }

    from niv_ai.niv_core.api.chat import send_message
    chat_result = send_message(conversation_id=conversation_id, message=user_text)
    response_text = chat_result.get("response", "") or chat_result.get("message", "") or chat_result.get("content", "")

    audio_url = None
    if response_text:
        try:
            tts_result = text_to_speech(text=response_text)
            audio_url = tts_result.get("audio_url")
        except Exception:
            pass

    return {
        "text": user_text,
        "response": response_text,
        "audio_url": audio_url,
        "conversation_id": conversation_id,
        "message_id": chat_result.get("message_id"),
        "tokens": {
            "input": chat_result.get("input_tokens", 0),
            "output": chat_result.get("output_tokens", 0),
            "total": chat_result.get("total_tokens", 0),
        },
    }


@frappe.whitelist(allow_guest=False)
def get_tts_status():
    """Check which TTS engines are available"""
    config = _get_voice_config()
    openai_available = bool(config.get("api_key")) and config.get("provider_type") != "mistral"
    return {
        "elevenlabs": bool(config.get("elevenlabs_api_key")),
        "piper": _is_piper_available(),
        "openai": openai_available,
        "edge": True,
        "browser": True,
        "ssml_enabled": True,
        "provider_type": config.get("provider_type", "unknown"),
    }


@frappe.whitelist(allow_guest=False)
def get_available_voices():
    """List popular voices"""
    return [
        {"id": "en_US-lessac-medium", "name": "Lessac (English US)", "lang": "en"},
        {"id": "en_US-amy-medium", "name": "Amy (English US)", "lang": "en"},
        {"id": "en_US-ryan-medium", "name": "Ryan (English US)", "lang": "en"},
        {"id": "en_GB-alba-medium", "name": "Alba (English UK)", "lang": "en"},
        {"id": "hi_IN-swara-medium", "name": "Swara (Hindi)", "lang": "hi"},
        {"id": "de_DE-thorsten-medium", "name": "Thorsten (German)", "lang": "de"},
        {"id": "fr_FR-siwis-medium", "name": "Siwis (French)", "lang": "fr"},
        {"id": "es_ES-sharvard-medium", "name": "Sharvard (Spanish)", "lang": "es"},
    ]


@frappe.whitelist(allow_guest=False)
def cleanup_voice_file(file_url):
    """Delete a temporary voice file after playback"""
    if not file_url:
        return
    _cleanup_file(file_url)
    return {"status": "ok"}


def _cleanup_file(file_url):
    """Delete a file by URL"""
    try:
        # Try to delete the physical file directly for /files/ paths (public)
        if file_url and file_url.startswith("/files/"):
            physical_path = frappe.get_site_path("public", "files", os.path.basename(file_url))
            if os.path.exists(physical_path):
                os.unlink(physical_path)
                return

        files = frappe.get_all("File", filters={"file_url": file_url}, fields=["name"])
        for f in files:
            frappe.delete_doc("File", f["name"], ignore_permissions=True, force=True)
    except Exception:
        pass
