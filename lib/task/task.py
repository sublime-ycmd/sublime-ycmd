#!/usr/bin/env python3

'''
lib/task/task.py
Task abstraction.

Defines a task which should be run off-thread in a task pool.
'''

import logging
import sys

# for type annotations only:
import concurrent                   # noqa: F401

logger = logging.getLogger('sublime-ycmd.' + __name__)


class Task(object):

    def __init__(self, future, fn, args, kwargs):
        self._future = future   # type: concurrent.futures.Future
        self._fn = fn           # type: callable
        self._args = args
        self._kwargs = kwargs

    def run(self):
        if not self._future.set_running_or_notify_cancel():
            # cancelled, skip it
            return

        try:
            result = self._fn(*self._args, **self._kwargs)
        except:     # noqa: E722
            # failure - set exception details
            exception, traceback = sys.exc_info()[1:]
            self._future.set_exception(exception, traceback)
        else:
            # success - set result
            self._future.set_result(result)

    def __repr__(self):
        return '%s(%r)' % ('Task', {
            'future': self._future,
            'fn': self._fn,
            'args': self._args,
            'kwargs': self._kwargs,
        })
