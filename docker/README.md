# Niv AI - Docker Persistence Setup

## Problem

Frappe Docker containers lose customizations on restart:
1. **pip packages** (openai, tiktoken, etc.) need reinstalling
2. **Nginx SSE config** for streaming needs re-patching

## Solution

A docker-compose override file + startup scripts that automatically handle both.

## Files

| File | Location | Purpose |
|------|----------|---------|
| `startup.sh` | This dir → copied to Docker | Installs pip deps before backend/worker start |
| `nginx-patch.sh` | This dir → copied to Docker | Patches nginx config for SSE, then starts nginx |
| `niv_ai_override.yml` | `D:\erpnext\frappe_docker\` | Compose override that wires scripts into containers |
| `restart.ps1` | This dir | One-click Windows restart script |

## Usage

### Option A: One-click (recommended)
```powershell
& "$env:USERPROFILE\.openclaw\workspace\niv_ai\docker\restart.ps1"
```

### Option B: Manual
```powershell
# 1. Copy scripts
Copy-Item .\startup.sh D:\erpnext\frappe_docker\niv_ai_docker_scripts\
Copy-Item .\nginx-patch.sh D:\erpnext\frappe_docker\niv_ai_docker_scripts\

# 2. Start with override
cd D:\erpnext\frappe_docker
docker compose -f pwd.yml -f niv_ai_override.yml up -d
```

### Option C: Without override (original pwd.yml only)
If you don't want the override, use the restart script which falls back to manual exec:
```powershell
cd D:\erpnext\frappe_docker
docker compose -f pwd.yml up -d
# Then manually:
docker exec frappe_docker-backend-1 pip install openai tiktoken ...
docker exec frappe_docker-backend-1 pip install -e /home/frappe/frappe-bench/apps/niv_ai
# Repeat for queue-short, queue-long, scheduler
```

## How It Works

### Backend + Workers (`startup.sh`)
- Runs `pip install` for all dependencies
- Runs `pip install -e` for niv_ai app
- Then `exec "$@"` passes control to the original command (gunicorn/bench worker)

### Frontend (`nginx-patch.sh`)
- Replicates `nginx-entrypoint.sh` (envsubst template → config)
- Injects SSE location block for `/api/method/niv_ai.niv_core.api.stream.stream_message`
- Starts `nginx -g 'daemon off;'`

### Override file (`niv_ai_override.yml`)
- Bind-mounts scripts via a named volume from `./niv_ai_docker_scripts/`
- Overrides entrypoint on backend/workers to run startup.sh first
- Overrides frontend command to use nginx-patch.sh instead of nginx-entrypoint.sh

## Adding New Dependencies

Edit `startup.sh` and add packages to the `pip install` line.

## Troubleshooting

```powershell
# Check if deps installed
docker exec frappe_docker-backend-1 python -c "import openai; print('OK')"

# Check nginx config
docker exec frappe_docker-frontend-1 cat /etc/nginx/conf.d/frappe.conf | Select-String "niv_ai"

# View startup logs
docker logs frappe_docker-backend-1 2>&1 | Select-String "niv_ai"
```
