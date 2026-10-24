#!/bin/bash
set -euo pipefail
pull_request_number=$1
reviewer exec review \
  --model "${REVIEW_MODEL:?}" \
  --effort "${REVIEW_EFFORT:?}" \
  --pull-request "$pull_request_number" \
  --post-comments
