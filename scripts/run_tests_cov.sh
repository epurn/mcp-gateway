#!/usr/bin/env bash
set -euo pipefail

coverage_dir=".pytest_tmp/coverage"
mkdir -p "$coverage_dir"

# Use a writable, local coverage file to avoid locked .coverage issues.
export COVERAGE_FILE="$coverage_dir/.coverage.local"

python -m coverage erase
python -m coverage run --source=src -m pytest --basetemp=.pytest_tmp
python -m coverage report -m
