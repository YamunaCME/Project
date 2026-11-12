# Windows PowerShell Script to Run Multilingual HTR Locally

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Multilingual Handwritten and Printed Text Recognition   " -ForegroundColor Cyan
Write-Host " Starting Local Django Development Server                " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Ensure we are in multilingual_htr directory
if (Test-Path "manage.py") {
    $TargetDir = "."
} elseif (Test-Path "multilingual_htr\manage.py") {
    $TargetDir = "multilingual_htr"
} else {
    Write-Host "Error: manage.py not found!" -ForegroundColor Red
    exit 1
}

Push-Location $TargetDir

Write-Host "`n[1/3] Running database migrations..." -ForegroundColor Yellow
python manage.py migrate

Write-Host "`n[2/3] Seeding demo data (superuser 'admin' & test documents)..." -ForegroundColor Yellow
python manage.py seed_demo_data

Write-Host "`n[3/3] Starting Django development server at http://127.0.0.1:8000/..." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop the server.`n" -ForegroundColor DarkGray

Start-Process "http://127.0.0.1:8000/"
python manage.py runserver 127.0.0.1:8000

Pop-Location
