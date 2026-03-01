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

import logging
import importlib
import random
import re
import wx

from pubsub import pub
from wx import dataview as dv

from .. import get_dummydata

try:
    serial = importlib.import_module('serial')
except Exception:
    serial = None

_logger = logging.getLogger(__name__)


class ExternalSensorParam(object):
    def __init__(self, identifier, name, sensor_type, config):
        self._identifier = identifier
        self._name = name
        self._sensor_type = sensor_type
        self._config = config
        self._enabled = False
        self._value = None
        self._serial = None
        self._rx_buffer = b''

    def _open_serial(self):
        if serial is None:
            raise RuntimeError('pyserial not installed')

        timeout = max(float(self._config.get('timeout_ms', 250)) / 1000.0, 0.0)
        self._serial = serial.Serial(
            port=self._config.get('port', 'COM3'),
            baudrate=int(self._config.get('baud', 9600)),
            timeout=min(timeout, 0.05),
            write_timeout=min(timeout, 0.05),
        )
        self._rx_buffer = b''

    def _close_serial(self):
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

    def _parse_numeric(self, line):
        vals = re.findall(r'[-+]?\d+(?:\.\d+)?', line)
        if not vals:
            return None

        try:
            return float(vals[-1])
        except Exception:
            return None

    def _read_serial_value(self):
        if self._serial is None:
            return None

        try:
            waiting = self._serial.in_waiting
            if waiting and waiting > 0:
                self._rx_buffer += self._serial.read(waiting)
            else:
                chunk = self._serial.read(64)
                if chunk:
                    self._rx_buffer += chunk

            if not self._rx_buffer:
                return None

            if b'\n' not in self._rx_buffer and b'\r' not in self._rx_buffer:
                return None

            lines = self._rx_buffer.replace(b'\r', b'\n').split(b'\n')
            self._rx_buffer = lines[-1]

            parsed = None
            for raw in lines[:-1]:
                if not raw:
                    continue
                line = raw.decode('ascii', errors='ignore').strip()
                if not line:
                    continue
                val = self._parse_numeric(line)
                if val is not None:
                    parsed = val

            return parsed

        except Exception as e:
            _logger.warning('External sensor read failed ({}): {}'.format(self._identifier, str(e)))
            return None

    def enable(self):
        if self._enabled:
            return True

        if not get_dummydata() and self._sensor_type == 'AEM X WideBand Series':
            try:
                self._open_serial()
            except Exception as e:
                _logger.error(
                    'Unable to open external sensor {} on {}: {}'.format(
                        self._name,
                        self._config.get('port', 'N/A'),
                        str(e),
                    )
                )
                pub.sendMessage(
                    'logger.status',
                    center='External sensor not connected',
                    temporary=True,
                )
                self._enabled = False
                return False

        self._enabled = True
        return True

    def disable(self):
        self._enabled = False
        self._value = None
        self._close_serial()

    def update_reading(self):
        if not self._enabled:
            self._value = None
            return

        if get_dummydata():
            if self._sensor_type == 'AEM X WideBand Series':
                self._value = random.uniform(13.5, 15.5)
            else:
                self._value = random.uniform(0.0, 100.0)
            return

        if self._sensor_type == 'AEM X WideBand Series':
            v = self._read_serial_value()
            if v is not None:
                self._value = v
        else:
            self._value = random.uniform(13.5, 15.5)

    def close(self):
        self.disable()

    @property
    def Identifier(self):
        return self._identifier

    @property
    def Name(self):
        return self._name

    @property
    def Enabled(self):
        return self._enabled

    @property
    def ValueStr(self):
        if self._value is None:
            return ''
        return '{:.2f}'.format(self._value)

    @property
    def Config(self):
        return self._config


