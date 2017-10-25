#!/usr/bin/env python3

'''
lib/ycmd/server.py
Server abstraction layer.

Defines a server class that represents a connection to a ycmd server process.
Information about the actual server process is available via the properties.

The ycmd server handlers are exposed as methods on this class. To send a
request to the server process, call the method, and it will package up the
parameters and send the request. These calls will block, and return the result
of the request (or raise an exception for unexpected errors).

NOTE : This uses `http` instead of `urllib`, as `urllib` raises exceptions when
       the server responds with an error status code. This prevents fetching
       the response body to parse/retrieve the error message.
'''

import http
import logging
import os
import threading

from lib.process import Process
from lib.schema.completions import parse_completions
from lib.schema.request import RequestParameters
from lib.util.format import (
    json_serialize,
    json_parse,
)
from lib.util.fs import (
    is_file,
    get_base_name,
)
from lib.util.hmac import (
    calculate_hmac,
    new_hmac_secret,
)
from lib.util.lock import lock_guard
from lib.util.str import (
    str_to_bytes,
    truncate,
)
from lib.util.sys import get_unused_port
from lib.ycmd.constants import (
    YCMD_HMAC_SECRET_LENGTH,
    YCMD_HMAC_HEADER,
    YCMD_HANDLER_SHUTDOWN,
    YCMD_HANDLER_DEFINED_SUBCOMMANDS,
    YCMD_HANDLER_DEBUG_INFO,
    YCMD_HANDLER_GET_COMPLETIONS,
    YCMD_HANDLER_EVENT_NOTIFICATION,
    YCMD_HANDLER_HEALTHY,
    YCMD_EVENT_FILE_READY_TO_PARSE,
    YCMD_EVENT_BUFFER_VISIT,
    YCMD_EVENT_BUFFER_UNLOAD,
    YCMD_EVENT_INSERT_LEAVE,
    YCMD_EVENT_CURRENT_IDENTIFIER_FINISHED,
)
from lib.ycmd.start import (
    StartupParameters,
    to_startup_parameters,
    write_ycmd_settings_file,
    prepare_ycmd_process,
)

logger = logging.getLogger('sublime-ycmd.' + __name__)
# special logger instance for use in the server class
# this logger uses a filter to add server information to all log statements
_server_logger = logging.getLogger('sublime-ycmd.' + __name__ + '.server')


