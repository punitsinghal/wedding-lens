#!/usr/bin/env bash
# PostToolUse hook — lint TypeScript/TSX files after Edit/Write
# Advisory only — never blocks. Fails open if eslint is not available.

set +e

input=$(cat)
file=$(printf '%s' "$input" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('tool_input', {}).get('file_path') or d.get('tool_response', {}).get('filePath') or '')" 2>/dev/null || echo "")

[ -z "$file" ] && exit 0

case "$file" in
  *.ts|*.tsx) ;;
  *) exit 0 ;;
esac

repo=""
case "$file" in
  /projects/wedding-lens/frontend/*) repo=/projects/wedding-lens/frontend ;;
esac

[ -z "$repo" ] && exit 0

# Locate eslint: repo-local first, then PATH
eslint_bin=""
if [ -x "$repo/node_modules/.bin/eslint" ]; then
  eslint_bin="$repo/node_modules/.bin/eslint"
elif command -v eslint >/dev/null 2>&1; then
  eslint_bin="eslint"
else
  exit 0
fi

cd "$repo" || exit 0
output=$("$eslint_bin" --max-warnings 0 -- "$file" 2>&1)
status=$?
if [ $status -ne 0 ]; then
  echo "[lint-ts] $file" >&2
  echo "$output" >&2
fi

exit 0
