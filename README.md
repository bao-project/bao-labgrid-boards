# bao-labgrid-boards

[labgrid](https://labgrid.readthedocs.io/) drivers and boot strategies for the boards Bao runs
on: the ways of getting an image running on a board that labgrid does not
ship. They depend on labgrid alone, so anything that speaks labgrid can use
them: a test framework such as bao-kao, a board lab's tooling. The board can be on the desk or behind a labgrid exporter; the driver
runs the vendor tool wherever the hardware is.

    pip install git+https://github.com/bao-project/bao-labgrid-boards

An environment file registers the drivers and strategies with one line:

```yaml
imports:
  - bao_labgrid_boards
```

## What is here

| # | Kind | Name | For |
|---|---|---|---|
| 1 | loader | `ZynqMPJTAGBootDriver` | Zynq UltraScale+ over JTAG, with `xsdb` |
| 2 | loader | `Trace32Driver` | anything a Lauterbach debugger reaches |
| 3 | loader | `RFPDriver` | Renesas microcontrollers, with `rfp-cli` |
| 4 | strategy | `LoaderStrategy` | boards whose loader starts the images itself |
| 5 | strategy | `UBootLoaderStrategy` | boards whose loader leaves U-Boot at its prompt |
| 6 | strategy | `UBootNetStrategy` | boards whose U-Boot fetches the image over the network |
| 7 | strategy | `SDCardStrategy` | boards that boot from an SD card behind a USB-SD-Mux |
| 8 | power | `TapoPowerDriver` | TP-Link Tapo plugs |

A loader puts images on a board; a strategy sequences power, console and
loader to take a board from off to running them:

```python
from labgrid import Environment

target = Environment(config_file="board.yaml").get_target()
target.get_strategy().boot([("bao.bin", "0x200000")], firmware="fw/")
```

## Documentation

| # | Document | What it covers |
|---|---|---|
| 1 | [docs/loaders.md](docs/loaders.md) | each loader: its settings, an environment file, how it loads |
| 2 | [docs/strategies.md](docs/strategies.md) | the boot strategies and the SD card layout |
| 3 | [docs/power.md](docs/power.md) | the Tapo power driver and its account file |

## Layout

    bao_labgrid_boards/drivers/   one module per driver: zynqmp_jtag.py, trace32.py, rfp.py, tapo.py
    bao_labgrid_boards/strategy.py   the boot strategies
    bao_labgrid_boards/card.py       SD card images for boards that boot from one
    bao_labgrid_boards/power/     power backends in labgrid's shape: tapo.py

## Status

| # | Driver | Tried on hardware |
|---|---|---|
| 1 | `ZynqMPJTAGBootDriver` | boots a ZCU104 to the U-Boot prompt with `xsdb` 2020.2 and the 2023.1 prebuilt firmware, the board's switches on JTAG. The software override of the boot mode has not been tried with the switches on another mode. |
| 2 | `Trace32Driver` | loads an S32Z270 in a lab, headless, with a script of the caller's; the built-in `init` and `go` path only against stand-ins |
| 3 | `RFPDriver` | no: only against a stand-in for `rfp-cli`; the options were checked against `rfp-cli` V1.13 |
| 4 | `TapoPowerDriver` | the backend has read the state of a P110; switching, and the driver class on a real plug, not yet |
| 5 | `UBootLoaderStrategy` | runs Bao's tests on a ZCU104 in a lab, over JTAG |
| 6 | `SDCardStrategy` | runs Bao's tests on a K3 CoM260 in a lab |
| 7 | `LoaderStrategy` | runs Bao's tests on an S32Z270 in a lab, through TRACE32; not with `RFPDriver` |
| 8 | `UBootNetStrategy` | no |
