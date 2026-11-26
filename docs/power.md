# Power

| # | Driver | Switch | Binds to | Needs |
|---|---|---|---|---|
| 1 | `TapoPowerDriver` | TP-Link Tapo plugs (P100, P110) | `NetworkPowerPort` with `model: tapo` | python-kasa: `pip install "bao-labgrid-boards[tapo] @ git+https://github.com/bao-project/bao-labgrid-boards"` |

labgrid's own `NetworkPowerDriver` covers many switches (Shelly, Gude, ...)
but not Tapo, whose plugs want the TP-Link account. `TapoPowerDriver` is the
same driver with a Tapo backend: `on`, `off`, `cycle`, `get`.

```yaml
imports:
  - bao_labgrid_boards
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
`bao_labgrid_boards/power/tapo.py` into labgrid's `driver/power` directory.
