# Boot strategies

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
layout, builds the card around it with `firmware` (`bao_labgrid_boards/card.py`:
firmware files at raw offsets, one ext4 partition with the payload; needs
`mke2fs`, `sgdisk` and `dd` where it is built). `off()` also leaves the card on
the board's side.

`LoaderStrategy` takes `settle`, for a debugger powered from the board's own
socket; `UBootNetStrategy` takes `serverip`, `wget` (`url` or `legacy`) and
`timeout`.
