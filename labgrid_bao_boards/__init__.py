"""
Copyright (c) Bao Project and Contributors. All rights reserved

SPDX-License-Identifier: Apache-2.0

labgrid drivers for the boards Bao runs on. Importing the package registers
them with labgrid; an environment file does that with

    imports:
      - labgrid_bao_boards
"""

from . import drivers  # noqa: F401
