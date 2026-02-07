$ErrorActionPreference = "Stop"

$coverageDir = Join-Path (Get-Location) ".pytest_tmp\\coverage"
New-Item -ItemType Directory -Force $coverageDir | Out-Null

# Use a writable, local coverage file to avoid locked .coverage issues on Windows.
$env:COVERAGE_FILE = Join-Path $coverageDir ".coverage.local"

python -m coverage erase
python -m coverage run --source=src -m pytest --basetemp=.pytest_tmp
python -m coverage report -m
