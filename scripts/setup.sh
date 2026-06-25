#!/usr/bin/env bash
# scripts/setup.sh — Phase 1 skeleton: create venv, install contract-layer deps, copy .env.
# Run from any directory: bash scripts/setup.sh
# Phase 2 TODO: add PhoWhisper-CT2 and Piper model-download steps here.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# ---- Python version check ----
PYTHON=""
for candidate in python3.11 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        VER_OUT=$("$candidate" --version 2>&1) || continue
        VER=$(echo "$VER_OUT" | grep -oE '[0-9]+\.[0-9]+' | head -1) || continue
        [ -z "$VER" ] && continue
        MAJOR=$(echo "$VER" | cut -d. -f1)
        MINOR=$(echo "$VER" | cut -d. -f2)
        if [ "${MAJOR:-0}" -ge 3 ] && [ "${MINOR:-0}" -ge 11 ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.11+ not found. Install it from https://python.org and re-run."
    exit 1
fi

echo "Found: $($PYTHON --version 2>&1)"

# ---- Create .venv if missing ----
if [ ! -d ".venv" ]; then
    echo "Creating .venv ..."
    "$PYTHON" -m venv .venv
else
    echo ".venv already exists — skipping creation."
fi

# ---- Locate activation script (POSIX: bin/activate; Windows Git Bash: Scripts/activate) ----
if [ -f ".venv/bin/activate" ]; then
    ACTIVATE=".venv/bin/activate"
elif [ -f ".venv/Scripts/activate" ]; then
    ACTIVATE=".venv/Scripts/activate"
else
    echo "ERROR: could not locate .venv activation script."
    exit 1
fi

# ---- Activate and upgrade pip ----
# shellcheck source=/dev/null
source "$ACTIVATE"
echo "Upgrading pip ..."
python -m pip install --upgrade pip --quiet

# ---- Install contract-layer deps ----
echo "Installing requirements.txt (contract-layer deps) ..."
python -m pip install -r requirements.txt

# ---- Copy .env.example -> .env if missing ----
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Copied .env.example -> .env. Fill in OLLAMA_HOST and model names before running."
else
    echo ".env already exists — skipping copy."
fi

# TODO(phase-2): Download PhoWhisper-CT2 weights and Piper binary + voice model here.
# Example: bash scripts/download_models.sh

# ---- Next steps ----
echo ""
echo "=== Next steps ==="
echo "  1. Edit .env — set OLLAMA_HOST, LLM_MODEL, ASR_MODEL, JUDGE_MODEL, HF_TOKEN."
echo "  2. Activate venv: source $ACTIVATE"
echo "  3. Run scaffold smoke-test: python -m pytest tests/ -q"
echo "  4. Run text mode (after Track A engine lands): python -m callbot --text"
echo "  NOTE: Model downloads (PhoWhisper, Piper) will be added in Phase 2."
echo "=== Setup complete ==="
