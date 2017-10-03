#!/usr/bin/env python3

'''
tests/task/simulate.py
Tests for the task module as a whole.

Sets up a task pool, workers, and tasks. Runs the tasks. Checks the results.
'''

import logging
import time
import unittest

from lib.task import Pool
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
        if pool.queue.empty():
            logger.debug('task pool empty! returning')
            return

        logger.debug('tasks are still pending, waiting %rs', sleep_interval)
        time.sleep(sleep_interval)
        current_wait_time += sleep_interval

    if current_wait_time >= max_wait_time:
        raise TimeoutError('run time exceeded %r seconds' % (max_wait_time))


def stop_task_pool(pool, max_wait_time=5, sleep_interval=1):
    '''
    Shuts down the provided task `Pool` and waits for the workers to exit.

    The `max_wait_time` and `sleep_interval` parameters work the same as they
    do in `process_task_pool`.
    '''
    if not isinstance(max_wait_time, (int, float)):
        raise TypeError('max wait time must be a number: %r' % (max_wait_time))
    if not isinstance(pool, Pool):
        raise TypeError('task pool must be a Pool: %r' % (pool))

    no_timeout = (max_wait_time == 0)
    if no_timeout:
        raise NotImplementedError

    logger.debug(
        'waiting %r seconds in %r second intervals for pool to shutdown',
        max_wait_time, sleep_interval,
    )

    # not the most elegant solution, but fairly reliable
    current_wait_time = 0
    while current_wait_time < max_wait_time:
        if pool.shutdown(wait=True, timeout=0):
            logger.debug('task pool has shut down! returning')
            return

        logger.debug(
            'task pool still has running workers, waiting %rs', sleep_interval,
        )
        time.sleep(sleep_interval)
        current_wait_time += sleep_interval

    if current_wait_time >= max_wait_time:
        raise TimeoutError(
            'shutdown time exceeded %r seconds' % (max_wait_time)
        )


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

        logger.debug('creating pool with %d worker(s)', num_workers)
        pool = Pool(max_workers=num_workers, thread_name_prefix='runtest-')

        logger.debug('creating %d task(s)', num_tasks)
        futures = [
            pool.submit(_sleep) for _ in range(num_tasks)
        ]

        logger.debug('waiting for tasks to complete...')
        process_task_pool(pool, max_wait_time=max_wait_time)

        logger.debug('waiting for task pool to shutdown...')
        stop_task_pool(pool, max_wait_time=max_wait_time)

        logger.debug('checking task results')
        for task_number, future in enumerate(futures, start=1):
            logger.debug('[%d] %r', task_number, future)
            self.assertIsNone(
                future.exception(timeout=0),
                'task #%d failed' % (task_number)
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
