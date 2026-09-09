#!/usr/bin/env bash
# set up the venv and give the api a run to serve
set -euo pipefail

cd "$(dirname "$0")/.."

# the image has python 3.12 but not the venv module
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3.12-venv
fi

# project venv (.venv is gitignored)
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip -q

# pipeline deps, the api extras, and pytest
.venv/bin/pip install -q -r requirements.txt -r requirements-api.txt pytest

# geopandas is optional: without it the pipeline just skips the map
.venv/bin/pip install -q geopandas \
  || echo "geopandas unavailable; the pipeline will skip the choropleth map"

# seed the sqlite store so the api has something on first boot. the pipeline
# also rewrites the tracked outputs, so put those back afterwards.
.venv/bin/python pipeline.py >/dev/null 2>&1 || true
git checkout -- docs/data/index.json outputs 2>/dev/null || true
