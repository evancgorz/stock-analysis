$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $scriptDir

$appUrl = "http://localhost:8501"

$existing = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -match "^python" -and
        $_.CommandLine -match "streamlit" -and
        $_.CommandLine -match "app.py"
    }

if (-not $existing) {
    Start-Process -FilePath "python" -ArgumentList "-m", "streamlit", "run", "app.py", "--server.headless", "true"
    Start-Sleep -Seconds 4
}

Start-Process $appUrl
Write-Host "Opened $appUrl"
