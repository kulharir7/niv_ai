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

    # Remove code blocks entirely (``` ... ```) — replace with "code block"
    t = re.sub(r'```[\s\S]*?```', ' code block ', t)

    # Remove inline code
    t = re.sub(r'`[^`]+`', '', t)

    # Detect error stack traces (lines starting with "Traceback", "  File ", "Error:", etc.)
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

    # Remove markdown tables (lines that are mostly pipes/dashes)
    t = re.sub(r'(?m)^\|.*\|$', '', t)
    t = re.sub(r'(?m)^[\s|:-]+$', '', t)

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

    # Collapse whitespace
    t = re.sub(r'\n{2,}', '. ', t)
    t = re.sub(r'\n', ' ', t)
    t = re.sub(r'\s{2,}', ' ', t)

    # Clean up punctuation artifacts like ". ." or ".. "
    t = re.sub(r'\.(\s*\.)+', '.', t)

    return t.strip()


# ─── Config ──────────────────────────────────────────────────────────────

def _get_voice_config():
    """Get voice API configuration from Niv Settings"""
    settings = frappe.get_single("Niv Settings")
    api_key = settings.get_password("voice_api_key") if settings.voice_api_key else None
    base_url = settings.voice_base_url or "https://api.openai.com/v1"
    default_voice = settings.default_voice or "hi_IN-priyamvada-medium"
    tts_model = settings.tts_model or "tts-1"

    # Read additional voice settings safely (fields may not exist yet)
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

    # Detect provider type from base_url
    provider_type = "openai"  # default
    if base_url and "mistral" in base_url.lower():
        provider_type = "mistral"
    elif base_url and "anthropic" in base_url.lower():
        provider_type = "anthropic"

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

    # Download from Hugging Face
    base_url = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
    # Parse voice name: lang_REGION-name-quality
    parts = voice_name.split("-")
    if len(parts) >= 3:
        lang_region = parts[0]  # e.g. en_US or hi_IN
        name = "-".join(parts[1:-1])  # e.g. lessac
        quality = parts[-1]  # e.g. medium
        lang = lang_region.split("_")[0]  # e.g. en or hi
    else:
        frappe.throw(f"Invalid voice name format: {voice_name}. Expected: lang_REGION-name-quality")
        return None, None

    model_url = f"{base_url}/{lang}/{lang_region}/{name}/{quality}/{voice_name}.onnx"
    config_url = f"{base_url}/{lang}/{lang_region}/{name}/{quality}/{voice_name}.onnx.json"

    try:
        # Download model
        frappe.logger().info(f"Downloading Piper voice model: {voice_name}")
        resp = requests.get(model_url, stream=True, timeout=120)
        resp.raise_for_status()
        with open(model_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        # Download config
        resp = requests.get(config_url, timeout=30)
        resp.raise_for_status()
        with open(config_path, "wb") as f:
            f.write(resp.content)

        frappe.logger().info(f"Piper voice model downloaded: {voice_name}")
        return model_path, config_path

    except Exception as e:
        # Cleanup partial downloads
        for p in [model_path, config_path]:
            if os.path.exists(p):
                os.unlink(p)
        frappe.throw(f"Failed to download Piper voice model '{voice_name}': {e}")
        return None, None


def _is_piper_voice_name(name):
    """Check if a voice name looks like a Piper voice (e.g. en_US-lessac-medium)"""
    if not name:
        return False
    # Piper voices have format: lang_REGION-name-quality
    return bool(re.match(r'^[a-z]{2}_[A-Z]{2}-\w+-\w+$', name))


def _tts_piper(text, voice_name=None):
    """Generate speech using Piper TTS (local, free, fast)"""
    try:
        from piper import PiperVoice
    except ImportError:
        return None

    # Always use Piper-format voice name, fallback to default
    if not voice_name or not _is_piper_voice_name(voice_name):
        voice_name = "en_US-lessac-medium"

    try:
        import wave

        model_path, config_path = _get_piper_model_path(voice_name)
        if not model_path:
            return None

        voice = PiperVoice.load(model_path, config_path=config_path)

        # Generate audio — use synthesize_wav which handles wave params
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


# ─── OpenAI TTS ──────────────────────────────────────────────────────────

def _tts_openai(text, voice, model, response_format, config):
    """Generate speech using OpenAI-compatible API"""
    # Don't pass Piper-format voice names to OpenAI
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


# ─── Public APIs ─────────────────────────────────────────────────────────

def _tts_edge(text, voice=None):
    """Edge TTS — Microsoft Azure neural voices, free, unlimited, human-like."""
    try:
        import edge_tts
        import asyncio
    except ImportError:
        return None

    # Default voices based on language detection
    if not voice:
        # Simple Hindi detection
        has_hindi = any(ord(c) > 0x0900 and ord(c) < 0x097F for c in text)
        has_hindi_words = any(w in text.lower() for w in ["kya", "hai", "haan", "nahi", "aap", "main", "kaise", "mera", "tera"])
        if has_hindi or has_hindi_words:
            voice = "hi-IN-SwaraNeural"  # Female Hindi
        else:
            voice = "en-US-JennyNeural"  # Female English — natural, warm

    try:
        # Generate audio
        output_dir = frappe.get_site_path("public", "files")
        filename = "tts_edge_{0}.mp3".format(uuid.uuid4().hex[:12])
        output_path = os.path.join(output_dir, filename)

        # Run async edge-tts
        async def _generate():
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_path)

        # Get or create event loop
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
            frappe.logger().info("Edge TTS: generated {0} with voice {1}".format(filename, voice))
            return {
                "audio_url": audio_url,
                "engine": "edge",
                "voice": voice,
                "text": text,
            }
    except Exception as e:
        frappe.logger().warning("Edge TTS failed: {0}".format(str(e)))

    return None


