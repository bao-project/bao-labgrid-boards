"""
Copyright (c) Bao Project and Contributors. All rights reserved

SPDX-License-Identifier: Apache-2.0

labgrid driver that boots a Zynq UltraScale+ board over JTAG with xsdb:
PMU firmware, FSBL, TF-A and U-Boot go into RAM together with the caller's
images, and U-Boot is left running. Nothing is written to the board. The
boot mode is forced to JTAG from the debugger, so the board's boot-mode
switches should not matter. Registered by the environment's
``imports: [bao_labgrid_boards]``.

xsdb runs where the cable is: on this machine for a local resource, on the
exporter host (through ssh) for a remote one, after the files were copied
there. The ``tools`` key ``xsdb`` of the environment names the executable.
"""

import os
import tempfile

import attr
from labgrid.driver.common import Driver
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.util.helper import processwrapper
from labgrid.util.managedfile import ManagedFile

FIRMWARE = ("pmufw.elf", "zynqmp_fsbl.elf", "bl31.elf", "u-boot.elf")
DTB = "system.dtb"
DTB_ADDR = "0x100000"


def is_elf(path):
    """Whether the file starts with the ELF magic."""
    with open(path, "rb") as image:
        return image.read(4) == b"\x7fELF"


@target_factory.reg_driver
@attr.s(eq=False)
class ZynqMPJTAGBootDriver(Driver):
    """Boot a ZynqMP board to U-Boot over its JTAG cable.

    Args:
        firmware (str): directory with pmufw.elf, zynqmp_fsbl.elf, bl31.elf,
            u-boot.elf and optionally system.dtb; load() can override it
        cable_serial (str): serial of the JTAG cable as hw_server reports it,
            needed when several Xilinx cables share the machine
        fsbl_time (int): how long the FSBL runs before it is stopped, in ms
    """
    bindings = {"cable": {"USBFlashableDevice", "NetworkUSBFlashableDevice"}}

    firmware = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(str))
    )
    cable_serial = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(str))
    )
    fsbl_time = attr.ib(default=4000, validator=attr.validators.instance_of(int))

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        # pylint: disable-next=attribute-defined-outside-init
        self.tool = self.target.env.config.get_tool("xsdb") if self.target.env else "xsdb"

    def on_activate(self):
        pass

    def on_deactivate(self):
        pass

    def _stage(self, path):
        """Make a file reachable by xsdb and return its path there."""
        managed = ManagedFile(os.path.abspath(path), self.cable)  # pylint: disable=no-member
        managed.sync_to_resource()
        return managed.get_remote_path()

    def script(self, firmware, images):
        """The xsdb commands for a firmware set and a list of (path, address)."""
        cable = f'jtag_cable_serial =~ "{self.cable_serial}*" && ' if self.cable_serial else ""

        def target(name):
            return f'targets -set -nocase -filter {{{cable}name =~ "{name}"}}'

        lines = [
            "connect",
            target("*PSU*"),
            # boot mode JTAG whatever the board's switches say (BOOT_MODE_USER:
            # use the alternate mode, which is 0), so the FSBL waits for the
            # debugger instead of looking for a boot device and resetting
            "mwr 0xff5e0200 0x0100",
            "rst -system",
            "after 1000",
            # let the PMU run code loaded over JTAG
            "mask_write 0xFFCA0038 0x1C0 0x1C0",
            target("*MicroBlaze PMU*"),
            "catch {stop}; after 500",
            f"dow {{{firmware['pmufw.elf']}}}",
            "con",
            "after 500",
            target("*APU*"),
            # a branch-to-self at the reset vector, then release the A53 from reset
            "mwr 0xffff0000 0x14000000",
            "mask_write 0xFD1A0104 0x501 0x0",
            target("*A53*#0"),
            "catch {stop}",
            f"dow {{{firmware['zynqmp_fsbl.elf']}}}",
            "con",
            f"after {self.fsbl_time}",
            "stop",
        ]
        if DTB in firmware:
            lines.append(f"dow -data {{{firmware[DTB]}}} {DTB_ADDR}")
        for path, address in images:
            lines.append(f"dow -data {{{path}}} {address}" if address else f"dow {{{path}}}")
        lines += [
            f"dow {{{firmware['u-boot.elf']}}}",
            f"dow {{{firmware['bl31.elf']}}}",
            "con",
            "disconnect",
        ]
        return "\n".join(lines) + "\n"

    @Driver.check_active
    @step(args=["images", "firmware"])
    def load(self, images, firmware=None):
        """Boot to U-Boot with the images in RAM.

        Args:
            images (list): (path, address) pairs; the address is None for an
                ELF, which carries its own, and required for a raw binary
            firmware (str): firmware directory, instead of the driver's
        """
        firmware = firmware or self.firmware
        if not firmware:
            raise ValueError("no firmware directory: set 'firmware' on the driver or pass one")
        staged_fw = {}
        for name in FIRMWARE + (DTB,):
            path = os.path.join(firmware, name)
            if os.path.isfile(path):
                staged_fw[name] = self._stage(path)
            elif name != DTB:
                raise FileNotFoundError(path)
        staged = []
        for path, address in images:
            if address is None and not is_elf(path):
                raise ValueError(f"{path} is a raw binary and needs a load address")
            if address is not None and is_elf(path):
                raise ValueError(f"{path} is an ELF and carries its own addresses")
            staged.append((self._stage(path), address))
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "zynqmp-jtag-boot.tcl")
            with open(script, "w", encoding="utf-8") as tcl:
                tcl.write(self.script(staged_fw, staged))
            command = self.cable.wrap_command([self.tool, self._stage(script)])  # pylint: disable=no-member
            return processwrapper.check_output(command).decode(errors="replace")
