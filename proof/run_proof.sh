#!/usr/bin/env bash
# One-command proof runner for Git Bash / macOS / Linux.
set -e
cd "$(dirname "$0")/.."
python -m pip install -r requirements.txt scipy matplotlib statsmodels
python proof/run_proof.py
