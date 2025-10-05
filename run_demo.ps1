Write-Host "🚀 Starting Waresys demo stack..."
try { docker compose pull } catch {}
docker compose build --no-cache waresys_ui
docker compose up -d --build

Start-Sleep -Seconds 2

Start-Process "http://localhost:8000/docs"
Start-Process "http://localhost:8080"

docker compose ps
Write-Host "✅ Ready. Swagger on :8000, UI on :8080."
