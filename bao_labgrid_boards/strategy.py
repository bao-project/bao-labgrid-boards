"""
Copyright (c) Bao Project and Contributors. All rights reserved

SPDX-License-Identifier: Apache-2.0

Boot strategies: how a kind of board gets from off to running the caller's
images, and back to off. A strategy binds the board's power, console and
loader drivers, so that whoever boots the board (a test framework, a lab's
command line) names the images and nothing else:

    strategy = target.get_strategy()
    strategy.boot([("bao.bin", "0x200000")], firmware="fw/")
    ...
    strategy.off()

After boot() the console driver is active and holds whatever the board has
printed since it started.
"""

import enum
import os
import tempfile
import time

import attr
from labgrid.binding import BindingState
from labgrid.factory import target_factory
from labgrid.strategy import Strategy

from . import card as sdcard


class Status(enum.Enum):
    unknown = 0
    off = 1
    running = 2


@attr.s(eq=False)
class BootStrategy(Strategy):
    """What the boot strategies share: the power cycle and the way back to off.

    Args:
        settle (float): seconds to wait after power on before touching the
            board, for a debugger powered from the board's own socket
    """
    settle = attr.ib(default=0.0, converter=float)
    status = attr.ib(default=Status.unknown)

    def boot(self, images, firmware=None):
        """Power cycle the board and start the images.

        Args:
            images (list): (path, address) pairs, as the board's loader takes them
            firmware (str): directory with the boot firmware, for loaders that need one
        """
        raise NotImplementedError

    def _stop_loader(self):
        # only a loader in use can have a session open; one powered from the
        # board's socket is not even reachable while the board is off
        loader = getattr(self, "loader", None)
        if (
            loader is not None
            and loader.state is BindingState.active
            and callable(getattr(loader, "stop", None))
        ):
            loader.stop()

    def _power_cycle(self):
        self._stop_loader()
        self.target.activate(self.power)  # pylint: disable=no-member
        self.power.cycle()  # pylint: disable=no-member
        time.sleep(self.settle)
        # before anything is loaded, so that the first output is not lost
        self.target.activate(self.console)  # pylint: disable=no-member
        self.status = Status.unknown

    def off(self):
        """End a debugger session left open and power the board off."""
        try:
            self._stop_loader()
        finally:
            self.target.activate(self.power)  # pylint: disable=no-member
            self.power.off()  # pylint: disable=no-member
            self.status = Status.off


def _start_address(images):
    for _, address in images:
        if address:
            return address
    raise ValueError("no image with an address to start at")


@target_factory.reg_driver
@attr.s(eq=False)
class LoaderStrategy(BootStrategy):
    """Boards whose loader starts the images itself: a debugger script, a
    flash programmer that resets into what it wrote."""
    bindings = {
        "power": "PowerProtocol",
        "console": "ConsoleProtocol",
        "loader": {"Trace32Driver", "RFPDriver"},
    }

    def boot(self, images, firmware=None):
        self._power_cycle()
        self.target.activate(self.loader)
        self.loader.load(images, firmware=firmware)
        self.status = Status.running


@target_factory.reg_driver
@attr.s(eq=False)
class UBootLoaderStrategy(BootStrategy):
    """Boards whose loader leaves U-Boot at its prompt with the images in
    memory; U-Boot jumps to the first image that has an address."""
    bindings = {
        "power": "PowerProtocol",
        "console": "ConsoleProtocol",
        "loader": "ZynqMPJTAGBootDriver",
        "uboot": "UBootDriver",
    }

    def boot(self, images, firmware=None):
        address = _start_address(images)
        self._power_cycle()
        self.target.activate(self.loader)
        self.loader.load(images, firmware=firmware)
        self.target.activate(self.uboot)
        self.console.sendline(f"go {address}")
        # the next boot must wait for the prompt again
        self.target.deactivate(self.uboot)
        self.status = Status.running


@target_factory.reg_driver
@attr.s(eq=False)
class UBootNetStrategy(BootStrategy):
    """Boards that boot their own U-Boot, which fetches the first image from
    the target's TFTP or HTTP provider and jumps to it.

    Args:
        serverip (str): the provider's address as the board sees it, when
            DHCP does not hand it out
        wget (str): "url" for a U-Boot with lwIP, "legacy" for one that takes
            host:path and only port 80
        timeout (int): seconds for DHCP and for the transfer
    """
    bindings = {
        "power": "PowerProtocol",
        "console": "ConsoleProtocol",
        "uboot": "UBootDriver",
        "provider": {"TFTPProviderDriver", "HTTPProviderDriver"},
    }
    serverip = attr.ib(default=None, validator=attr.validators.optional(attr.validators.instance_of(str)))
    wget = attr.ib(default="url", validator=attr.validators.in_(("url", "legacy")))
    timeout = attr.ib(default=120, validator=attr.validators.instance_of(int))

    def boot(self, images, firmware=None):
        image, address = images[0]
        self.target.activate(self.provider)
        # a local provider links the image by name and refuses an existing link
        stale = os.path.join(self.provider.provider.internal, os.path.basename(image))
        if os.path.islink(stale):
            os.unlink(stale)
        path = self.provider.stage(image)

        self._power_cycle()
        self.target.activate(self.uboot)
        self.uboot.run_check("setenv autoload no")
        self.uboot.run_check("dhcp", timeout=self.timeout)
        if self.serverip:
            self.uboot.run_check(f"setenv serverip {self.serverip}")
        if path.startswith(("http://", "https://")):
            if self.wget == "legacy":
                host, _, file_path = path.split("://", 1)[1].partition("/")
                path = f"{host.split(':')[0]}:/{file_path}"
            self.uboot.run_check(f"wget {address} {path}", timeout=self.timeout)
        else:
            self.uboot.run_check(f"tftpboot {address} {path}", timeout=self.timeout)
        self.console.sendline(f"go {address}")
        self.target.deactivate(self.uboot)
        self.status = Status.running


@target_factory.reg_driver
@attr.s(eq=False)
class SDCardStrategy(BootStrategy):
    """Boards that boot from an SD card behind a USB-SD-Mux: the card is
    written while the board is off, handed to the board, and the board
    powered on. Its own boot chain starts the payload.

    Args:
        card (dict): layout of the card to build around the first image with
            the firmware (see bao_labgrid_boards.card); without it the first
            image is a whole-card image, written as it is
    """
    bindings = {
        "power": "PowerProtocol",
        "console": "ConsoleProtocol",
        "mux": "USBSDMuxDriver",
        "storage": "USBStorageDriver",
    }
    card = attr.ib(default=None, validator=attr.validators.optional(attr.validators.instance_of(dict)))

    def boot(self, images, firmware=None):
        image = images[0][0]
        self.target.activate(self.power)
        self.power.off()
        self.target.activate(self.mux)
        self.mux.set_mode("host")
        self.target.activate(self.storage)
        try:
            if self.card:
                with tempfile.TemporaryDirectory() as tmp:
                    built = sdcard.build(self.card, image, firmware, os.path.join(tmp, "card.img"))
                    self.storage.write_image(built)
            else:
                self.storage.write_image(image)
        finally:
            # the card always goes back: some boards loop without it
            self.target.deactivate(self.storage)
            self.mux.set_mode("dut")
        self.target.activate(self.console)
        self.power.on()
        time.sleep(self.settle)
        self.status = Status.running

    def off(self):
        """Power the board off and leave the card on its side."""
        try:
            super().off()
        finally:
            self.target.activate(self.mux)
            self.mux.set_mode("dut")
