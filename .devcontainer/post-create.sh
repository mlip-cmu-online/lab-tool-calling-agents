#!/usr/bin/env bash
set -euo pipefail

python -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ./python/mcp_airline -e ./python/agent
.venv/bin/python scripts/smoke_tools_list.py
