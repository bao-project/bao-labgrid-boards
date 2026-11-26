"""
Copyright (c) Bao Project and Contributors. All rights reserved

SPDX-License-Identifier: Apache-2.0

labgrid power driver for TP-Link Tapo smart plugs (P100, P110). Registered
by the environment's ``imports: [bao_labgrid_boards]``.

It is labgrid's NetworkPowerDriver with the Tapo backend of this package
(..power.tapo), which labgrid itself does not ship: same resource, same
on/off/cycle/get, same tunnelling through the exporter host for a remote
place. Needs python-kasa (pip install bao-labgrid-boards[tapo]).
"""

import attr
from labgrid.driver.powerdriver import NetworkPowerDriver
from labgrid.factory import target_factory

from ..power import tapo


@target_factory.reg_driver
@attr.s(eq=False)
class TapoPowerDriver(NetworkPowerDriver):
    """Switch a board's power through a Tapo plug.

    Binds to a NetworkPowerPort with ``model: tapo``, ``host`` the plug's
    address and ``index: 0``. The Tapo account comes from TAPO_USER and
    TAPO_PASS or from ~/.config/tapo.env (see ..power.tapo).

    Args:
        delay (float): seconds between off and on in a cycle
    """

    def __attrs_post_init__(self):
        # past NetworkPowerDriver, which looks the model up among labgrid's own backends
        super(NetworkPowerDriver, self).__attrs_post_init__()  # pylint: disable=bad-super-call
        self.backend = tapo
        self._host = None
        self._port = None
