#!/usr/bin/env bash
set -euo pipefail
shopt -s globstar nullglob

# ---- Config ----
SEARCH_ROOT="${1:-D:/.conan/}"   # override with first arg
: "${SENTRY_URL:?need SENTRY_URL env var (e.g. https://sentry.io/)}"
# SENTRY_AUTH_TOKEN / SENTRY_ORG / SENTRY_PROJECT should be in env for sentry-cli

# ---- Helpers ----
# Extract Sentry Debug ID from any file (PE/PDB/etc) via sentry-cli.
# Works without dumpbin/dia2dump.
debug_id() {
  local f="$1"
  # Output format usually includes a line like "Debug ID: XXXXX"
  # We grep that and print the value.
  sentry-cli --url "$SENTRY_URL" difutil check "$f" 2>/dev/null \
    | tr -d '\r' \
    | awk -F': ' '/^[[:space:]]*Debug ID:/ {print $2; exit}'
}

echo "Scanning under: $SEARCH_ROOT"

mapfile -t PDBS < <(compgen -G "$SEARCH_ROOT/**/*.pdb" || true)
mapfile -t BINS < <(compgen -G "$SEARCH_ROOT/**/*.dll"; compgen -G "$SEARCH_ROOT/**/*.exe" || true)

((${#PDBS[@]})) || { echo "No PDBs found."; exit 1; }
((${#BINS[@]})) || echo "Warning: no EXE/DLLs found."

echo "Sample PDBs:"
printf '  %s\n' "${PDBS[@]:0:20}"

# ---- Index PDBs by Debug ID (skip toolchain vc*.pdb) ----
declare -A PDB_BY_ID=()
for p in "${PDBS[@]}"; do
  base="${p##*/}"
  [[ "${base,,}" == vc*.pdb ]] && continue
  id="$(debug_id "$p" || true)"
  [[ -n "$id" ]] && [[ -z "${PDB_BY_ID[$id]:-}" ]] && PDB_BY_ID["$id"]="$p"
done
echo "Indexed ${#PDB_BY_ID[@]} unique PDB debug IDs."

# ---- Match binaries to PDBs by Debug ID ----
declare -A UPLOAD_PDB_SET=()
declare -a UPLOAD_BIN=()

for b in "${BINS[@]}"; do
  id="$(debug_id "$b" || true)"
  if [[ -z "$id" ]]; then
    echo "No Debug ID in: $b"
    continue
  fi
  pdb="${PDB_BY_ID[$id]:-}"
  if [[ -n "$pdb" ]]; then
    UPLOAD_PDB_SET["$pdb"]=1
    UPLOAD_BIN+=("$b")
    printf 'Match:\n  BIN %s\n  PDB %s\n' "$b" "$pdb"
  else
    echo "No matching PDB for: $b (Debug ID $id)"
  fi
done

UPLOAD_PDB=("${!UPLOAD_PDB_SET[@]}")
((${#UPLOAD_PDB[@]})) || { echo "No matching PDBs found."; exit 1; }

echo "Uploading ${#UPLOAD_PDB[@]} PDB(s)…"
sentry-cli --url "$SENTRY_URL" debug-files upload --include-sources -t pdb "${UPLOAD_PDB[@]}"

# Optional: also upload the binaries (helps symcache building)
if ((${#UPLOAD_BIN[@]})); then
  echo "Uploading ${#UPLOAD_BIN[@]} binaries…"
  sentry-cli --url "$SENTRY_URL" debug-files upload "${UPLOAD_BIN[@]}"
fi

echo "Done."