@frappe.whitelist(allow_guest=False)
def text_to_speech(text, voice=None, model=None, response_format="wav", engine=None):
    """
    Convert text to speech. Tries engines in order:
    1. Edge TTS (free, human-like, Microsoft Azure neural voices)
    2. Piper TTS (free, local, offline fallback)
    3. OpenAI-compatible API — if API key configured AND provider supports TTS
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

    # ── Try Edge TTS first (free, human-like, best quality) ──
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

    # ── Try OpenAI-compatible API (only if provider supports TTS) ──
    if engine in (None, "auto", "openai") and config.get("api_key"):
        # Skip OpenAI TTS for providers that don't have /audio/speech (e.g. Mistral)
        if config.get("provider_type") == "mistral":
            frappe.logger().info("Skipping OpenAI TTS: Mistral does not support /audio/speech")
        else:
            openai_voice = voice if (voice and not _is_piper_voice_name(voice)) else "alloy"
            return _tts_openai(text, openai_voice, model or config["tts_model"], response_format, config)

    # ── Fallback: tell client to use browser TTS ──
    return {"audio_url": None, "engine": "browser", "text": text}


@frappe.whitelist(allow_guest=False)
def speech_to_text(audio_file):
    """
    Transcribe audio using OpenAI-compatible or Mistral STT API.
    audio_file: URL of uploaded file
    """
    check_rate_limit()
    log_api_call("speech_to_text")

    if not audio_file:
        frappe.throw("No audio file provided")

    config = _get_voice_config()
    if not config.get("api_key"):
        frappe.throw("No API key configured for STT. Use browser speech recognition instead.")

    file_path = frappe.get_site_path("private" if "/private/" in audio_file else "public",
                                      "files", os.path.basename(audio_file))
    if not os.path.exists(file_path):
        file_path = frappe.get_site_path(audio_file.lstrip("/"))
    if not os.path.exists(file_path):
        frappe.throw(f"Audio file not found: {audio_file}")

    # Auto-detect STT model based on provider
    provider_type = config.get("provider_type", "openai")
    if provider_type == "mistral":
        stt_model = "mistral-stt-latest"
    else:
        stt_model = "whisper-1"

    # Build request data
    data = {"model": stt_model}

    # Add language parameter if configured
    lang = config.get("tts_language", "")
    if lang:
        data["language"] = lang

    with open(file_path, "rb") as f:
        resp = requests.post(
            f"{config['base_url']}/audio/transcriptions",
            headers={"Authorization": f"Bearer {config['api_key']}"},
            files={"file": (os.path.basename(audio_file), f, "audio/webm")},
            data=data,
            timeout=60,
        )

    if resp.status_code != 200:
        frappe.throw(f"STT API error ({resp.status_code}): {resp.text[:300]}")

    result = resp.json()
    return {"text": result.get("text", "")}


@frappe.whitelist(allow_guest=False)
def voice_chat(conversation_id, audio_file, voice=None):
    """
    Combined voice chat: STT → Chat → TTS in one call.
    """
    check_rate_limit()
    log_api_call("voice_chat", conversation_id=conversation_id)

    if not conversation_id:
        frappe.throw("No conversation_id provided")
    if not audio_file:
        frappe.throw("No audio file provided")

    config = _get_voice_config()
    voice = voice or config["default_voice"]

    # Step 1: Speech to Text
    stt_result = speech_to_text(audio_file)
    user_text = stt_result.get("text", "").strip()

    if not user_text:
        return {
            "text": "",
            "response": "I couldn't understand what you said. Please try again.",
            "audio_url": None,
        }

    # Step 2: Send to chat
    from niv_ai.niv_core.api.chat import send_message
    chat_result = send_message(conversation_id=conversation_id, message=user_text)
    response_text = chat_result.get("response", "") or chat_result.get("message", "")

    # Step 3: TTS on response (text_to_speech already cleans)
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
    """Voice chat using base64-encoded audio — bypasses upload_file API.
    
    Args:
        audio_base64: base64 encoded audio data
        conversation_id: optional, auto-creates if empty
        browser_transcript: optional, browser STT result
    """
    import base64, tempfile, os
    
    audio_base64 = frappe.form_dict.get("audio_base64", "")
    conversation_id = frappe.form_dict.get("conversation_id", "")
    browser_transcript = frappe.form_dict.get("browser_transcript", "")
    
    # Auto-create conversation if not provided
    if not conversation_id:
        try:
            conv = frappe.get_doc({
                "doctype": "Niv Conversation",
                "user": frappe.session.user,
                "title": "Voice Chat",
                "channel": "voice",
            })
            conv.insert(ignore_permissions=True)
            frappe.db.commit()
            conversation_id = conv.name
        except Exception as e:
            frappe.throw("Failed to create conversation: " + str(e))
    
    user_text = browser_transcript
    
    # If we have audio, try server-side STT
    if audio_base64 and not user_text:
        try:
            audio_bytes = base64.b64decode(audio_base64)
            # Write to temp file
            tmp = tempfile.NamedTemporaryFile(suffix=".webm", delete=False)
            tmp.write(audio_bytes)
            tmp.close()
            
            # Save as Frappe file
            from frappe.utils.file_manager import save_file
            file_doc = save_file(
                "voice_input.webm", audio_bytes, "Niv Conversation",
                conversation_id, folder="Home/Niv AI", is_private=1
            )
            file_url = file_doc.file_url
            
            # Run STT
            stt_result = speech_to_text(file_url)
            user_text = stt_result.get("text", "")
            
            # Cleanup temp file
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
    
    # Send to chat
    from niv_ai.niv_core.api.chat import send_message
    chat_result = send_message(conversation_id=conversation_id, message=user_text)
    response_text = chat_result.get("response", "") or chat_result.get("message", "") or chat_result.get("content", "")
    
    # Generate TTS
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
    # OpenAI TTS only available if provider supports it (not Mistral)
    openai_available = bool(config.get("api_key")) and config.get("provider_type") != "mistral"
    return {
        "piper": _is_piper_available(),
        "openai": openai_available,
        "browser": True,
        "provider_type": config.get("provider_type", "unknown"),
    }


@frappe.whitelist(allow_guest=False)
def get_available_voices():
    """List popular Piper voices"""
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
        files = frappe.get_all("File", filters={"file_url": file_url}, fields=["name"])
        for f in files:
            frappe.delete_doc("File", f["name"], ignore_permissions=True, force=True)
    except Exception:
        pass
