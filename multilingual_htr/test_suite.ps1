# Windows PowerShell Script to Execute Test Suite & Benchmark Evaluation

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Multilingual HTR - Automated Test Suite & Benchmarks     " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

if (Test-Path "manage.py") {
    $TargetDir = "."
} elseif (Test-Path "multilingual_htr\manage.py") {
    $TargetDir = "multilingual_htr"
} else {
    Write-Host "Error: manage.py not found!" -ForegroundColor Red
    exit 1
}

Push-Location $TargetDir

Write-Host "`n[1/2] Running automated Django unit and integration tests..." -ForegroundColor Yellow
python manage.py test

Write-Host "`n[2/2] Running CER & WER Accuracy Benchmark Evaluation..." -ForegroundColor Yellow
python manage.py evaluate_accuracy

Write-Host "`nAll verification steps completed!" -ForegroundColor Green
Pop-Location
