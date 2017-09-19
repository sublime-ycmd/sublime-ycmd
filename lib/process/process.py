#!/usr/bin/env python3

'''
lib/process/process.py
Process wrapper class.

Provides utilities for managing processes. This is useful for starting the ycmd
server process, checking if it's still alive, and shutting it down.
'''

import logging
import subprocess

from lib.process.filehandles import FileHandles
from lib.util.fs import (
    is_directory,
    is_file,
    resolve_binary_path,
)

logger = logging.getLogger('sublime-ycmd.' + __name__)


class Process(object):
    '''
    Process class
    This class represents a managed process.
    '''

    def __init__(self):
        self._binary = None
        self._args = None
        self._env = None
        self._cwd = None
        self._filehandles = FileHandles()

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
        assert is_file(binary), 'binary path invalid: %r' % binary

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
        # collect the arguments, so we don't exhaust the iterator
        args = list(args)

        if self._args is not None:
            logger.warning('overwriting existing process args: %r', self._args)
        logger.debug('setting args to: %s', args)

        self._args = list(args)

    @property
    def env(self):
        ''' Returns the process env. Initializes it if it is `None`. '''
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
        if not is_directory(cwd):
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
        When `inpt` is `None`, stdin is immediately closed.
        When `timeout` is `None`, this waits indefinitely for the process to
        terminate. Otherwise, it is interpreted as the number of seconds to
        wait for until raising a `TimeoutExpired` exception.
        '''
        if not self.alive():
            logger.debug('process not alive, unlikely to block')

        assert self._handle is not None, '[internal] process handle is null'
        return self._handle.communicate(inpt, timeout)

    def wait(self, maxwait=10):
        ''' Waits maxwait seconds for the process to finish. '''
        if not self.alive():
            logger.debug('process not alive, nothing to wait for')
            return

        assert self._handle is not None, '[internal] process handle is null'
        self._handle.wait(maxwait)

    def kill(self):
        ''' Kills the associated process by sending a signal. '''
        if not self.alive():
            logger.debug('process is already dead, not sending signal')
            return

        assert self._handle is not None, '[internal] process handle is null'
        self._handle.kill()
