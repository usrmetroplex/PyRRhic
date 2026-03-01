#   Copyright (C) 2020  Shamit Som <shamitsom@gmail.com>
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
import sys

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    _base_dir = sys._MEIPASS
else:
    _base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

submod_dir = os.path.join(_base_dir, 'submodules')

# add J2534 submodule to PYTHONPATH
sys.path.insert(0,
    os.path.join(submod_dir, 'PyJ2534')
)

_debug = False
_dummydata = True

def set_dummydata(enabled):
    global _dummydata
    _dummydata = bool(enabled)

def get_dummydata():
    return _dummydata
