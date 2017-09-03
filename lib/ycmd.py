#!/usr/bin/env python3

'''
lib/ycmd.py
High-level helpers for managing the youcompleteme daemon.
'''

import http
import logging
import os
import socket
import tempfile

# for type annotations only:
import io       # noqa: F401

from lib.fs import (
    is_directory,
    is_file,
    get_directory_name,
    load_json_file,
    save_json_file,
    default_python_binary_path,
)
from lib.jsonmodels import (
    parse_completion_options,
)
from lib.process import (
    SYprocess,
    SYfileHandles,
)
from lib.strutils import (
    truncate,
    new_hmac_secret,
    calculate_hmac,
    format_json,
    parse_json,
    base64_encode,
    bytes_to_str,
    str_to_bytes,
)

logger = logging.getLogger('sublime-ycmd.' + __name__)
# special logger instance for use in the server class
# this logger uses a filter to add server information to all log statements
server_logger = logging.getLogger('sublime-ycmd.' + __name__ + '.server')

# most constants were taken from the ycmd example client:
# https://github.com/Valloric/ycmd/blob/master/examples/example_client.py

# the missing ones were taken from the ycmd handler logic:
# https://github.com/Valloric/ycmd/blob/master/ycmd/handlers.py

YCMD_HMAC_HEADER = 'X-Ycm-Hmac'
YCMD_HMAC_SECRET_LENGTH = 16
# YCMD_SERVER_IDLE_SUICIDE_SECONDS = 30       # 30 secs
YCMD_SERVER_IDLE_SUICIDE_SECONDS = 5 * 60   # 5 mins
# YCMD_SERVER_IDLE_SUICIDE_SECONDS = 3 * 60 * 60  # 3 hrs
YCMD_MAX_SERVER_WAIT_TIME_SECONDS = 5

YCMD_HANDLER_GET_COMPLETIONS = '/completions'
YCMD_HANDLER_RUN_COMPLETER_COMMAND = '/run_completer_command'
YCMD_HANDLER_EVENT_NOTIFICATION = '/event_notification'
YCMD_HANDLER_DEFINED_SUBCOMMANDS = '/defined_subcommands'
YCMD_HANDLER_DETAILED_DIAGNOSTIC = '/detailed_diagnostic'
YCMD_HANDLER_LOAD_EXTRA_CONF = '/load_extra_conf_file'
YCMD_HANDLER_IGNORE_EXTRA_CONF = '/ignore_extra_conf_file'
YCMD_HANDLER_DEBUG_INFO = '/debug_info'
YCMD_HANDLER_SHUTDOWN = '/shutdown'

YCMD_COMMAND_GET_TYPE = 'GetType'
YCMD_COMMAND_GET_PARENT = 'GetParent'
YCMD_COMMAND_GO_TO_DECLARATION = 'GoToDeclaration'
YCMD_COMMAND_GO_TO_DEFINTION = 'GoToDefinition'
YCMD_COMMAND_GO_TO = 'GoTo'
YCMD_COMMAND_GO_TO_IMPRECISE = 'GoToImprecise'
YCMD_COMMAND_CLEAR_COMPILATION_FLAG_CACHE = 'ClearCompilationFlagCache'

YCMD_EVENT_FILE_READY_TO_PARSE = 'FileReadyToParse'
YCMD_EVENT_BUFFER_UNLOAD = 'BufferUnload'
YCMD_EVENT_BUFFER_VISIT = 'BufferVisit'
YCMD_EVENT_INSERT_LEAVE = 'InsertLeave'
YCMD_EVENT_CURRENT_IDENTIFIER_FINISHED = 'CurrentIdentifierFinished'


