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
    podman run --rm --network none --entrypoint /bin/sh "$image" -ec 'test ! -e /usr/local/bin/kitinerary-extractor; ! dpkg -s libxml2 >/dev/null 2>&1; cd /app; node -e '\''if (require("proxy-addr/package.json").version !== "2.0.8" || JSON.parse(require("fs").readFileSync("node_modules/dompurify/package.json")).version !== "3.4.17") process.exit(1)'\'''
    ;;
  homeassistant)
    podman run --rm --network none --entrypoint /bin/sh "$image" -ec 'go2rtc --help >/dev/null; printf "{{ .value }}" >/tmp/template; printf "{\"value\":\"working\"}" | tempio -template /tmp/template | grep -x working; ! grep -rqE "Pillow==12\.3\.0|uv==0\.12\.23" /usr/src/homeassistant/homeassistant; python3 -c "import PIL, homeassistant.components.image_upload, homeassistant.components.go2rtc; assert PIL.__version__ == \"13.0.0\""'
    ;;
  socket-proxy)
    podman run --rm --network none --volume "$(pwd)/configs/environment/socket-proxy/haproxy.cfg:/usr/local/etc/haproxy/haproxy.cfg:ro" --entrypoint haproxy "$image" -c -f /usr/local/etc/haproxy/haproxy.cfg
    ;;
esac
