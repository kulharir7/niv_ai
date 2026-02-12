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
    settings = frappe.get_cached_doc("Niv Settings")

    provider_name = provider_name or settings.default_provider
    if not provider_name:
        frappe.throw("No AI provider configured. Set default_provider in Niv Settings.")

    provider = frappe.get_doc("Niv AI Provider", provider_name)
    api_key = provider.get_password("api_key")
    model = model or provider.default_model or settings.default_model

    if not model:
        frappe.throw(f"No model specified and provider '{provider_name}' has no default_model.")

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
