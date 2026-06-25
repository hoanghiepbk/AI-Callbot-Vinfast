#Requires -Version 5.1
# scripts/setup.ps1 — Phase 1 skeleton: create venv, install contract-layer deps, copy .env.
# Run from any directory: .\scripts\setup.ps1
# Phase 2 TODO: add PhoWhisper-CT2 and Piper model-download steps here.

Push-Location "$PSScriptRoot\.."
try {
    # ---- Python version check ----
    $python = $null
    foreach ($candidate in @("python3.11", "python3", "python")) {
        try {
            $ver = & $candidate --version 2>&1
            if ($ver -match "Python 3\.(\d+)") {
                $minor = [int]$Matches[1]
                if ($minor -ge 11) {
                    $python = $candidate
                    break
                }
            }
        } catch {}
    }

    if (-not $python) {
        Write-Host "ERROR: Python 3.11+ not found. Install it from https://python.org and re-run." -ForegroundColor Red
        exit 1
    }

    Write-Host "Found: $(&$python --version)" -ForegroundColor Green

    # ---- Create .venv if missing ----
    if (-not (Test-Path ".venv")) {
        Write-Host "Creating .venv ..." -ForegroundColor Yellow
        & $python -m venv .venv
    } else {
        Write-Host ".venv already exists — skipping creation." -ForegroundColor Green
    }

    # ---- Upgrade pip ----
    Write-Host "Upgrading pip ..." -ForegroundColor Yellow
    & .venv\Scripts\python.exe -m pip install --upgrade pip --quiet

    # ---- Install contract-layer deps ----
    Write-Host "Installing requirements.txt (contract-layer deps) ..." -ForegroundColor Yellow
    & .venv\Scripts\python.exe -m pip install -r requirements.txt

    # ---- Copy .env.example -> .env if missing ----
    if (-not (Test-Path ".env")) {
        Copy-Item ".env.example" ".env"
        Write-Host "Copied .env.example -> .env. Fill in OLLAMA_HOST and model names before running." -ForegroundColor Yellow
    } else {
        Write-Host ".env already exists — skipping copy." -ForegroundColor Green
    }

    # TODO(phase-2): Download PhoWhisper-CT2 weights and Piper binary + voice model here.
    # Example: scripts\download_models.ps1

    # ---- Next steps ----
    Write-Host ""
    Write-Host "=== Next steps ===" -ForegroundColor Green
    Write-Host "  1. Edit .env — set OLLAMA_HOST, LLM_MODEL, ASR_MODEL, JUDGE_MODEL, HF_TOKEN." -ForegroundColor Green
    Write-Host "  2. Activate venv: .venv\Scripts\Activate.ps1" -ForegroundColor Green
    Write-Host "  3. Run scaffold smoke-test: python -m pytest tests/ -q" -ForegroundColor Green
    Write-Host "  4. Run text mode (after Track A engine lands): python -m callbot --text" -ForegroundColor Green
    Write-Host "  NOTE: Model downloads (PhoWhisper, Piper) will be added in Phase 2." -ForegroundColor Yellow
    Write-Host "=== Setup complete ===" -ForegroundColor Green

} finally {
    Pop-Location
}
