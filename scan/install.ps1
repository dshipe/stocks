# install.ps1 -- Install all dependencies for the stock scanning system
# Run from the scan/ directory:
#   cd scan
#   .\install.ps1

$ErrorActionPreference = "Continue"

function Write-Step { param($msg) Write-Host "" ; Write-Host ">> $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "   OK   $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "   WARN $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "   FAIL $msg" -ForegroundColor Red }


# ---------------------------------------------------------------------------
# 1. Find Python 3.9+
# ---------------------------------------------------------------------------
Write-Step "Checking Python"

$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 9) {
                $python = $cmd
                Write-Ok "$ver  ($cmd)"
                break
            } else {
                Write-Warn "$ver is below 3.9 -- skipping"
            }
        }
    } catch {
        # command not found -- try next
    }
}

if (-not $python) {
    Write-Fail "Python 3.9+ not found. Download from https://python.org/downloads/ and re-run."
    exit 1
}


# ---------------------------------------------------------------------------
# 2. Upgrade pip
# ---------------------------------------------------------------------------
Write-Step "Upgrading pip"
& $python -m pip install --upgrade pip --quiet
Write-Ok "pip ready"


# ---------------------------------------------------------------------------
# 3. Install Python packages
# ---------------------------------------------------------------------------
Write-Step "Installing packages from requirements.txt"

$reqFile = Join-Path $PSScriptRoot "requirements.txt"
if (-not (Test-Path $reqFile)) {
    Write-Fail "requirements.txt not found at: $reqFile"
    exit 1
}

& $python -m pip install -r $reqFile
if ($LASTEXITCODE -ne 0) {
    Write-Fail "pip install failed -- see output above"
    exit 1
}
Write-Ok "All packages installed"


# ---------------------------------------------------------------------------
# 4. ODBC Driver 18 for SQL Server
# ---------------------------------------------------------------------------
Write-Step "Checking ODBC Driver 18 for SQL Server"

$odbcInstalled = Get-OdbcDriver -Name "ODBC Driver 18 for SQL Server" -ErrorAction SilentlyContinue

if ($odbcInstalled) {
    Write-Ok "ODBC Driver 18 already installed"
} else {
    Write-Warn "ODBC Driver 18 not found -- downloading..."

    $installerUrl  = "https://go.microsoft.com/fwlink/?linkid=2249006"
    $installerPath = Join-Path $env:TEMP "msodbcsql18.msi"

    try {
        Write-Host "   Downloading from Microsoft..." -NoNewline
        Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing
        Write-Host " done" -ForegroundColor Green
    } catch {
        Write-Fail "Download failed: $_"
        Write-Host "   Install manually: https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server"
        exit 1
    }

    Write-Host "   Installing ODBC Driver 18 (silent)..."
    $msiArgs = "/i `"$installerPath`" /quiet /norestart IACCEPTMSODBCSQLLICENSETERMS=YES"
    $proc = Start-Process -FilePath "msiexec.exe" -ArgumentList $msiArgs -Wait -PassThru
    Remove-Item $installerPath -Force -ErrorAction SilentlyContinue

    if ($proc.ExitCode -eq 0) {
        Write-Ok "ODBC Driver 18 installed"
    } elseif ($proc.ExitCode -eq 3010) {
        Write-Warn "ODBC Driver 18 installed -- reboot required to complete"
    } else {
        Write-Fail "Installer exited with code $($proc.ExitCode) -- try running as Administrator"
        exit 1
    }
}


# ---------------------------------------------------------------------------
# 5. Verify key imports
# ---------------------------------------------------------------------------
Write-Step "Verifying key imports"

$modules = @(
    "yfinance",
    "pandas",
    "numpy",
    "pyodbc",
    "dotenv",
    "requests",
    "pytz",
    "yahoo_fin"
)

$allOk = $true
foreach ($mod in $modules) {
    & $python -c "import $mod" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Ok $mod
    } else {
        Write-Fail "$mod -- import failed"
        $allOk = $false
    }
}


# ---------------------------------------------------------------------------
# 6. Test database connection
# ---------------------------------------------------------------------------
Write-Step "Testing database connection"

$testScript = Join-Path $env:TEMP "db_test.py"
$scanDir    = $PSScriptRoot -replace '\\', '\\'

Set-Content -Path $testScript -Value @"
import sys
sys.path.insert(0, r'$PSScriptRoot')
from shared.db_writer import test_connection
ok = test_connection()
sys.exit(0 if ok else 1)
"@

& $python $testScript 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Ok "SQL Server connection successful"
} else {
    Write-Warn "SQL Server connection failed -- check scan/.env has DB_SERVER, DB_USER, DB_PASSWORD"
}
Remove-Item $testScript -Force -ErrorAction SilentlyContinue


# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
Write-Host ""
if ($allOk) {
    Write-Host "All done. Quick test:" -ForegroundColor Green
    Write-Host "  python watchlist_scanner.py --dry-run --ticker NVDA"
} else {
    Write-Host "Some imports failed -- check errors above." -ForegroundColor Yellow
}
Write-Host ""
