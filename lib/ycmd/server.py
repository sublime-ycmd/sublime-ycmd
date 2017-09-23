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
'''

import http
import logging

from lib.process import Process
from lib.schema.completions import parse_completions
from lib.schema.request import RequestParameters
from lib.util.format import (
    json_serialize,
    json_parse,
)
from lib.util.hmac import calculate_hmac
from lib.util.str import (
    str_to_bytes,
    truncate,
)
from lib.ycmd.constants import (
    YCMD_HMAC_HEADER,
    YCMD_HANDLER_SHUTDOWN,
    YCMD_HANDLER_DEFINED_SUBCOMMANDS,
    YCMD_HANDLER_DEBUG_INFO,
    YCMD_HANDLER_GET_COMPLETIONS,
    YCMD_HANDLER_EVENT_NOTIFICATION,
    YCMD_EVENT_FILE_READY_TO_PARSE,
    YCMD_EVENT_BUFFER_VISIT,
    YCMD_EVENT_BUFFER_UNLOAD,
    YCMD_EVENT_INSERT_LEAVE,
    YCMD_EVENT_CURRENT_IDENTIFIER_FINISHED,
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

        assert isinstance(self._process_handle, Process), \
            '[internal] process handle is not Process: %r' % \
            (self._process_handle)
        # TODO : Also use the '/healthy' handler to check if it's alive.
        return self._process_handle.alive()

    def communicate(self, inpt=None, timeout=None):
        if not self._process_handle:
            self._logger.debug('no process handle, cannot get process output')
            return None, None

        assert isinstance(self._process_handle, Process), \
            '[internal] process handle is not Process: %r' % \
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

    def _send_request(self, handler, request_params=None, method=None):
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
        assert request_params is None or \
            isinstance(request_params, RequestParameters), \
            '[internal] request parameters is not RequestParameters: %r' % \
            (request_params)
        assert method is None or isinstance(method, str), \
            '[internal] method is not a str: %r' % (method)

        has_params = request_params is not None

        if has_params:
            logger.debug('generating json body from parameters')
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
                    response_data = json_parse(response_content)
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

    def get_code_completions(self, request_params):
        assert isinstance(request_params, RequestParameters), \
            'request parameters must be RequestParameters: %r' % \
            (request_params)

        completion_data = self._send_request(
            YCMD_HANDLER_GET_COMPLETIONS,
            request_params=request_params,
            method='POST',
        )
        self._logger.debug(
            'received completion results: %s', truncate(completion_data),
        )

        completions = parse_completions(completion_data, request_params)
        self._logger.debug('parsed completions: %r', completions)

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
        self._logger = ServerLoggerAdapter(_server_logger, {
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
