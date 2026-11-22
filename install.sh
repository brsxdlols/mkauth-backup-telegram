#!/bin/bash
set -euo pipefail
if [ "$(id -u)" != 0 ]; then echo 'Execute o instalador como root.' >&2; exit 1; fi
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
for cmd in python3 sudo visudo bzip2 timeout; do
 command -v "$cmd" >/dev/null || { echo "Dependência ausente: $cmd" >&2; exit 1; }
done
python3 "$HERE/installer.py" "$@"
