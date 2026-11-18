"""
Copyright (c) Bao Project and Contributors. All rights reserved

SPDX-License-Identifier: Apache-2.0

TP-Link Tapo smart plugs (P100, P110) through python-kasa, as a labgrid power
backend. One plug is one outlet, so the index is always 0.

    NetworkPowerPort:
      model: tapo
      host: http://<plug address>
      index: 0

Tapo plugs want the TP-Link account: TAPO_USER and TAPO_PASS, taken from the
environment or from a file of NAME=value lines. The file is $LAB_TAPO_ENV if
set, else ~/.config/tapo.env, else /etc/lab/power/tapo.env.

The module has no imports from this package, so that it also works copied or
linked into labgrid's own driver/power directory, where labgrid-client looks
for the model.
"""

import asyncio
import os
from urllib.parse import urlparse

FILES = ("~/.config/tapo.env", "/etc/lab/power/tapo.env")


def credentials():
    """The Tapo account as (user, password)."""
    values = {name: os.environ[name] for name in ("TAPO_USER", "TAPO_PASS") if name in os.environ}
    if len(values) < 2:
        candidates = [os.environ["LAB_TAPO_ENV"]] if "LAB_TAPO_ENV" in os.environ else FILES
        for candidate in candidates:
            path = os.path.expanduser(candidate)
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8") as lines:
                for line in lines:
                    key, sep, value = line.strip().partition("=")
                    if sep and not key.startswith("#"):
                        key = key.removeprefix("export ").strip()
                        values.setdefault(key, value.strip().strip("'\""))
            break
    if "TAPO_USER" not in values or "TAPO_PASS" not in values:
        raise RuntimeError(
            "Tapo account not found: set TAPO_USER and TAPO_PASS, or put them in "
            + " or ".join(FILES)
        )
    return values["TAPO_USER"], values["TAPO_PASS"]


async def _run(host, index, value):
    # imported here: only setups with a Tapo plug need python-kasa
    from kasa import Credentials, Device, DeviceConfig  # pylint: disable=import-outside-toplevel
    from kasa import DeviceConnectionParameters  # pylint: disable=import-outside-toplevel
    from kasa import DeviceEncryptionType, DeviceFamily  # pylint: disable=import-outside-toplevel

    assert int(index) == 0, "a Tapo plug has one outlet: index 0"
    url = urlparse(host if "://" in host else f"http://{host}")
    config = DeviceConfig(
        host=url.hostname,
        port_override=url.port,
        credentials=Credentials(*credentials()),
        connection_type=DeviceConnectionParameters(
            DeviceFamily.SmartTapoPlug, DeviceEncryptionType.Klap, login_version=2
        ),
    )
    device = await Device.connect(config=config)
    try:
        if value is True:
            await device.turn_on()
        elif value is False:
            await device.turn_off()
        await device.update()
        return device.is_on
    finally:
        await device.disconnect()


def power_set(host, port, index, value):  # pylint: disable=unused-argument
    """Switch the plug on (True) or off (False)."""
    asyncio.run(_run(host, index, value))


def power_get(host, port, index):  # pylint: disable=unused-argument
    """Whether the plug is on."""
    return asyncio.run(_run(host, index, None))
