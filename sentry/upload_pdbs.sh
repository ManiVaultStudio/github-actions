#!/usr/bin/env bash
set -euo pipefail
shopt -s globstar nullglob

SEARCH_ROOT="${1:-D:/.conan/}"    # override with first arg
# Sentry config must be available to sentry-cli (env or .sentryclirc)
: "${SENTRY_URL:?need SENTRY_URL env var (e.g. https://sentry.io/)}"

echo "Scanning under: $SEARCH_ROOT"

mapfile -t PDBS < <(compgen -G "$SEARCH_ROOT/**/*.pdb" || true)
mapfile -t DLLS < <(compgen -G "$SEARCH_ROOT/**/*.dll" || true)
mapfile -t EXES < <(compgen -G "$SEARCH_ROOT/**/*.exe" || true)
BINS=("${DLLS[@]}" "${EXES[@]}")

((${#PDBS[@]})) || { echo "No PDBs found."; exit 1; }

echo "Sample PDBs:"
printf '  %s\n' "${PDBS[@]:0:20}"

# ---------- try Debug-ID match first ----------
debug_id() {
  sentry-cli --url "$SENTRY_URL" difutil check "$1" 2>/dev/null \
    | tr -d '\r' \
    | awk -F': ' '/^[[:space:]]*Debug ID:/ {print $2; exit}'
}

declare -A PDB_BY_ID=()
for p in "${PDBS[@]}"; do
  base="${p##*/}"
  [[ "${base,,}" == vc*.pdb ]] && continue
  id="$(debug_id "$p" || true)"
  [[ -n "$id" ]] && [[ -z "${PDB_BY_ID[$id]:-}" ]] && PDB_BY_ID["$id"]="$p"
done

declare -A UP_PDB=()
declare -a UP_BIN=()

if ((${#PDB_BY_ID[@]})); then
  echo "Indexed ${#PDB_BY_ID[@]} PDB debug IDs. Matching binaries…"
  for b in "${BINS[@]}"; do
    id="$(debug_id "$b" || true)"
    [[ -z "$id" ]] && continue
    pdb="${PDB_BY_ID[$id]:-}"
    if [[ -n "$pdb" ]]; then
      UP_PDB["$pdb"]=1
      UP_BIN+=("$b")
      printf 'Match (debug-id):\n  BIN %s\n  PDB %s\n' "$b" "$pdb"
    fi
  done
fi

# ---------- fallback: stem match (prefer RelWithDebInfo) ----------
if ((${#UP_PDB[@]}==0)); then
  echo "No Debug-ID matches found. Falling back to stem matching…"

  # build index of PDBs by stem, prefer RelWithDebInfo paths
  declare -A PDB_BY_STEM=()
  for p in "${PDBS[@]}"; do
    base="${p##*/}"
    stem="${base%.*}"
    [[ "${base,,}" == vc*.pdb ]] && continue
    if [[ -z "${PDB_BY_STEM[${stem,,}]:-}" ]]; then
      PDB_BY_STEM["${stem,,}"]="$p"
    else
      # prefer RelWithDebInfo
      [[ "$p" == *"/RelWithDebInfo/"* || "$p" == *"\\RelWithDebInfo\\"* ]] && PDB_BY_STEM["${stem,,}"]="$p"
    fi
  done

  # match bins to pdb by same stem (case-insensitive), prefer RelWithDebInfo bins too
  for b in "${BINS[@]}"; do
    bbase="${b##*/}"
    bstem="${bbase%.*}"
    pdb="${PDB_BY_STEM[${bstem,,}]:-}"
    [[ -z "$pdb" ]] && continue
    # optionally prefer RelWithDebInfo bins: keep first, replace if RelWithDebInfo
    if [[ -z "${UP_PDB[$pdb]:-}" ]]; then
      UP_PDB["$pdb"]=1
      UP_BIN+=("$b")
    else
      # if we already have that pdb, swap in a RelWithDebInfo bin when found
      if [[ "$b" == *"/RelWithDebInfo/"* || "$b" == *"\\RelWithDebInfo\\"* ]]; then
        # replace last occurrence of this pdb's bin with this one (simple append is fine too)
        UP_BIN+=("$b")
      fi
    fi
    printf 'Match (stem):\n  BIN %s\n  PDB %s\n' "$b" "$pdb"
  done
fi

PDB_LIST=("${!UP_PDB[@]}")
if ((${#PDB_LIST[@]}==0)); then
  echo "No matching PDBs found."
  exit 1
fi

echo "Uploading ${#PDB_LIST[@]} PDB(s)…"
sentry-cli --url "$SENTRY_URL" debug-files upload --include-sources -t pdb "${PDB_LIST[@]}"

# Optional: also upload binaries (helps symcaches)
if ((${#UP_BIN[@]})); then
  echo "Uploading ${#UP_BIN[@]} binaries…"
  sentry-cli --url "$SENTRY_URL" debug-files upload "${UP_BIN[@]}"
fi

echo "Done."
