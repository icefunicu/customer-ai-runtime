#!/usr/bin/env bash
set -euo pipefail

python -m compileall -q src tests

python -m ruff check .
python -m ruff format --check .

python -m pytest

