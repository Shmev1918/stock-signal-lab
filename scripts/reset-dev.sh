#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' 'This will destroy local dev data and rebuild the schema.'
printf '%s' 'Type YES to continue: '

if [[ ! -t 0 ]]; then
  printf '\n' >&2
  printf '%s\n' '[reset-dev] ERROR: interactive confirmation required' >&2
  exit 1
fi

read -r confirm
if [[ "$confirm" != "YES" ]]; then
  printf '%s\n' 'Aborted.'
  exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
cd "$repo_root"

make reset-db
