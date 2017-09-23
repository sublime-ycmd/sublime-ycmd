#!/usr/bin/env python3

'''
lib/ycmd/start.py
Server bootstrap logic. Starts up a ycmd server process and returns a handle.
'''

import logging
import os
import socket
import tempfile

from lib.process import (
    FileHandles,
    Process,
)
from lib.util.fs import (
    is_file,
    default_python_binary_path,
    get_base_name,
    save_json_file,
)
from lib.util.hmac import new_hmac_secret
from lib.ycmd.constants import (
    YCMD_HMAC_SECRET_LENGTH,
    YCMD_DEFAULT_SERVER_IDLE_SUICIDE_SECONDS,
    YCMD_DEFAULT_MAX_SERVER_WAIT_TIME_SECONDS,
)
from lib.ycmd.server import Server
from lib.ycmd.settings import (
    get_default_settings_path,
    generate_settings_data,
)

logger = logging.getLogger('sublime-ycmd.' + __name__)


class StartupParameters(object):
    '''
    Startup parameters for a ycmd server instance.
    Should include all the necessary configuration for creating the ycmd
    server process. Also calculates defaults for certain parameters.
    '''

    def __init__(self, ycmd_root_directory=None,
                 ycmd_settings_path=None,
                 working_directory=None,
                 python_binary_path=None,
                 server_idle_suicide_seconds=None,
                 max_server_wait_time_seconds=None):
        self._ycmd_root_directory = None
        self._ycmd_settings_path = None

        self._working_directory = None
        self._python_binary_path = None
        self._server_idle_suicide_seconds = None
        self._max_server_wait_time_seconds = None

        self._ycmd_module_directory = None

        self.ycmd_root_directory = ycmd_root_directory
        self.ycmd_settings_path = ycmd_settings_path
        self.working_directory = working_directory
        self.python_binary_path = python_binary_path
        self.server_idle_suicide_seconds = server_idle_suicide_seconds
        self.max_server_wait_time_seconds = max_server_wait_time_seconds

    @property
    def ycmd_root_directory(self):
        if self._ycmd_root_directory is None:
            logger.warning('no ycmd root directory has been set')
        return self._ycmd_root_directory

    @ycmd_root_directory.setter
    def ycmd_root_directory(self, ycmd_root_directory):
        if ycmd_root_directory is not None and \
                not isinstance(ycmd_root_directory, str):
            raise TypeError(ycmd_root_directory,)
        self._ycmd_root_directory = ycmd_root_directory

    @property
    def ycmd_settings_path(self):
        if self._ycmd_settings_path is None:
            if self._ycmd_root_directory is not None:
                return get_default_settings_path(self._ycmd_root_directory)
            logger.warning('no ycmd root directory has been set')

        return self._ycmd_settings_path

    @ycmd_settings_path.setter
    def ycmd_settings_path(self, ycmd_settings_path):
        if ycmd_settings_path is not None and \
                not isinstance(ycmd_settings_path, str):
            raise TypeError(ycmd_settings_path,)
        self._ycmd_settings_path = ycmd_settings_path

    @property
    def working_directory(self):
        if self._working_directory is None:
            return os.getcwd()
        return self._working_directory

    @working_directory.setter
    def working_directory(self, working_directory):
        if working_directory is not None and \
                not isinstance(working_directory, str):
            raise TypeError(working_directory,)
        self._working_directory = working_directory

    @property
    def python_binary_path(self):
        if self._python_binary_path is None:
            return default_python_binary_path()
        return self._python_binary_path

    @python_binary_path.setter
    def python_binary_path(self, python_binary_path):
        if python_binary_path is not None and \
                not isinstance(python_binary_path, str):
            raise TypeError(python_binary_path,)
        self._python_binary_path = python_binary_path

    @property
    def server_idle_suicide_seconds(self):
        if self._server_idle_suicide_seconds is None:
            return YCMD_DEFAULT_SERVER_IDLE_SUICIDE_SECONDS
        return self._server_idle_suicide_seconds

    @server_idle_suicide_seconds.setter
    def server_idle_suicide_seconds(self, server_idle_suicide_seconds):
        if server_idle_suicide_seconds is not None and \
                not isinstance(server_idle_suicide_seconds, int):
            raise TypeError(server_idle_suicide_seconds,)
        self._server_idle_suicide_seconds = server_idle_suicide_seconds

    @property
    def max_server_wait_time_seconds(self):
        if self._max_server_wait_time_seconds is None:
            return YCMD_DEFAULT_MAX_SERVER_WAIT_TIME_SECONDS
        return self._max_server_wait_time_seconds

    @max_server_wait_time_seconds.setter
    def max_server_wait_time_seconds(self, max_server_wait_time_seconds):
        if max_server_wait_time_seconds is not None and \
                not isinstance(max_server_wait_time_seconds, int):
            raise TypeError(max_server_wait_time_seconds,)
        self._max_server_wait_time_seconds = max_server_wait_time_seconds

    @property
    def ycmd_module_directory(self):
        if self._ycmd_root_directory is None:
            logger.error('no ycmd root directory set')
            raise AttributeError
        return os.path.join(self._ycmd_root_directory, 'ycmd')

    def __iter__(self):
        ''' Dictionary-compatible iterator. '''
        return iter((
            ('ycmd_root_directory', self.ycmd_root_directory),
            ('ycmd_settings_path', self.ycmd_settings_path),
            ('working_directory', self.working_directory),
            ('python_binary_path', self.python_binary_path),
            ('server_idle_suicide_seconds', self.server_idle_suicide_seconds),
            (
                'max_server_wait_time_seconds',
                self.max_server_wait_time_seconds,
            ),
            ('ycmd_module_directory', self.ycmd_module_directory),
        ))

    def __str__(self):
        return (
            'ycmd path, default settings path, '
            'python binary path, working directory: '
            '%(ycmd_root_directory)s, %(ycmd_settings_path)s, '
            '%(python_binary_path)s, %(working_directory)s' %
            (dict(self))
        )

    def __repr__(self):
        return '%s(%r)' % (StartupParameters, dict(self))