class SYserver(object):
    '''
    Self-contained ycmd server object. Creates and maintains a persistent
    connection to a ycmd server process. Provides a simple-ish way to send
    API requests to the backend, including control functions like stopping and
    pinging the server.
    TODO : Run all this stuff off-thread.
    '''

    def __init__(self, process_handle=None,
                 hostname=None, port=None, hmac=None, label=None):

        self._process_handle = process_handle

        self._hostname = hostname
        self._port = port
        self._hmac = hmac
        self._label = label

        self._reset_logger()

    def stop(self, hard=False):
        if not self.alive():
            return

        if hard:
            self._process_handle.kill()
        else:
            self._send_request(YCMD_HANDLER_SHUTDOWN, method='POST')

    def alive(self):
        if not self._process_handle:
            self._logger.debug('no process handle, ycmd server must be dead')
            return False

        assert isinstance(self._process_handle, SYprocess), \
            '[internal] process handle is not SYprocess: %r' % \
            (self._process_handle)
        # TODO : Also use the '/healthy' handler to check if it's alive.
        return self._process_handle.alive()

    def communicate(self, inpt=None, timeout=None):
        if not self._process_handle:
            self._logger.debug('no process handle, cannot get process output')
            return None, None

        assert isinstance(self._process_handle, SYprocess), \
            '[internal] process handle is not SYprocess: %r' % \
            (self._process_handle)
        return self._process_handle.communicate(inpt=inpt, timeout=timeout)

    def _generate_hmac_header(self, method, path, body=None):
        if body is None:
            body = b''
        assert isinstance(body, bytes), 'body must be bytes: %r' % (body)

        content_hmac = calculate_hmac(
            self._hmac, method, path, body,
        )

        return {
            YCMD_HMAC_HEADER: content_hmac,
        }

    def _send_request(self, handler, params=None, method=None):
        '''
        Sends a request to the associated ycmd server and returns the response.
        The `handler` should be one of the ycmd handler constants.
        If `params` are supplied, it should be either a string (to use )
        If `method` is provided, it should be an HTTP verb (e.g. 'GET',
        'POST'). If omitted, it is set to 'GET' when no parameters are given,
        and 'POST' otherwise.
        '''
        has_params = params is not None

        body = format_json(params) if has_params else None
        if isinstance(body, str):
            body = str_to_bytes(body)

        if not method:
            method = 'GET' if not params else 'POST'

        hmac_headers = self._generate_hmac_header(method, handler, body)
        content_type_headers = \
            {'Content-Type': 'application/json'} if has_params else None

        headers = {}
        if hmac_headers:
            headers.update(hmac_headers)
        if content_type_headers:
            headers.update(content_type_headers)

        self._logger.debug(
            'about to send a request with '
            'method, handler, params, headers: %s, %s, %s, %s',
            method, handler, truncate(params), truncate(headers),
        )

        response_status = None
        response_reason = None
        response_headers = None
        response_data = None
        try:
            connection = http.client.HTTPConnection(
                host=self.hostname, port=self.port,
            )
            connection.request(
                method=method,
                url=handler,
                body=body,
                headers=headers,
            )

            response = connection.getresponse()

            response_status = response.status
            response_reason = response.reason

            # TODO : Move http response logic somewhere else.
            response_headers = response.getheaders()
            response_content_type = response.getheader('Content-Type')
            response_content_length = response.getheader('Content-Length', 0)
            self._logger.critical('[TODO] verify hmac for response')

            try:
                response_content_length = int(response_content_length)
            except ValueError:
                pass

            if response_content_length > 0:
                response_content = response.read()
                # TODO : EAFP, always try parsing as JSON.
                if response_content_type == 'application/json':
                    response_data = parse_json(response_content)
                else:
                    response_data = response_content
        except http.client.HTTPException as e:
            self._logger.error('error during ycmd request: %s', e)
        except ConnectionError as e:
            self._logger.error(
                'connection error, ycmd server may be dead: %s', e,
            )

        self._logger.critical(
            '[REMOVEME] parsed status, reason, headers, data: %s, %s, %s, %s',
            response_status, response_reason, response_headers, response_data,
        )

        return response_data

    def get_completer_commands(self):
        return self._send_request(
            YCMD_HANDLER_DEFINED_SUBCOMMANDS,
            params={
                'completer_target': 'identifier',
            },
            method='POST',
        )

    def get_debug_info(self):
        return self._send_request(
            YCMD_HANDLER_DEBUG_INFO,
            params={},
            method='POST',
        )

    def get_code_completions(self, file_path,
                             file_contents=None, file_types=None,
                             line_num=1, column_num=1, extra_params=None):
        if file_contents is None:
            file_contents = ''
        assert isinstance(file_contents, str), \
            'file contents must be a str: %s' % (file_contents)
        # TODO : Refactor between this and `_notify_event`.

        if not file_types:
            # TODO : Figure out the proper generic file type for ycmd.
            self._logger.warning(
                '[TODO] Using generic file type, might be wrong: text',
            )
            file_types = ['text']
        elif not isinstance(file_types, (list, tuple)):
            file_types = [file_types]
        assert isinstance(file_types, (list, tuple)), \
            'file types must be a list: %r' % (file_types)

        assert extra_params is None or isinstance(extra_params, dict), \
            'extra data must be a dict: %r' % (extra_params)

        params = {
            'filepath': file_path,
            'file_data': {
                file_path: {
                    'filetypes': file_types,
                    'contents': file_contents,
                },
            },

            'line_num': line_num,
            'column_num': column_num,
        }

        if extra_params:
            params.update(extra_params)

        completion_data = self._send_request(
            YCMD_HANDLER_GET_COMPLETIONS,
            params=params,
            method='POST',
        )
        self._logger.debug(
            'received completion results: %s', truncate(completion_data),
        )

        # completions = parse_completion_options(completion_data, params)
        self._logger.warning('[TODO] pass in request parameters')
        completions = parse_completion_options(completion_data)
        self._logger.debug('parsed completions: %r', completions)

        return completions

    def _notify_event(self, event_name, file_path,
                      file_contents=None, file_types=None,
                      line_num=1, column_num=1, extra_params=None):
        if file_contents is None:
            file_contents = ''
        assert isinstance(file_contents, str), \
            'file contents must be a str: %s' % (file_contents)

        if not file_types:
            # TODO : Figure out the proper generic file type for ycmd.
            self._logger.warning(
                '[TODO] Using generic file type, might be wrong: text',
            )
            file_types = ['text']
        elif not isinstance(file_types, (list, tuple)):
            file_types = [file_types]
        assert isinstance(file_types, (list, tuple)), \
            'file types must be a list: %r' % (file_types)

        assert extra_params is None or isinstance(extra_params, dict), \
            'extra data must be a dict: %r' % (extra_params)

        params = {
            'event_name': event_name,

            'filepath': file_path,
            'file_data': {
                file_path: {
                    'filetypes': file_types,
                    'contents': file_contents,
                },
            },

            'line_num': line_num,
            'column_num': column_num,
        }

        if extra_params:
            params.update(extra_params)

        self._logger.debug(
            'sending event notification for event: %s', event_name,
        )

        return self._send_request(
            YCMD_HANDLER_EVENT_NOTIFICATION,
            params=params,
            method='POST',
        )

    def notify_file_ready_to_parse(self, file_path,
                                   file_contents=None, file_types=None,
                                   line_num=1, column_num=1,
                                   extra_params=None):
        return self._notify_event(
            YCMD_EVENT_FILE_READY_TO_PARSE,
            file_path=file_path,
            file_contents=file_contents,
            file_types=file_types,
            line_num=line_num,
            column_num=column_num,
            extra_params=extra_params,
        )

    def notify_buffer_enter(self, file_path,
                            file_contents=None, file_types=None,
                            line_num=1, column_num=1, extra_params=None):
        return self._notify_event(
            YCMD_EVENT_BUFFER_VISIT,
            file_path=file_path,
            file_contents=file_contents,
            file_types=file_types,
            line_num=line_num,
            column_num=column_num,
            extra_params=extra_params,
        )

    def notify_buffer_leave(self, file_path,
                            file_contents=None, file_types=None,
                            line_num=1, column_num=1, extra_params=None):
        return self._notify_event(
            YCMD_EVENT_BUFFER_UNLOAD,
            file_path=file_path,
            file_contents=file_contents,
            file_types=file_types,
            line_num=line_num,
            column_num=column_num,
            extra_params=extra_params,
        )

    def notify_leave_insert_mode(self, file_path,
                                 file_contents=None, file_types=None,
                                 line_num=1, column_num=1, extra_params=None):
        return self._notify_event(
            YCMD_EVENT_INSERT_LEAVE,
            file_path=file_path,
            file_contents=file_contents,
            file_types=file_types,
            line_num=line_num,
            column_num=column_num,
            extra_params=extra_params,
        )

    def notify_current_identifier_finished(self, file_path,
                                           file_contents=None, file_types=None,
                                           line_num=1, column_num=1,
                                           extra_params=None):
        return self._notify_event(
            YCMD_EVENT_CURRENT_IDENTIFIER_FINISHED,
            file_path=file_path,
            file_contents=file_contents,
            file_types=file_types,
            line_num=line_num,
            column_num=column_num,
            extra_params=extra_params,
        )

    @property
    def hostname(self):
        if not self._hostname:
            self._logger.warning('server hostname is not set')
        return self._hostname

    @hostname.setter
    def hostname(self, hostname):
        if not isinstance(hostname, str):
            self._logger.warning('hostname is not a str: %r', hostname)
        self._hostname = hostname
        self._reset_logger()

    @property
    def port(self):
        if not self._port:
            self._logger.warning('server port is not set')
        return self._port

    @port.setter
    def port(self, port):
        if not isinstance(port, int):
            self._logger.warning('port is not an int: %r', port)
        self._port = port
        self._reset_logger()

    @property
    def hmac(self):
        self._logger.error('returning server hmac secret... '
                           'nobody else should need it...')
        return self._hmac

    @hmac.setter
    def hmac(self, hmac):
        if not isinstance(hmac, str):
            self._logger.warning('server hmac secret is not a str: %r', hmac)
        self._hmac = hmac

    @property
    def label(self):
        return self._label

    @label.setter
    def label(self, label):
        if not isinstance(label, str):
            self._logger.warning('server label is not a str: %r', label)
        self._label = label

    def _reset_logger(self):
        self._logger = SYserverLoggerAdapter(server_logger, {
            'hostname': self._hostname or '?',
            'port': self._port or '?',
        })

    def pretty_str(self):
        label_desc = ' "%s"' % (self._label) if self._label else ''
        server_desc = 'ycmd server%s' % (label_desc)

        if not self._hmac:
            return '%s - null' % (server_desc)

        if self._hostname is None or self._port is None:
            return '%s - unknown' % (server_desc)

        return '%s - %s:%d' % (server_desc, self._hostname, self._port)

    def __str__(self):
        return '%s:%s' % (self._hostname or '', self._port or '')


