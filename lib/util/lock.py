#!/usr/bin/env python3

'''
lib/util/lock.py
Contains lock utilities.
'''

import functools
import logging
import threading

logger = logging.getLogger('sublime-ycmd.' + __name__)


def lock_guard(lock=None):
    '''
    Locking decorator.

    Calls the decorated function with the `lock` held, and releases when done.

    If `lock` is omitted, and a class method is passed in, the decorated method
    will attempt to use the instance-specific `self._lock` variable. If the
    instance has no lock, or if a static function is decorated, a unique
    `threading.RLock` will be created.
    '''

    _lock = lock if lock is not None else threading.RLock()

    if not hasattr(_lock, '__enter__') or not hasattr(_lock, '__exit__'):
        raise TypeError('lock must support context management: %r' % (_lock))

    def lock_guard_function(fn):

        if hasattr(fn, '__self__'):
            # given a method, so attempt to use an instance-specific lock
            @functools.wraps(fn)
            def lock_guard_run(self, *args, **kwargs):
                __lock = getattr(self, '_lock', _lock)
                with __lock:
                    return fn(*args, **kwargs)
        else:
            # given a function, always use the default lock
            @functools.wraps(fn)
            def lock_guard_run(*args, **kwargs):
                __lock = _lock
                with __lock:
                    return fn(*args, **kwargs)

        return lock_guard_run

    return lock_guard_function
