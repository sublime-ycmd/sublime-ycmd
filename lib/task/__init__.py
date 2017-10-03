#!/usr/bin/env python3

'''
lib/task
sublime-ycmd task/thread abstraction module.

This logic mainly exists to support missing APIs in older python versions.
Ideally, this would be based `concurrent.futures`, but some of it did not
appear to work correctly under the sublime plugin host.

This module is built on primitives from `queue` and `threading`, so it should
be supported in just about all environments.
'''

from lib.task.pool import Pool      # noqa
from lib.task.task import Task      # noqa
from lib.task.worker import (       # noqa
    spawn_worker,
    Worker,
)

__all__ = ['pool', 'task', 'worker']
