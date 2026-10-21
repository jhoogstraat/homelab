# Draft response to matterjs-server #333

For <https://github.com/matter-js/matterjs-server/issues/333>. Not posted.

---

Update: the VARMBLIXT now works with Matter Server 1.5.0, commissioned through the Home Assistant iPhone app.

On my Fedora bootc Pi 4, firewalld was blocking LAN → Thread traffic (`filter_FWD_public_REJECT: IN=end0 OUT=wpan0`). Pinging the bulb from the Pi worked; testing from another LAN device exposed the problem.

My LAN uses the `public` zone with intra-zone forwarding enabled. Assigning OTBR's interface to that same zone fixed it:

```sh
sudo firewall-cmd --zone=public --add-interface=wpan0
sudo firewall-cmd --permanent --zone=public --add-interface=wpan0
```

Use your own LAN zone/Thread interface. This allows forwarding into the entire Thread mesh.

With the Pi's existing Thread credentials synchronized to my iPhone 17, I added the reset lamp in Home Assistant: **Add Matter device → No, it's new**, using the original code. It joined the existing Thread network without an Apple TV or HomePod.

Separately, the onboard BCM4345C0 lacked its [firmware](https://github.com/RPi-Distro/bluez-firmware/blob/cdf61dc691a49ff01a124752bd04194907f0f9cd/debian/firmware/broadcom/BCM4345C0.hcd). Installing it restored controller initialization, but direct Pi BLE commissioning still failed with HCI `0x3e`, also reproducible through BlueZ alone. This confirms a working phone commissioning route, not a fix for the original direct-BLE failure.
