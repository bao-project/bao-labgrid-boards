# labgrid-bao-boards

[labgrid](https://labgrid.readthedocs.io/) drivers and boot strategies for the boards Bao runs
on: the ways of getting an image running on a board that labgrid does not
ship. They depend on labgrid alone, so anything that speaks labgrid can use
them: a test framework such as bao-kao, a board lab's tooling. The board can be on the desk or behind a labgrid exporter; the driver
runs the vendor tool wherever the hardware is.

    pip install git+https://github.com/bao-project/labgrid-bao-boards

An environment file registers the drivers and strategies with one line:

```yaml
imports:
  - labgrid_bao_boards
```

## Loaders

A loader is a driver with one method, `load(images, firmware=None)`:
`images` is a list of `(path, address)` pairs, the address `None` for an
ELF, which carries its own, and a hex string for a raw binary.

| # | Driver | Boards | Binds to | Tool |
|---|---|---|---|---|
| 1 | `ZynqMPJTAGBootDriver` | Zynq UltraScale+ (ZCU104, ZCU102) | `USBFlashableDevice` (the JTAG cable) | `xsdb` |
| 2 | `Trace32Driver` | anything a Lauterbach debugger reaches (S32Z270, TC4x, RH850) | `USBFlashableDevice` (the debugger) | TRACE32 PowerView, `t32rem` |
| 3 | `RFPDriver` | Renesas microcontrollers (RH850 U2A16) | `USBFlashableDevice` (the E1, E2 or E2 Lite emulator) | `rfp-cli` (Renesas Flash Programmer) |

### ZynqMPJTAGBootDriver

Boots the board to U-Boot over JTAG: PMU firmware, FSBL, TF-A and U-Boot go
into RAM together with the images, and U-Boot is left running. Nothing is
written to the board. The driver forces the boot mode to JTAG from the
debugger before it resets the chip.

```yaml
imports:
  - labgrid_bao_boards
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

### Trace32Driver

Starts TRACE32 PowerView without its window (`SCREEN=OFF` in the generated
configuration), with its Remote API open, and
either runs your PRACTICE script or loads images after the board's own
bring-up script. PowerView stays up afterwards, so the session can be driven
further and must be stopped when done.

```yaml
imports:
  - labgrid_bao_boards
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

### RFPDriver

Programs the device's flash with `rfp-cli`, one run per image, and resets
the device into the program after the last one.

```yaml
imports:
  - labgrid_bao_boards
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

## Boot strategies

A strategy takes a kind of board from off to running the caller's images and
back, by sequencing the board's power, console and loader drivers. Whoever
boots the board names the images and nothing else, so a test framework and a
lab's command line boot it the same way.

| # | Strategy | For | Binds | `boot(images, firmware=None)` |
|---|---|---|---|---|
| 1 | `LoaderStrategy` | boards whose loader starts the images itself (`Trace32Driver`, `RFPDriver`) | power, console, loader | power cycle, wait `settle` seconds, load |
| 2 | `UBootLoaderStrategy` | boards whose loader leaves U-Boot at its prompt (`ZynqMPJTAGBootDriver`) | power, console, loader, `UBootDriver` | power cycle, load, `go` to the first image that has an address |
| 3 | `UBootNetStrategy` | boards that boot their own U-Boot | power, console, `UBootDriver`, a TFTP or HTTP provider | stage the first image, power cycle, `dhcp`, fetch, `go` |
| 4 | `SDCardStrategy` | boards that boot from an SD card behind a USB-SD-Mux | power, console, `USBSDMuxDriver`, `USBStorageDriver` | power off, card to the host, write it, card back, power on |

`off()` ends a debugger session a loader left open and powers the board off.
After `boot()` the console driver is active and holds what the board has
printed since it started.

```yaml
    drivers:
      SerialDriver: {}
      NetworkPowerDriver: {}
      ZynqMPJTAGBootDriver: {}
      UBootDriver:
        prompt: "ZynqMP> "
      UBootLoaderStrategy: {}         # after the drivers it binds
```

```python
strategy = target.get_strategy()
strategy.boot([("bao.bin", "0x200000")], firmware="fw/")
print(target.get_driver("ConsoleProtocol").read())
strategy.off()
```

`SDCardStrategy` writes the first image as a whole card, or, given a `card`
layout, builds the card around it with `firmware` (`labgrid_bao_boards/card.py`:
firmware files at raw offsets, one ext4 partition with the payload; needs
`mke2fs`, `sgdisk` and `dd` where it is built). `off()` also leaves the card on
the board's side.

`LoaderStrategy` takes `settle`, for a debugger powered from the board's own
socket; `UBootNetStrategy` takes `serverip`, `wget` (`url` or `legacy`) and
`timeout`.

## Layout

    labgrid_bao_boards/drivers/   one module per driver: zynqmp_jtag.py, trace32.py, rfp.py, tapo.py
    labgrid_bao_boards/strategy.py   the boot strategies
    labgrid_bao_boards/card.py       SD card images for boards that boot from one
    labgrid_bao_boards/power/     power backends in labgrid's shape: tapo.py

## Power

| # | Driver | Switch | Binds to | Needs |
|---|---|---|---|---|
| 1 | `TapoPowerDriver` | TP-Link Tapo plugs (P100, P110) | `NetworkPowerPort` with `model: tapo` | python-kasa: `pip install "labgrid-bao-boards[tapo] @ git+https://github.com/bao-project/labgrid-bao-boards"` |

labgrid's own `NetworkPowerDriver` covers many switches (Shelly, Gude, ...)
but not Tapo, whose plugs want the TP-Link account. `TapoPowerDriver` is the
same driver with a Tapo backend: `on`, `off`, `cycle`, `get`.

```yaml
imports:
  - labgrid_bao_boards
targets:
  main:
    resources:
      - NetworkPowerPort:
          model: tapo
          host: http://192.168.1.50     # the plug
          index: 0                      # one plug, one outlet
    drivers:
      TapoPowerDriver:
        delay: 3.0
```

The account is read from `TAPO_USER` and `TAPO_PASS`, in the environment or
in `~/.config/tapo.env` (`NAME=value` lines; `$LAB_TAPO_ENV` names another
file). Keep that file readable by you alone.

`labgrid-client power` does not use this driver: it looks the model up among
labgrid's own backends. A lab that wants it there links
`labgrid_bao_boards/power/tapo.py` into labgrid's `driver/power` directory.

## Using a loader

From Python, like any labgrid driver:

```python
from labgrid import Environment

target = Environment(config_file="board.yaml").get_target()
loader = target.get_driver("ZynqMPJTAGBootDriver")
loader.load([("bao.bin", "0x200000"), ("guest.elf", None)])
```

## Status

| # | Driver | Tried on hardware |
|---|---|---|
| 1 | `ZynqMPJTAGBootDriver` | boots a ZCU104 to the U-Boot prompt with `xsdb` 2020.2 and the 2023.1 prebuilt firmware, the board's switches on JTAG. The software override of the boot mode has not been tried with the switches on another mode. |
| 2 | `Trace32Driver` | no: only against stand-ins for PowerView and `t32rem` |
| 3 | `RFPDriver` | no: only against a stand-in for `rfp-cli`; the options were checked against `rfp-cli` V1.13 |
| 4 | `TapoPowerDriver` | the backend has read the state of a P110; switching, and the driver class on a real plug, not yet |
| 5 | `UBootLoaderStrategy` | runs Bao's tests on a ZCU104 in a lab, over JTAG |
| 6 | `SDCardStrategy` | runs Bao's tests on a K3 CoM260 in a lab |
| 7 | `LoaderStrategy` | loads an S32Z270 through TRACE32 in a lab, up to Bao's banner |
| 8 | `UBootNetStrategy` | no |
