#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python_bin="${PYTHON_BIN:-python3}"
"$python_bin" -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ required"'
"$python_bin" -m venv .venv
.venv/bin/python -m pip install -r requirements-runtime.txt
if [ ! -f config/app.local.json ]; then cp config/app.json config/app.local.json; fi
printf '%s\n' 'Runtime installed. Continue provisioning and application-login setup in docs/production-test.md.'
