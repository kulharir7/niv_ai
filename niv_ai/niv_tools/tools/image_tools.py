import frappe
import json
import requests
import os
import uuid
from datetime import datetime


def generate_image(prompt, size="1024x1024", style="natural"):
    """Generate an image using DALL-E or compatible API"""
    settings = frappe.get_single("Niv Settings")

    if not settings.enable_image_generation:
        return {"error": "Image generation is not enabled. Ask admin to enable it in Niv Settings."}

    # Get API key - use image-specific key or fall back to provider key
    api_key = settings.get_password("image_api_key") if settings.image_api_key else None
    if not api_key:
        provider_name = settings.default_provider
        if provider_name:
            provider = frappe.get_doc("Niv AI Provider", provider_name)
            api_key = provider.get_password("api_key")

    if not api_key:
        return {"error": "No API key configured for image generation."}

    base_url = (settings.image_api_url or "https://api.openai.com/v1").rstrip("/")

    # Validate size
    valid_sizes = ["256x256", "512x512", "1024x1024", "1024x1792", "1792x1024"]
    if size not in valid_sizes:
        size = "1024x1024"

    try:
        resp = requests.post(
            f"{base_url}/images/generations",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "dall-e-3",
                "prompt": prompt,
                "n": 1,
                "size": size,
                "style": style,
                "response_format": "url",
            },
            timeout=120,
        )

        if resp.status_code != 200:
            try:
                err = resp.json().get("error", {}).get("message", resp.text[:300])
            except Exception:
                err = resp.text[:300]
            return {"error": f"Image generation failed ({resp.status_code}): {err}"}

        result = resp.json()
        image_url = result["data"][0]["url"]
        revised_prompt = result["data"][0].get("revised_prompt", prompt)

        # Download and save as Frappe File
        img_resp = requests.get(image_url, timeout=60)
        if img_resp.status_code != 200:
            return {"error": "Failed to download generated image."}

        filename = f"niv_generated_{uuid.uuid4().hex[:8]}.png"
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": filename,
            "content": img_resp.content,
            "is_private": 0,
            "folder": "Home/Niv AI",
        })
        file_doc.save(ignore_permissions=True)
        frappe.db.commit()

        return {
            "success": True,
            "file_url": file_doc.file_url,
            "revised_prompt": revised_prompt,
            "message": f"Image generated successfully!\n\n![Generated Image]({file_doc.file_url})",
        }

    except requests.Timeout:
        return {"error": "Image generation timed out. Try a simpler prompt."}
    except Exception as e:
        frappe.log_error(f"Image generation error: {str(e)}", "Niv AI Image Generation")
        return {"error": f"Image generation failed: {str(e)}"}


def describe_image(image_url):
    """Describe an image using a vision model"""
    settings = frappe.get_single("Niv Settings")

    provider_name = settings.default_provider
    if not provider_name:
        return {"error": "No AI provider configured."}

    provider = frappe.get_doc("Niv AI Provider", provider_name)
    api_key = provider.get_password("api_key")
    model = settings.default_model or provider.default_model or "gpt-4o"

    # Build absolute URL if relative
    if image_url.startswith("/"):
        site_url = frappe.utils.get_url()
        image_url = f"{site_url}{image_url}"

    try:
        resp = requests.post(
            f"{provider.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Describe this image in detail."},
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ],
                    }
                ],
                "max_tokens": 1000,
            },
            timeout=60,
        )

        if resp.status_code != 200:
            return {"error": f"Vision API error ({resp.status_code})"}

        result = resp.json()
        description = result["choices"][0]["message"]["content"]
        return {"success": True, "description": description}

    except Exception as e:
        return {"error": f"Image description failed: {str(e)}"}
