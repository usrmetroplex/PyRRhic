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

import json
import logging
import os
import csv
import re
from datetime import datetime, timedelta

from pubsub import pub

from queue import Empty

from .common import _prefs_file
from .common.definitions import DefinitionManager, ROMDefinition
from .common.helpers import PyrrhicJSONEncoder, PyrrhicMessage
from .common.preferences import PreferenceManager
from .common.rom import Rom

from .comms.phy import get_all_interfaces
from .comms.protocol import get_all_protocols, TranslatorParseError
from .comms.worker import CommsWorker

_logger = logging.getLogger(__name__)

class DefinitionFound(Exception):
    pass

class PyrrhicController(object):
    "Top-level application controller"

    def __init__(self, editor_frame=None, logger_frame=None):

        self._prefs = PreferenceManager(_prefs_file)
        # create default preference file if it doesn't already exist
        if not os.path.isfile(_prefs_file):
            self.save_prefs()

        # editor-related
        self._editor_frame = editor_frame
        self._roms = {}

        # logger-related
        self._available_interfaces = {}
        self._logger_frame = logger_frame
        self._comms_worker = None
        self._comms_translator = None
        self._logger_connect_started = None
        self._logger_connect_timeout = timedelta(seconds=10)
        self._csv_log_fp = None
        self._csv_log_writer = None
        self._csv_log_params = []
        self._csv_log_started_at = None
        self._external_log_params = []

        self._defmgr = DefinitionManager(
            ecuflashRoot=self._prefs['ECUFlashRepo'].Value,
            rrlogger_path=self._prefs['RRLoggerDef'].Value
        )

        pub.subscribe(self.live_tune_pull, 'livetune.state.pull.init')
        pub.subscribe(self.live_tune_push, 'livetune.state.push.init')
        pub.subscribe(self.update_external_log_params, 'logger.external.updated')

        self.refresh_interfaces()

# Preferences
    def process_preferences(self):
        "Resolve state after any preference changes"

        ecuflash_repo_dir = self._prefs['ECUFlashRepo'].Value
        rrlogger_file = self._prefs['RRLoggerDef'].Value

        if ecuflash_repo_dir:
            self._defmgr.load_ecuflash_repository(ecuflash_repo_dir)
        if rrlogger_file:
            self._defmgr.load_rrlogger_file(rrlogger_file)

        self._editor_frame.refresh_tree()

    def save_prefs(self):

        with open(_prefs_file, 'w') as fp:
            _logger.info('Saving preferences to {}'.format(_prefs_file))
            json.dump(self._prefs, fp, cls=PyrrhicJSONEncoder, indent=4)

# Editor
    def open_rom(self, fpath):
        "Load the given filepath as a ROM image"

        if fpath in self._roms:
            self._editor_frame.push_status(
                'ROM {} already opened'.format(os.path.basename(fpath))
            )
            return

        defn = None

        _logger.debug('Loading ROM image {}'.format(fpath))

        # load raw image bytes
        with open(fpath, 'rb') as fp:
            rom_bytes = fp.read()

        # inspect bytes at all internal ID addresses specified in definitions
        try:
            for addr in self._defmgr.ECUFlashEditorSearchTree:
                len_tree = self._defmgr.ECUFlashEditorSearchTree[addr]

                for nbytes in len_tree:
                    vals = len_tree[nbytes]

                    id_bytes = rom_bytes[addr:addr + nbytes]
                    if id_bytes in vals:
                        defn = vals[id_bytes]
                        raise DefinitionFound

        except DefinitionFound:
            defn.resolve_dependencies(self._defmgr.ECUFlashDefs)
            d = ROMDefinition(EditorDef=defn)
            self._roms[fpath] = Rom(fpath, rom_bytes, d)
            return

        except Exception as e:
            raise

        self._editor_frame.error_box(
            'Undefined ROM',
            'Unable to find matching definition for ROM'
        )

