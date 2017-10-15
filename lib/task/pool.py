#!/usr/bin/env python3

'''
lib/task/pool.py
Task pool abstraction. Replacement for `concurrent.futures`.

Defines a task pool class that can be used to run tasks asynchronously.

Most of this logic was taken from pythonfutures:
https://github.com/agronholm/pythonfutures
https://git.io/vdCQ2
'''

from concurrent.futures import _base as futurebase
import logging
import queue
import threading

from lib.task.task import Task
from lib.task.worker import spawn_worker
from lib.util.id import generate_id
from lib.util.sys import get_cpu_count

logger = logging.getLogger('sublime-ycmd.' + __name__)


class Pool(object):
    '''
    Task pool. Schedules work to run in a thread pool.

    This class conforms to `concurrent.futures.Executor`. It does not use
    weak references, however, so it is expected that the application shuts down
    the pool properly. Worker threads are created as daemons, so they won't
    stop the program from shutting down.
    '''

    def __init__(self, max_workers=None, thread_name_prefix=''):
        if max_workers is None:
            max_workers = (get_cpu_count() or 1) * 5

        if not isinstance(max_workers, int):
            raise TypeError('max workers must be an int: %r' % (max_workers))
        if max_workers <= 0:
            raise ValueError(
                'max workers must be positive: %r' % (max_workers)
            )

        if not isinstance(thread_name_prefix, str):
            raise TypeError(
                'thread name prefix must be a str: %r' % (thread_name_prefix)
            )

        self._max_workers = max_workers
        self._thread_name_prefix = thread_name_prefix

        self._queue = queue.Queue()
        self._workers = None
        self._lock = threading.Lock()
        self._running = None

        self._name = None
        self.name = thread_name_prefix

        self.start()

    def start(self):
        with self._lock:
            self._running = True

            # NOTE : This unconditionally adds more workers (can go over max).
            self._create_workers()

    def _create_workers(self, num_workers=None):
        if num_workers is None:
            num_workers = self._max_workers
        assert isinstance(num_workers, int), \
            'num workers must be an int: %r' % (num_workers)

        # check existing workers and issue a warning if it exceeds max
        num_existing = len(self._workers) if self._workers else 0
        num_expected = num_workers + num_existing
        if num_expected > self._max_workers:
            logger.warning(
                'starting %d workers when %d already exist, '
                'total workers will exceed max workers: %d / %d',
                num_workers, num_existing, num_expected, self._max_workers,
            )
            # but fall through and start the new workers anyway

        created_workers = set(
            spawn_worker(self, name=generate_id(self._thread_name_prefix))
            for _ in range(num_workers)
        )
        logger.debug('created workers: %r', created_workers)

        if self._workers is None:
            self._workers = set()
        self._workers.update(created_workers)

    def submit(self, fn, *args, **kwargs):
        with self._lock:
            if not self._running:
                raise RuntimeError('task pool is not running')

            future = futurebase.Future()
            task = Task(future, fn, args, kwargs)

            self._queue.put(task)

            return future

    def shutdown(self, wait=True, timeout=None):
        '''
        TODO : Fill `shutdown` description.

        The `timeout` parameter is shared between all join operations. It is
        possible for this function to block for longer than `timeout` seconds.
        '''
        with self._lock:
            self._running = False
            self._queue.put(None)

        wait_result = True
        if wait:
            # create a copy of the worker set, as we'll be removing workers
            # once they get joined successfully
            workers = list(self._workers)

            for worker in workers:  # type: Worker
                try:
                    worker.join(timeout=timeout)
                except TimeoutError:
                    # update overall result to indicate failure
                    wait_result = False
                else:
                    # remove worker from worker set
                    self._workers.remove(worker)

        return wait_result

    @property
    def queue(self):
        return self._queue

    @property
    def running(self):
        with self._lock:
            return self._running

    def __repr__(self):
        if self._thread_name_prefix:
            return '%s(%r)' % ('Pool', self._thread_name_prefix)
        return 'Pool()'


def disown_task_pool(task_pool, name=None, daemon=None):
    '''
    Shuts down a task pool on a daemon thread. The thread allows the task pool
    to run to completion. Once it is completed, the thread itself terminates.

    TODO : Store a weak ref to the pool, in case we need to hard-stop a buggy
           one that keeps running indefinitely.
    '''

    if name is None:
        name = generate_id('shutdown-task-pool-')

    if daemon is None:
        daemon = True

    # Until the TODO is done, the interim solution is to give a grace period.
    # Specify the time limit for shutting down in seconds.
    _TASK_POOL_SHUTDOWN_GRACE = (5 * 60)        # 5 minutes

    def shutdown_task_pool(task_pool=task_pool,
                           timeout=_TASK_POOL_SHUTDOWN_GRACE):
        logger.debug('task pool shutdown thread has started')

        try:
            logger.debug('waiting for task pool to shut down...')
            if task_pool.shutdown(wait=True, timeout=timeout):
                logger.debug('task pool has shut down successfully')
            else:
                logger.warning(
                    'task pool did not shut down in %ss, ignoring it', timeout,
                )
        except Exception as e:
            logger.error('unhandled error during task pool shutdown: %r', e)

        # explicitly clear reference to the pool
        del task_pool

        logger.debug('task pool shutdown thread finished, about to exit')

    shutdown_thread = threading.Thread(
        target=shutdown_task_pool, name=name, daemon=daemon,
    )

    logger.debug('shutting down task pool on thread: %r', shutdown_thread)
    shutdown_thread.start()

    logger.debug('thread started, task pool will be shut down')
    return shutdown_thread