class Server(object):
    '''
    Self-contained ycmd server object. Creates and maintains a persistent
    connection to a ycmd server process. Provides a simple-ish way to send
    API requests to the backend, including control functions like stopping and
    pinging the server.

    TODO : Run all this stuff off-thread.
    TODO : Unit tests.
    TODO : Don't send requests in `is_alive`, add another method for that.
    '''

    NULL = 'Server.NULL'
    STARTING = 'Server.STARTING'
    RUNNING = 'Server.RUNNING'
    STOPPING = 'Server.STOPPING'

    def __init__(self):
        self._lock = threading.RLock()
        self._status = Server.NULL
        self._status_cv = threading.Condition(self._lock)

        self._process_handle = None
        # handles to the spooled log files:
        self._stdout_log_handle = None
        self._stderr_log_handle = None

        # TODO : Track the temporary settings file, and delete on exit.

        self._hostname = None
        self._port = None
        self._hmac = None
        self._label = None

        self.reset()

    def reset(self):
        self._status = Server.NULL
        self._process_handle = None
        self._stdout_log_handle = None
        self._stderr_log_handle = None

        self._hostname = None
        self._port = None
        self._hmac = None
        self._label = None

        self._reset_logger()

    def start(self, ycmd_root_directory,
              ycmd_settings_path=None, working_directory=None,
              python_binary_path=None, server_idle_suicide_seconds=None,
              max_server_wait_time_seconds=None):
        '''
        Launches a ycmd server process with the given startup parameters. The
        only required startup parameter is `ycmd_root_directory`. If it is a
        `str`, then all other omitted parameters will be calculated with
        respect to it. If it is an instance of `StartupParameters`, then all
        other parameters will be ignored, as that class contains all the
        necessary information. It is preferable to use `StartupParameters`.

        If `ycmd_settings_path` is not provided, it is calculated relative to
        the `ycmd_root_directory` (the repository contains the template in
        `default_settings.json`).

        If `working_directory` is not provided, the current working directory
        is used, as calculated by the `os` module.

        If `python_binary_path` is not provided, the system-installed python is
        used. This implicitly depends on the `PATH` environment variable.

        If `server_idle_suicide_seconds` is not provided, a default is used.

        If `max_server_wait_time_seconds` is not provided, a default is used.

        It is preferable to use the concrete `StartupParameters` class, since
        this ends up constructing one anyway if it isn't already in that form.
        '''
        startup_parameters = to_startup_parameters(
            ycmd_root_directory,
            ycmd_settings_path=ycmd_settings_path,
            working_directory=working_directory,
            python_binary_path=python_binary_path,
            server_idle_suicide_seconds=server_idle_suicide_seconds,
            max_server_wait_time_seconds=max_server_wait_time_seconds,
        )
        assert isinstance(startup_parameters, StartupParameters), \
            '[internal] startup parameters is not StartupParameters: %r' % \
            (startup_parameters)

        # don't use instance logger, since it may not be initialized
        logger.debug(
            'preparing to start ycmd server with startup parameters: %s',
            startup_parameters,
        )
        self.set_status(Server.STARTING)

        # update parameters to reflect normalized settings:
        ycmd_root_directory = startup_parameters.ycmd_root_directory
        ycmd_settings_path = startup_parameters.ycmd_settings_path
        working_directory = startup_parameters.working_directory
        python_binary_path = startup_parameters.python_binary_path
        server_idle_suicide_seconds = \
            startup_parameters.server_idle_suicide_seconds
        max_server_wait_time_seconds = \
            startup_parameters.max_server_wait_time_seconds

        ycmd_server_hostname = '127.0.0.1'
        ycmd_server_port = get_unused_port(ycmd_server_hostname)
        ycmd_server_label = get_base_name(working_directory)

        # initialize connection parameters asap to set up the instance logger:
        with self._lock:
            self.hostname = ycmd_server_hostname
            self.port = ycmd_server_port

        try:
            ycmd_hmac_secret = new_hmac_secret(
                num_bytes=YCMD_HMAC_SECRET_LENGTH,
            )
            ycmd_settings_tempfile_path = write_ycmd_settings_file(
                ycmd_settings_path, ycmd_hmac_secret,
            )

            if ycmd_settings_tempfile_path is None:
                self._logger.error(
                    'failed to generate ycmd server settings file, '
                    'cannot start server'
                )
                raise RuntimeError(
                    'failed to generate ycmd server settings file'
                )

            # NOTE : This does not start the process.
            ycmd_process_handle = prepare_ycmd_process(
                startup_parameters, ycmd_settings_tempfile_path,
                ycmd_server_hostname, ycmd_server_port,
            )
        except Exception as e:
            self._logger.error(
                'failed to prepare ycmd server process: %r', e, exc_info=True,
            )
            self.set_status(Server.NULL)
            return

        self._logger.debug(
            'successfully prepared server process, about to start it'
        )

        # TODO : Record the temporary settings path, and ensure it is deleted.
        with self._lock:
            self._process_handle = ycmd_process_handle
            self._stdout_log_handle = ycmd_process_handle.filehandles.stdout
            self._stderr_log_handle = ycmd_process_handle.filehandles.stderr

            self.hostname = ycmd_server_hostname
            self.port = ycmd_server_port
            self.hmac = ycmd_hmac_secret
            self.label = ycmd_server_label

        def _check_and_remove_settings_tmp():
            try:
                if is_file(ycmd_settings_tempfile_path):
                    self._logger.debug(
                        'removing temporary settings file: %s',
                        ycmd_settings_tempfile_path,
                    )
                    os.remove(ycmd_settings_tempfile_path)
            except Exception as e:
                self._logger.warning(
                    'failed to remove temporary settings file: %r',
                    ycmd_settings_tempfile_path,
                )

        try:
            ycmd_process_handle.start()
        except ValueError as e:
            self._logger.critical(
                'failed to launch ycmd server, argument error: %s', e,
            )
            _check_and_remove_settings_tmp()
        except OSError as e:
            self._logger.warning(
                'failed to launch ycmd server, system error: %s', e,
            )
            _check_and_remove_settings_tmp()

        if ycmd_process_handle.alive():
            self._logger.debug('process launched successfully!')
            self.set_status(Server.RUNNING)
        else:
            # nothing much we can do here - caller can check the output
            self._logger.debug(
                'process is no longer alive, there was probably an error'
            )
            self.set_status(Server.NULL)

    def stop(self, hard=False, timeout=None):
        with self._lock:
            if not self.is_alive(timeout=0):
                self._logger.debug('not alive, nothing to stop, returning')
                return

            if hard:
                self._process_handle.kill()
            elif not self.is_stopping():
                self._send_request(
                    YCMD_HANDLER_SHUTDOWN, method='POST', timeout=timeout,
                )
            else:
                self._logger.debug(
                    'already sent a shutdown request, not sending another one'
                )

            self.set_status(Server.STOPPING)

            # release lock before waiting
            process_handle = self._process_handle

        process_handle.wait(timeout=timeout)

        # if that didn't raise a `TimeoutError`, then the process is dead!
        with self._lock:
            self.set_status(Server.NULL)

    @lock_guard()
    def is_null(self):
        if self._status != Server.NULL:
            self._logger.debug('status is not null, assuming handle is valid')
            return False

        if self._process_handle is not None:
            self._logger.warning(
                'status is null, but process handle is not null, '
                'clearing handle: %r', self._process_handle
            )
            self._process_handle = None

        return True

    @lock_guard()
    def is_starting(self):
        return self._status == Server.STARTING

    @lock_guard()
    def is_alive(self, timeout=None):
        if self._status not in [Server.RUNNING, Server.STOPPING]:
            self._logger.debug('status is not running, assuming not alive')
            return False

        self._logger.debug('checking process handle: %r', self._process_handle)
        if not self._process_handle:
            if self._status != Server.STOPPING:
                self._logger.warning(
                    'status is running, but no process handle exists, '
                    'changing to null status'
                )
            self.set_status(Server.NULL)
            return False

        if not self._process_handle.alive():
            self._logger.debug('process has died, changing to null status')
            self._process_handle = None
            self.set_status(Server.NULL)
            return False

        if self._status == Server.STOPPING:
            # don't bother sending a health check request - it's shutting down
            self._logger.debug(
                'server is shutting down, so treating it as not alive, '
                'returning false'
            )
            return False

        if timeout == 0:
            # treat this as a "quick" check, and optimistically return true
            # (the caller should be aware of the implications)
            self._logger.debug(
                'timeout is 0, so not sending health-check request, '
                'returning true'
            )
            return True

        try:
            response = self._send_request(
                YCMD_HANDLER_HEALTHY, timeout=timeout,
            )
        except TimeoutError:
            self._logger.debug(
                'request timed out, server may be alive, but returning false'
            )
            # as noted, server may be alive, so don't change running status
            return False
        except Exception as e:
            self._logger.warning('error during health check: %r', e)
            response = None

        if response is None:
            self._logger.debug('health check failed, changing to null status')
            self._process_handle = None
            self.set_status(Server.NULL)
            return False
        return True

    @lock_guard()
    def is_stopping(self):
        return self._status == Server.STOPPING

    @lock_guard()
    def communicate(self, inpt=None, timeout=None):
        self._logger.warning('[DEPRECATED] communicate - use stdout/stderr')
        if not self._process_handle:
            self._logger.debug('no process handle, cannot communicate')
            return None, None

        assert isinstance(self._process_handle, Process), \
            '[internal] process handle is not Process: %r' % \
            (self._process_handle)
        return self._process_handle.communicate(inpt=inpt, timeout=timeout)

    @property
    @lock_guard()
    def stdout(self):
        '''
        Returns the handle to the ycmd process stdout output.

        Operations on the file handle do not need to be locked, so this handle
        can be safely returned to any callers.
        '''
        return self._stdout_log_handle

    @property
    @lock_guard()
    def stderr(self):
        '''
        Returns the handle to the ycmd process stderr output.

        Like the stdout output, operations on it do not require the lock.
        '''
        return self._stderr_log_handle

    def wait_for_status(self, status=None, timeout=None):
        '''
        Waits for the server status to change.

        If `status` is omitted, any status change will cause this to return.
        Otherwise, if `status` is a `Server` constant, then this will block
        until that status is reached. If `status` is a `list` of constants,
        then any status in that list will be awaited.

        If `timeout` is omitted, this will block indefinitely.
        Otherwise, `timeout` should be the number of seconds to wait for until
        a `TimeoutError` is raised.
        '''
        def _wait_condition(status=status):
            if status is None:
                return True

            if isinstance(status, (tuple, list)):
                return self._status in status

            return self._status == status

        with self._lock:
            # check if already satisfied from the start, and return if so
            if _wait_condition():
                return

            # otherwise, wait for status change notification and check again
            is_condition_satisfied = self._status_cv.wait_for(
                _wait_condition, timeout=timeout,
            )

            # cv does not raise exception timeout, it returns false instead
            # catch that and raise `TimeoutError` when it returns `False`
            if not is_condition_satisfied:
                raise TimeoutError

    def set_status(self, status):
        if status not in [
            Server.NULL, Server.STARTING, Server.RUNNING, Server.STOPPING,
        ]:
            self._logger.error('invalid status: %r', status)
            raise ValueError('invalid status: %r' % (status))

        if status == Server.NULL:
            valid_previous_states = None
        elif status == Server.STARTING:
            valid_previous_states = [Server.NULL]
        elif status == Server.RUNNING:
            valid_previous_states = [Server.NULL, Server.STARTING]
        elif status == Server.STOPPING:
            valid_previous_states = [Server.STOPPING, Server.RUNNING]
        else:
            self._logger.warning(
                'unhandled status, cannot validate: %r', status,
            )
            valid_previous_states = None

        # don't need to hold the lock for the whole thing
        # this part is only to issue a warning for unexpected transitions
        with self._lock:
            previous_status = self._status

        has_valid_previous_state = (
            not valid_previous_states or
            previous_status in valid_previous_states
        )
        if not has_valid_previous_state:
            self._logger.warning(
                'unexpected state transition: %r -> %r', self._status, status,
            )
            # but fall through and do it anyway

        self._logger.debug('transition: %r -> %r', self._status, status)

        # always update and notify waiting threads, even if it's the same
        with self._lock:
            self._status = status
            self._status_cv.notify_all()

    def _generate_hmac_header(self, method, path, body=None):
        if body is None:
            body = b''
        assert isinstance(body, bytes), 'body must be bytes: %r' % (body)

        with self._lock:
            hmac = self._hmac

        content_hmac = calculate_hmac(
            hmac, method, path, body,
        )

        return {
            YCMD_HMAC_HEADER: content_hmac,
        }

    def _send_request(self, handler,
                      request_params=None, method=None, timeout=None):
        '''
        Sends a request to the associated ycmd server and returns the response.
        The `handler` should be one of the ycmd handler constants.
        If `request_params` are supplied, it should be an instance of
        `RequestParameters`. Most handlers require these parameters, and ycmd
        will reject any requests that are missing them.
        If `method` is provided, it should be an HTTP verb (e.g. 'GET',
        'POST'). If omitted, it is set to 'GET' when no parameters are given,
        and 'POST' otherwise.
        '''
        with self._lock:
            if self._status == Server.STOPPING:
                self._logger.warning(
                    'server is shutting down, cannot send request to it',
                )
                return None

        try:
            # TODO : Move timeout constant somewhere else.
            wait_status_timeout = timeout if timeout is not None else 1
            self.wait_for_status(Server.RUNNING, timeout=wait_status_timeout)
        except TimeoutError as e:
            self._logger.warning(
                'server not ready, dropping due to timeout: %r', e,
            )
            return None

        assert request_params is None or \
            isinstance(request_params, RequestParameters), \
            '[internal] request parameters is not RequestParameters: %r' % \
            (request_params)
        assert method is None or isinstance(method, str), \
            '[internal] method is not a str: %r' % (method)

        has_params = request_params is not None

        if has_params:
            self._logger.debug('generating json body from parameters')
            json_params = request_params.to_json()
            body = json_serialize(json_params)
        else:
            json_params = None
            body = None

        if isinstance(body, str):
            body = str_to_bytes(body)

        if not method:
            method = 'GET' if not has_params else 'POST'

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
            method, handler, truncate(json_params), truncate(headers),
        )

        with self._lock:
            host = self.hostname
            port = self.port

        response_status = None
        response_reason = None
        response_headers = None
        response_data = None
        try:
            connection = http.client.HTTPConnection(
                host=host, port=port, timeout=timeout,
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

            # TODO : Move http response parsing somewhere else.
            response_headers = response.getheaders()
            response_content_type = response.getheader('Content-Type')
            response_content_length = response.getheader('Content-Length', 0)
            response_content_hmac = response.getheader(YCMD_HMAC_HEADER)

            try:
                response_content_length = int(response_content_length)
            except ValueError:
                response_content_length = 0

            has_content = response_content_length > 0
            is_content_json = response_content_type == 'application/json'

            # extract response and check hmac
            if has_content:
                response_content = response.read()
                with self._lock:
                    hmac = self._hmac

                expected_content_hmac = calculate_hmac(
                    hmac, response_content,
                )

                if response_content_hmac != expected_content_hmac:
                    self._logger.error(
                        'server responded with incorrect hmac, '
                        'dropping response - expected, received: %r, %r',
                        expected_content_hmac, response_content_hmac,
                    )
                    response_content = None
                else:
                    self._logger.debug(
                        'response hmac matches, response is valid',
                    )
            else:
                response_content = None

            # parse response as json
            if response_content and is_content_json:
                response_data = json_parse(response_content)
            else:
                if has_content or response_content:
                    self._logger.warning(
                        'ycmd server response is not json, content type: %r',
                        response_content_type,
                    )
                response_data = None

        except http.client.HTTPException as e:
            self._logger.error('error during ycmd request: %s', e)
        except ConnectionError as e:
            self._logger.error(
                'connection error, ycmd server may be dead: %s', e,
            )

        self._logger.debug(
            'parsed status, reason, headers, data: %s, %s, %s, %s',
            response_status, response_reason, response_headers, response_data,
        )

        return response_data

    def get_completer_commands(self, request_params):
        return self._send_request(
            YCMD_HANDLER_DEFINED_SUBCOMMANDS,
            request_params=request_params,
            method='POST',
        )

    def get_debug_info(self, request_params):
        return self._send_request(
            YCMD_HANDLER_DEBUG_INFO,
            request_params=request_params,
            method='POST',
        )

    def get_code_completions(self, request_params, timeout=None):
        assert isinstance(request_params, RequestParameters), \
            'request parameters must be RequestParameters: %r' % \
            (request_params)

        completion_data = self._send_request(
            YCMD_HANDLER_GET_COMPLETIONS,
            request_params=request_params,
            method='POST',
            timeout=timeout,
        )
        self._logger.debug(
            'received completion results: %s', truncate(completion_data),
        )

        # TODO : Handle exceptions for completions and diagnostics.
        # TODO : Display diagnostics in the status bar, or just return them.
        completion_response = parse_completions(
            completion_data, request_params,
        )
        self._logger.debug(
            'parsed completion response: %r', completion_response,
        )

        completions = completion_response.completions
        # diagnostics = completion_response.diagnostics
        # self._logger.debug('parsed completions: %r', completions)
        # self._logger.debug('parsed diagnostics: %r', diagnostics)

        return completions

    def _notify_event(self, event_name, request_params, method='POST'):
        assert isinstance(request_params, RequestParameters), \
            'request parameters must be RequestParameters: %r' % \
            (request_params)

        self._logger.debug(
            'sending event notification for event: %s', event_name,
        )

        request_params['event_name'] = event_name
        return self._send_request(
            YCMD_HANDLER_EVENT_NOTIFICATION,
            request_params=request_params,
            method=method,
        )

    def notify_file_ready_to_parse(self, request_params):
        return self._notify_event(
            YCMD_EVENT_FILE_READY_TO_PARSE,
            request_params=request_params,
        )

    def notify_buffer_enter(self, request_params):
        return self._notify_event(
            YCMD_EVENT_BUFFER_VISIT,
            request_params=request_params,
        )

    def notify_buffer_leave(self, request_params):
        return self._notify_event(
            YCMD_EVENT_BUFFER_UNLOAD,
            request_params=request_params,
        )

    def notify_leave_insert_mode(self, request_params):
        return self._notify_event(
            YCMD_EVENT_INSERT_LEAVE,
            request_params=request_params,
        )

    def notify_current_identifier_finished(self, request_params):
        return self._notify_event(
            YCMD_EVENT_CURRENT_IDENTIFIER_FINISHED,
            request_params=request_params,
        )

    @property
    @lock_guard()
    def hostname(self):
        if not self._hostname:
            self._logger.warning('server hostname is not set')
        return self._hostname

    @hostname.setter
    @lock_guard()
    def hostname(self, hostname):
        if not isinstance(hostname, str):
            self._logger.warning('hostname is not a str: %r', hostname)
        self._hostname = hostname
        self._reset_logger()

    @property
    @lock_guard()
    def port(self):
        if not self._port:
            self._logger.warning('server port is not set')
        return self._port

    @port.setter
    @lock_guard()
    def port(self, port):
        if not isinstance(port, int):
            self._logger.warning('port is not an int: %r', port)
        self._port = port
        self._reset_logger()

    @property
    @lock_guard()
    def hmac(self):
        self._logger.error(
            'returning server hmac secret... nobody else should need it...'
        )
        return self._hmac

    @hmac.setter
    @lock_guard()
    def hmac(self, hmac):
        if not isinstance(hmac, (bytes, str)):
            self._logger.warning('server hmac secret is not a str: %r', hmac)
        self._hmac = hmac

    @property
    @lock_guard()
    def label(self):
        return self._label

    @label.setter
    @lock_guard()
    def label(self, label):
        if not isinstance(label, str):
            self._logger.warning('server label is not a str: %r', label)
        self._label = label

    @lock_guard()
    def _reset_logger(self):
        self._logger = ServerLoggerAdapter(_server_logger, {
            'hostname': self._hostname or '?',
            'port': self._port or '?',
        })

    @lock_guard()
    def pretty_str(self):
        label_desc = ' "%s"' % (self._label) if self._label else ''
        server_desc = 'ycmd server%s' % (label_desc)

        if not self._hmac:
            return '%s - null' % (server_desc)

        if self._hostname is None or self._port is None:
            return '%s - unknown' % (server_desc)

        return '%s - %s:%d' % (server_desc, self._hostname, self._port)

    @lock_guard()
    def __str__(self):
        return '%s:%s' % (self._hostname or '', self._port or '')


class ServerLoggerAdapter(logging.LoggerAdapter):
    def __init__(self, logger, extra=None):
        # pylint: disable=redefined-outer-name
        super(ServerLoggerAdapter, self).__init__(logger, extra or {})

    def process(self, msg, kwargs):
        server_id = '(%s:%s)' % (
            self.extra.get('hostname', '?'),
            self.extra.get('port', '?'),
        )

        return '%-16s %s' % (server_id, msg), kwargs
