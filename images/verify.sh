#!/bin/sh
set -eux
app=$1
image=$2
case "$app" in
  homeassistant)
    base=$(awk '/^FROM ghcr.io\/home-assistant\/home-assistant:/ {print $2; exit}' "images/$app/Containerfile")
    original=$(podman run --rm --network none --entrypoint python3 "$base" -c 'from homeassistant.const import __version__; print(__version__)')
    actual=$(podman run --rm --network none --entrypoint python3 "$image" -c 'from homeassistant.const import __version__; print(__version__)')
    test "$original" = "$actual"
    podman run --rm --network none --entrypoint python3 "$image" -c 'import homeassistant.core, homeassistant.auth, homeassistant.components.matter, homeassistant.components.go2rtc, homeassistant.components.thread'
    podman run --rm -i --network none --entrypoint python3 "$image" < images/homeassistant/verify.py
    ;;
  otbr)
    podman run --rm --network none --entrypoint /bin/sh "$image" -ec 'test -x /opt/otbr-stable/sbin/otbr-agent; test -x /opt/otbr-beta/sbin/otbr-agent; printf "{{ .value }}" >/tmp/template; printf "{\"value\":\"working\"}" | tempio -template /tmp/template | grep -x working'
    ;;
  papra)
    podman run --rm --network none --entrypoint /bin/sh "$image" -ec 'find /app/node_modules -type f -name esbuild -exec sh -c '\''for binary do if head -c4 "$binary" | grep -q ELF; then "$binary" --version; fi; done'\'' sh {} +; cd /app; node -e '\''const p = require("./package.json"); if (!p.scripts["start:with-migrations"]) process.exit(1)'\'''
    ;;
  socket-proxy)
    podman run --rm --network none --volume "$(pwd)/configs/environment/socket-proxy/haproxy.cfg:/usr/local/etc/haproxy/haproxy.cfg:ro" --entrypoint haproxy "$image" -c -f /usr/local/etc/haproxy/haproxy.cfg
    ;;
esac
