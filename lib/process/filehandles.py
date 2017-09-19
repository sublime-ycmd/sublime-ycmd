#!/usr/bin/env python3

'''
lib/process/process.py
Process file handle wrapper class.

Provides a way to customize the stdin, stdout, and stderr file handles of a
process before launching it. By default, all handles will be closed, which
means it would be impossible to write data to it or read output from it.
'''

import io
import logging
import subprocess

logger = logging.getLogger('sublime-ycmd.' + __name__)


class FileHandles(object):
    '''
    Container class for process file handles (stdin, stdout, stderr).
    Provides an option to set up PIPEs when starting processes, and then allows
    reading/writing to those pipes with helper methods.
    '''

    PIPE = subprocess.PIPE
    DEVNULL = subprocess.DEVNULL
    STDOUT = subprocess.STDOUT

    def __init__(self):
        self._stdin = None
        self._stdout = None
        self._stderr = None

    def configure_filehandles(self, stdin=None, stdout=None, stderr=None):
        '''
        Sets the file handle behaviour for the launched process. Each handle
        can be assigned one of the subprocess handle constants:
            stdin = None, PIPE
            stdout = None, PIPE, DEVNULL
            stderr = None, PIPE, DEVNULL, STDOUT
        These value gets forwarded directly to Popen.
        '''
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr

    @staticmethod
    def valid_filehandle(handle):
        ''' Validates that a handle is `None`, or a file-like object. '''
        if handle is None or isinstance(handle, io.IOBase):
            return True

        # explicitly allow the special flags as well
        return handle in [
            FileHandles.PIPE,
            FileHandles.DEVNULL,
            FileHandles.STDOUT,
        ]

    @property
    def stdin(self):
        ''' Returns the configured stdin handle. '''
        return self._stdin

    @stdin.setter
    def stdin(self, stdin):
        ''' Sets the stdin file handle. '''
        if not self.valid_filehandle(stdin):
            raise ValueError('stdin handle must be a file instance')
        if stdin == self.STDOUT:
            # what?
            raise ValueError('stdin handle cannot be redirected to stdout')
        self._stdin = stdin

    @property
    def stdout(self):
        ''' Returns the configured stdout handle. '''
        return self._stdout

    @stdout.setter
    def stdout(self, stdout):
        if not self.valid_filehandle(stdout):
            raise ValueError('stdout handle must be a file instance')
        # do not allow STDOUT
        if stdout == self.STDOUT:
            raise ValueError('stdout handle cannot be redirected to stdout')
        self._stdout = stdout

    @property
    def stderr(self):
        ''' Returns the configured stderr handle. '''
        return self._stderr

    @stderr.setter
    def stderr(self, stderr):
        if not self.valid_filehandle(stderr):
            raise ValueError('stderr handle must be a file instance')
        self._stderr = stderr
