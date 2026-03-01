#   Copyright (C) 2021  Shamit Som <shamitsom@gmail.com>
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published
#   by the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.

import os
import platform

from .base import CommunicationDevice


class SocketCANDevice(CommunicationDevice):
    "Linux SocketCAN physical-layer skeleton."

    def __init__(self, interface_name, **kwargs):
        super(SocketCANDevice, self).__init__(interface_name, **kwargs)
        self._iface_name = interface_name
        self._bus = None

    def initialize(self, *args, **kwargs):
        raise NotImplementedError('SocketCAN skeleton backend not implemented yet')

    def terminate(self):
        self._initialized = False
        self._bus = None

    def read(self, num_msgs=1, timeout=None):
        raise NotImplementedError('SocketCAN skeleton backend not implemented yet')

    def write(self, msg_bytes, timeout=None):
        raise NotImplementedError('SocketCAN skeleton backend not implemented yet')

    def query(self, msg_bytes, num_msgs=1, timeout=None, delay=0):
        raise NotImplementedError('SocketCAN skeleton backend not implemented yet')

    def clear_rx_buffer(self):
        return

    def clear_tx_buffer(self):
        return


def _get_linux_can_ifaces():
    if platform.system().lower() != 'linux':
        return []

    net_dir = '/sys/class/net'
    if not os.path.isdir(net_dir):
        return []

    names = []
    for name in os.listdir(net_dir):
        if name.startswith('can') or name.startswith('vcan'):
            names.append(name)

    return sorted(names)


phys = {x: set([SocketCANDevice]) for x in _get_linux_can_ifaces()}