def get_ycmd_default_settings_path(ycmd_root_directory):
    if not is_directory(ycmd_root_directory):
        logger.warning('invalid ycmd root directory: %s', ycmd_root_directory)
        # but whatever, fall through and provide the expected path anyway

    return os.path.join(ycmd_root_directory, 'ycmd', 'default_settings.json')


def generate_settings_data(ycmd_settings_path, hmac_secret):
    '''
    Generates and returns a settings `dict` containing the options for
    starting a ycmd server. This settings object should be written to a JSON
    file and supplied as a command-line argument to the ycmd module.
    The `hmac_secret` argument should be the binary-encoded HMAC secret. It
    will be base64-encoded before adding it to the settings object.
    '''
    assert isinstance(ycmd_settings_path, str), \
        'ycmd settings path must be a str: %r' % (ycmd_settings_path)
    if not is_file(ycmd_settings_path):
        logger.warning(
            'ycmd settings path appears to be invalid: %r', ycmd_settings_path
        )

    ycmd_settings = load_json_file(ycmd_settings_path)
    logger.debug('loaded ycmd settings: %s', ycmd_settings)

    assert isinstance(ycmd_settings, dict), \
        'ycmd settings should be valid json: %r' % (ycmd_settings)

    # WHITELIST
    # Enable for everything. This plugin will decide when to send requests.
    if 'filetype_whitelist' not in ycmd_settings:
        logger.warning(
            'ycmd settings template is missing the '
            'filetype_whitelist placeholder'
        )
    ycmd_settings['filetype_whitelist'] = {}
    ycmd_settings['filetype_whitelist']['*'] = 1

    # BLACKLIST
    # Disable for nothing. This plugin will decide what to ignore.
    if 'filetype_blacklist' not in ycmd_settings:
        logger.warning(
            'ycmd settings template is missing the '
            'filetype_blacklist placeholder'
        )
    ycmd_settings['filetype_blacklist'] = {}

    # HMAC
    # Pass in the hmac parameter. It needs to be base-64 encoded first.
    if 'hmac_secret' not in ycmd_settings:
        logger.warning(
            'ycmd settings template is missing the hmac_secret placeholder'
        )

    if not isinstance(hmac_secret, bytes):
        logger.warning(
            'hmac secret was not passed in as binary, it might be incorrect'
        )
    else:
        logger.debug('converting hmac secret to base64')
        hmac_secret_binary = hmac_secret
        hmac_secret_encoded = base64_encode(hmac_secret_binary)
        hmac_secret_str = bytes_to_str(hmac_secret_encoded)
        hmac_secret = hmac_secret_str

    ycmd_settings['hmac_secret'] = hmac_secret

    # MISC
    # Settings to ensure that the ycmd server is enabled whenever possible.
    ycmd_settings['min_num_of_chars_for_completion'] = 0
    ycmd_settings['min_num_identifier_candidate_chars'] = 0
    ycmd_settings['collect_identifiers_from_comments_and_strings'] = 1
    ycmd_settings['complete_in_comments'] = 1
    ycmd_settings['complete_in_strings'] = 1

    return ycmd_settings


