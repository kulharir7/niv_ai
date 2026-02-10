"""
LLM Provider Factory
Maps Niv AI Provider DocType → LangChain ChatModel
"""
import frappe
from langchain_openai import ChatOpenAI


def get_llm(provider_name=None, model=None, streaming=True, callbacks=None):
    """Create LangChain LLM from Niv AI Provider settings.
    
    Falls back: provider_name → Niv Settings default → error
    Model falls back: model arg → provider.default_model → settings.default_model
    """
    if not provider_name:
        settings = frappe.get_cached_doc("Niv Settings")
        provider_name = settings.default_provider
        if not model:
            model = settings.default_model

    if not provider_name:
        frappe.throw("No AI provider configured. Set default_provider in Niv Settings.")

    provider = frappe.get_doc("Niv AI Provider", provider_name)
    api_key = provider.get_password("api_key")
    
    if not model:
        model = provider.default_model
    
    if not model:
        frappe.throw(f"No model specified and provider '{provider_name}' has no default_model.")

    return ChatOpenAI(
        base_url=provider.base_url,
        api_key=api_key,
        model=model,
        streaming=streaming,
        callbacks=callbacks or [],
        temperature=0.7,
        max_retries=2,
        request_timeout=120,
    )
