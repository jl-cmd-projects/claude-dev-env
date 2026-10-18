#!/bin/bash
set -euo pipefail

SKILL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_EXECUTABLE="$(command -v python3 || command -v python)"
export PYTHONPATH="${SKILL_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
exec "${PYTHON_EXECUTABLE}" "${SKILL_ROOT}/hooks/efficient_review_model_gate.py"
