#!/usr/bin/env python3

'''
lib/process.py
Contains utilities for working with processes. This is used to start and manage
the ycmd server process.
'''

import io
import logging
import os
import subprocess

from lib.fs import (
    resolve_binary_path,
)

logger = logging.getLogger('sublime-ycmd.' + __name__)


class SYfileHandles(object):
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
        ''' Validates that a handle is None, or a file-like object. '''
        if handle is None or isinstance(handle, io.IOBase):
            return True
        # explicitly allow the special flags as well
        if handle in [SYfileHandles.PIPE,
                      SYfileHandles.DEVNULL,
                      SYfileHandles.STDOUT]:
            return True
        return False

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


class SYprocess(object):
    '''
    Process class
    This class represents a managed process.
    '''

    def __init__(self):
        self._binary = None
        self._args = None
        self._env = None
        self._cwd = None
        self._filehandles = SYfileHandles()

        self._handle = None

    @property
    def binary(self):
        ''' Returns the process binary. '''
        return self._binary

    @binary.setter
    def binary(self, binary):
        ''' Sets the process binary. '''
        assert isinstance(binary, str), 'binary must be a string: %r' % binary
        binary = resolve_binary_path(binary)
        assert os.path.isfile(binary), 'binary path invalid: %r' % binary

        logger.debug('setting binary to: %s', binary)
        self._binary = binary

    @property
    def args(self):
        ''' Returns the process args. Initializes it if it is None. '''
        if self._args is None:
            self._args = []
        return self._args

    @args.setter
    def args(self, args):
        ''' Sets the process arguments. '''
        if self.alive():
            logger.warning('process already started... no point setting args')

        assert hasattr(args, '__iter__'), 'args must be iterable: %r' % args

        if self._args is not None:
            logger.warning('overwriting existing process args: %r', self._args)
        logger.debug('setting args to: %s', args)

        self._args = list(args)

    @property
    def env(self):
        ''' Returns the process env. Initializes it if it is None. '''
        if self._env is None:
            self._env = {}
        return self._env

    @env.setter
    def env(self, env):
        ''' Sets the process environment variables. '''
        if self.alive():
            logger.warning('process already started... no point setting env')

        assert isinstance(env, dict), 'env must be a dictionary: %r' % env

        if self._env is not None:
            logger.warning('overwriting existing process env: %r', self._env)
        logger.debug('setting env to: %s', env)

        self._env = dict(env)

    @property
    def cwd(self):
        ''' Returns the process working directory. '''
        return self._cwd

    @cwd.setter
    def cwd(self, cwd):
        ''' Sets the process working directory. '''
        if self.alive():
            logger.warning('process already started... no point setting cwd')

        assert isinstance(cwd, str), 'cwd must be a string: %r' % cwd
        if not os.path.isdir(cwd):
            logger.warning('invalid working directory: %s', cwd)

        logger.debug('setting cwd to: %s', cwd)
        self._cwd = cwd

    @property
    def filehandles(self):
        ''' Returns the process file handles. '''
        return self._filehandles

    def alive(self):
        ''' Returns whether or not the process is active. '''
        if self._handle is None:
            return False
        assert isinstance(self._handle, subprocess.Popen), \
            '[internal] handle is not a Popen instance: %r' % self._handle
        status = self._handle.poll()
        logger.debug('process handle status: %r', status)
        return status is None

    def start(self):
        ''' Starts the process according to current configuration. '''
        if self.alive():
            raise Exception('process has already been started')

        assert self._binary is not None and isinstance(self._binary, str), \
            'process binary is invalid: %r' % self._binary
        assert self._args is None or hasattr(self._args, '__iter__'), \
            'process args list is invalid: %r' % self._args

        process_args = [self._binary]
        if self._args:
            process_args.extend(self._args)

        popen_args = {
            'args': process_args,
            'stdin': self._filehandles.stdin,
            'stdout': self._filehandles.stdout,
            'stderr': self._filehandles.stderr,
            'cwd': self._cwd,
            'env': self._env,
        }
        logger.debug('arguments to Popen are: %r', popen_args)

        self._handle = subprocess.Popen(**popen_args)

    def communicate(self, inpt=None, timeout=None):
        '''
        Sends data via stdin and reads data from stdout, stderr.
        This will likely block if the process is still alive.
        When input is None, stdin is immediately closed.
        When timeout is None, this waits indefinitely for the process to
        terminate. Otherwise, it is interpreted as the number of seconds to
        wait for, until raising a TimeoutExpired exception.
        '''
        if not self.alive():
            logger.debug('process not alive, unlikely to block')

        assert self._handle is not None
        return self._handle.communicate(inpt, timeout)

    def wait(self, maxwait=10):
        ''' Waits maxwait seconds for the process to finish. '''
        if not self.alive():
            logger.debug('process not alive, nothing to wait for')
            return

        assert self._handle is not None
        self._handle.wait(maxwait)

    def kill(self):
        ''' Kills the associated process, by sending a signal. '''
        if not self.alive():
            logger.debug('process is already dead, not sending signal')
            return

        assert self._handle is not None
        self._handle.kill()
