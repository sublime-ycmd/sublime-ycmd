#!/usr/bin/env python3

'''
lib/task/worker.py
Task pool worker thread. Meant for internal use only.

Runs a thread to process items in a task pool. The class itself does not
inherit from `threading.Thread` directly. Instead, a helper function is exposed
for use in a thread target.

Users should not need to access this. Task pools will generate and manage
workers by itself.
'''

import queue
import logging
import threading

# for type annotations only:
from lib.task.task import Task      # noqa: F401

logger = logging.getLogger('sublime-ycmd.' + __name__)


def spawn_worker(pool, name=None):
    if name is not None and not isinstance(name, str):
        raise TypeError('name must be a str: %r' % (name))

    worker_instance = Worker(pool)

    def run_worker():
        try:
            worker_instance.run()
        except Exception as e:
            logger.critical(
                'unhandled exception during worker thread loop: %r', e,
            )

        # explicitly delete references since worker is about to exit:
        worker_instance.clear()

    worker_thread = threading.Thread(target=run_worker, name=name)
    worker_thread.daemon = True

    worker_instance.handle = worker_thread
    logger.debug('created worker: %r', worker_instance)

    worker_thread.start()
    return worker_instance


class Worker(object):
    '''
    Worker thread abstraction class.

    Defines a worker unit that runs an infinite loop, processing tasks from a
    task pool.

    This class is compatible with (i.e. can inherit from) `threading.Thread`.
    It is deliberately left as a plain object though.

    This class does not use locking. It is expected that the owners will.

    TODO : Use a log adapter to decorate based on worker info.
    '''

    def __init__(self, pool, handle=None):
        self._pool = pool       # type: Pool
        self._handle = None     # type: threading.Thread

        self.handle = handle

    def run(self):
        '''
        Starts the worker thread, running an infinite loop waiting for jobs.

        This should be run on an alternate thread, as it will block.
        '''
        task_queue = self.pool.queue    # type: queue.Queue

        logger.debug('task worker starting: %r', self)
        while True:
            # explicitly specify `block`, in case the queue has custom settings
            task = task_queue.get(block=True)   # type: Task

            if task is not None:
                # NOTE : Tasks should catch their own exceptions.
                try:
                    task.run()
                except Exception as e:
                    logger.error(
                        'exception during task execution: %r',
                        e, exc_info=True,
                    )

                # explicitly clear reference to task
                del task
                continue

            # task is none, so check if a shutdown is requested
            if not self.pool.running:
                logger.debug('task pool has stopped running, exit loop')

                # pass on the signal to any other worker threads
                try:
                    task_queue.put(None, block=True, timeout=1)
                except queue.Full:
                    logger.warning(
                        'task queue is full, '
                        'cannot signal other workers to exit'
                    )

                break

            logger.warning('unhandled task on worker thread: %r', task)

        logger.debug('task worker exiting:  %r', self)

    def join(self, timeout=None):
        '''
        Joins the underlying thread for this worker.

        If `timeout` is omitted, this will block indefinitely until the thread
        has exited.
        If `timeout` is provided, it should be the maximum number of seconds to
        wait until returning. If the thread is still alive after the timeout
        expires, a `TimeoutError` will be raised.
        '''
        handle = self._handle       # type: threading.Thread
        if not handle:
            # worker is already dead
            return

        handle.join(timeout=timeout)
        if handle.is_alive():
            timeout_desc = (
                ' after %rs' % (timeout) if timeout is not None else ''
            )
            raise TimeoutError('thread did not exit%s' % (timeout_desc))

    def clear(self):
        '''
        Clears the locally held reference to the task pool and thread handle.
        '''
        self._pool = None
        self._handle = None

    @property
    def handle(self):
        '''
        Retrieves the currently held thread handle, if any.
        '''
        return self._handle

    @handle.setter
    def handle(self, handle):
        '''
        Sets the thread handle for the worker.
        '''
        if handle is None:
            # clear state
            self._handle = None
            return

        if handle is not None and not isinstance(handle, threading.Thread):
            raise TypeError(
                'thread handle must be a threading.Thread: %r' % (handle)
            )

        self._handle = handle

    @property
    def pool(self):
        '''
        Retrieves the parent task pool.
        '''
        return self._pool

    @property
    def name(self):
        '''
        Retrieves the name from the thread handle, if available.
        '''
        if self._handle:
            return self._handle.name

        return None

    @name.setter
    def name(self, name):
        '''
        Sets the name of the held thread handle.
        '''
        if self._handle:
            self._handle.name = name
        # else, meh, whatever

    def __repr__(self):
        return '%s(%r)' % ('Worker', {
            'handle': self.handle,
            'name': self.name,
            'pool': self.pool,
        })
