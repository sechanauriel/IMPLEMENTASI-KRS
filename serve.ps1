$venv = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venv)) {
    Write-Error "Virtual environment python not found at $venv. Activate venv or install dependencies."
    exit 1
}
$log = Join-Path $PSScriptRoot "server.log"
$err = Join-Path $PSScriptRoot "server.err"
$args = "-m uvicorn krs:app --host 127.0.0.1 --port 8000"
Start-Process -FilePath $venv -ArgumentList $args -RedirectStandardOutput $log -RedirectStandardError $err -WindowStyle Minimized
Write-Output "Server starting in background. Logs: $log, $err"