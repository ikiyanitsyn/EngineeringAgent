<#
EngineeringAgent start menu for Windows. Launched by START-HERE.cmd (double-click).
Installs everything on first use, then offers the simplest ways to get a part or an analysis.
#>
param(
    [string]$Do = "",      # non-interactive action for scripts and CI: prompt | request | units | doctor
    [string]$File = ""     # request file for -Do request
)
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$ea = Join-Path $root ".venv\Scripts\engagent.exe"
$Host.UI.RawUI.WindowTitle = "EngineeringAgent"

function Pause-Key { Write-Host ""; Read-Host "Press Enter to go back to the menu" | Out-Null }

function Ensure-Installed {
    if (Test-Path $ea) { return $true }
    Write-Host "First start: installing EngineeringAgent (5 to 10 minutes, only once) ..." -ForegroundColor Cyan
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "setup.ps1")
    return (Test-Path $ea)
}

function Open-Latest-Job {
    $jobs = Join-Path $root "jobs"
    $latest = Get-ChildItem $jobs -Directory -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
    if ($latest) {
        Write-Host "Opening $($latest.FullName)" -ForegroundColor Green
        Invoke-Item $latest.FullName
        $pdf = Join-Path $latest.FullName "report.pdf"
        if (Test-Path $pdf) { Invoke-Item $pdf }
    }
}

function Get-Units { try { (& $ea units --json | ConvertFrom-Json).units } catch { "metric" } }

function Setup-AI {
    Write-Host ""
    Write-Host "Which free AI should turn your words into models and analyses?" -ForegroundColor Cyan
    Write-Host "  1  GitHub Models  - free with your GitHub account (needs a token, 2 minutes)"
    Write-Host "  2  Ollama         - runs on this PC, offline, private (large download, 16 GB RAM recommended)"
    Write-Host "  3  Google Gemini  - free API key from Google AI Studio"
    $c = Read-Host "Choose 1, 2 or 3"
    if ($c -eq "1") {
        Write-Host "A browser page opens. Create a fine-grained token: any name, expiry as you like,"
        Write-Host "and under 'Account permissions' set 'Models' to 'Read-only'. Copy the token."
        Start-Process "https://github.com/settings/personal-access-tokens/new"
        $tok = Read-Host "Paste the token here"
        if ($tok) {
            [Environment]::SetEnvironmentVariable("ENGAGENT_LLM_KEY", $tok.Trim(), "User")
            [Environment]::SetEnvironmentVariable("ENGAGENT_LLM_URL", "https://models.github.ai/inference/chat/completions", "User")
            [Environment]::SetEnvironmentVariable("ENGAGENT_LLM_MODEL", "openai/gpt-4.1", "User")
        }
    } elseif ($c -eq "2") {
        if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
            Write-Host "Installing Ollama ..."
            winget install --id Ollama.Ollama -e --silent --accept-package-agreements --accept-source-agreements
            $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
        }
        $model = Read-Host "Model to use (Enter for qwen2.5-coder:14b; use qwen2.5-coder:7b on a smaller PC)"
        if (-not $model) { $model = "qwen2.5-coder:14b" }
        Write-Host "Downloading $model (several GB, once) ..."
        & ollama pull $model
        [Environment]::SetEnvironmentVariable("ENGAGENT_LLM_URL", "http://localhost:11434/v1/chat/completions", "User")
        [Environment]::SetEnvironmentVariable("ENGAGENT_LLM_MODEL", $model, "User")
        [Environment]::SetEnvironmentVariable("ENGAGENT_LLM_KEY", $null, "User")
    } elseif ($c -eq "3") {
        Write-Host "A browser page opens: sign in and click 'Create API key'. Copy the key."
        Start-Process "https://aistudio.google.com/apikey"
        $key = Read-Host "Paste the key here"
        if ($key) {
            [Environment]::SetEnvironmentVariable("ENGAGENT_LLM_KEY", $key.Trim(), "User")
            [Environment]::SetEnvironmentVariable("ENGAGENT_LLM_URL", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "User")
            [Environment]::SetEnvironmentVariable("ENGAGENT_LLM_MODEL", "gemini-2.5-flash", "User")
        }
    } else { return $false }
    foreach ($n in "ENGAGENT_LLM_KEY", "ENGAGENT_LLM_URL", "ENGAGENT_LLM_MODEL") {
        Set-Item -Path "Env:$n" -Value ([Environment]::GetEnvironmentVariable($n, "User"))
    }
    Write-Host "Saved for your Windows account (not in the project folder)." -ForegroundColor Green
    return $true
}

