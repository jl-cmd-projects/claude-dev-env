#!/bin/bash
set -euo pipefail
action=$1
shift
head_sha_for() {
  gh api "repos/$GITHUB_REPOSITORY/pulls/$1" -q .head.sha
}
case "$action" in
  open) gh api "repos/$GITHUB_REPOSITORY/check-runs" -f name=ai-review -f head_sha="$1" -f status=in_progress ;;
  open-for-pr) gh api "repos/$GITHUB_REPOSITORY/check-runs" -f name=ai-review -f head_sha="$(head_sha_for "$1")" -f status=in_progress ;;
  complete) gh api "repos/$GITHUB_REPOSITORY/check-runs" -f name=ai-review -f head_sha="$1" -f status=completed -f conclusion="$2" ;;
  complete-for-pr) gh api "repos/$GITHUB_REPOSITORY/check-runs" -f name=ai-review -f head_sha="$(head_sha_for "$1")" -f status=completed -f conclusion="$2" ;;
  *) echo "unknown action $action" >&2; exit 2 ;;
esac
