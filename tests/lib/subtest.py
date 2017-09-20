#!/usr/bin/env python3
'''
tests/lib/subtest.py
Utility functions for running sub-tests within a test case. Includes additional
logging to add context during sub-test execution.
'''

import logging
import unittest

from tests.lib.decorator import log_function

logger = logging.getLogger('sublime-ycmd.' + __name__)


def _is_args_kwargs(test_case):
    if not isinstance(test_case, (tuple, list)):
        return False
    if len(test_case) != 2:
        return False

    if not isinstance(test_case[1], dict):
        return False

    return True


def map_test_function(test_instance, test_function, test_cases):
    assert isinstance(test_instance, unittest.TestCase), \
        'test instance must be a unittest.TestCase: %r' % (test_instance)
    assert callable(test_function), \
        'test function must be callable: %r' % (test_function)
    assert hasattr(test_cases, '__iter__'), \
        'test cases must be iterable: %r' % (test_cases)

    for test_index, test_case in enumerate(test_cases, start=1):
        is_args_kwargs = _is_args_kwargs(test_case)
        is_kwargs = isinstance(test_case, dict)
        is_args = not (is_args_kwargs or is_kwargs)

        if is_args_kwargs:
            test_args, test_kwargs = test_case
        elif is_kwargs:
            test_args = tuple()
            test_kwargs = test_case
        elif is_args:
            test_args = test_case
            test_kwargs = dict()

        log_args = is_args_kwargs or is_args
        log_kwargs = is_args_kwargs or is_kwargs

        wrapped_test_function = log_function(
            desc='[%d]' % (test_index),
            include_args=log_args, include_kwargs=log_kwargs,
        )(test_function)

        wrapped_test_function(*test_args, **test_kwargs)
