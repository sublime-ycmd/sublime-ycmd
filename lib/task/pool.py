#!/usr/bin/env python3

'''
lib/task/pool.py
Task pool abstraction.

Defines a task pool class that can be used to run tasks asynchronously.
'''

import logging
import queue
import threading

from lib.task.task import Task

logger = logging.getLogger('sublime-ycmd.' + __name__)


class Pool(object):

    def __init__(self):
        self._queue = queue.Queue()
        self._lock = threading.RLock()
        self._cv = threading.Condition(self._lock)

    def empty(self):
        return self._queue.empty()

    def put(self, task, block=True, timeout=None):
        if not isinstance(task, Task):
            raise TypeError('task must be a Task: %r' % (task))

        self._queue.put(task, block=block, timeout=timeout)
        self._register_task(task)
        with self._cv:
            self._cv.notify()

    def get(self, block=True, timeout=None):
        task = self._queue.get(block=block, timeout=timeout)    # type: Task
        return task

    def task_done(self):
        self._queue.task_done()

    def join(self):
        # wake all worker threads prior to joining
        # should not be necessary, but just in case
        with self._cv:
            self._cv.notify_all()

        self._queue.join()

    @property
    def cv(self):
        cv = self._cv       # type: threading.Condition
        return cv

    def _register_task(self, task):
        assert isinstance(task, Task), \
            '[internal] task is not a Task: %r' % (task)

        task.set_pending(owner=self)
