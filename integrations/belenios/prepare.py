# SPDX-License-Identifier: GPL-3.0-only
"""Unpack a pinned Debian amd64 Belenios executable and loader in a new directory."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
from urllib.error import URLError
from urllib.request import urlopen

MIRRORS = ("https://deb.debian.org/debian/",
           "https://snapshot.debian.org/archive/debian/20261118T200719Z/")
TOOL_SHA256 = "ed25763c359b1c4a513b5f7e6c5ffe454ac6fe21cb24b41f4164613578984812"


def download(package):
    for mirror in MIRRORS:
        try:
            with urlopen(mirror + package["path"], timeout=30) as response:
                data = response.read(package["size"] + 1)
        except URLError:
            continue
        if len(data) != package["size"] or hashlib.sha256(data).hexdigest() != package["sha256"]:
            raise ValueError("Debian package digest or size differs: " + package["path"])
        return data
    raise OSError("Debian package unavailable: " + package["path"])


def prepare(target):
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ValueError("this package set requires Linux x86-64")
    packages = json.loads(Path(__file__).with_name("debian-amd64.json").read_text())
    target.mkdir(mode=0o700)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            deb = Path(tmp) / "package.deb"
            for package in packages:
                deb.write_bytes(download(package))
                subprocess.run(["dpkg-deb", "-x", deb, target / "root"], check=True)
        binary = target / "root/usr/bin/belenios-tool"
        if hashlib.sha256(binary.read_bytes()).hexdigest() != TOOL_SHA256:
            raise ValueError("unexpected native executable digest")
        wrapper = target / "belenios-tool"
        wrapper.write_text(
            '#!/bin/sh\nset -eu\n'
            'root=$(dirname "$(readlink -f "$0")")/root/usr\n'
            'lib="$root/lib/x86_64-linux-gnu"\n'
            'exec "$lib/ld-linux-x86-64.so.2" --inhibit-cache --library-path "$lib" '
            '"$root/bin/belenios-tool" "$@"\n')
        wrapper.chmod(0o700)
        subprocess.run([wrapper.resolve(), "--version"], check=True)
    except BaseException:
        shutil.rmtree(target)
        raise
    return wrapper


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("new_directory", type=Path)
    args = parser.parse_args()
    print(prepare(args.new_directory))
