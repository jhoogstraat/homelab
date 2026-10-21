"""Check the security dependency patch against Home Assistant's runtime paths."""
import asyncio
from importlib.metadata import version
from io import BytesIO
from pathlib import Path
import subprocess

import homeassistant
from homeassistant.util.package import async_get_installed_packages, install_package
from PIL import Image, ImageOps

subprocess.run(["uv", "pip", "check"], check=True)
constraints = Path(homeassistant.__path__[0]) / "package_constraints.txt"
for package, expected in (("Pillow", "13.0.0"), ("uv", "0.13.4"),
                          ("certifi", "2026.10.19")):
    assert version(package) == expected, package
    assert install_package(f"{package}=={expected}", upgrade=False,
                           constraints=str(constraints), timeout=15), package
assert any(package["name"] == "homeassistant"
           for package in asyncio.run(async_get_installed_packages()))

for format in ("JPEG", "PNG", "GIF", "WEBP"):
    data = BytesIO()
    Image.new("RGB", (32, 24), "red").save(data, format=format)
    data.seek(0)
    with Image.open(data) as image:
        image.load()
        assert ImageOps.exif_transpose(image).resize((8, 6)).size == (8, 6)
print("Home Assistant dependency installer and image processing checks passed")