def _to_startup_parameters(ycmd_root_directory,
                           ycmd_settings_path=None,
                           working_directory=None,
                           python_binary_path=None,
                           server_idle_suicide_seconds=None,
                           max_server_wait_time_seconds=None):
    if isinstance(ycmd_root_directory, StartupParameters):
        # great, already in the desired state
        # check if other params are provided and issue a warning
        # (they get ignored in that case)
        if ycmd_settings_path is not None:
            logger.warning(
                'ycmd settings path will be ignored: %s', ycmd_settings_path,
            )
        if working_directory is not None:
            logger.warning(
                'working directory will be ignored: %s', working_directory,
            )
        if python_binary_path is not None:
            logger.warning(
                'python binary path will be ignored: %s', python_binary_path,
            )
        if server_idle_suicide_seconds is not None:
            logger.warning(
                'server idle suicide seconds will be ignored: %s',
                server_idle_suicide_seconds,
            )
        if max_server_wait_time_seconds is not None:
            logger.warning(
                'max server wait time seconds will be ignored: %s',
                max_server_wait_time_seconds,
            )

        return ycmd_root_directory

    # else, generate them
    logger.debug(
        'generating startup parameters with root: %s', ycmd_root_directory,
    )

    return StartupParameters(
        ycmd_root_directory,
        ycmd_settings_path=ycmd_settings_path,
        working_directory=working_directory,
        python_binary_path=python_binary_path,
        server_idle_suicide_seconds=server_idle_suicide_seconds,
        max_server_wait_time_seconds=max_server_wait_time_seconds,
    )


def write_ycmd_settings_file(ycmd_settings_path, ycmd_hmac_secret, out=None):
    '''
    Writes out a ycmd server settings file based on the template file
    `ycmd_settings_path`. A uniquely-generated `ycmd_hmac_secret` must also be
    supplied, as it needs to be written into this file.
    The return value is the path to the settings file, as a `str`.
    If `out` is omitted, a secure temporary file is created, and the returned
    path should be passed via the options flag to ycmd.
    If `out` is provided, it should be a path to an output file (`str`), or a
    file-like handle (must support `.write`). This is not recommended for use
    with ycmd, as it may be insecure.
    '''
    ycmd_settings_data = generate_settings_data(
        ycmd_settings_path, ycmd_hmac_secret,
    )

    out_path = None

    if out is None:
        # no point using `with` for this, since we also use `delete=True`
        temp_file_object = tempfile.NamedTemporaryFile(
            prefix='ycmd_settings_', suffix='.json', delete=False,
        )
        temp_file_name = temp_file_object.name
        temp_file_handle = temp_file_object.file    # type: io.TextIOWrapper

        out = temp_file_handle
        out_path = temp_file_name

        def flush():
            temp_file_handle.flush()

        def close():
            temp_file_object.close()
    else:
        raise NotImplementedError('unimplemented: output to specific file')

    if out_path is None and out is not None:
        logger.error('failed to get path for output file: %r', out)
        # fall through and write it out anyway

    save_json_file(out, ycmd_settings_data)

    flush()
    close()

    logger.debug('successfully wrote file: %s', out_path)
    return out_path


