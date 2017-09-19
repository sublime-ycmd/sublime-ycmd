#!/usr/bin/env python3
'''
tests/utils.py
Contains utility code for the unit tests.
'''

import logging
import unittest

logger = logging.getLogger('sublime-ycmd.' + __name__)


def logtest(testname):
    '''
    Decorator for test functions
    Generates log messages when executing the supplied test.
    '''
    def logtest_run_wrapper(testrunner):
        '''
        Base decorator. Decorates the testrunner function.
        '''
        def logtest_run(*args, **kwargs):
            '''
            Base decorator callback. Runs the testrunner function with the
            supplied positional & keyword arguments.
            '''
            logger.debug('running test %r with positional arguments: %s '
                         'and keyword arguments: %s', testname, args, kwargs)
            result = testrunner(*args, **kwargs)
            logger.debug('finished test %r, got result: %s', testname, result)
        return logtest_run
    return logtest_run_wrapper


def applytestfunction(testinstance, testfunction, testcases):
    '''
    Applies testfunction to each item in testcases. Each testcase item is given
    a subcase scope on the testinstance. This allows the test runner to report
    the specific parameters that caused the test to fail.
    Test cases themselves are expected to be tuples in the form (args, kwargs).
    '''
    assert isinstance(testinstance, unittest.TestCase), \
        'testinstance must be a unittest.TestCase instance: %r' % testinstance
    assert callable(testfunction), \
        'testfunction must be callable: %r' % testfunction
    assert hasattr(testcases, '__iter__'), \
        'testcases must be iterable: %r' % testcases

    testcounter = 0
    for testcaseargs, testcasekwargs in testcases:
        logger.debug('running test subcase #%d, args = %s, kwargs = %s',
                     testcounter, testcaseargs, testcasekwargs)
        with testinstance.subTest(**testcasekwargs):
            try:
                testfunction(*testcaseargs, **testcasekwargs)
            except Exception as exc:
                exc_lines = str(exc).splitlines()
                exc_info = exc_lines[0] if exc_lines else exc
                logger.debug('test case #%d resulted in an error: %r',
                             testcounter, exc_info)
                raise
            else:
                logger.debug('finished running test case #%d', testcounter)

        testcounter += 1

    logger.info('finished running %d subtests', testcounter)
