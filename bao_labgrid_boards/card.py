"""
Copyright (c) Bao Project and Contributors. All rights reserved

SPDX-License-Identifier: Apache-2.0

SD card images for boards that boot from one: the board's firmware at the
raw offsets its boot ROM expects, and one ext4 partition holding the
caller's payload. The layout is data:

    size: 48M                    # of the image
    raw:                         # firmware files at fixed offsets, in KiB
      FSBL.bin: 1536
    partition:
      start: 12288               # KiB
      size: 32M
      label: bootfs
      files: [boot.scr]          # firmware files copied into it
      payload: bao.itb           # the name the payload gets in it

Needs mke2fs, sgdisk and dd on the machine that builds the image.
"""

import os
import shutil
import subprocess
import tempfile

UNITS = {"K": 1, "M": 1024, "G": 1024 * 1024}


def kib(value):
    """A size such as 1536, "32M" or "1G", in KiB."""
    text = str(value)
    return int(text[:-1]) * UNITS[text[-1]] if text[-1] in UNITS else int(text)


def _run(*command):
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)


def build(layout, payload, firmware, out):
    """Write the card image for a payload to out.

    Args:
        layout (dict): the card layout, as above
        payload (str): the file the board's boot script loads
        firmware (str): directory with the files the layout names
        out (str): the image to write
    """
    part = layout["partition"]
    label = part.get("label", "boot")
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "root")
        os.mkdir(root)
        shutil.copy(payload, os.path.join(root, part["payload"]))
        for name in part.get("files") or []:
            shutil.copy(os.path.join(firmware, name), root)
        filesystem = os.path.join(tmp, "fs.ext4")
        _run("mke2fs", "-q", "-t", "ext4", "-L", label, "-d", root, filesystem, f"{kib(part['size'])}K")
        with open(out, "wb") as image:
            image.truncate(kib(layout["size"]) * 1024)
        first = kib(part["start"]) * 2
        last = first + kib(part["size"]) * 2 - 1
        _run("sgdisk", "--clear", "-n", f"1:{first}:{last}", "-c", f"1:{label}", out)

        def put(path, at):
            _run("dd", f"if={path}", f"of={out}", "bs=1024", f"seek={at}", "conv=notrunc", "status=none")

        for name, at in (layout.get("raw") or {}).items():
            put(os.path.join(firmware, name), kib(at))
        put(filesystem, kib(part["start"]))
    return out
