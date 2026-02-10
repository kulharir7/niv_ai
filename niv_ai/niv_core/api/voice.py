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
    default_voice = settings.default_voice or "en_US-lessac-medium"
    tts_model = settings.tts_model or "tts-1"

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

    return {
        "api_key": api_key,
        "base_url": base_url.rstrip("/") if base_url else "",
        "default_voice": default_voice,
        "tts_model": tts_model,
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


def _tts_piper(text, voice_name=None):
    """Generate speech using Piper TTS (local, free, fast)"""
    try:
        from piper import PiperVoice
    except ImportError:
        return None

    voice_name = voice_name or "en_US-lessac-medium"

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

@frappe.whitelist(allow_guest=False)
def text_to_speech(text, voice=None, model=None, response_format="wav", engine=None):
    """
    Convert text to speech. Tries engines in order:
    1. Piper TTS (free, local, fast) — if installed
    2. OpenAI-compatible API — if API key configured
    3. Returns engine='browser' signal for client-side fallback
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

    # ── Try Piper TTS (free, local) ──
    if engine in (None, "auto", "piper"):
        result = _tts_piper(text, voice or config.get("default_voice"))
        if result:
            return result

    # ── Try OpenAI-compatible API ──
    if engine in (None, "auto", "openai") and config.get("api_key"):
        return _tts_openai(text, voice or "alloy", model or config["tts_model"], response_format, config)

    # ── Fallback: tell client to use browser TTS ──
    return {"audio_url": None, "engine": "browser", "text": text}


@frappe.whitelist(allow_guest=False)
def speech_to_text(audio_file):
    """
    Transcribe audio using OpenAI-compatible Whisper API.
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

    with open(file_path, "rb") as f:
        resp = requests.post(
            f"{config['base_url']}/audio/transcriptions",
            headers={"Authorization": f"Bearer {config['api_key']}"},
            files={"file": (os.path.basename(audio_file), f, "audio/webm")},
            data={"model": "whisper-1"},
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
    response_text = chat_result.get("message", "")

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
def get_tts_status():
    """Check which TTS engines are available"""
    return {
        "piper": _is_piper_available(),
        "openai": bool(_get_voice_config().get("api_key")),
        "browser": True,
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
