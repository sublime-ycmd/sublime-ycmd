#!/usr/bin/env python3
'''
tests/test_process.py
Unit tests for the process module.
'''

import io
import logging
import unittest

import lib.process
import tests.utils

logger = logging.getLogger('sublime-ycmd.' + __name__)


def make_output_stream(process):
    '''
    Creates an in-memory output stream and binds the given process' stdout
    and stderr to it.
    '''
    assert isinstance(process, lib.process.SYprocess), \
        '[internal] process is not a SYprocess instance: %r' % process

    memstream = io.StringIO()

    process.filehandles.stdout = memstream
    process.filehandles.stderr = memstream

    return memstream


def set_process_output_pipes(process):
    '''
    Sets the stdout and stderr handles for the process to be a PIPE. This
    allows reading stdout and stderr from the process.
    '''
    assert isinstance(process, lib.process.SYprocess), \
        '[internal] process is not a SYprocess instance: %r' % process

    assert not process.alive(), \
        '[internal] process is running already, cannot redirect outputs'

    process.filehandles.stdout = lib.process.SYfileHandles.PIPE
    process.filehandles.stderr = lib.process.SYfileHandles.PIPE


def poll_process_output(process):
    '''
    Reads and returns the output to stdout and stderr for the supplied process.
    This blocks until the process has either terminated, or has closed the
    output file descriptors.
    '''
    assert isinstance(process, lib.process.SYprocess), \
        '[internal] process is not a SYprocess instance: %r' % process

    if process.alive():
        logger.debug('process is still alive, this will likely block')

    # wait at most 3 seconds, and throw TimeoutExpired if that passes
    return process.communicate(None, 3)


class SYTprocess(unittest.TestCase):
    '''
    Unit tests for the process class. This class should allow configuration
    and management of a generic process.
    '''

    @tests.utils.logtest('process : echo')
    def test_pr_echo(self):
        ''' Ensures that the process can launch a simple echo command. '''
        echo_process = lib.process.SYprocess()
        set_process_output_pipes(echo_process)

        echo_process.binary = 'echo'
        echo_process.args.extend(['hello', 'world'])

        echo_process.start()

        stdout, stderr = poll_process_output(echo_process)

        logger.debug('process finished, output is: %s', stdout)

        self.assertEqual(b'hello world\n', stdout)
        self.assertEqual(b'', stderr)
