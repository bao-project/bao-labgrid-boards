# Loaders

A loader is a driver with one method, `load(images, firmware=None)`:
`images` is a list of `(path, address)` pairs, the address `None` for an
ELF, which carries its own, and a hex string for a raw binary.

| # | Driver | Boards | Binds to | Tool |
|---|---|---|---|---|
| 1 | `ZynqMPJTAGBootDriver` | Zynq UltraScale+ (ZCU104, ZCU102) | `USBFlashableDevice` (the JTAG cable) | `xsdb` |
| 2 | `Trace32Driver` | anything a Lauterbach debugger reaches (S32Z270, TC4x, RH850) | `USBFlashableDevice` (the debugger) | TRACE32 PowerView, `t32rem` |
| 3 | `RFPDriver` | Renesas microcontrollers (RH850 U2A16) | `USBFlashableDevice` (the E1, E2 or E2 Lite emulator) | `rfp-cli` (Renesas Flash Programmer) |

## ZynqMPJTAGBootDriver

Boots the board to U-Boot over JTAG: PMU firmware, FSBL, TF-A and U-Boot go
into RAM together with the images, and U-Boot is left running. Nothing is
written to the board. The driver forces the boot mode to JTAG from the
debugger before it resets the chip.

```yaml
imports:
  - bao_labgrid_boards
targets:
  main:
    resources:
      - USBFlashableDevice:
          match:
            ID_SERIAL_SHORT: "XXXXXXXX"
    drivers:
      ZynqMPJTAGBootDriver:
        firmware: /path/to/firmware     # pmufw.elf zynqmp_fsbl.elf bl31.elf u-boot.elf [system.dtb]
        # cable_serial: "XXXXXXXX"      # with several Xilinx cables on the machine
tools:
  xsdb: /opt/xilinx/Vivado/2023.1/bin/xsdb    # default: xsdb from PATH
```

With a remote place the resource comes from the exporter as a
`NetworkUSBFlashableDevice`; labgrid copies the files to the exporter host
and `xsdb` runs there, so that is where it must be installed.

## Trace32Driver

Starts TRACE32 PowerView without its window (`SCREEN=OFF` in the generated
configuration), with its Remote API open, and
either runs your PRACTICE script or loads images after the board's own
bring-up script. PowerView stays up afterwards, so the session can be driven
further and must be stopped when done.

```yaml
imports:
  - bao_labgrid_boards
targets:
  main:
    resources:
      - USBFlashableDevice:
          match:
            ID_VENDOR_ID: "0897"        # Lauterbach
    drivers:
      Trace32Driver:
        executable: t32marm             # PowerView for the architecture
        sys: /opt/t32                   # TRACE32 system directory
        port: 20000                     # Remote API port, unique per debugger
        # node: "<debugger name>"       # with several debuggers on USB
        # init: /path/to/bringup.cmm    # leaves the target ready for Data.LOAD
        # go: false                     # load without starting
        # headless: false               # show the PowerView window
        # xvfb: true                    # run under xvfb-run, if PowerView still wants a display
tools:
  t32marm: /opt/t32/bin/pc_linux64/t32marm
  t32rem: /opt/t32/bin/pc_linux64/t32rem
```

`load(images)` takes one of two shapes:

1. a PRACTICE script first, then its arguments:
   `[("t32.cmm", None), ("bao.bin", None), ("guest.bin", None)]` runs
   `DO t32.cmm bao.bin guest.bin`;
2. images only, which needs `init`: after the init script, an ELF is loaded
   with `Data.LOAD.Elf`, a raw binary with `Data.LOAD.Binary` at its address.

Then `Go`, unless `go` is off. `command("Break")` sends any TRACE32 command,
`stop()` quits PowerView, `log()` returns what it printed.

The license is in the debug cable.

## RFPDriver

Programs the device's flash with `rfp-cli`, one run per image, and resets
the device into the program after the last one.

```yaml
imports:
  - bao_labgrid_boards
targets:
  main:
    resources:
      - USBFlashableDevice:
          match:
            ID_VENDOR_ID: "045b"        # Renesas
    drivers:
      RFPDriver:
        device: RH850/U2x               # as rfp-cli names the family
        tool: e2                        # e1, e2, e2l
        osc: 40.0                       # the board's main oscillator, MHz
        # tool_serial: "XXXXXXXX"       # with several emulators on the machine
        # auth_id: "FFFF...FF"          # the device's ID code, all F by default
        # run: false                    # program without starting
tools:
  rfp-cli: /opt/renesas/linux-x64/rfp-cli    # default: rfp-cli from PATH
```

`load(images)` takes a hex or S-record file with the address `None` and a raw
binary with its address: `[("guest.hex", None), ("bao.bin", "0x0")]`. An ELF
is refused, since `rfp-cli` cannot read one.

## Using a loader

From Python, like any labgrid driver:

```python
from labgrid import Environment

target = Environment(config_file="board.yaml").get_target()
loader = target.get_driver("ZynqMPJTAGBootDriver")
loader.load([("bao.bin", "0x200000"), ("guest.elf", None)])
```
