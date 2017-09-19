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


def start_ycmd_server(ycmd_root_directory,
                      ycmd_settings_path=None, working_directory=None,
                      ycmd_python_binary_path=None,
                      ycmd_server_idle_suicide_seconds=None,
                      ycmd_max_server_wait_time_seconds=None):
    assert isinstance(ycmd_root_directory, str), \
        'ycmd root directory must be a str: %r' % (ycmd_root_directory)

    if ycmd_settings_path is None:
        ycmd_settings_path = \
            get_default_settings_path(ycmd_root_directory)
    assert isinstance(ycmd_settings_path, str), \
        'ycmd settings path must be a str: %r' % (ycmd_settings_path)

    if ycmd_python_binary_path is None:
        ycmd_python_binary_path = default_python_binary_path()
    assert isinstance(ycmd_python_binary_path, str), \
        'ycmd python binary path must be a str: %r' % (ycmd_python_binary_path)

    if ycmd_server_idle_suicide_seconds is None:
        ycmd_server_idle_suicide_seconds = \
            YCMD_DEFAULT_SERVER_IDLE_SUICIDE_SECONDS
    assert isinstance(ycmd_server_idle_suicide_seconds, int), \
        'ycmd server idle suicide seconds must be an int: %r' % \
        (ycmd_server_idle_suicide_seconds)

    if ycmd_max_server_wait_time_seconds is None:
        ycmd_max_server_wait_time_seconds = \
            YCMD_DEFAULT_MAX_SERVER_WAIT_TIME_SECONDS
    assert isinstance(ycmd_max_server_wait_time_seconds, int), \
        'ycmd max server wait time seconds must be an int: %r' % \
        (ycmd_max_server_wait_time_seconds)

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

    # toggle-able log file naming scheme
    # use whichever to test/debug
    _GENERATE_UNIQUE_TMPLOGS = False
    if _GENERATE_UNIQUE_TMPLOGS:
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
    ycmd_server_hostname = '127.0.0.1'
    ycmd_server_port = _get_unused_port(ycmd_server_hostname)
    ycmd_server_label = get_base_name(working_directory)

    ycmd_process_handle.binary = ycmd_python_binary_path
    ycmd_process_handle.args.extend([
        ycmd_module_directory,
        '--host=%s' % (ycmd_server_hostname),
        '--port=%s' % (ycmd_server_port),
        '--idle_suicide_seconds=%s' % (ycmd_server_idle_suicide_seconds),
        '--check_interval_seconds=%s' % (ycmd_max_server_wait_time_seconds),
        '--options_file=%s' % (temp_file_name),
        # XXX : REMOVE ME - testing only
        '--log=debug',
        '--stdout=%s' % (stdout_file_name),
        '--stderr=%s' % (stderr_file_name),
        '--keep_logfiles',
    ])
    ycmd_process_handle.cwd = working_directory

    # don't start it up just yet... set up the return value while we can
    ycmd_server = Server(
        process_handle=ycmd_process_handle,
        hostname=ycmd_server_hostname,
        port=ycmd_server_port,
        hmac=ycmd_hmac_secret,
        label=ycmd_server_label,
    )

    ycmd_process_handle.filehandles.stdout = FileHandles.PIPE
    ycmd_process_handle.filehandles.stderr = FileHandles.PIPE

    try:
        ycmd_process_handle.start()
    except ValueError as e:
        logger.critical('failed to launch ycmd server, argument error: %s', e)
    except OSError as e:
        logger.warning('failed to launch ycmd server, system error: %s', e)
    finally:
        pass
        # TODO : Add this into the Server logic.
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
