#!/bin/sh
set -eux
app=$1
image=$2
case "$app" in
  otbr)
    podman run --rm --network none --entrypoint /bin/sh "$image" -ec 'test -x /opt/otbr-stable/sbin/otbr-agent; test -x /opt/otbr-beta/sbin/otbr-agent; printf "{{ .value }}" >/tmp/template; printf "{\"value\":\"working\"}" | tempio -template /tmp/template | grep -x working'
    ;;
  papra)
    podman run --rm --network none --entrypoint /bin/sh "$image" -ec 'find /app/node_modules -type f -name esbuild -exec sh -c '\''for binary do if head -c4 "$binary" | grep -q ELF; then "$binary" --version; fi; done'\'' sh {} +; cd /app; node -e '\''const p = require("./package.json"); if (!p.scripts["start:with-migrations"]) process.exit(1)'\'''
    ;;
  trek)
    podman run --rm --network none --entrypoint /bin/sh "$image" -ec 'test ! -e /usr/local/bin/kitinerary-extractor; ! dpkg -s libxml2 >/dev/null 2>&1'
    ;;
  homeassistant)
    podman run --rm --network none --entrypoint /bin/sh "$image" -ec 'python3 -c "import authlib; assert authlib.__version__ == \"1.9.0\""'
    ;;
esac