def start_ycmd_server(ycmd_root_directory,
                      ycmd_settings_path=None,
                      ycmd_python_binary_path=None,
                      working_directory=None):
    assert isinstance(ycmd_root_directory, str), \
        'ycmd root directory must be a str: %r' % (ycmd_root_directory)

    if ycmd_settings_path is None:
        ycmd_settings_path = \
            get_ycmd_default_settings_path(ycmd_root_directory)
    assert isinstance(ycmd_settings_path, str), \
        'ycmd settings path must be a str: %r' % (ycmd_settings_path)

    if ycmd_python_binary_path is None:
        ycmd_python_binary_path = default_python_binary_path()
    assert isinstance(ycmd_python_binary_path, str), \
        'ycmd python binary path must be a str: %r' % (ycmd_python_binary_path)

    if working_directory is None:
        working_directory = os.getcwd()
    assert isinstance(working_directory, str), \
        'working directory must be a str: %r' % (working_directory)

    ycmd_module_directory = os.path.join(ycmd_root_directory, 'ycmd')

    logger.debug(
        'preparing to start ycmd server with '
        'ycmd path, default settings path, python binary path, '
        'working directory: %s, %s, %s, %s',
        ycmd_root_directory, ycmd_settings_path,
        ycmd_python_binary_path, working_directory,
    )

    ycmd_hmac_secret = new_hmac_secret(num_bytes=YCMD_HMAC_SECRET_LENGTH)
    ycmd_settings_data = \
        generate_settings_data(ycmd_settings_path, ycmd_hmac_secret)

    # no point using `with` for this, since we also use `delete=True`
    temp_file_object = tempfile.NamedTemporaryFile(
        prefix='ycmd_settings_', suffix='.json', delete=False,
    )
    temp_file_name = temp_file_object.name
    temp_file_handle = temp_file_object.file    # type: io.TextIOWrapper

    save_json_file(temp_file_handle, ycmd_settings_data)

    temp_file_handle.flush()
    temp_file_object.close()

    logger.critical('[REMOVEME] generating temporary files for log output')
    '''
    stdout_file_object = tempfile.NamedTemporaryFile(
        prefix='ycmd_stdout_', suffix='.log', delete=False,
    )
    stderr_file_object = tempfile.NamedTemporaryFile(
        prefix='ycmd_stderr_', suffix='.log', delete=False,
    )
    stdout_file_name = stdout_file_object.name
    stderr_file_name = stderr_file_object.name
    stdout_file_object.close()
    stderr_file_object.close()
    '''
    tempdir = tempfile.gettempdir()
    alnum_working_directory = \
        ''.join(c if c.isalnum() else '_' for c in working_directory)
    stdout_file_name = os.path.join(
        tempdir, 'ycmd_stdout_%s.log' % (alnum_working_directory)
    )
    stderr_file_name = os.path.join(
        tempdir, 'ycmd_stderr_%s.log' % (alnum_working_directory)
    )

    logger.critical(
        '[REMOVEME] keeping log files for stdout, stderr: %s, %s',
        stdout_file_name, stderr_file_name,
    )

    ycmd_process_handle = SYprocess()
    ycmd_server_hostname = '127.0.0.1'
    ycmd_server_port = _get_unused_port(ycmd_server_hostname)
    ycmd_server_label = get_directory_name(working_directory)

    ycmd_process_handle.binary = ycmd_python_binary_path
    ycmd_process_handle.args.extend([
        ycmd_module_directory,
        '--host=%s' % (ycmd_server_hostname),
        '--port=%s' % (ycmd_server_port),
        '--idle_suicide_seconds=%s' % (YCMD_SERVER_IDLE_SUICIDE_SECONDS),
        '--check_interval_seconds=%s' % (YCMD_MAX_SERVER_WAIT_TIME_SECONDS),
        '--options_file=%s' % (temp_file_name),
        # XXX : REMOVE ME - testing only
        '--log=debug',
        '--stdout=%s' % (stdout_file_name),
        '--stderr=%s' % (stderr_file_name),
        '--keep_logfiles',
    ])
    ycmd_process_handle.cwd = working_directory

    # don't start it up just yet... set up the return value while we can
    ycmd_server = SYserver(
        process_handle=ycmd_process_handle,
        hostname=ycmd_server_hostname,
        port=ycmd_server_port,
        hmac=ycmd_hmac_secret,
        label=ycmd_server_label,
    )

    ycmd_process_handle.filehandles.stdout = SYfileHandles.PIPE
    ycmd_process_handle.filehandles.stderr = SYfileHandles.PIPE

    try:
        ycmd_process_handle.start()
    except ValueError as e:
        logger.critical('failed to launch ycmd server, argument error: %s', e)
    except OSError as e:
        logger.warning('failed to launch ycmd server, system error: %s', e)
    finally:
        pass
        # TODO : Add this into the SYserver logic.
        #        It should check that the file is deleted after exit.
        '''
        if is_file(temp_file_name):
            # was not removed by startup, so we should clean up after it...
            os.remove(temp_file_name)
        '''

    if not ycmd_process_handle.alive():
        stdout, stderr = ycmd_process_handle.communicate(timeout=0)
        logger.error('failed to launch ycmd server, error output: %s', stderr)

    return ycmd_server


def _get_unused_port(interface='127.0.0.1'):
    ''' Finds an available port for the ycmd server process to listen on. '''
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((interface, 0))

    port = s.getsockname()[1]
    logger.debug('found unused port: %d', port)

    s.close()
    return port


class SYserverLoggerAdapter(logging.LoggerAdapter):
    def __init__(self, logger, extra=None):
        super(SYserverLoggerAdapter, self).__init__(logger, extra or {})

    def process(self, msg, kwargs):
        server_id = '(%s:%s)' % (
            self.extra.get('hostname', '?'),
            self.extra.get('port', '?'),
        )

        return '%-16s %s' % (server_id, msg), kwargs
