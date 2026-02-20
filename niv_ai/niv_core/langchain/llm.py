"""
LLM Provider Factory
Maps Niv AI Provider DocType → LangChain ChatModel.
Supports OpenAI-compatible (Mistral, OpenAI, Ollama, Groq, Together),
Anthropic (Claude), and Google (Gemini).
"""
import frappe
from functools import lru_cache


# Provider type → LangChain class mapping
_PROVIDER_CLASSES = {
    "openai": "langchain_openai.ChatOpenAI",
    "anthropic": "langchain_anthropic.ChatAnthropic",
    "google": "langchain_google_genai.ChatGoogleGenerativeAI",
}


def _import_class(dotted_path: str):
    """Dynamically import a class from dotted path."""
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _detect_provider_type(base_url: str, provider_name: str) -> str:
    """Auto-detect provider type from base_url or name."""
    name_lower = (provider_name or "").lower()
    url_lower = (base_url or "").lower()

    if "anthropic" in name_lower or "claude" in name_lower or "anthropic" in url_lower:
        return "anthropic"
    if "google" in name_lower or "gemini" in name_lower or "generativelanguage" in url_lower:
        return "google"
    # Default: OpenAI-compatible (works with Mistral, OpenAI, Ollama, Groq, Together, etc.)
    return "openai"


def get_llm(provider_name=None, model=None, streaming=True, callbacks=None):
    """Create LangChain LLM from Niv AI Provider settings.

    Fallback chain:
      provider: provider_name arg → settings.default_provider
      model: model arg → provider.default_model → settings.default_model
    """
    from niv_ai.niv_core.utils import get_niv_settings
    settings = get_niv_settings()

    provider_name = provider_name or settings.default_provider
    if not provider_name:
        frappe.throw("No AI provider configured. Set default_provider in Niv Settings.")

    provider = frappe.get_doc("Niv AI Provider", provider_name)
    # Get API key — auto-refresh OAuth tokens if expired
    auth_type = getattr(provider, "auth_type", "API Key") or "API Key"
    if auth_type in ("Setup Token", "ChatGPT Login") and getattr(provider, "refresh_token", None):
        from niv_ai.niv_core.api.oauth import refresh_if_needed
        api_key = refresh_if_needed(provider_name)
    else:
        api_key = provider.get_password("api_key")
    
    model = model or provider.default_model or settings.default_model

    if not model:
        frappe.throw(f"No model specified and provider '{provider_name}' has no default_model.")

    auth_type = getattr(provider, "auth_type", "API Key") or "API Key"

    # OAuth auth types → force correct provider type
    if auth_type == "Setup Token":
        provider_type = "anthropic"
    elif auth_type == "ChatGPT Login":
        provider_type = "openai"
    else:
        provider_type = _detect_provider_type(provider.base_url, provider_name)

    common_kwargs = {
        "model": model,
        "streaming": streaming,
        "callbacks": callbacks or [],
        "temperature": 0.7,
    }

    if provider_type == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            base_url=provider.base_url,
            api_key=api_key,
            max_retries=2,
            request_timeout=120,
            **common_kwargs,
        )

    elif provider_type == "anthropic":
        try:
            ChatAnthropic = _import_class(_PROVIDER_CLASSES["anthropic"])
        except ImportError:
            frappe.throw("Install langchain-anthropic: pip install langchain-anthropic")
        return ChatAnthropic(
            api_key=api_key,
            max_retries=2,
            timeout=120,
            **common_kwargs,
        )

    elif provider_type == "google":
        try:
            ChatGoogle = _import_class(_PROVIDER_CLASSES["google"])
        except ImportError:
            frappe.throw("Install langchain-google-genai: pip install langchain-google-genai")
        return ChatGoogle(
            google_api_key=api_key,
            **common_kwargs,
        )

    # Fallback to OpenAI-compatible
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        base_url=provider.base_url,
        api_key=api_key,
        max_retries=2,
        request_timeout=120,
        **common_kwargs,
    )


def get_vision_llm(callbacks=None):
    """Create LLM configured for vision/OCR tasks.
    
    Uses vision_model from Niv Settings. Falls back to default model.
    Non-streaming since we need the full OCR text before passing to main LLM.
    """
    from niv_ai.niv_core.utils import get_niv_settings
    settings = get_niv_settings()
    
    vision_model = getattr(settings, "vision_model", None)
    if not vision_model:
        # Fallback to default model
        vision_model = settings.default_model
    
    return get_llm(
        model=vision_model,
        streaming=False,
        callbacks=callbacks,
    )


def call_vision(image_base64: str, prompt: str = None, mime_type: str = "image/jpeg") -> str:
    """Send image to vision model and get text extraction.
    
    Args:
        image_base64: Base64-encoded image data
        prompt: Custom prompt for vision model. Defaults to OCR extraction prompt.
        mime_type: Image MIME type (image/jpeg, image/png, etc.)
    
    Returns:
        Extracted text/description from the image
    """
    from niv_ai.niv_core.utils import get_niv_settings
    settings = get_niv_settings()
    
    if not getattr(settings, "enable_vision", 0):
        return "[Vision not enabled. Enable it in Niv Settings → Vision & Image]"
    
    if not prompt:
        prompt = (
            "Extract ALL text from this image. If it contains a table, preserve the table structure. "
            "If it's a document (Aadhaar, PAN, cheque, bank statement, invoice), extract all fields with labels. "
            "If it's a chart/graph, describe the data points and trends. "
            "Return the extracted content in a clean, structured format."
        )
    
    llm = get_vision_llm()
    
    from langchain_core.messages import HumanMessage
    
    message = HumanMessage(
        content=[
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{image_base64}"
                }
            }
        ]
    )
    
    try:
        response = llm.invoke([message])
        max_tokens = int(getattr(settings, "vision_max_tokens", 2048) or 2048)
        text = response.content or ""
        if len(text) > max_tokens * 4:  # rough char limit
            text = text[:max_tokens * 4] + "\n...[truncated]"
        return text
    except Exception as e:
        frappe.log_error(f"Vision call failed: {e}", "Niv AI Vision")
        return f"[Vision processing failed: {str(e)}]"
