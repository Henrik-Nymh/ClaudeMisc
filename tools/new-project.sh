#!/usr/bin/env bash
# Scaffold a new project under projects/<name> with a README stub.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <project-name>" >&2
  exit 1
fi

name="$1"
if [[ ! "$name" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
  echo "error: project name must be kebab-case, e.g. my-project" >&2
  exit 1
fi

root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
dir="$root/projects/$name"

if [[ -e "$dir" ]]; then
  echo "error: $dir already exists" >&2
  exit 1
fi

mkdir -p "$dir"
cat > "$dir/README.md" <<EOF
# $name

**Status:** in progress · **Started:** $(date +%Y-%m-%d)

## What

TODO: one or two sentences on what this is and why it exists.

## Run

\`\`\`bash
TODO
\`\`\`

## Notes
EOF

echo "created projects/$name/README.md"
