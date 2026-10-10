"""Exercise the real HAProxy policy against an isolated fake Podman API."""
import json
from pathlib import Path
import subprocess
import sys
import uuid


def command(*args):
    return subprocess.run(["podman", *args], check=True, text=True,
                          stdout=subprocess.PIPE).stdout.strip()


image = sys.argv[1]
proxy_image = next(line.removeprefix("Image=").strip() for line in
                   (Path(__file__).resolve().parents[1] / "quadlets/socket-proxy.container").read_text().splitlines()
                   if line.startswith("Image="))
if len(sys.argv) > 2:
    proxy_image = sys.argv[2]
prefix = "homelab-audit-" + uuid.uuid4().hex[:12]
backend, proxy = prefix + "-backend", prefix + "-proxy"
fake_api = """
import http.server, socketserver
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Length', '2')
        self.end_headers()
        self.wfile.write(b'{}')
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()
    def log_message(self, *args): pass
socketserver.UnixStreamServer('/var/run/podman.sock', Handler).serve_forever()
"""
cases = [
    ("GET", "/_ping", 200), ("HEAD", "/_ping", 200),
    ("GET", "/v1.47/version", 200), ("GET", "/info", 200),
    ("GET", "/events?filters=%7B%7D", 200),
    ("GET", "/containers/json?all=1", 200),
    ("GET", "/v1.47/containers/abc123/json", 200),
    ("GET", "/containers/abc123/stats?stream=0", 200),
    ("POST", "/containers/create", 403),
    ("POST", "/containers/abc123/exec", 403),
    ("POST", "/containers/json", 403),
    ("DELETE", "/containers/abc123", 403),
    ("PUT", "/containers/abc123/archive", 403),
    ("GET", "/containers/abc123/archive?path=/", 403),
    ("GET", "/containers/abc123/logs", 403),
    ("GET", "/images/json", 403),
    ("GET", "/v5.0.0/libpod/containers/json", 403),
    ("GET", "/containers/../images/json", 403),
    ("GET", "/containers/abc123%2Farchive/json", 403),
    ("HEAD", "/containers/json", 403),
]
probe = """
import json, time, urllib.request, urllib.error
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
for attempt in range(30):
    try:
        opener.open('http://PROXY:2375/_ping', timeout=1).close()
        break
    except (OSError, urllib.error.URLError): time.sleep(1)
else: raise RuntimeError('Proxy did not start')
for method, path, expected in json.loads(CASES):
    request = urllib.request.Request('http://PROXY:2375' + path, method=method)
    try:
        with opener.open(request, timeout=3) as response: status = response.status
    except urllib.error.HTTPError as error: status = error.code
    assert status == expected, (method, path, status, expected)
print('Validated', len(json.loads(CASES)), 'API allow/deny cases')
""".replace("PROXY", proxy).replace("CASES", repr(json.dumps(cases)))

try:
    if len(sys.argv) < 3:
        command("pull", proxy_image)
    command("network", "create", "--internal", prefix)
    command("volume", "create", prefix)
    command("run", "-d", "--name", backend, "--network", prefix,
            "--volume", prefix + ":/var/run", "--entrypoint", "/usr/bin/python3",
            image, "-c", fake_api)
    command("create", "--name", proxy, "--network", prefix,
            "--volume", prefix + ":/var/run:ro", "--read-only",
            "--user", "0",
            "--cap-drop=ALL", "--security-opt=no-new-privileges", proxy_image)
    config = Path(__file__).resolve().parents[1] / "configs/environment/socket-proxy/haproxy.cfg"
    command("cp", str(config), proxy + ":/usr/local/etc/haproxy/haproxy.cfg")
    command("start", proxy)
    print(command("exec", backend, "/usr/bin/python3", "-c", probe))
except Exception:
    for name in (proxy, backend):
        subprocess.run(["podman", "logs", name], check=False)
    raise
finally:
    for name in (proxy, backend):
        subprocess.run(["podman", "rm", "-f", "--ignore", name], check=False,
                       stdout=subprocess.DEVNULL)
    subprocess.run(["podman", "volume", "rm", "-f", prefix], check=False,
                   stdout=subprocess.DEVNULL)
    subprocess.run(["podman", "network", "rm", prefix], check=False,
                   stdout=subprocess.DEVNULL)
