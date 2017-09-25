#!/usr/bin/env python3

'''
tests/task/simulate.py
Tests for the task module as a whole.

Sets up a task pool, workers, and tasks. Runs the tasks. Checks the results.
'''

import logging
import time
import unittest

from lib.task import (
    Pool,
    Task,
    Worker,
    spawn_worker,
)
from tests.lib.decorator import log_function

logger = logging.getLogger('sublime-ycmd.' + __name__)


def process_task_pool(pool, max_wait_time=5, sleep_interval=1):
    '''
    Runs the provided task `Pool` until all tasks have finished.

    The `max_wait_time` indicates the (minimum) amount of seconds that must
    pass until an exception is raised. If set to `0`, no timeout will occur.

    This will attempt to recover from potential pitfalls (i.e. unintended
    behaviour), so it hopefully won't block indefinitely.

    Raises a `TimeoutError` if run time exceeds `max_wait_time` seconds.
    '''
    if not isinstance(max_wait_time, (int, float)):
        raise TypeError('max wait time must be a number: %r' % (max_wait_time))
    if not isinstance(pool, Pool):
        raise TypeError('task pool must be a Pool: %r' % (pool))

    no_timeout = (max_wait_time == 0)
    if no_timeout:
        raise NotImplementedError

    logger.debug(
        'waiting %r seconds in %r second intervals for tasks to complete',
        max_wait_time, sleep_interval,
    )

    # not the most elegant solution, but fairly reliable
    current_wait_time = 0
    while current_wait_time < max_wait_time:
        with pool.cv:
            if pool.empty():
                logger.debug('task pool empty! returning')
                return

        logger.debug('tasks are still pending, waiting %rs', sleep_interval)
        time.sleep(sleep_interval)
        current_wait_time += sleep_interval

    if current_wait_time >= max_wait_time:
        raise TimeoutError('run time exceeded %r seconds' % (max_wait_time))


def stop_task_workers(workers, max_wait_time=5, sleep_interval=1):
    '''
    Attempts to gracefully stop `workers`, which should be an iterable of
    task `Worker` instances.

    They will first be stopped, which should cause the worker to break out of
    its infinite loop. Then, the worker threads are joined, so they should get
    cleaned up.

    The behaviour of `max_wait_time` and `sleep_interval` is the same as in
    `process_task_pool`. See that for more info.
    '''
    if not hasattr(workers, '__iter__'):
        raise TypeError('workers must be an iterable: %r' % (workers))

    no_timeout = (max_wait_time == 0)
    if no_timeout:
        raise NotImplementedError

    logger.debug(
        'waiting %r seconds in %r second intervals for workers to stop',
        max_wait_time, sleep_interval,
    )

    def try_join_worker(worker):
        assert isinstance(worker, Worker), \
            '[internal] worker is not a Worker: %r' % (worker)

        try:
            # send a stop command, it won't do anything if it's already stopped
            worker.stop()
            # threads can be joined multiple times, that won't error out
            worker.join(timeout=0)
        except TimeoutError:
            return False
        return True

    # keep the active workers in a set so they can be removed as they exit
    worker_set = set(workers)

    current_wait_time = 0
    while current_wait_time < max_wait_time:
        joined_workers = set(filter(try_join_worker, worker_set))
        live_workers = worker_set - joined_workers

        worker_set = live_workers
        if not live_workers:
            logger.debug('all threads joined! returning')
            return

        logger.debug('workers are still alive, waiting %rs', sleep_interval)
        time.sleep(sleep_interval)
        current_wait_time += sleep_interval

    if current_wait_time >= max_wait_time:
        raise TimeoutError('join time exceeded %r seconds' % (max_wait_time))


def _calculate_expected_run_time(sleep_time, num_tasks, num_workers):
    return (float(sleep_time) * num_tasks) / num_workers


def check_task_parameters(sleep_time, num_tasks, num_workers, max_wait_time):
    expected_run_time = _calculate_expected_run_time(
        sleep_time, num_tasks, num_workers,
    )
    if expected_run_time >= max_wait_time:
        logger.critical(
            'invalid test parameters, test is expected to fail: %r',
            {
                'sleep_time': sleep_time,
                'num_tasks': num_tasks,
                'num_workers': num_workers,
                'max_wait_time': max_wait_time,
            },
        )
    assert expected_run_time < max_wait_time, \
        'simulation parameters invalid, ' \
        'expected run time exceeds max wait time: %r vs. %r seconds' % \
        (expected_run_time, max_wait_time)

    run_time_margin = max_wait_time - expected_run_time
    if run_time_margin <= 1.0:
        logger.warning(
            'test might fail, not much margin between '
            'expected run time and max wait time: %r vs. %r seconds',
            expected_run_time, max_wait_time,
        )


class TestSleepTasks(unittest.TestCase):
    '''
    Tests that use "sleep" to simulate work.
    '''

    def _run_sleep_tasks(self, sleep_time, num_tasks,
                         num_workers, max_wait_time,
                         task_fn=None):
        check_task_parameters(
            sleep_time, num_tasks, num_workers, max_wait_time,
        )

        def _sleep():
            time.sleep(sleep_time)

        pool = Pool()

        logger.debug('creating %d worker(s)', num_workers)
        workers = [
            spawn_worker(pool, name='worker %d' % (i))
            for i in range(num_workers)
        ]

        logger.debug('creating %d task(s)', num_tasks)
        tasks = [Task(_sleep) for i in range(num_tasks)]
        for task in tasks:
            pool.put(task)

        logger.debug('waiting for tasks to complete...')
        process_task_pool(pool, max_wait_time=max_wait_time)

        logger.debug('waiting for worker threads to finish...')
        stop_task_workers(workers, max_wait_time=max_wait_time)

        logger.debug('checking task results')
        for task_number, task in enumerate(tasks, start=1):
            logger.debug('[%d] %r', task_number, task)
            self.assertFalse(
                task.had_error,
                'task #%d was unsuccessful: %r' % (task_number, task.result),
            )

    @log_function('[task-sleep : single]')
    def test_sleep_single(self):
        '''
        Single worker.
        '''
        # NOTE : When selecting these numbers, ensure that:
        #        sleep_time * num_tasks / num_workers < max_wait_time
        sleep_time = 0.2
        num_tasks = 8
        num_workers = 1
        max_wait_time = 5
        self._run_sleep_tasks(
            sleep_time=sleep_time, num_tasks=num_tasks,
            num_workers=num_workers, max_wait_time=max_wait_time,
        )

    @log_function('[task-sleep : multi]')
    def test_sleep_multi(self):
        '''
        Multiple workers.
        '''
        sleep_time = 0.2
        num_tasks = 64
        num_workers = 8
        max_wait_time = 5
        self._run_sleep_tasks(
            sleep_time=sleep_time, num_tasks=num_tasks,
            num_workers=num_workers, max_wait_time=max_wait_time,
        )
