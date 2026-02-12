# Niv AI - One-click Docker restart with persistence
# Run from any directory

$ErrorActionPreference = "Stop"
$DockerDir = "D:\erpnext\frappe_docker"
$ScriptsDir = "$DockerDir\niv_ai_docker_scripts"

Write-Host "=== Niv AI Docker Restart ===" -ForegroundColor Cyan

# Step 1: Copy startup scripts to Docker context
Write-Host "`n[1/4] Copying startup scripts..." -ForegroundColor Yellow
if (!(Test-Path $ScriptsDir)) { New-Item -ItemType Directory -Path $ScriptsDir -Force | Out-Null }

$ScriptSource = Split-Path -Parent $PSScriptRoot
if (!(Test-Path "$ScriptSource\docker\startup.sh")) {
    $ScriptSource = "$env:USERPROFILE\.openclaw\workspace\niv_ai"
}
Copy-Item "$ScriptSource\docker\startup.sh" "$ScriptsDir\startup.sh" -Force
Copy-Item "$ScriptSource\docker\nginx-patch.sh" "$ScriptsDir\nginx-patch.sh" -Force
Write-Host "  Scripts copied to $ScriptsDir"

# Step 2: Docker compose up with override
Write-Host "`n[2/4] Starting containers..." -ForegroundColor Yellow
Push-Location $DockerDir
try {
    docker compose -f pwd.yml -f niv_ai_override.yml up -d
} finally {
    Pop-Location
}

# Step 3: Wait for backend to be ready
Write-Host "`n[3/4] Waiting for backend..." -ForegroundColor Yellow
$maxWait = 60
$elapsed = 0
do {
    Start-Sleep -Seconds 3
    $elapsed += 3
    $health = docker exec frappe_docker-backend-1 curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/method/ping 2>$null
    Write-Host "  Waiting... ($elapsed`s)" -NoNewline
    Write-Host ""
} while ($health -ne "200" -and $elapsed -lt $maxWait)

if ($health -eq "200") {
    Write-Host "  Backend is ready!" -ForegroundColor Green
} else {
    Write-Host "  Backend not responding after ${maxWait}s (may still be starting)" -ForegroundColor Yellow
}

# Step 4: Verify
Write-Host "`n[4/4] Verifying..." -ForegroundColor Yellow
$containers = @("frappe_docker-backend-1", "frappe_docker-queue-short-1", "frappe_docker-queue-long-1")
foreach ($c in $containers) {
    $result = docker exec $c python -c "import openai; print('openai OK')" 2>&1
    if ($result -match "OK") {
        Write-Host "  $c : pip deps OK" -ForegroundColor Green
    } else {
        Write-Host "  $c : pip deps MISSING (may still be installing)" -ForegroundColor Yellow
    }
}

$sseCheck = docker exec frappe_docker-frontend-1 grep -c "niv_ai.*stream" /etc/nginx/conf.d/frappe.conf 2>$null
if ($sseCheck -gt 0) {
    Write-Host "  frontend: SSE config OK" -ForegroundColor Green
} else {
    Write-Host "  frontend: SSE config MISSING" -ForegroundColor Yellow
}

Write-Host "`n=== Done! ERPNext at http://localhost:8081 ===" -ForegroundColor Cyan
