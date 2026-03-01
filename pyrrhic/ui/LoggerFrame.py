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

import wx
import xml.etree.ElementTree as ET

from pubsub import pub

from wx.aui import AUI_BUTTON_STATE_NORMAL, AUI_BUTTON_STATE_DISABLED

from .base import bLoggerFrame
from .PrefsDialog import PrefsDialog
from .. import get_dummydata, set_dummydata

class LoggerFrame(bLoggerFrame):
    def __init__(self, parent, controller):
        self._controller = controller
        super(LoggerFrame, self).__init__(parent)

        self._connect_text = 'Connect'
        self._connecting_text = 'Connecting...'
        self._cancel_text = 'Cancel'
        self._disconnect_text = 'Disconnect'
        self._cancelling_text = 'Cancelling...'
        self._disconnecting_text = 'Disconnecting...'
        self._connection_pending = False
        self._start_log_text = 'Start Log'
        self._end_log_text = 'End Log'
        self._connect_but.SetLabelText(self._connect_text)
        self._disconnect_but.SetLabelText(self._cancel_text)
        self._disconnect_but.Disable()

        self._log_but.SetLabelText(self._start_log_text)
        self._log_but.SetMinSize(wx.Size(140, 36))
        _log_font = self._log_but.GetFont()
        _log_font.SetWeight(wx.FONTWEIGHT_BOLD)
        self._log_but.SetFont(_log_font)
        self._style_log_button(active=False)

        self._iface_text = 'Interface Selection'
        self._protocol_text = 'Protocol Selection'

        self._temp_status_delay = 3000 # ms
        self._left_status_timer = wx.Timer(self)
        self._center_status_timer = wx.Timer(self)
        self._right_status_timer = wx.Timer(self)
        self._log_blink_timer = wx.Timer(self)
        self._log_blink_on = False

        self.Bind(
            wx.EVT_TIMER, self._pop_left_status, self._left_status_timer
        )
        self.Bind(
            wx.EVT_TIMER, self._pop_center_status, self._center_status_timer
        )
        self.Bind(
            wx.EVT_TIMER, self._pop_right_status, self._right_status_timer
        )
        self.Bind(
            wx.EVT_TIMER, self._on_log_blink_timer, self._log_blink_timer
        )

        pub.subscribe(self.push_status, 'logger.status')
        pub.subscribe(self.update_freq, 'logger.freq.updated')
        pub.subscribe(self.on_connection, 'logger.connection.change')

        self._build_logger_menu()
        self._dummy_mode_chk.SetToolTip('Enable or disable mock/dummy data mode')
        self._dummy_mode_chk.SetValue(get_dummydata())
        self.OnRefreshInterfaces()
        self._update_logger_menu_state(False)

    def _build_logger_menu(self):
        self._logger_menu = wx.Menu()
        self._mi_logger_prefs = self._logger_menu.Append(
            wx.ID_ANY, 'Preferences', 'Open Logger preferences'
        )
        self._logger_menu.AppendSeparator()
        self._mi_save_preset = self._logger_menu.Append(
            wx.ID_ANY, 'Save Preset', 'Save selected params and external sensors to XML'
        )
        self._mi_import_preset = self._logger_menu.Append(
            wx.ID_ANY, 'Import Preset', 'Import logger preset XML (connected ECU required)'
        )
        self._logger_menu.AppendSeparator()
        self._mi_start_log = self._logger_menu.Append(
            wx.ID_ANY, 'Start Log', 'Start CSV logging for selected logger parameters'
        )
        self._mi_stop_log = self._logger_menu.Append(
            wx.ID_ANY, 'Stop Log', 'Stop active CSV logging'
        )
        self._menubar.Append(self._logger_menu, 'Logger')

        self.Bind(wx.EVT_MENU, self.OnLoggerPreferences, id=self._mi_logger_prefs.GetId())
        self.Bind(wx.EVT_MENU, self.OnSavePreset, id=self._mi_save_preset.GetId())
        self.Bind(wx.EVT_MENU, self.OnImportPreset, id=self._mi_import_preset.GetId())
        self.Bind(wx.EVT_MENU, self.OnStartLog, id=self._mi_start_log.GetId())
        self.Bind(wx.EVT_MENU, self.OnStopLog, id=self._mi_stop_log.GetId())

    def _update_logger_menu_state(self, connected):
        logging = self._controller.IsLogging
        self._mi_save_preset.Enable(connected)
        self._mi_import_preset.Enable(connected)
        self._mi_start_log.Enable(connected and not logging)
        self._mi_stop_log.Enable(logging)
        self._update_log_controls(connected, logging)

    def _style_log_button(self, active=False):
        if active:
            bg = wx.Colour(231, 76, 60) if self._log_blink_on else wx.Colour(192, 57, 43)
            self._log_but.SetBackgroundColour(bg)
            self._log_but.SetForegroundColour(wx.WHITE)
        else:
            self._log_but.SetBackgroundColour(wx.Colour(46, 204, 113))
            self._log_but.SetForegroundColour(wx.BLACK)
        self._log_but.Refresh()

    def _set_log_indicator(self, active=False):
        self._statusbar.SetStatusText('● LOG REC' if active else '', i=1)

    def _update_log_controls(self, connected, logging):
        self._log_but.Enable(connected or logging)
        self._log_but.SetLabelText(self._end_log_text if logging else self._start_log_text)

        if logging:
            if not self._log_blink_timer.IsRunning():
                self._log_blink_on = False
                self._log_blink_timer.Start(500)
        else:
            if self._log_blink_timer.IsRunning():
                self._log_blink_timer.Stop()
            self._log_blink_on = False

        self._style_log_button(active=logging)
        self._set_log_indicator(active=logging)

    def _on_log_blink_timer(self, event):
        self._log_blink_on = not self._log_blink_on
        self._style_log_button(active=True)

    def _enable_toolbar_controls(self, enable=True):
        if enable:
            self._refresh_but.SetState(AUI_BUTTON_STATE_NORMAL)
            self._iface_choice.Enable()
            self._protocol_choice.Enable()
        else:
            self._refresh_but.SetState(AUI_BUTTON_STATE_DISABLED)
            self._iface_choice.Disable()
            self._protocol_choice.Disable()

    def _disable_toolbar_controls(self):
        self._enable_toolbar_controls(enable=False)

    def _safe_pop_status(self, field):
        try:
            self._statusbar.PopStatusText(field=field)
        except wx.wxAssertionError:
            self._statusbar.SetStatusText('', i=field)

    def _pop_left_status(self, event=None):
        self._safe_pop_status(0)

    def _pop_center_status(self, event=None):
        self._safe_pop_status(1)

    def _pop_right_status(self, event=None):
        self._safe_pop_status(2)

    def on_connection(self, connected=True, translator=None):
        self._connection_pending = False
        self._connect_but.SetLabelText(self._connect_text)
        self._enable_toolbar_controls(enable=not connected)
        self._update_logger_menu_state(connected)

        if connected:
            self._connect_but.Disable()
            self._disconnect_but.SetLabelText(self._disconnect_text)
            self._disconnect_but.Enable()
            self._param_panel.initialize(translator)
            self.push_status(left='ID: {}'.format(translator.Definition.LoggerDef.Identifier))
            self.push_status(left='Connected', temporary=True)
        else:
            self._disconnect_but.SetLabelText(self._cancel_text)
            self._disconnect_but.Disable()
            self._param_panel.clear()
            self._center_status_timer.Stop()
            self._right_status_timer.Stop()
            self._statusbar.SetStatusText('', i=1)
            self._statusbar.SetStatusText('', i=2)
            self._pop_left_status()
            self.OnSelectProtocol()
            self._update_log_controls(False, False)

    def push_status(self, left=None, center=None, right=None, temporary=False):
        """Push text to the corresponding portion of the status bar.

        Pass a `str` to the `left`, `center` and `right` keywords to set
        the text of the corresponding part of the statusbar. Use the
        `temporary` keyword to indicate that the text pushed to the
        status bar should be popped after a small delay (which is held
        in the local binding `LoggerFrame._temp_status_delay`).
        """

        if isinstance(left, str):
            self._statusbar.PushStatusText(left, field=0)
            if temporary:
                self._left_status_timer.StartOnce(self._temp_status_delay)

        if isinstance(center, str):
            self._statusbar.PushStatusText(center, field=1)
            if temporary:
                self._center_status_timer.StartOnce(self._temp_status_delay)

        if isinstance(right, str):
            self._statusbar.PushStatusText(right, field=2)
            if temporary:
                self._right_status_timer.StartOnce(self._temp_status_delay)

    def update_freq(self, avg_freq):
        freq_str = 'Query Freq: {: >6.2f} Hz'.format(avg_freq)
        self._statusbar.SetStatusText(freq_str, i=2)

    def OnRefreshInterfaces(self, event=None):
        self._iface_choice.Clear()
        self._controller.refresh_interfaces()
        self._iface_choice.Append(
            [self._iface_text] +
            list(self._controller.AvailableInterfaces.keys())
        )
        self._iface_choice.SetSelection(len(self._iface_choice.Items) - 1)
        self.OnSelectInterface()
        self._update_dummy_mode_visibility()

    def OnSelectInterface(self, event=None):
        self._protocol_choice.Clear()
        self._protocol_choice.Append(self._protocol_text)

        if self._iface_choice.GetStringSelection() != self._iface_text:
            self._protocol_choice.Append(
                self._controller.get_supported_protocols(
                    self._iface_choice.GetStringSelection()
                )
            )
            self._protocol_choice.SetSelection(
                len(self._protocol_choice.Items) - 1
            )
        else:
            self._protocol_choice.SetSelection(0)

        self.OnSelectProtocol()
        self._update_dummy_mode_visibility()

    def OnSelectProtocol(self, event=None):
        self._connect_but.Enable(
            self._protocol_choice.GetStringSelection() != self._protocol_text
        )
        self._update_dummy_mode_visibility()

    def _is_mock_selection(self):
        return (
            self._iface_choice.GetStringSelection() == 'Mock Interface'
            and self._protocol_choice.GetStringSelection() == 'Mock SSM'
        )

    def _update_dummy_mode_visibility(self):
        self._dummy_mode_chk.SetValue(get_dummydata())
        self._dummy_mode_chk.Show(True)
        self._dummy_mode_chk.Enable(True)
        self._toolbar.Realize()

    def OnToggleDummyMode(self, event):
        enabled = self._dummy_mode_chk.GetValue()
        was_mock_selection = self._is_mock_selection()

        if (not enabled) and was_mock_selection and (
            self._controller.IsLoggerConnected or self._connection_pending
        ):
            self.OnDisconnectButton(None)

        set_dummydata(enabled)
        self.OnRefreshInterfaces()
        self.push_status(
            center='Dummy Mode {}'.format('ON' if enabled else 'OFF'),
            temporary=True,
        )

    def OnConnectButton(self, event):
        iface = self._iface_choice.GetStringSelection()
        protocol = self._protocol_choice.GetStringSelection()

        if iface == self._iface_text or protocol == self._protocol_text:
            self.push_status(center='Select interface and protocol', temporary=True)
            return

        supported = self._controller.get_supported_protocols(iface)
        if protocol not in supported:
            self.push_status(
                center='Protocol no longer available, refreshing list',
                temporary=True,
            )
            self.OnRefreshInterfaces()
            return

        # lock toolbar controls during connection startup
        self._connection_pending = True
        self._disable_toolbar_controls()
        self._connect_but.Disable()
        self._disconnect_but.Enable()
        self._disconnect_but.SetLabelText(self._cancel_text)
        self._connect_but.SetLabelText(self._connecting_text)

        # spawn a logger thread
        self._controller.spawn_logger(iface, protocol)

    def OnDisconnectButton(self, event):
        # lock controls while shutting down worker
        self._disable_toolbar_controls()
        self._connect_but.Disable()
        self._disconnect_but.Disable()
        text = self._cancelling_text if self._connection_pending else self._disconnecting_text
        self._disconnect_but.SetLabelText(text)
        self._connection_pending = False

        self._controller.kill_logger()

    def OnSavePreset(self, event):
        if not self._controller.IsLoggerConnected:
            self.warning_box('Logger Preset', 'Connect to ECU before saving a preset.')
            return

        with wx.FileDialog(
            self,
            'Save Logger Preset',
            wildcard='XML files (*.xml)|*.xml',
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as file_dlg:
            if file_dlg.ShowModal() != wx.ID_OK:
                return
            fpath = file_dlg.GetPath()

        root = ET.Element('LoggerPreset', version='1')
        params_node = ET.SubElement(root, 'Parameters')
        for pid in self._param_panel.get_enabled_param_ids():
            ET.SubElement(params_node, 'Parameter', id=pid)

        ext_node = ET.SubElement(root, 'ExternalSensors')
        for sensor_cfg in self._external_sensor_panel.get_preset_data():
            sensor_node = ET.SubElement(
                ext_node,
                'Sensor',
                type=str(sensor_cfg.get('type', '')),
                enabled='1' if sensor_cfg.get('enabled', False) else '0',
            )
            for key in ['name', 'port', 'baud', 'timeout_ms', 'source']:
                ET.SubElement(sensor_node, key).text = str(sensor_cfg.get(key, ''))

        tree = ET.ElementTree(root)
        tree.write(fpath, encoding='utf-8', xml_declaration=True)
        self.push_status(center='Preset saved', temporary=True)

    def OnImportPreset(self, event):
        if not self._controller.IsLoggerConnected:
            self.warning_box('Logger Preset', 'Import preset requires active ECU connection.')
            return

        with wx.FileDialog(
            self,
            'Import Logger Preset',
            wildcard='XML files (*.xml)|*.xml',
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as file_dlg:
            if file_dlg.ShowModal() != wx.ID_OK:
                return
            fpath = file_dlg.GetPath()

        try:
            tree = ET.parse(fpath)
            root = tree.getroot()

            param_ids = [
                x.attrib.get('id')
                for x in root.findall('./Parameters/Parameter')
                if x.attrib.get('id')
            ]

            sensors = []
            for snode in root.findall('./ExternalSensors/Sensor'):
                cfg = {
                    'type': snode.attrib.get('type', 'AEM X WideBand Series'),
                    'enabled': snode.attrib.get('enabled', '0') == '1',
                }
                for key in ['name', 'port', 'baud', 'timeout_ms', 'source']:
                    child = snode.find(key)
                    cfg[key] = child.text if child is not None and child.text is not None else ''

                try:
                    cfg['timeout_ms'] = int(cfg.get('timeout_ms') or 500)
                except Exception:
                    cfg['timeout_ms'] = 500
                sensors.append(cfg)

            self._param_panel.apply_enabled_param_ids(param_ids)
            self._controller.update_log_params()
            self._external_sensor_panel.apply_preset_data(sensors)

        except Exception as e:
            self.error_box('Import Preset Failed', str(e))
            return

        self.push_status(center='Preset imported', temporary=True)

    def OnStartLog(self, event):
        self._start_logging()

    def _start_logging(self):
        if not self._controller.IsLoggerConnected:
            self.warning_box('Start Log', 'Connect to ECU before starting CSV log.')
            return

        try:
            fpath = self._controller.start_log()
        except Exception as e:
            self.error_box('Start Log Failed', str(e))
            return
        self._update_logger_menu_state(True)
        self.push_status(center='CSV logging started: {}'.format(fpath), temporary=True)

    def OnStopLog(self, event):
        self._stop_logging()

    def _stop_logging(self):
        if not self._controller.IsLogging:
            self.warning_box('Stop Log', 'CSV logging is not active.')
            return

        self._controller.stop_log()
        self._update_logger_menu_state(self._controller.IsLoggerConnected)
        self.push_status(center='CSV logging stopped', temporary=True)

    def OnToggleLogButton(self, event):
        if self._controller.IsLogging:
            self._stop_logging()
        else:
            self._start_logging()

    def OnLoggerPreferences(self, event):
        dlg = PrefsDialog(self, self._controller.Preferences, sections=['Logger'])
        dlg.ShowModal()
        dlg.Destroy()

    def OnIdle(self, event):
        self._controller.check_comms()
        event.RequestMore() # ensure UI updates continuously
