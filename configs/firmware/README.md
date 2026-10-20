# Raspberry Pi Bluetooth firmware

`brcm/BCM4345C0.hcd` is the UART Bluetooth RAM patch for the Raspberry Pi 4's
onboard BCM4345C0 controller. Fedora's `brcmfmac-firmware` package supplies the
separate Wi-Fi firmware and did not provide this Bluetooth file on pi1.

- Source: [RPi-Distro/bluez-firmware](https://github.com/RPi-Distro/bluez-firmware/blob/cdf61dc691a49ff01a124752bd04194907f0f9cd/debian/firmware/broadcom/BCM4345C0.hcd)
- Source commit: `cdf61dc691a49ff01a124752bd04194907f0f9cd`
- Size: 63,806 bytes
- SHA-256: `51c45e77ddad91a19e96dc8fb75295b2087c279940df2634b23baf71b6dea42c`
- License: [LICENSE.cypress](LICENSE.cypress), extracted without text changes
  from the Cypress license stanza in the same commit's
  [Debian copyright file](https://github.com/RPi-Distro/bluez-firmware/blob/cdf61dc691a49ff01a124752bd04194907f0f9cd/debian/copyright).

`Containerfile` installs the firmware at `/usr/lib/firmware/brcm/BCM4345C0.hcd`
and its license under `/usr/share/licenses/rpi-bluez-firmware/`. The normal
bootc build's `tests/verify_image.py` checks the firmware digest inside the
finished image and requires the license. Changes under `configs/` already
trigger that workflow.

A temporary load on pi1 on 2026-10-20 changed the controller from build 0000
with placeholder address `AA:AA:AA:AA:AA:AA` to build 0382 with its real
address. The kernel reported `BCM4345C0 'brcm/BCM4345C0.hcd' Patch`. The Pi
accepted BLE connection commands afterward, but the VARMBLIXT lamp still
failed link establishment with status `0x3e`, including a direct BlueZ test.
This firmware fixes host initialization; it does not yet fix lamp commissioning.

After deploying and booting the new image, verify the kernel reports the
patch and build 0382, and check `sudo btmgmt info` for a real controller
address. The live `/run/matter-bluetooth-firmware` workaround is volatile;
the image uses the standard firmware search path without that override.
