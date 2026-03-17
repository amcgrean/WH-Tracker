$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptRoot

$python = Join-Path $scriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Tracker virtualenv Python not found at $python"
}

$logDir = Join-Path $scriptRoot "logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}
$logFile = Join-Path $logDir "erp_sync.log"

function Write-Log($message) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$timestamp] $message" | Out-File -FilePath $logFile -Append -Encoding utf8
    Write-Host "[$timestamp] $message"
}

$maxRetries = 3
$retryCount = 0
$success = $false

while (-not $success -and $retryCount -lt $maxRetries) {
    try {
        Write-Log "Starting ERP Sync (Attempt $($retryCount + 1))..."
        & $python "sync_erp.py" "--once" 2>&1 | Out-File -FilePath $logFile -Append -Encoding utf8
        if ($LASTEXITCODE -eq 0) {
            $success = $true
            Write-Log "Sync completed successfully."
        } else {
            throw "sync_erp.py failed with exit code $LASTEXITCODE"
        }
    } catch {
        $retryCount++
        Write-Log "Error: $($_.Exception.Message)"
        if ($retryCount -lt $maxRetries) {
            $waitSec = [Math]::Pow(2, $retryCount) * 5
            Write-Log "Retrying in $waitSec seconds..."
            Start-Sleep -Seconds $waitSec
        } else {
            Write-Log "Max retries reached. Sync failed."
            exit 1
        }
    }
}