def prepare_ycmd_process(startup_parameters, ycmd_settings_tempfile_path,
                         ycmd_server_hostname, ycmd_server_port):
    '''
    Initializes and returns a `Process` handle, correctly configured to launch
    a ycmd server process. It does not automatically start it though.
    The `ycmd_settings_tempfile_path` should be created by (return value of)
    `write_ycmd_settings_file`. The ycmd server process will read that file on
    startup and then immediately delete it.
    The `ycmd_server_hostname` and `ycmd_server_port` must also be provided to
    instruct the server to listen on the given address.
    '''
    assert isinstance(startup_parameters, StartupParameters), \
        'startup parameters must be StartupParameters: %r' % \
        (startup_parameters)
    assert isinstance(ycmd_settings_tempfile_path, str), \
        'ycmd settings temporary file path must be a str: %r' % \
        (ycmd_settings_tempfile_path)

    working_directory = startup_parameters.working_directory
    python_binary_path = startup_parameters.python_binary_path
    server_idle_suicide_seconds = \
        startup_parameters.server_idle_suicide_seconds
    max_server_wait_time_seconds = \
        startup_parameters.max_server_wait_time_seconds
    ycmd_module_directory = startup_parameters.ycmd_module_directory

    # toggle-able log file naming scheme
    # use whichever to test/debug
    _generate_unique_tmplogs = False
    if _generate_unique_tmplogs:
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
    else:
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

    ycmd_process_handle = Process()

    ycmd_process_handle.binary = python_binary_path
    ycmd_process_handle.args.extend([
        ycmd_module_directory,
        '--host=%s' % (ycmd_server_hostname),
        '--port=%s' % (ycmd_server_port),
        '--idle_suicide_seconds=%s' % (server_idle_suicide_seconds),
        '--check_interval_seconds=%s' % (max_server_wait_time_seconds),
        '--options_file=%s' % (ycmd_settings_tempfile_path),
        # XXX : REMOVE ME - testing only
        '--log=debug',
        '--stdout=%s' % (stdout_file_name),
        '--stderr=%s' % (stderr_file_name),
        '--keep_logfiles',
    ])
    ycmd_process_handle.cwd = working_directory

    ycmd_process_handle.filehandles.stdout = FileHandles.PIPE
    ycmd_process_handle.filehandles.stderr = FileHandles.PIPE

    return ycmd_process_handle


def start_ycmd_server(ycmd_root_directory,
                      ycmd_settings_path=None,
                      working_directory=None,
                      python_binary_path=None,
                      server_idle_suicide_seconds=None,
                      max_server_wait_time_seconds=None):
    '''
    Launches a ycmd server instances and returns a `Server` instance for it.
    The only required startup parameter is `ycmd_root_directory`. If it is a
    `str`, then all other (optional) parameters will be calculated with respect
    to it. If it is `StartupParameters`, then all other parameters are ignored,
    as that class already contains them all.

    If `ycmd_settings_path` is not provided, it is calculated relative to the
    `ycmd_root_directory` (the repository contains a `default_settings.json`).
    If `working_directory` is not provided, the current working directory is
    used, as calculated by the `os` module.
    If `python_binary_path` is not provided, the system-installed python
    is used. This implicitly depends on the `PATH` environment variable.
    If `server_idle_suicide_seconds` is not provided, a default is used.
    If `max_server_wait_time_seconds` is not provided, a default is used.

    It is preferable to use the concrete `StartupParameters` class, since this
    ends up constructing one anyway if it isn't already in that form.
    '''
    startup_parameters = _to_startup_parameters(
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

    logger.debug(
        'preparing to start ycmd server with startup parameters: %s',
        startup_parameters,
    )

    # update parameters to reflect normalized settings:
    ycmd_root_directory = startup_parameters.ycmd_root_directory
    ycmd_settings_path = startup_parameters.ycmd_settings_path
    working_directory = startup_parameters.working_directory
    python_binary_path = startup_parameters.python_binary_path
    server_idle_suicide_seconds = \
        startup_parameters.server_idle_suicide_seconds
    max_server_wait_time_seconds = \
        startup_parameters.max_server_wait_time_seconds

    ycmd_hmac_secret = new_hmac_secret(num_bytes=YCMD_HMAC_SECRET_LENGTH)
    ycmd_settings_tempfile_path = write_ycmd_settings_file(
        ycmd_settings_path, ycmd_hmac_secret,
    )

    if ycmd_settings_tempfile_path is None:
        logger.error(
            'failed to generate ycmd server settings file, '
            'cannot start server'
        )
        return None

    ycmd_server_hostname = '127.0.0.1'
    ycmd_server_port = _get_unused_port(ycmd_server_hostname)
    ycmd_server_label = get_base_name(working_directory)

    # don't start it up just yet... set up the return value while we can
    ycmd_process_handle = prepare_ycmd_process(
        startup_parameters, ycmd_settings_tempfile_path,
        ycmd_server_hostname, ycmd_server_port,
    )

    ycmd_server = Server(
        process_handle=ycmd_process_handle,
        hostname=ycmd_server_hostname,
        port=ycmd_server_port,
        hmac=ycmd_hmac_secret,
        label=ycmd_server_label,
    )

    def _check_and_remove_settings_tmp():
        if is_file(ycmd_settings_path):
            os.remove(ycmd_settings_path)

    try:
        ycmd_process_handle.start()
    except ValueError as e:
        logger.critical('failed to launch ycmd server, argument error: %s', e)
        _check_and_remove_settings_tmp()
    except OSError as e:
        logger.warning('failed to launch ycmd server, system error: %s', e)
        _check_and_remove_settings_tmp()

    if not ycmd_process_handle.alive():
        _, stderr = ycmd_process_handle.communicate(timeout=0)
        logger.error('failed to launch ycmd server, error output: %s', stderr)

    return ycmd_server


def _get_unused_port(interface='127.0.0.1'):
    ''' Finds an available port for the ycmd server process to listen on. '''
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((interface, 0))

    port = sock.getsockname()[1]
    logger.debug('found unused port: %d', port)

    sock.close()
    return port
