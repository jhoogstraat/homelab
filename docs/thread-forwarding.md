# LAN access to the Thread mesh

On 2026-10-21, the Pi retained all 16 Matter nodes with the same 15 online,
but LAN clients could not reach a known working Thread bulb through it.
The Mac had already learned the Thread route through the Pi. A Pi-local
ping to that bulb succeeded, while a LAN UDP probe to port 5540 was rejected:

```text
filter_FWD_public_REJECT: IN=end0 OUT=wpan0 ... PROTO=UDP ... DPT=5540
```

`wpan0` had no explicit firewalld zone assignment. It fell back to the public
zone for filtering, but its name was absent from that zone's allowed
intra-zone forwarding destinations. The OTBR accept chain ran before
firewalld and did not override the later rejection.

A bounded runtime test explicitly added `wpan0` to the existing public
zone. The same LAN probe then appeared on both `end0` and `wpan0`. At
11:43:10 CEST, an ICMPv6 echo test also completed the full path:

```text
end0  In   LAN -> existing Thread bulb: echo request
wpan0 Out  LAN -> existing Thread bulb: echo request
wpan0 In   existing Thread bulb -> LAN: echo reply
end0  Out  existing Thread bulb -> LAN: echo reply
```

Both temporary tests removed the interface assignment afterward. They did
not change pairings, Thread credentials, the Bluetooth backend, or service
state. This proves a forwarding defect in the iPhone commissioning path;
the lamp still needs an actual iPhone commissioning retry after repair.

The repair is explicit public-zone membership for `wpan0`:

```sh
sudo firewall-cmd --permanent --zone=public --add-interface=wpan0
sudo firewall-cmd --zone=public --add-interface=wpan0
```

This enables forwarding from other interfaces in that zone, including the
Ethernet LAN, into the entire Thread mesh. It is not restricted to the lamp
or Matter port. The existing public zone already permits forwarding back
to Ethernet. Host input filtering remains the same public-zone policy.
No firewall reload or application restart is required.

The `scripts/build-host` change packages the same interface
assignment into bootc. `tests/verify_image.py` checks membership and enabled
intra-zone forwarding inside the built image. Local validation passed 46
tests with two platform-dependent skips, plus Bash syntax and diff checks.

The user explicitly approved interface-wide LAN-to-Thread forwarding and
bootc publication after automatic approval review required clarification of
that scope. The repair was applied on pi1 at approximately 12:02 CEST on
2026-10-21, at runtime and in permanent firewalld configuration, without a
reload or service restart. Recovery metadata and the previous public-zone
XML are stored in
`/var/lib/homelab/recovery/thread-forwarding-20261021-uyfo6xj3/`.
After application, the LAN-to-Thread echo check passed and all 16 saved
Matter nodes with the same 15 online nodes were verified. Lamp commissioning
through the iPhone remains to be tested.

To undo this specific repair after application, remove only the new
membership at runtime and in permanent configuration:

```sh
sudo firewall-cmd --zone=public --remove-interface=wpan0
sudo firewall-cmd --permanent --zone=public --remove-interface=wpan0
```

Also revert the corresponding build-host line to prevent a later image
from restoring it.