class AEMXSeriesConfigDialog(wx.Dialog):
    def __init__(self, parent, sensor_name='AEM X WB 1'):
        super(AEMXSeriesConfigDialog, self).__init__(
            parent,
            title='Configure AEM X WideBand Series',
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )

        self.SetSizeHints(wx.Size(420, 260), wx.DefaultSize)

        _sizer = wx.GridBagSizer(6, 6)
        _sizer.SetFlexibleDirection(wx.BOTH)
        _sizer.SetNonFlexibleGrowMode(wx.FLEX_GROWMODE_SPECIFIED)

        self._name_label = wx.StaticText(self, wx.ID_ANY, 'Sensor Name')
        self._name_input = wx.TextCtrl(self, wx.ID_ANY, sensor_name)

        self._port_label = wx.StaticText(self, wx.ID_ANY, 'Serial Port')
        self._port_input = wx.TextCtrl(self, wx.ID_ANY, 'COM3')

        self._baud_label = wx.StaticText(self, wx.ID_ANY, 'Baud Rate')
        self._baud_choice = wx.Choice(
            self,
            wx.ID_ANY,
            choices=['9600', '19200', '38400', '57600', '115200'],
        )
        self._baud_choice.SetStringSelection('9600')

        self._timeout_label = wx.StaticText(self, wx.ID_ANY, 'Read Timeout (ms)')
        self._timeout_spin = wx.SpinCtrl(self, wx.ID_ANY, min=50, max=5000, initial=500)

        self._afr_label = wx.StaticText(self, wx.ID_ANY, 'AFR Source')
        self._afr_choice = wx.Choice(
            self,
            wx.ID_ANY,
            choices=['Serial Stream', 'CAN Stream'],
        )
        self._afr_choice.SetSelection(0)

        _sizer.Add(self._name_label, wx.GBPosition(0, 0), wx.GBSpan(1, 1), wx.ALIGN_CENTER_VERTICAL)
        _sizer.Add(self._name_input, wx.GBPosition(0, 1), wx.GBSpan(1, 1), wx.EXPAND)

        _sizer.Add(self._port_label, wx.GBPosition(1, 0), wx.GBSpan(1, 1), wx.ALIGN_CENTER_VERTICAL)
        _sizer.Add(self._port_input, wx.GBPosition(1, 1), wx.GBSpan(1, 1), wx.EXPAND)

        _sizer.Add(self._baud_label, wx.GBPosition(2, 0), wx.GBSpan(1, 1), wx.ALIGN_CENTER_VERTICAL)
        _sizer.Add(self._baud_choice, wx.GBPosition(2, 1), wx.GBSpan(1, 1), wx.EXPAND)

        _sizer.Add(self._timeout_label, wx.GBPosition(3, 0), wx.GBSpan(1, 1), wx.ALIGN_CENTER_VERTICAL)
        _sizer.Add(self._timeout_spin, wx.GBPosition(3, 1), wx.GBSpan(1, 1), wx.EXPAND)

        _sizer.Add(self._afr_label, wx.GBPosition(4, 0), wx.GBSpan(1, 1), wx.ALIGN_CENTER_VERTICAL)
        _sizer.Add(self._afr_choice, wx.GBPosition(4, 1), wx.GBSpan(1, 1), wx.EXPAND)

        _button_sizer = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)
        _sizer.Add(_button_sizer, wx.GBPosition(5, 0), wx.GBSpan(1, 2), wx.EXPAND)

        _sizer.AddGrowableCol(1)

        self.SetSizer(_sizer)
        self.Layout()
        self.Centre(wx.BOTH)

    def get_config(self):
        return {
            'name': self._name_input.GetValue().strip() or 'AEM X WB',
            'type': 'AEM X WideBand Series',
            'port': self._port_input.GetValue().strip() or 'COM3',
            'baud': self._baud_choice.GetStringSelection(),
            'timeout_ms': self._timeout_spin.GetValue(),
            'source': self._afr_choice.GetStringSelection(),
        }


