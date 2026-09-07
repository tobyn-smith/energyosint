#!/usr/bin/env bash
# Idempotent development-environment setup for the Grid Resilience Exposure Index.
# Refreshes the project virtualenv and seeds the API's local database.
set -euo pipefail

cd "$(dirname "$0")/.."

# The default image ships Python 3.12 but not the venv module; add it once.
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3.12-venv
fi

# Project virtualenv (.venv is gitignored).
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip -q

# Core pipeline deps, the optional JSON API deps, and the test runner.
.venv/bin/pip install -q -r requirements.txt -r requirements-api.txt pytest

# geopandas unlocks the choropleth map and GeoPackage export. It is optional, so
# a failure here should not fail setup: the pipeline degrades to the bar chart.
.venv/bin/pip install -q geopandas \
  || echo "geopandas unavailable; the pipeline will skip the choropleth map"

# Seed the SQLite store (outputs/index.db, gitignored) so the API has a run to
# serve on first boot. The pipeline also rewrites the tracked sample outputs, so
# restore those afterwards to keep the committed real-data results pristine.
.venv/bin/python pipeline.py >/dev/null 2>&1 || true
git checkout -- docs/data/index.json outputs 2>/dev/null || true
