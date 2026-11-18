# labgrid-bao-boards

[labgrid](https://labgrid.readthedocs.io/) drivers for the boards Bao runs
on: the ways of getting an image running on a board that labgrid does not
ship. They depend on labgrid alone, so anything that speaks labgrid can use
them: a test framework such as bao-kao, a board lab's tooling. The board can be on the desk or behind a labgrid exporter; the driver
runs the vendor tool wherever the hardware is.

    pip install git+https://github.com/bao-project/labgrid-bao-boards

An environment file registers the drivers with one line:

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

### ZynqMPJTAGBootDriver

Boots the board to U-Boot over JTAG: PMU firmware, FSBL, TF-A and U-Boot go
into RAM together with the images, and U-Boot is left running. Nothing is
written to the board, whose boot-mode switches must select JTAG.

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

## Using a loader

From Python, like any labgrid driver:

```python
from labgrid import Environment

target = Environment(config_file="board.yaml").get_target()
loader = target.get_driver("ZynqMPJTAGBootDriver")
loader.load([("bao.bin", "0x200000"), ("guest.elf", None)])
```

## Status

The ZynqMP sequence has only run against a stand-in for `xsdb`, not on a
board yet.
