<#
EngineeringAgent setup for Windows (PowerShell, no administrator rights needed).

    powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

Creates .venv, installs the Python packages, downloads the CalculiX solver into
tools\calculix, then runs the built-in benchmark. Safe to re-run.
#>
param(
    [string]$CalculixUrl = "https://www.dhondt.de/calculix_2.23_4win.zip",
    [switch]$SkipSolver
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Find-Python {
    foreach ($v in "3.12", "3.13", "3.11", "3.10") {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            $exe = & py "-$v" -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $exe) { return $exe.Trim() }
        }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) {
        $ver = & python -c "import sys; print('%d.%d' % sys.version_info[:2])"
        if ($ver -in "3.10", "3.11", "3.12", "3.13") { return $cmd.Source }
    }
    return $null
}

Write-Host "== EngineeringAgent setup ==" -ForegroundColor Cyan
$py = Find-Python
if (-not $py) {
    Write-Host "Python 3.10-3.13 was not found. Install it with:" -ForegroundColor Yellow
    Write-Host "    winget install --id Python.Python.3.12 -e"
    Write-Host "then open a new PowerShell window and run this script again."
    exit 1
}
Write-Host "Python: $py"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment .venv ..."
    & $py -m venv .venv
}
$vpy = Join-Path $root ".venv\Scripts\python.exe"
Write-Host "Installing Python packages (build123d, gmsh, ...). This takes a few minutes the first time."
& $vpy -m pip install --upgrade pip --quiet
& $vpy -m pip install -e ".[mcp,dev]" --quiet
if ($LASTEXITCODE -ne 0) { Write-Host "pip install failed - copy the error above into Claude Code." -ForegroundColor Red; exit 1 }

if (-not $SkipSolver) {
    $have = Get-ChildItem -Path "tools\calculix" -Recurse -Filter "ccx*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($have) {
        Write-Host "CalculiX already present: $($have.FullName)"
    } else {
        Write-Host "Downloading CalculiX from $CalculixUrl (about 60 MB) ..."
        New-Item -ItemType Directory -Force "tools\calculix" | Out-Null
        $zip = Join-Path $env:TEMP "calculix_win.zip"
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri $CalculixUrl -OutFile $zip -UseBasicParsing
            Expand-Archive -Path $zip -DestinationPath "tools\calculix" -Force
            Remove-Item $zip -ErrorAction SilentlyContinue
        } catch {
            Write-Host "Download failed: $($_.Exception.Message)" -ForegroundColor Yellow
            Write-Host "Download the Windows zip from https://www.dhondt.de by hand, unzip it into"
            Write-Host "  $root\tools\calculix"
            Write-Host "(keep all files together), or set ENGAGENT_CCX to the full path of ccx_static.exe."
        }
    }
}

Write-Host ""
& (Join-Path $root ".venv\Scripts\engagent.exe") doctor --full
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Setup complete. Start Claude Code in this folder (run: claude) and ask for a part or an analysis." -ForegroundColor Green
    Write-Host "Command line:  .\ea.cmd units        .\ea.cmd fea new jobs\01-my-part -a static"
    Write-Host "MCP server for other AI clients:  $root\.venv\Scripts\engagent-mcp.exe   (see docs\mcp.md)"
} else {
    Write-Host "Setup finished with problems - see the items marked above." -ForegroundColor Yellow
    exit 1
}
