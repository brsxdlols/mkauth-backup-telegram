#!/bin/bash
set -euo pipefail
if [ "$(id -u)" != 0 ]; then echo 'Execute o instalador como root.' >&2; exit 1; fi
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
for cmd in python3 php sudo visudo bzip2 timeout; do
 command -v "$cmd" >/dev/null || { echo "Dependência ausente: $cmd" >&2; exit 1; }
done
php -r 'foreach(["curl","json","mysqli","posix"] as $m)if(!extension_loaded($m)){fwrite(STDERR,"Extensão PHP ausente: $m\n");exit(1);}if(PHP_VERSION_ID<80000)exit(1);'
python3 "$HERE/installer.py" "$@"
