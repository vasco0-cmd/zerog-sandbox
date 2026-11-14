#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1

echo "=============================================================="
echo "       Starting ZeroG-Sandbox Local Interactive Demo          "
echo "=============================================================="
echo ""

if command -v python3 >/dev/null 2>&1; then
    echo "[ZeroG] Launching Web UI with 'python3'..."
    python3 -m zerog_sandbox.cli ui --repo "${SCRIPT_DIR}/examples/sample_repo" --port 8484
elif command -v python >/dev/null 2>&1; then
    echo "[ZeroG] Launching Web UI with 'python'..."
    python -m zerog_sandbox.cli ui --repo "${SCRIPT_DIR}/examples/sample_repo" --port 8484
else
    echo "[ERROR] Python 3 was not found in your PATH."
    echo "Please install Python 3.9+ from https://python.org"
    exit 1
fi
