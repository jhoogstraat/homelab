"""Verify that the public tunnel entrypoint exposes Vaultwarden but denies admin."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid


def command(*args):
    return subprocess.check_output(["podman", *args], text=True).strip()


host_image = sys.argv[1]
traefik_image = next(line.removeprefix("Image=") for line in
                     Path("quadlets/traefik.container").read_text().splitlines()
                     if line.startswith("Image="))
prefix = "homelab-routes-" + uuid.uuid4().hex[:12]
backend, proxy = prefix + "-backend", prefix + "-proxy"
cases = [("vault.hoogstraat.net", path, status) for path, status in [
    ("/", 200), ("/api/config", 200), ("/identity/connect/token", 200),
    ("/notifications/hub", 200), ("/admin", 403), ("/admin/", 403),
    ("/admin/config", 403), ("/%61dmin", 403), ("/admin%2Fconfig", 403),
]] + [("adguard.hoogstraat.net", "/", 404), ("ha.hoogstraat.de", "/", 404)]
probe = """
import http.client,json,time
for attempt in range(30):
    try:
        conn=http.client.HTTPConnection(PROXY,8080,timeout=2)
        conn.request('GET','/',headers={'Host':'vault.hoogstraat.net'})
        if conn.getresponse().status==200: break
    except OSError: pass
    time.sleep(1)
else: raise RuntimeError('Public router did not start')
for host,path,expected in json.loads(CASES):
    conn=http.client.HTTPConnection(PROXY,8080,timeout=2)
    conn.request('GET',path,headers={'Host':host,'X-Forwarded-For':'127.0.0.1'})
    status=conn.getresponse().status
    conn.close()
    assert status==expected,(host,path,status,expected)
print('Validated',len(json.loads(CASES)),'public-route cases')
for host in ('vault.hoogstraat.net', 'ha.hoogstraat.de'):
    conn=http.client.HTTPConnection(PROXY,8443,timeout=2)
    conn.request('GET','/',headers={'Host':host,'X-Forwarded-For':'192.168.0.10'})
    status=conn.getresponse().status
    conn.close()
    assert status==403,(host,status)
print('Validated LAN restriction against bridge sources and forged headers')
""".replace("PROXY", repr(proxy)).replace("CASES", repr(json.dumps(cases)))
try:
    command("network", "create", "--internal", prefix)
    command("run", "-d", "--name", backend, "--network", prefix,
            "--network-alias", "vaultwarden", "--entrypoint", "/usr/bin/python3",
            host_image, "-c",
            "import http.server; "
            "H=type('H',(http.server.BaseHTTPRequestHandler,),"
            "{'do_GET':lambda s:(s.send_response(200),s.end_headers(),s.wfile.write(b'{}'))}); "
            "http.server.HTTPServer(('0.0.0.0',80),H).serve_forever()")
    command("create", "--name", proxy, "--network", prefix, traefik_image,
            "--entrypoints.tunnel.address=:8080",
            "--entrypoints.tunnel.http.aliasHeadersStrategy=delete", "--entrypoints.https.address=:8443",
            "--entrypoints.https.http.middlewares=lan-only@file",
            "--providers.file.filename=/public-routes.yml", "--log.level=ERROR")
    # A fixture router exercises the actual LAN middleware without a Docker socket.
    config = Path("configs/environment/traefik/public-routes.yml").read_text().replace(
        "  routers:\n", "  routers:\n    lan-test:\n"
        "      rule: Host(`vault.hoogstraat.net`) || Host(`ha.hoogstraat.de`)\n"
        "      entryPoints: [https]\n      service: vault\n")
    with tempfile.TemporaryDirectory(prefix=prefix) as directory:
        fixture = Path(directory) / "routes.yml"
        fixture.write_text(config)
        command("cp", str(fixture), proxy + ":/public-routes.yml")
    command("start", proxy)
    print(command("exec", backend, "/usr/bin/python3", "-c", probe))
except Exception:
    subprocess.run(["podman", "logs", proxy], check=False)
    raise
finally:
    for name in (proxy, backend):
        subprocess.run(["podman", "rm", "-f", "--ignore", name], check=False,
                       stdout=subprocess.DEVNULL)
    subprocess.run(["podman", "network", "rm", prefix], check=False,
                   stdout=subprocess.DEVNULL)