function Test-Ollama {
    try { Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 2 | Out-Null; return $true } catch { return $false }
}

function Ask-PlainEnglish {
    $configured = [Environment]::GetEnvironmentVariable("ENGAGENT_LLM_URL", "User") -or $env:ENGAGENT_LLM_URL -or $env:ENGAGENT_LLM_KEY -or (Test-Ollama)
    if (-not $configured) { if (-not (Setup-AI)) { return } }
    Write-Host ""
    Write-Host "Describe what you need, with dimensions and units. For an analysis also say the material," -ForegroundColor Cyan
    Write-Host "where it is held and the load. Example:" -ForegroundColor Cyan
    Write-Host "  Aluminium L-bracket, 60 mm legs, 40 wide, 6 thick, bolted through the base holes, 300 N pulling the upright sideways. Safety factor 2?" -ForegroundColor DarkGray
    $text = Read-Host "`nYou"
    if (-not $text) { return }
    & $ea ask $text
    if ($LASTEXITCODE -eq 0) { Open-Latest-Job }
}

function Run-Pasted {
    Write-Host "Paste the chatbot's whole reply below, then type END on its own line and press Enter." -ForegroundColor Cyan
    $lines = @()
    while ($true) { $l = Read-Host; if ($l -eq "END") { break }; $lines += $l }
    $f = Join-Path $env:TEMP "engagent-request.txt"
    $lines -join "`n" | Set-Content -Path $f -Encoding UTF8
    & $ea request $f
    Open-Latest-Job
}

if (-not (Ensure-Installed)) {
    Write-Host "Setup did not finish. Scroll up for the message, or ask for help with it." -ForegroundColor Red
    if (-not $Do) { Read-Host "Press Enter to close" }
    exit 1
}

if ($Do) {                                   # one action, no menu (used by CI and shortcuts)
    switch ($Do) {
        "prompt"  { & $ea prompt; exit $LASTEXITCODE }
        "request" { & $ea request $File; exit $LASTEXITCODE }
        "units"   { $u = Get-Units; if ($u -eq "metric") { & $ea units imperial } else { & $ea units metric }; exit $LASTEXITCODE }
        "doctor"  { & $ea doctor --full; exit $LASTEXITCODE }
        default   { Write-Host "unknown action $Do (prompt, request, units, doctor)"; exit 2 }
    }
}

while ($true) {
    Clear-Host
    $units = Get-Units
    Write-Host "  EngineeringAgent  -  CAD, 3D printing and FEA from plain English" -ForegroundColor Cyan
    Write-Host "  ---------------------------------------------------------------"
    Write-Host "  1  Describe what you need in plain English (free AI)"
    Write-Host "  2  Open Claude Code here (best results; needs a Claude subscription)"
    Write-Host "  3  Copy the chatbot prompt (for ChatGPT, Gemini, Claude.ai, Copilot ...)"
    Write-Host "  4  Run a reply pasted from a chatbot"
    Write-Host "  5  Open my results (jobs folder)"
    Write-Host "  6  Units: $units  (switch)"
    Write-Host "  7  Change the free AI used by option 1"
    Write-Host "  8  Check / repair the installation"
    Write-Host "  9  Update EngineeringAgent"
    Write-Host "  0  Exit"
    $c = Read-Host "`nChoose"
    switch ($c) {
        "1" { Ask-PlainEnglish; Pause-Key }
        "2" {
            if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
                Write-Host "Installing Claude Code ..."
                Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression
                $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
            }
            Write-Host "Type what you need, e.g. 'Design a printable PETG phone stand'. Type /exit to come back."
            & claude
        }
        "3" {
            & $ea prompt | Set-Clipboard
            Write-Host "Copied. Paste it as the first message (or the custom instructions) of any chatbot," -ForegroundColor Green
            Write-Host "then describe your part. Bring the reply back with option 4."
            Pause-Key
        }
        "4" { Run-Pasted; Pause-Key }
        "5" { New-Item -ItemType Directory -Force (Join-Path $root "jobs") | Out-Null; Invoke-Item (Join-Path $root "jobs") }
        "6" { if ($units -eq "metric") { & $ea units imperial } else { & $ea units metric }; Pause-Key }
        "7" { Setup-AI | Out-Null; Pause-Key }
        "8" { & $ea doctor --full; Pause-Key }
        "9" {
            if (Get-Command git -ErrorAction SilentlyContinue) { git pull; & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "setup.ps1") -NoShortcut }
            else { Write-Host "Download the latest ZIP from GitHub (Code > Download ZIP) and extract it over this folder." }
            Pause-Key
        }
        "0" { exit 0 }
    }
}
