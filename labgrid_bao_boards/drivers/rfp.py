"""
Copyright (c) Bao Project and Contributors. All rights reserved

SPDX-License-Identifier: Apache-2.0

labgrid driver that programs a Renesas microcontroller's flash with
Renesas Flash Programmer (rfp-cli) through an E1, E2 or E2 Lite emulator.
Registered by the environment's ``imports: [labgrid_bao_boards]``.

rfp-cli runs where the emulator is: on this machine for a local resource, on
the exporter host (through ssh) for a remote one, after the files were copied
there. The ``tools`` key ``rfp-cli`` of the environment names the executable.
"""

import os

import attr
from labgrid.driver.common import Driver
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.util.helper import processwrapper
from labgrid.util.managedfile import ManagedFile

from .zynqmp_jtag import is_elf

NO_ID = "F" * 64


@target_factory.reg_driver
@attr.s(eq=False)
class RFPDriver(Driver):
    """Program images into flash with rfp-cli and reset into them.

    Args:
        device (str): the device family as rfp-cli names it (RH850/U2x)
        tool (str): the emulator (e1, e2, e2l)
        tool_serial (str): the emulator's serial, with several on the machine
        osc (float): the board's main oscillator, in MHz
        auth_id (str): the ID code that unlocks the device
        run (bool): reset the device into the program after the last image
    """
    bindings = {"programmer": {"USBFlashableDevice", "NetworkUSBFlashableDevice"}}

    device = attr.ib(default="RH850/U2x", validator=attr.validators.instance_of(str))
    tool = attr.ib(default="e2", validator=attr.validators.instance_of(str))
    tool_serial = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(str))
    )
    osc = attr.ib(default=40.0, validator=attr.validators.instance_of(float))
    auth_id = attr.ib(default=NO_ID, validator=attr.validators.instance_of(str))
    run = attr.ib(default=True, validator=attr.validators.instance_of(bool))

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        config = self.target.env.config if self.target.env else None
        # pylint: disable=attribute-defined-outside-init
        self.rfp = config.get_tool("rfp-cli") if config else "rfp-cli"

    def on_activate(self):
        pass

    def on_deactivate(self):
        pass

    def command(self, path, address, last):
        """The rfp-cli command line for one image, by its path where rfp-cli runs."""
        tool = self.tool if not self.tool_serial else f"{self.tool}:{self.tool_serial}"
        cmd = [self.rfp, "-device", self.device, "-tool", tool, "-osc", str(self.osc),
               "-auth", "id", self.auth_id, "-program"]
        cmd += ["-bin", address, path] if address else ["-file", path]
        if last and self.run:
            cmd.append("-run")
        return cmd

    @Driver.check_active
    @step(args=["images"])
    def load(self, images, firmware=None, entry=None):  # pylint: disable=unused-argument
        """Program the images in order; the device starts after the last one.

        Args:
            images (list): (path, address) pairs. The address is None for a
                hex or S-record file, which carries its own, and a hex string
                for a raw binary. An ELF is not accepted: rfp-cli cannot read one
        """
        if not images:
            raise ValueError("nothing to program")
        for path, _ in images:
            if not os.path.isfile(path):
                raise FileNotFoundError(path)
            if is_elf(path):
                raise ValueError(f"{path} is an ELF: rfp-cli takes a hex, S-record or raw binary")
        output = ""
        for index, (path, address) in enumerate(images):
            managed = ManagedFile(os.path.abspath(path), self.programmer)  # pylint: disable=no-member
            managed.sync_to_resource()
            cmd = self.command(managed.get_remote_path(), address, index == len(images) - 1)
            wrapped = self.programmer.wrap_command(cmd)  # pylint: disable=no-member
            output += processwrapper.check_output(wrapped).decode(errors="replace")
        return output
