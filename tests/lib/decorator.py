#!/usr/bin/env python3
'''
tests/lib/decorator.py
Defines decorators for wrapping test functions.
'''

import functools
import logging

logger = logging.getLogger('sublime-ycmd.' + __name__)


class LoggingContextFilter(logging.Filter):
    ''' Specialized log filter for adding a prefix to log records. '''

    def __init__(self, name='', prefix=None):
        super(LoggingContextFilter, self).__init__(name=name)
        self._prefix = prefix if prefix is not None else ''

    def filter(self, record):
        # chain with other decorators - add onto the end
        current_decoration = getattr(record, 'decoration', '')
        next_decoration = current_decoration + self._prefix
        setattr(record, 'decoration', next_decoration)

        current_msg = getattr(record, 'msg')    # type: str
        if current_msg.startswith(current_decoration):
            # remove previous decoration
            current_decoration_len = len(current_decoration)
            # technically this can raise an index error, but whatever
            has_space = current_msg[current_decoration_len] == ' '

            trim_len = (
                current_decoration_len + 1
                if has_space
                else current_decoration_len
            )
            base_msg = current_msg[trim_len:]
        else:
            base_msg = current_msg

        next_msg = '%s ' % (next_decoration) + base_msg
        setattr(record, 'msg', next_msg)

        # always pass filter - don't reject any messages
        return True


class LoggingContext(object):
    '''
    Specialized logging context manager for adding context to log records.
    '''

    def __init__(self, logger, desc=None):
        # pylint: disable=redefined-outer-name
        self._logger = logger
        self._handler = None
        self._filter = None
        self._desc = desc if desc is not None else ''

    def _get_first_handler(self):
        if not self._logger:
            return None

        if not self._logger.hasHandlers():
            # attach directly to logger
            return self._logger

        handlers = self._logger.handlers
        if not handlers:
            # again, attach directly to logger
            return self._logger

        first_handler = handlers[0]
        return first_handler

    def __enter__(self):
        self._handler = self._get_first_handler()
        if not self._handler:
            logger.error('failed to get handler for: %r', self._logger)
            return

        self._filter = LoggingContextFilter(name=self._desc, prefix=self._desc)
        self._handler.addFilter(self._filter)

    def __exit__(self, exc_type, exc_value, traceback):
        if self._handler and self._filter:
            self._handler.removeFilter(self._filter)

        self._handler = None
        self._filter = None

        # make sure to return `None` to indicate that we don't want to swallow
        # the exception (if there even was one)
        return None


def log_function(desc=None, logger=None,
                 include_args=False, include_kwargs=False,
                 include_return=False):
    '''
    Decorator for a function call.
    Generates log messages when executing the underlying function. Attaches a
    specialized filter to the logger to prepend the description to all log
    messages while executing the function.
    If `desc` is provided, it is used in the log message prefix. If omitted,
    the function name will be used.
    If `logger` is provided, a handler is attached to it during the execution
    of the test function, and restored afterwards. Log statements will then
    include a prefix of `desc` in the messages. If `logger` is omitted, the
    root logger is used.
    If `include_args` is true, then positional arguments are logged prior to
    running the function.
    If `include_kwargs` is true, then keyword-arguments are logged prior to
    running the function.
    If `include_return` is true, then the return value is logged after running
    the function.
    '''

    # pylint: disable=redefined-outer-name
    if desc:
        def get_desc(fn):
            # pylint: disable=unused-argument
            return desc
    else:
        def get_desc(fn):
            if hasattr(fn, '__name__'):
                return getattr(fn, '__name__')
            return '?'

    if logger is None:
        logger = logging.getLogger('sublime-ycmd')

    def log_function_runner(fn):
        ''' Base decorator. Decorates the underlying function. '''

        desc = get_desc(fn)

        @functools.wraps(fn)
        def log_function_run(*args, **kwargs):
            with LoggingContext(logger=logger, desc=desc):
                if include_args and include_kwargs:
                    logger.debug('args, kwargs: %r, %r', args, kwargs)
                elif include_args:
                    logger.debug('args: %r', args)
                elif include_kwargs:
                    logger.debug('kwargs: %r', kwargs)

                result = fn(*args, **kwargs)

                if include_return:
                    logger.debug('return: %r', result)

                return result

        return log_function_run

    return log_function_runner
