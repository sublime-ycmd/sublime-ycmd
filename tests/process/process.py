#!/usr/bin/env python3

'''
lib/process/process.py
Tests for the process class.
'''

import io
import logging
import unittest

from lib.process import (
    FileHandles,
    Process,
)
from tests.lib.decorator import log_function

logger = logging.getLogger('sublime-ycmd.' + __name__)


def make_output_stream(process):
    '''
    Creates an in-memory output stream and binds the given process' stdout
    and stderr to it.
    '''
    assert isinstance(process, Process), \
        '[internal] process is not a Process instance: %r' % process

    memstream = io.StringIO()

    process.filehandles.stdout = memstream
    process.filehandles.stderr = memstream

    return memstream


def set_process_output_pipes(process):
    '''
    Sets the stdout and stderr handles for the process to be a PIPE. This
    allows reading stdout and stderr from the process.
    '''
    assert isinstance(process, Process), \
        '[internal] process is not a Process instance: %r' % process

    assert not process.alive(), \
        '[internal] process is running already, cannot redirect outputs'

    process.filehandles.stdout = FileHandles.PIPE
    process.filehandles.stderr = FileHandles.PIPE


def poll_process_output(process):
    '''
    Reads and returns the output to stdout and stderr for the supplied process.
    This blocks until the process has either terminated, or has closed the
    output file descriptors.
    '''
    assert isinstance(process, Process), \
        '[internal] process is not a Process instance: %r' % process

    if process.alive():
        logger.debug('process is still alive, this will likely block')

    # wait at most 3 seconds, and throw TimeoutExpired if that passes
    return process.communicate(None, 3)


class TestProcess(unittest.TestCase):
    '''
    Unit tests for the process class. This class should allow configuration
    and management of a generic process.
    '''

    @log_function('[process : echo]')
    def test_process_echo(self):
        ''' Ensures that the process can launch a simple echo command. '''
        echo_process = Process()
        set_process_output_pipes(echo_process)

        echo_process.binary = 'echo'
        echo_process.args.extend(['hello', 'world'])

        echo_process.start()

        stdout, stderr = poll_process_output(echo_process)

        logger.debug('process finished, output is: %s', stdout)

        self.assertEqual(b'hello world\n', stdout)
        self.assertEqual(b'', stderr)
