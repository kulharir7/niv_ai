"""
Ollama Cloud Keep-Alive Ping
Sends a tiny request every 5 minutes to prevent cold starts.
Run via cron: */5 * * * * cd /home/gws/frappe-bench/sites && ../env/bin/python ../apps/niv_ai/scripts/keepalive_ping.py
"""
import sys, os
sys.path.insert(0, '/home/gws/frappe-bench/apps/frappe')
sys.path.insert(0, '/home/gws/frappe-bench/apps/niv_ai')
os.chdir('/home/gws/frappe-bench/sites')

import frappe, requests, time

try:
    frappe.init(site='erp024.growthsystem.in')
    frappe.connect()
    
    provider = frappe.get_doc('Niv AI Provider', 'ollama-cloud')
    api_key = provider.get_password('api_key')
    base_url = provider.base_url
    model = provider.default_model
    
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    
    t = time.time()
    r = requests.post(f"{base_url}/chat/completions", headers=headers, json={
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "stream": False,
        "max_tokens": 1
    }, timeout=30)
    elapsed = time.time() - t
    
    status = "OK" if r.status_code == 200 else f"ERR:{r.status_code}"
    print(f"[keepalive] {model} | {status} | {elapsed:.1f}s")
    
except Exception as e:
    print(f"[keepalive] ERROR: {e}")
finally:
    frappe.destroy()