# Logger
    def refresh_interfaces(self):
        self._available_interfaces = get_all_interfaces()

    def get_supported_protocols(self, interface_name):
        "`list` of `str` indicating protocols supported by the given interface"
        ret = []

        iface_phys = self._available_interfaces.get(interface_name, None)
        if iface_phys is None:
            _logger.warn(('Selected interface "{}" no longer available, try'
                ' refreshing available interfaces and try again').format(
                    interface_name
                )
            )
            return []

        protocols = get_all_protocols()
        for protocol_name in protocols:
            protocol, query = protocols[protocol_name]
            if protocol._supported_phy <= iface_phys:
                ret.append(protocol_name)

        return ret

    def spawn_logger(self, interface_name, protocol_name):
        iface_phys = self._available_interfaces.get(interface_name)
        if iface_phys is None:
            pub.sendMessage('logger.status', center='Selected interface is not available', temporary=True)
            pub.sendMessage('logger.connection.change', connected=False)
            return

        protocols = get_all_protocols()
        if protocol_name not in protocols:
            pub.sendMessage('logger.status', center='Selected protocol is not available', temporary=True)
            pub.sendMessage('logger.connection.change', connected=False)
            return

        protocol, translator = protocols[protocol_name]

        # get specific `CommunicationDevice` subclass for this protocol
        phy = list(protocol._supported_phy.intersection(iface_phys))[0]

        try:
            # create the worker and spawn the new thread
            self._comms_worker = CommsWorker(interface_name, phy, protocol)
            self._comms_worker.start()
            self._logger_connect_started = datetime.now()

            # instantiate the appropriate `EndpointTranslator`
            self._comms_translator = translator()

        except Exception as e:
            self._comms_worker = None
            self._comms_translator = None
            self._logger_connect_started = None

            err = str(e)
            if (
                'ERR_DEVICE_NOT_CONNECTED' in err
                or 'Device ID invalid' in err
            ):
                msg = 'Device not found'
                _logger.error(msg)
            else:
                msg = 'Logger connection failed'
                _logger.error('{}: {}'.format(msg, err))

            pub.sendMessage('logger.status', center=msg, temporary=True)
            pub.sendMessage('logger.connection.change', connected=False)

    def kill_logger(self):
        was_connected = (
            self._comms_translator is not None
            and self._comms_translator.Definition is not None
        )
        self._logger_connect_started = None

        if self._comms_worker:
            _logger.debug('Killing communication thread')

            # signal comms thread to stop
            self._comms_worker.join()

            if was_connected:
                _logger.info('Logger disconnected')
            else:
                _logger.info('Logger connect attempt cancelled')
                pub.sendMessage(
                    'logger.status',
                    center='Connection cancelled',
                    temporary=True
                )
            self._comms_worker = None

        pub.sendMessage('logger.connection.change', connected=False)

        # remove all parameters from UI
        pub.sendMessage('logger.query.updated', params=[])
        self.stop_log()
        if self._comms_translator:
            for p in (
                self._comms_translator.EnabledParams
                + self._comms_translator.EnabledSwitches
            ):
                p.disable()

        self._comms_translator = None

    def check_comms(self):
        "Idle event handler that checks logging thread for updates."
        if self._comms_worker is not None:
            if (
                self._logger_connect_started is not None
                and self._comms_translator is not None
                and self._comms_translator.Definition is None
                and (datetime.now() - self._logger_connect_started) > self._logger_connect_timeout
            ):
                _logger.warning('Connection timeout')
                pub.sendMessage(
                    'logger.status',
                    center='Connection timeout - no endpoint response',
                    temporary=True
                )
                self.kill_logger()
                return

            try:
                item = self._comms_worker.OutQueue.get(False)
            except Empty as e:
                item = None

            if item:
                msg = item.Message
                time = item.RawTimestamp
                data = item.Data
                if msg == 'Init':
                    self._logger_init(data)
                elif msg == 'LogQueryResponse':

                    try:
                        self._comms_translator.extract_values(data)
                    except TranslatorParseError as e:
                        pub.sendMessage('logger.status',
                            center=str(e), temporary=True
                        )
                        return

                    pub.sendMessage('logger.freq.updated',
                        avg_freq=self._comms_translator.AverageFreq
                    )
                    pub.sendMessage('logger.params.updated')
                    self._write_csv_log_row(time)

                elif msg == 'LiveTuneResponse':

                    try:
                        self._comms_translator.extract_livetune_state(data)

                    except TranslatorParseError as e:
                        _logger.warning(str(e))

                    else:
                        req = self._comms_translator.generate_livetune_query()

                        # send next (or blank) query to worker
                        self._comms_worker.InQueue.put(
                            PyrrhicMessage('LiveTuneQuery', req)
                        )

                        if not req:
                            pub.sendMessage('livetune.state.pull.complete')

                elif msg == 'LiveTuneVerify':
                    self._comms_translator.validate_livetune_write()
                    req = self._comms_translator.generate_livetune_write()
                    self._comms_worker.InQueue.put(
                        PyrrhicMessage('LiveTuneWrite', req)
                    )

                    if not req:
                        pub.sendMessage('livetune.state.push.complete')

                elif msg == 'Exception':
                    raise data

    def update_log_params(self):
        if self._comms_worker is not None:

            # get new request and push it to worker thread
            req = self._comms_translator.generate_log_request()
            self._comms_worker.InQueue.put(
                PyrrhicMessage('LogQuery', req)
            )

            # send enabled parameters to logger frame for gauge updates
            params = self._comms_translator.EnabledParams
            switches = self._comms_translator.EnabledSwitches
            pub.sendMessage('logger.query.updated', params=(params + switches))

    def live_tune_pull(self):
        if self._comms_worker is not None:

            req = self._comms_translator.generate_livetune_query()
            if req:
                self._comms_worker.InQueue.put(
                    PyrrhicMessage('LiveTuneQuery', req)
                )
                pub.sendMessage('livetune.state.pending')

    def start_log(self, filepath=None):
        if filepath is None:
            filepath = self._generate_log_filepath()

        if not self.IsLoggerConnected:
            raise RuntimeError('Logger is not connected')

        if self.IsLogging:
            raise RuntimeError('CSV logging is already active')

        params = (
            self._comms_translator.EnabledParams
            + self._comms_translator.EnabledSwitches
            + self._external_log_params
        )
        if not params:
            raise ValueError('No parameters selected. Enable at least one parameter before starting log.')

        self._csv_log_params = list(params)
        self._csv_log_started_at = datetime.now()
        self._csv_log_fp = open(filepath, 'w', newline='', encoding='utf-8')
        self._csv_log_writer = csv.writer(self._csv_log_fp)
        headers = ['Time (msec)', *[p.Name for p in self._csv_log_params]]
        self._csv_log_writer.writerow(headers)
        self._csv_log_fp.flush()
        _logger.info('Started CSV logging: {}'.format(filepath))
        return filepath

    def update_external_log_params(self, params):
        self._external_log_params = list(params) if params else []

    def _generate_log_filepath(self):
        log_dir = self._prefs['LogOutputDir'].Value
        if not log_dir or not os.path.isdir(log_dir):
            raise RuntimeError('Invalid logger output directory in preferences')

        append = self._prefs['LogFileAppend'].Value or ''
        append = append.strip()
        append = re.sub(r'[<>:"/\\|?*]+', '_', append)

        timestamp = datetime.now().strftime('%d%m%Y%H%M')
        base_name = '{}_{}'.format(append, timestamp) if append else timestamp

        fpath = os.path.join(log_dir, '{}.csv'.format(base_name))
        seq = 1
        while os.path.exists(fpath):
            fpath = os.path.join(log_dir, '{}_{}.csv'.format(base_name, seq))
            seq += 1

        return fpath

    def stop_log(self):
        if self._csv_log_fp is not None:
            try:
                self._csv_log_fp.close()
            except Exception:
                pass

        self._csv_log_fp = None
        self._csv_log_writer = None
        self._csv_log_params = []
        self._csv_log_started_at = None

    def _write_csv_log_row(self, timestamp):
        if not self.IsLogging:
            return

        try:
            if self._csv_log_started_at is None:
                self._csv_log_started_at = timestamp

            elapsed_ms = int((timestamp - self._csv_log_started_at).total_seconds() * 1000)
            vals = [
                p.ValueStr if p is not None and p.ValueStr is not None else ''
                for p in self._csv_log_params
            ]

            row = [elapsed_ms, *vals]
            self._csv_log_writer.writerow(row)
            self._csv_log_fp.flush()

        except Exception as e:
            _logger.error('CSV logging failed: {}'.format(str(e)))
            self.stop_log()
            pub.sendMessage('logger.status', center='CSV logging stopped (write error)', temporary=True)

    def live_tune_push(self):
        if self._comms_worker is not None:

            req = self._comms_translator.generate_livetune_write()
            if req:
                self._comms_worker.InQueue.put(
                    PyrrhicMessage('LiveTuneWrite', req)
                )
                pub.sendMessage('livetune.state.pending')

    def sync_live_tune(self):
        if self._comms_worker is not None:

            self._comms_translator.generate_livetune

    def _logger_init(self, init_data):
        """
        Arguments:
        - `init_data`: 4-tuple containing logging initialization data:
            `(LoggerProtocol, LoggerEndpoint, identifier, raw_data)`
        """
        protocol, endpoint, identifier, capabilities = init_data
        _logger.debug('Received {} {} init'.format(protocol.name, endpoint.name))
        _logger.debug('Identifier: {}'.format(identifier))
        _logger.debug('Raw Bytes: {}'.format(capabilities.hex()))

        defs = self._defmgr.Definitions[protocol].get(identifier, None)
        if defs is not None:

            # for logger init, CALID unimportant, so just pick first definition
            definition = next(iter(defs.values()))
            logger_def = definition.LoggerDef
            logger_def.resolve_dependencies(self._defmgr.RRLoggerDefs[protocol])
            logger_def.resolve_valid_params(capabilities)
            _logger.info(
                'Connected to {}: {}'.format(endpoint.name, identifier)
            )

            self._comms_translator.Definition = definition
            self._logger_connect_started = None
            pub.sendMessage('logger.connection.change', translator=self._comms_translator)

            # check if a ROM corresponding to the initialized ECU has been loaded
            if self._roms:
                loaded_roms = set([
                    x.Definition.EditorID for x in self._roms.values()
                ])
                compatible_roms = set(defs.keys())
                matching_roms = loaded_roms.intersection(compatible_roms)

                # for any matching loaded roms, if the definition for this
                # loaded ROM is a ROMDefinition only containing editor defs
                for editor_id in matching_roms:
                    roms = filter(
                        lambda x: (
                            x.Definition.EditorID == editor_id
                            and x.Definition.LoggerDef is None
                        ),
                        self._roms.values()
                    )
                    for rom in roms:
                        rom.Definition = defs[editor_id]

                rom = None

                if len(matching_roms) == 1:
                    editor_id = next(iter(matching_roms))
                    rom = next(filter(
                        lambda x: x.Definition.EditorID == editor_id,
                        self._roms.values()
                    ))
                    self._comms_translator.instantiate_livetune(rom)

                    if self._comms_translator.SupportsLiveTune:
                        pub.sendMessage(
                            'editor.livetune.enable',
                            livetune=self._comms_translator.LiveTuneData
                        )

        else:
            _logger.info(
                'Unable to find logger definition for endpoint {}'.format(
                    identifier
                )
            )
            self.kill_logger()

# Properties
    @property
    def LoadedROMs(self):
        return self._roms

    @property
    def ModifiedROMs(self):
        return {k: v for k, v in self._roms.items() if v.IsModified}

    @property
    def Preferences(self):
        return self._prefs

    @property
    def DefsValid(self):
        return self._defmgr.IsValid

    @property
    def EditorFrame(self):
        return self._editor_frame

    @EditorFrame.setter
    def EditorFrame(self, frame):
        self._editor_frame = frame

    @property
    def LoggerFrame(self):
        return self._logger_frame

    @LoggerFrame.setter
    def LoggerFrame(self, frame):
        self._logger_frame = frame

    @property
    def AvailableInterfaces(self):
        return self._available_interfaces

    @property
    def CommsWorker(self):
        return self._comms_worker

    @property
    def IsLoggerConnected(self):
        return (
            self._comms_worker is not None
            and self._comms_translator is not None
            and self._comms_translator.Definition is not None
        )

    @property
    def IsLogging(self):
        return self._csv_log_writer is not None
