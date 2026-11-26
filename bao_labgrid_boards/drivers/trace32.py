"""
Copyright (c) Bao Project and Contributors. All rights reserved

SPDX-License-Identifier: Apache-2.0

labgrid driver that loads a board through a Lauterbach TRACE32 debugger.
Registered by the environment's ``imports: [bao_labgrid_boards]``.

PowerView runs where the debugger is: on this machine for a local resource,
on the exporter host (through ssh) for a remote one, after the files were
copied there. It is started without a window (SCREEN=OFF) and with its Remote
API open; the script is then sent through that API, since a windowless
PowerView does not run a start-up script given on its command line. The
session stays up and can be driven with command() until stop(). The ``tools`` keys of the environment name the PowerView executable
(``t32marm``, or whatever ``executable`` says) and ``t32rem``.
"""

import os
import shlex
import subprocess
import tempfile
import time

import attr
from labgrid.driver.common import Driver
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.util.helper import processwrapper
from labgrid.util.managedfile import ManagedFile

from .zynqmp_jtag import is_elf


@target_factory.reg_driver
@attr.s(eq=False)
class Trace32Driver(Driver):  # pylint: disable=too-many-instance-attributes
    """Load and run images through TRACE32 PowerView.

    Args:
        executable (str): PowerView for the architecture (t32marm, t32mtc, ...)
        sys (str): TRACE32 system directory on the machine PowerView runs on
        port (int): Remote API port, unique per debugger on that machine
        node (str): name of the debugger, with several on USB
        init (str): PRACTICE script that brings the target up, ready for
            Data.LOAD; needed to load images without a script of your own
        go (bool): start the target after loading
        headless (bool): run PowerView without its window (SCREEN=OFF)
        xvfb (bool): also give it a virtual display (xvfb-run), for PowerView
            builds that want an X server even with the screen off
        timeout (int): how long PowerView may take to answer, in seconds
        script_timeout (int): how long the load script may take, in seconds
    """
    bindings = {"debugger": {"USBFlashableDevice", "NetworkUSBFlashableDevice"}}

    executable = attr.ib(default="t32marm", validator=attr.validators.instance_of(str))
    sys = attr.ib(default="/opt/t32", validator=attr.validators.instance_of(str))
    port = attr.ib(default=20000, validator=attr.validators.instance_of(int))
    node = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(str))
    )
    init = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(str))
    )
    go = attr.ib(default=True, validator=attr.validators.instance_of(bool))
    headless = attr.ib(default=True, validator=attr.validators.instance_of(bool))
    xvfb = attr.ib(default=False, validator=attr.validators.instance_of(bool))
    timeout = attr.ib(default=30, validator=attr.validators.instance_of(int))
    script_timeout = attr.ib(default=120, validator=attr.validators.instance_of(int))

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        config = self.target.env.config if self.target.env else None
        # pylint: disable=attribute-defined-outside-init
        self.powerview = config.get_tool(self.executable) if config else self.executable
        self.t32rem = config.get_tool("t32rem") if config else "t32rem"
        self.workdir = f"/tmp/labgrid-t32-{self.port}"

    def on_activate(self):
        pass

    def on_deactivate(self):
        pass

    def _run(self, command):
        """Run a command where the debugger is and return its output."""
        wrapped = self.debugger.wrap_command(command)  # pylint: disable=no-member
        return processwrapper.check_output(wrapped).decode(errors="replace")

    def _stage(self, path):
        """Make a file reachable by PowerView and return its path there."""
        managed = ManagedFile(os.path.abspath(path), self.debugger)  # pylint: disable=no-member
        managed.sync_to_resource()
        return managed.get_remote_path()

    def _stage_text(self, name, text):
        # kept after the call: PowerView reads these once it runs, and for a
        # local debugger the staged file is this very file
        local = os.path.join(tempfile.gettempdir(), f"labgrid-t32-{self.port}-{os.getuid()}")
        os.makedirs(local, exist_ok=True)
        path = os.path.join(local, name)
        with open(path, "w", encoding="utf-8") as out:
            out.write(text)
        return self._stage(path)

    def running(self):
        """Whether a PowerView answers on the Remote API port."""
        try:
            self._run([self.t32rem, "localhost", f"port={self.port}", "PRINT"])
            return True
        except subprocess.CalledProcessError:
            return False

    def config(self):
        """The PowerView configuration file."""
        lines = ["OS=", f"ID=T32_{self.port}", f"SYS={self.sys}", f"TMP={self.workdir}", ""]
        lines += ["PBI=", "USB"]
        if self.node:
            lines.append(f"NODE={self.node}")
        lines += ["", "RCL=NETASSIST", "PACKLEN=1024", f"PORT={self.port}", ""]
        if self.headless:
            lines += ["SCREEN=OFF", ""]
        return "\n".join(lines)

    def practice(self, images, entry=None):
        """The PRACTICE commands for a list of (path on the debugger's machine, address)."""
        if images[0][0].endswith(".cmm"):
            arguments = " ".join(f'"{path}"' for path, _ in images[1:])
            lines = [f'DO "{images[0][0]}" {arguments}'.rstrip()]
        else:
            lines = [f'DO "{self._stage(self.init)}"']
            for path, address in images:
                if address:
                    lines.append(f'Data.LOAD.Binary "{path}" {address}')
                else:
                    lines.append(f'Data.LOAD.Elf "{path}"')
            first = entry or images[0][1]
            if first:
                lines.append(f"Register.Set PC {first}")
        if self.go:
            lines.append("Go")
        # tells load() that the script ran to its end
        lines += [f'OPEN #1 "{self.workdir}/done" /Create', "CLOSE #1", "ENDDO"]
        return "\n".join(lines) + "\n"

    @Driver.check_active
    @step(args=["images"])
    def load(self, images, firmware=None, entry=None):  # pylint: disable=unused-argument
        """Start PowerView, load the images and, unless go is off, run them.

        Args:
            images (list): (path, address) pairs. Either a PRACTICE script
                first, run with the remaining paths as its arguments, or
                images for the driver's init script: the address is None for
                an ELF and required for a raw binary
        """
        if self.running():
            raise ValueError(f"a PowerView already answers on port {self.port}: stop it first")
        script = images[0][0].endswith(".cmm")
        if not script and not self.init:
            raise ValueError("no init script on the driver: pass a PRACTICE script first")
        for path, address in images:
            if not os.path.isfile(path):
                raise FileNotFoundError(path)
            if script:
                continue
            if address is None and not is_elf(path):
                raise ValueError(f"{path} is a raw binary and needs a load address")
            if address is not None and is_elf(path):
                raise ValueError(f"{path} is an ELF and carries its own addresses")
        staged = [(self._stage(path), address) for path, address in images]
        config = self._stage_text("config.t32", self.config())
        practice = self._stage_text("run.cmm", self.practice(staged, entry))
        launch = " ".join(shlex.quote(arg) for arg in (self.powerview, "-c", config))
        if self.xvfb:
            launch = f"xvfb-run -a {launch}"
        self._run(["sh", "-c", f"mkdir -p {self.workdir} && cd {self.workdir} && rm -f done && "
                               f"nohup {launch} > powerview.log 2>&1 < /dev/null &"])
        deadline = time.monotonic() + self.timeout
        while not self.running():
            if time.monotonic() > deadline:
                raise TimeoutError(f"PowerView did not answer on port {self.port}:\n{self.log()}")
            time.sleep(1)

        self._run([self.t32rem, "localhost", f"port={self.port}", "DO", practice])
        deadline = time.monotonic() + self.script_timeout
        while not self._exists(f"{self.workdir}/done"):
            if time.monotonic() > deadline:
                raise TimeoutError("the load script did not finish: " + self._where())
            time.sleep(1)
        return f"PowerView is up (Remote API port {self.port}), script done\n"

    def _exists(self, path):
        try:
            self._run(["test", "-e", path])
            return True
        except subprocess.CalledProcessError:
            return False

    def _ask(self, function):
        """The value of a TRACE32 function, as text."""
        try:
            out = self._run([self.t32rem, "localhost", f"port={self.port}", "PRINT", function])
        except subprocess.CalledProcessError:
            return "?"
        return out.rsplit("message:", 1)[-1].strip()

    def _where(self):
        """Where a script stands and the last error PowerView recorded."""
        error = self._ask("ERROR.MESSAGE()")
        return (f"stopped at {self._ask('PRACTICE.CALLER.FILE(0)')} line "
                f"{self._ask('PRACTICE.CALLER.LINE(0)')}; last error: {error or 'none'}")

    @Driver.check_active
    @step(args=["command"])
    def command(self, command):
        """Send one TRACE32 command to the running PowerView."""
        return self._run([self.t32rem, "localhost", f"port={self.port}", *command.split()])

    @Driver.check_active
    @step()
    def stop(self):
        """Quit PowerView."""
        try:
            self._run([self.t32rem, "localhost", f"port={self.port}", "QUIT"])
        except subprocess.CalledProcessError:
            pass
        # a PowerView whose debugger lost power no longer answers QUIT
        try:
            self._run(["pkill", "-f", f"labgrid-t32-{self.port}-[0-9]*/config.t32"])
        except subprocess.CalledProcessError:
            pass

    @Driver.check_active
    def log(self):
        """What PowerView printed since it was started."""
        try:
            return self._run(["cat", f"{self.workdir}/powerview.log"])
        except subprocess.CalledProcessError:
            return ""
