#!/usr/bin/env python3

'''
lib/ycmd/start.py
Server bootstrap logic. Includes a utility class for normalizing parameters and
calculating default ones. Also includes a helper to set up the temporary
options file.
'''

import logging
import os
import tempfile

from ..process import (
    FileHandles,
    Process,
)
from ..util.fs import (
    default_python_binary_path,
    save_json_file,
)
from ..ycmd.constants import (
    YCMD_LOG_SPOOL_OUTPUT,
    YCMD_LOG_SPOOL_SIZE,
    YCMD_DEFAULT_SERVER_IDLE_SUICIDE_SECONDS,
    YCMD_DEFAULT_MAX_SERVER_WAIT_TIME_SECONDS,
)
from ..ycmd.settings import (
    get_default_settings_path,
    generate_settings_data,
)

logger = logging.getLogger('sublime-ycmd.' + __name__)


class StartupParameters(object):
    '''
    Startup parameters for a ycmd server instance.
    Should include all the necessary configuration for creating the ycmd
    server process. Also calculates defaults for certain parameters.

    TODO : Rename `ycmd_settings_path` to `ycmd_default_settings_path`, and
           add a `ycmd_temp_settings_path` field to this.
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

        # additional attributes, can be set via the properties
        self._log_level = None
        self._stdout_log_path = None
        self._stderr_log_path = None
        self._keep_logs = None

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
    def log_level(self):
        return self._log_level

    @log_level.setter
    def log_level(self, log_level):
        if log_level is not None and not isinstance(log_level, str):
            raise TypeError('log level must be a str: %r' % (log_level))

        if log_level is not None and not _is_valid_log_level(log_level):
            logger.warning('log level unrecognized: %r', log_level)
            # but fall through and do it anyway

        self._log_level = log_level

    @property
    def stdout_log_path(self):
        return self._stdout_log_path

    @stdout_log_path.setter
    def stdout_log_path(self, stdout_log_path):
        if stdout_log_path is not None and \
                not isinstance(stdout_log_path, str):
            raise TypeError(
                'stdout log path must be a str: %r' % (stdout_log_path)
            )
        self._stdout_log_path = stdout_log_path

    @property
    def stderr_log_path(self):
        return self._stderr_log_path

    @stderr_log_path.setter
    def stderr_log_path(self, stderr_log_path):
        if stderr_log_path is not None and \
                not isinstance(stderr_log_path, str):
            raise TypeError(
                'stderr_log_path must be a str: %r' % (stderr_log_path)
            )
        self._stderr_log_path = stderr_log_path

    @property
    def keep_logs(self):
        if self._keep_logs is None:
            return False
        return self._keep_logs

    @keep_logs.setter
    def keep_logs(self, keep_logs):
        if keep_logs is not None and not isinstance(keep_logs, bool):
            raise TypeError('keep-logs must be a bool: %r' % (keep_logs))
        self._keep_logs = keep_logs

    @property
    def ycmd_module_directory(self):
        if self._ycmd_root_directory is None:
            logger.error('no ycmd root directory set')
            raise AttributeError
        return os.path.join(self._ycmd_root_directory, 'ycmd')

    def copy(self):
        '''
        Creates a shallow-copy of the startup parameters.
        '''
        raw_attrs = [
            '_ycmd_root_directory',
            '_ycmd_settings_path',
            '_working_directory',
            '_python_binary_path',
            '_server_idle_suicide_seconds',
            '_max_server_wait_time_seconds',
        ]
        result = StartupParameters()

        for attr in raw_attrs:
            attr_value = getattr(self, attr)
            setattr(result, attr, attr_value)

        return result

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


def to_startup_parameters(ycmd_root_directory,
                          ycmd_settings_path=None,
                          working_directory=None,
                          python_binary_path=None,
                          server_idle_suicide_seconds=None,
                          max_server_wait_time_seconds=None):
    '''
    Internal convenience function. Receives the raw arguments to starting a
    ycmd server and returns a `StartupParameters` instance from it.

    If the first argument is already `StartupParameters`, it is returned as-is,
    and the remaining parameters are ignored.

    Otherwise, a `StartupParameters` instance is constructed with all the given
    parameters and returned.
    '''
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
    logger.warning('[DEPRECATED] to startup parameters', stack_info=True)
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


def check_startup_parameters(startup_parameters):
    '''
    Performs quick, non-blocking validation on startup parameters to catch type
    mismatches or empty configurations. Raises an exception or returns `None`.

    This is meant to be run on the main thread to catch common startup errors
    before initializing the server off-thread. It isn't strictly necessary, but
    produces nicer error messages when the plugin is not configured correctly.

    NOTE : This does not check the file system for things like missing files,
           as that can be a blocking operation.
    '''
    if not isinstance(startup_parameters, StartupParameters):
        raise TypeError(
            'startup parameters must be StartupParameters: %r' %
            (startup_parameters)
        )

    ycmd_root_directory = startup_parameters.ycmd_root_directory
    if not ycmd_root_directory:
        raise RuntimeError('no ycmd root directory has been set')

    ycmd_settings_path = startup_parameters.ycmd_settings_path
    if not ycmd_settings_path:
        raise RuntimeError('no ycmd default settings path has been set')

    logger.debug(
        'startup parameters seem to be filled in, ',
        'ready to attempt startup: %r', startup_parameters,
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
        # no point using `with` for this, since we also use `delete=False`
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

    # this may throw:
    check_startup_parameters(startup_parameters)

    working_directory = startup_parameters.working_directory
    python_binary_path = startup_parameters.python_binary_path
    server_idle_suicide_seconds = \
        startup_parameters.server_idle_suicide_seconds
    max_server_wait_time_seconds = \
        startup_parameters.max_server_wait_time_seconds
    ycmd_module_directory = startup_parameters.ycmd_module_directory

    if YCMD_LOG_SPOOL_OUTPUT:
        stdout_log_spool = \
            tempfile.SpooledTemporaryFile(max_size=YCMD_LOG_SPOOL_SIZE)
        stderr_log_spool = \
            tempfile.SpooledTemporaryFile(max_size=YCMD_LOG_SPOOL_SIZE)

        logger.debug(
            'using temporary spools for stdout, stderr: %r, %r',
            stdout_log_spool, stderr_log_spool,
        )

        stdout_handle = stdout_log_spool
        stderr_handle = stderr_log_spool
    else:
        # explicitly close handles - don't inherit from this process
        stdout_handle = FileHandles.DEVNULL
        stderr_handle = FileHandles.DEVNULL

    ycmd_process_handle = Process()

    ycmd_process_handle.binary = python_binary_path
    ycmd_process_handle.args.extend([
        ycmd_module_directory,
        '--host=%s' % (ycmd_server_hostname),
        '--port=%s' % (ycmd_server_port),
        '--idle_suicide_seconds=%s' % (server_idle_suicide_seconds),
        '--check_interval_seconds=%s' % (max_server_wait_time_seconds),
        '--options_file=%s' % (ycmd_settings_tempfile_path),
    ])

    ycmd_process_handle.cwd = working_directory
    ycmd_process_handle.filehandles.stdout = stdout_handle
    ycmd_process_handle.filehandles.stderr = stderr_handle

    if startup_parameters.log_level is not None:
        add_ycmd_debug_args(
            ycmd_process_handle,
            log_level=startup_parameters.log_level,
            stdout_file_name=startup_parameters.stdout_log_path,
            stderr_file_name=startup_parameters.stderr_log_path,
            keep_logfiles=startup_parameters.keep_logs,
        )

    return ycmd_process_handle


def add_ycmd_debug_args(ycmd_process_handle, log_level='info',
                        stdout_file_name=None, stderr_file_name=None,
                        keep_logfiles=False):
    '''
    Adds startup flags to `ycmd_process_handle` to enable logging output.

    The `ycmd_process_handle` should be an instance of `Process`.

    The `log_level` should be one of 'debug', 'info', 'warning', 'error', or
    'critical'. Any `str` is accepted, this routine does not actually check it.

    If `stdout_file_name` and `stderr_file_name` are provided, the server will
    write log messages to the given files. The bulk of the logs will be on
    stderr, with only a few startup messages appearing on stdout.

    If `keep_logfiles` is `True`, then the server won't delete the log files
    when it exits. Otherwise, the log files will be deleted when it shuts down.
    '''
    if not isinstance(ycmd_process_handle, Process):
        raise TypeError(
            'ycmd process handle must be a Process: %r' % (ycmd_process_handle)
        )
    assert isinstance(ycmd_process_handle, Process)
    if ycmd_process_handle.alive():
        raise ValueError(
            'ycmd process is already started, cannot modify it: %r' %
            (ycmd_process_handle)
        )

    if not _is_valid_log_level(log_level):
        logger.warning('log level unrecognized: %r', log_level)
        # but fall through and do it anyway

    ycmd_debug_args = [
        '--log=%s' % (log_level),
    ]
    if stdout_file_name and stderr_file_name:
        ycmd_debug_args.extend([
            '--stdout=%s' % (stdout_file_name),
            '--stderr=%s' % (stderr_file_name),
        ])

        if keep_logfiles:
            ycmd_debug_args.append(
                '--keep_logfiles',
            )

    logger.debug('adding ycmd debug args: %r', ycmd_debug_args)
    ycmd_process_handle.args.extend(ycmd_debug_args)


def _is_valid_log_level(log_level):
    if not isinstance(log_level, str):
        raise TypeError('log level must be a str: %r' % (log_level))

    # these can be found by running `python /path/to/ycmd/ycmd --help`
    recognized_log_levels = [
        'debug',
        'info',
        'warning',
        'error',
        'critical',
    ]
    return log_level in recognized_log_levels
