# Patched application images

The ARM64 derivatives in `images/` retain the pinned upstream application versions, startup commands, ports, data mounts and runtime users. They update OS packages and vulnerable runtime dependencies so the existing application security gate can pass without exceptions or ignored findings.

| Image | Changes |
| --- | --- |
| Home Assistant | Alpine updates; rebuild the existing go2rtc 1.9.14 and tempio 2024.11.2 sources using Go 1.27.2; remove unused Nexity-only `warrant-lite` and its unpatched `python-jose` dependency |
| OTBR | Debian updates; rebuild the existing tempio source using Go 1.27.2 |
| Matter | Debian updates; replace affected npm packages with published fixes |
| Papra | Debian updates; replace affected npm packages with published fixes; rebuild esbuild 0.18.20 and 0.25.10 with Go 1.27.2; preserve `nonroot` |
| API broker | Alpine updates, including patched PCRE2; preserve HAProxy 3.2 and the restricted API configuration |

Nexity login support is unavailable in the Home Assistant derivative until its upstream dependency has a reviewed fix. The Pi does not have the Overkiz/Nexity integration enabled. The image still runs `uv pip check`; enabled Home Assistant integrations and core startup must also be validated before deployment.

`Build patched application images` publishes ARM64 artifacts under `ghcr.io/jhoogstraat/homelab:<app>-sha-<commit>`. These staging tags are not deployed automatically. Resolve and scan each exact digest, run compatibility checks, then update its Quadlet pin in a reviewed change. The normal host build and application scan must pass before merge. The scan still rejects unpinned images, scanner errors, critical findings, and any HIGH API-broker finding.

`images/patch-node.py` installs the fixed versions through npm and replaces the existing package directories while keeping pnpm/npm paths intact. New dependencies remain nested inside their package. Regression tests cover npm metadata, module links, and retained native esbuild copies. The esbuild patch replaces every native copy, including pnpm hardlinks, while keeping both original API versions.

Retain application data backups and previous pinned images when deploying a derivative. An image rollback does not undo database migrations; these recipes do not change the application versions or migration commands.
