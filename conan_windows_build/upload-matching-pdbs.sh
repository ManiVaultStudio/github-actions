#!/usr/bin/env bash
set -euo pipefail
shopt -s globstar nullglob

# --- Config ---
SEARCH_ROOT="${1:-D:/.conan/}"      # override with first arg
: "${SENTRY_URL:?need SENTRY_URL env var (e.g. https://sentry.io/)}"
# Optionally rely on sentry-cli's default org/project config via auth

# --- Helpers ---
lower() { tr '[:upper:]' '[:lower:]'; }

# Extract GUID + Age from a PE (EXE/DLL) using dumpbin
bin_guid_age() {
  local bin="$1"
  # Need VS dev prompt / vcvars set so dumpbin is on PATH
  dumpbin /all "$bin" 2>/dev/null \
    | tr -d '\r' \
    | awk '/RSDS/ {print $2" "$3; exit}'
}

# Extract GUID + Age from a PDB using dia2dump (preferred) or llvm-pdbutil (fallback)
pdb_guid_age() {
  local pdb="$1"
  if command -v dia2dump >/dev/null 2>&1; then
    # dia2dump prints lines like: "Signature: <GUID>" and "Age: <N>"
    local sig age
    sig="$(dia2dump -all "$pdb" 2>/dev/null | tr -d '\r' | awk '/Signature:/ {print $2; exit}')"
    age="$(dia2dump -all "$pdb" 2>/dev/null | tr -d '\r' | awk '/Age:/ {print $2; exit}')"
    [[ -n "${sig:-}" && -n "${age:-}" ]] && { echo "$sig $age"; return 0; }
  fi
  if command -v llvm-pdbutil >/dev/null 2>&1; then
    # llvm-pdbutil dump -pdb-stream shows "Signature" and "Age"
    local sig age
    read -r sig age < <(llvm-pdbutil dump -pdb-stream "$pdb" 2>/dev/null \
        | tr -d '\r' \
        | awk '
            /Signature/ && $2 ~ /[0-9A-Fa-f-]+/ { g=$2 }
            /Age/ && $2 ~ /^[0-9]+$/ { a=$2 }
            END { if (g && a) print g, a }')
    [[ -n "${sig:-}" && -n "${age:-}" ]] && { echo "$sig $age"; return 0; }
  fi
  return 1
}

# --- Gather candidates ---
echo "Scanning under: $SEARCH_ROOT"
mapfile -t ALL_PDBS < <(compgen -G "$SEARCH_ROOT/**/*.pdb" || true)
mapfile -t ALL_BIN  < <(compgen -G "$SEARCH_ROOT/**/*.dll" ; compgen -G "$SEARCH_ROOT/**/*.exe" || true)

if ((${#ALL_BIN[@]}==0)); then
  echo "No EXE/DLLs found under $SEARCH_ROOT" >&2
fi
if ((${#ALL_PDBS[@]}==0)); then
  echo "No PDBs found under $SEARCH_ROOT" >&2
  exit 1
fi

echo "Sample PDBs:"
printf '  %s\n' "${ALL_PDBS[@]:0:20}"

# --- Index PDBs by GUID+Age (skip toolchain PDBs like vc143.pdb) ---
declare -A PDB_BY_KEY=()     # KEY = GUID|AGE  -> absolute PDB path
declare -A SEEN_HASH=()

for pdb in "${ALL_PDBS[@]}"; do
  base="$(basename "$pdb")"
  lb="$(echo "$base" | lower)"
  [[ "$lb" == vc*.pdb ]] && continue
  if ga="$(pdb_guid_age "$pdb")"; then
    guid="${ga%% *}"; age="${ga##* }"
    key="${guid}|${age}"
    # First one wins; prefer a RelWithDebInfo path if available
    if [[ -z "${PDB_BY_KEY[$key]:-}" ]]; then
      PDB_BY_KEY["$key"]="$pdb"
    else
      # Prefer a path containing RelWithDebInfo
      if [[ "$pdb" == *"/RelWithDebInfo/"* || "$pdb" == *"\\RelWithDebInfo\\"* ]]; then
        PDB_BY_KEY["$key"]="$pdb"
      fi
    fi
  fi
done

echo "Indexed ${#PDB_BY_KEY[@]} unique PDB signatures."

# --- For each binary, find matching PDB by GUID+Age ---
declare -A UPLOAD_PDB_SET=()
declare -a UPLOAD_BIN=()

for bin in "${ALL_BIN[@]}"; do
  if ga="$(bin_guid_age "$bin")"; then
    guid="${ga%% *}"; age="${ga##* }"
    key="${guid}|${age}"
    if pdb="${PDB_BY_KEY[$key]:-}"; then
      UPLOAD_PDB_SET["$pdb"]=1
      UPLOAD_BIN+=("$bin")
      printf 'Match: %s\n       %s\n' "$bin" "$pdb"
    else
      echo "No matching PDB for: $bin (GUID=$guid Age=$age)"
    fi
  else
    echo "No RSDS (GUID/Age) found in: $bin"
  fi
done

# Materialize the unique PDB list
UPLOAD_PDB=("${!UPLOAD_PDB_SET[@]}")

if ((${#UPLOAD_PDB[@]}==0)); then
  echo "No matching PDBs found for discovered binaries."
  exit 1
fi

echo "Will upload ${#UPLOAD_PDB[@]} PDB(s) and ${#UPLOAD_BIN[@]} binary(ies)."

# --- Upload ---
sentry-cli --url "$SENTRY_URL" debug-files upload \
  --include-sources \
  -t pdb \
  "${UPLOAD_PDB[@]}"

# Optional: also upload the binaries so Sentry can build symcaches faster
if ((${#UPLOAD_BIN[@]})); then
  sentry-cli --url "$SENTRY_URL" debug-files upload "${UPLOAD_BIN[@]}"
fi

echo "Done."