class ExternalSensorsPanel(wx.Panel):
    def __init__(self, parent, id=wx.ID_ANY, pos=wx.DefaultPosition, size=wx.DefaultSize, style=wx.TAB_TRAVERSAL):
        super(ExternalSensorsPanel, self).__init__(parent, id=id, pos=pos, size=size, style=style)

        self._sensors = []
        self._sensor_seq = 1

        _sizer = wx.BoxSizer(wx.VERTICAL)

        _base_font = wx.Font(
            8,
            wx.FONTFAMILY_DEFAULT,
            wx.FONTSTYLE_NORMAL,
            wx.FONTWEIGHT_NORMAL,
            False,
            wx.EmptyString,
        )

        self._title = wx.StaticText(self, wx.ID_ANY, 'External Sensors')
        self._title.SetFont(_base_font)
        _sizer.Add(self._title, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)

        self._dvlc = dv.DataViewListCtrl(self, wx.ID_ANY, style=dv.DV_ROW_LINES)
        self._dvlc.SetFont(_base_font)
        self._dvlc.AppendToggleColumn('', width=34)
        self._dvlc.AppendTextColumn('ID', width=90)
        self._dvlc.AppendTextColumn('Name', width=140)
        self._dvlc.AppendTextColumn('Type', width=160)
        self._dvlc.AppendTextColumn('Port', width=80)
        self._dvlc.AppendTextColumn('Baud', width=80)
        _sizer.Add(self._dvlc, 1, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(_sizer)
        self.Layout()

        self.Bind(wx.EVT_CONTEXT_MENU, self.OnContextMenu)
        self._dvlc.Bind(wx.EVT_CONTEXT_MENU, self.OnContextMenu)
        self._dvlc.Bind(wx.EVT_RIGHT_UP, self.OnRightClick)
        self._dvlc.Bind(dv.EVT_DATAVIEW_ITEM_CONTEXT_MENU, self.OnContextMenu)
        self._dvlc.Bind(dv.EVT_DATAVIEW_ITEM_VALUE_CHANGED, self.OnToggleSensor)

        self._sensor_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.OnSensorTimer, self._sensor_timer)
        self._sensor_timer.Start(250)
        self.Bind(wx.EVT_WINDOW_DESTROY, self.OnDestroy)

    def _publish_enabled_sensors(self):
        enabled = [x for x in self._sensors if x.Enabled]
        pub.sendMessage('logger.external.updated', params=enabled)

    def OnContextMenu(self, event):
        menu = wx.Menu()
        m_add = menu.Append(wx.ID_ANY, 'Add Sensor...')
        menu.Bind(wx.EVT_MENU, self.OnAddSensor, m_add)
        self._dvlc.PopupMenu(menu)
        menu.Destroy()

    def OnRightClick(self, event):
        self.OnContextMenu(event)

    def OnAddSensor(self, event):
        choices = ['AEM X WideBand Series']

        with wx.SingleChoiceDialog(
            self,
            'Select an external sensor to add',
            'Add External Sensor',
            choices,
        ) as sel_dlg:
            if sel_dlg.ShowModal() != wx.ID_OK:
                return
            sensor_type = sel_dlg.GetStringSelection()

        if sensor_type != 'AEM X WideBand Series':
            return

        default_name = 'AEM X WB {}'.format(self._sensor_seq)
        with AEMXSeriesConfigDialog(self, sensor_name=default_name) as cfg_dlg:
            if cfg_dlg.ShowModal() != wx.ID_OK:
                return
            cfg = cfg_dlg.get_config()

        self._add_sensor_from_config(cfg, enabled=False)

    def _add_sensor_from_config(self, cfg, enabled=False):
        sensor_type = cfg.get('type', 'AEM X WideBand Series')
        sensor = ExternalSensorParam(
            identifier='EXT_{:03d}'.format(self._sensor_seq),
            name=cfg.get('name', 'External Sensor {}'.format(self._sensor_seq)),
            sensor_type=sensor_type,
            config=cfg,
        )
        self._sensor_seq += 1
        self._sensors.append(sensor)

        self._dvlc.AppendItem([
            bool(enabled),
            sensor.Identifier,
            sensor.Name,
            cfg.get('type', ''),
            cfg.get('port', ''),
            str(cfg.get('baud', '')),
        ])

        row = self._dvlc.GetItemCount() - 1
        if enabled:
            ok = sensor.enable()
            if not ok:
                self._dvlc.SetValue(False, row, 0)

        self._publish_enabled_sensors()

    def OnToggleSensor(self, event):
        item = event.GetItem()
        if not item.IsOk():
            return

        row = self._dvlc.ItemToRow(item)
        if row < 0 or row >= len(self._sensors):
            return

        enabled = bool(self._dvlc.GetValue(row, 0))
        sensor = self._sensors[row]

        if enabled:
            ok = sensor.enable()
            if not ok:
                self._dvlc.SetValue(False, row, 0)
        else:
            sensor.disable()

        self._publish_enabled_sensors()

    def OnSensorTimer(self, event):
        has_enabled = False
        for sensor in self._sensors:
            if sensor.Enabled:
                has_enabled = True
                sensor.update_reading()

        if has_enabled:
            pub.sendMessage('logger.external.params.updated')

    def OnDestroy(self, event):
        self._sensor_timer.Stop()
        for sensor in self._sensors:
            sensor.close()
        event.Skip()

    def clear_sensors(self):
        for sensor in self._sensors:
            sensor.close()
        self._sensors = []
        self._sensor_seq = 1
        self._dvlc.DeleteAllItems()
        self._publish_enabled_sensors()

    def get_preset_data(self):
        out = []
        for sensor in self._sensors:
            cfg = dict(sensor.Config)
            cfg['enabled'] = sensor.Enabled
            out.append(cfg)
        return out

    def apply_preset_data(self, sensors):
        self.clear_sensors()
        for cfg in sensors:
            enabled = bool(cfg.get('enabled', False))
            self._add_sensor_from_config(cfg, enabled=enabled)
