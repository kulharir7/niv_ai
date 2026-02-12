#!/usr/bin/env python3
"""Pre-deploy validator for Niv AI - catches issues that cause blank pages."""
import os, sys, re

ERRORS = []
APP_DIR = os.path.join(os.path.dirname(__file__), "..", "niv_ai")

def check_html_no_single_quotes(path):
    """Frappe wraps HTML templates in single quotes — any ' inside breaks JS eval."""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    for i, line in enumerate(content.split("\n"), 1):
        if "'" in line:
            ERRORS.append(f"SINGLE QUOTE in HTML: {path}:{i} -> {line.strip()[:80]}")

def check_js_no_html_comments(path):
    """HTML comments (<!-- -->) inside JS template literals break eval."""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    for i, line in enumerate(content.split("\n"), 1):
        if "<!--" in line or "-->" in line:
            ERRORS.append(f"HTML COMMENT in JS: {path}:{i} -> {line.strip()[:80]}")

def check_python_safe_imports(path):
    """Utils imports must be wrapped in try/except to survive missing modules."""
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    for i, line in enumerate(lines, 1):
        if "from niv_ai.niv_core.utils" in line and line.strip().startswith("from"):
            # Check if any previous line in the block is "try:" (within 10 lines)
            context = [l.strip() for l in lines[max(0,i-11):i-1]]
            if "try:" not in context:
                ERRORS.append(f"UNPROTECTED UTILS IMPORT: {path}:{i} -> {line.strip()[:80]}")

# Scan all page HTML files
for root, dirs, files in os.walk(APP_DIR):
    for f in files:
        path = os.path.join(root, f)
        if f.endswith(".html") and "page" in root:
            check_html_no_single_quotes(path)
        if f.endswith(".js") and "page" in root:
            check_js_no_html_comments(path)
        if f.endswith(".py") and "api" in root:
            check_python_safe_imports(path)

if ERRORS:
    print(f"[FAIL] {len(ERRORS)} ERRORS FOUND - DO NOT DEPLOY!")
    for e in ERRORS:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("[OK] All checks passed - safe to deploy!")
    sys.exit(0)
