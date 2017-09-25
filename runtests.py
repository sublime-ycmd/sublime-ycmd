#!/usr/bin/env python3
'''
runtests.py
Unit test runner. Without any arguments, this runs all available tests. Flags
may be used to selectively run tests, or just show some diagnostic information.
Log output is automatically captured by this script.
'''

import functools
import io
import logging
import os
import sys
import unittest

sys.path.append(os.path.dirname(__file__))  # noqa: E402

from cli.args import base_cli_argparser
from lib.util.log import get_smart_truncate_formatter

logger = logging.getLogger('sublime-ycmd.' + __name__)

# custom log level - used when logging results from the unittest TestRunner
LOGLEVEL_NOTICE = 100
LOGLEVELNAME_NOTICE = 'NOTICE'


def configure_logging(log_level=None, output_stream=None):
    '''
    Configures the logging module for running tests. This automatically binds
    the helpers in lib.logutils and captures output into a specified file.
    Supplying None to the parameters will result in defaults.
    '''
    if log_level is None:
        log_level = logging.WARNING
    if output_stream is None:
        output_stream = sys.stderr

    logging.addLevelName(LOGLEVEL_NOTICE, LOGLEVELNAME_NOTICE)

    logger_instance = logging.getLogger('sublime-ycmd')
    logger_instance.propagate = False

    # handler/filter will decide how to filter, so log everything here:
    logger_instance.setLevel(logging.DEBUG)

    if logger_instance.hasHandlers():
        logger_handlers_old = [h for h in logger_instance.handlers]
        for logger_handler in logger_handlers_old:
            logger_instance.removeHandler(logger_handler)

    logger_stream = logging.StreamHandler(stream=output_stream)
    logger_stream.setLevel(log_level)
    logger_formatter = get_smart_truncate_formatter()
    logger_stream.setFormatter(logger_formatter)
    logger_instance.addHandler(logger_stream)


def get_test_suite_items(test_suite):
    '''
    Generates a flattened iterator of all registered tests from the supplied
    test suite. Use it for pretty-printing/logging only.
    '''
    assert isinstance(test_suite, unittest.TestSuite), \
        '[internal] test_suite is not a unittest.TestSuite: %r' % test_suite

    def get_subitems(test_suite_item):
        ''' Helper that returns the sub-items of a single test suite item. '''
        if isinstance(test_suite_item, unittest.TestSuite):
            return get_test_suite_items(test_suite_item)
        elif isinstance(test_suite_item, unittest.TestCase):
            return [str(test_suite_item)]
        logger.warning('unknown test suite item type: %r', test_suite_item)
        return []

    test_suite_items = \
        functools.reduce(lambda sum, cur: sum + get_subitems(cur),
                         test_suite, [])

    return test_suite_items


def get_cli_argparser():
    '''
    Generates and returns an argparse.ArgumentParser instance for use with
    parsing test-related options.
    '''
    parser = base_cli_argparser(
        description='sublime-ycmd unit test runner',
    )

    testing_group = parser.add_argument_group(title='tests')
    testing_group.add_argument(
        '-l', '--list', action='store_true',
        help='lists available tests (does not run them)',
    )
    testing_group.add_argument(
        '-t', '--test', nargs='+',
        help='runs only the specified tests',
    )

    return parser


class TestRunnerLogStream(io.TextIOBase):
    '''
    File stream wrapper class for use with TestRunner.
    Instances of this class will accept messages written by a test runner
    and then log them in the custom NOTICE log level. This produces nicely
    formatted messages from the test runner output.
    '''

    def __init__(self):
        super(TestRunnerLogStream, self).__init__()
        self._buffer = ''

    def consume_line(self):
        '''
        Returns a complete buffered line, if one exists, and removes it from
        the buffer. If a complete line does not exist, this returns None, and
        no modifications are made to the buffer.
        '''
        buffered_lines = self._buffer.splitlines()
        if len(buffered_lines) <= 1:
            return None

        first_line = buffered_lines[0]
        remaining_buffer = '\n'.join(buffered_lines[1:])

        self._buffer = remaining_buffer
        return first_line

    @staticmethod
    def testrunner_log(*args):
        '''
        Dummy wrapper around the logger log statement. This method exists to
        provide a better funcName in the log record.
        '''
        logger.log(LOGLEVEL_NOTICE, *args)

    def write(self, s):
        '''
        Receives messages and logs them using the test runner log level.
        '''
        nbytes = len(s)
        self._buffer += s

        buffered_line = self.consume_line()
        while buffered_line:
            self.testrunner_log(buffered_line)
            buffered_line = self.consume_line()

        return nbytes

    def close(self):
        '''
        Receives the 'close' event. This writes out any pending buffered data
        and then calls the parent 'close' method.
        '''
        for buffered_line in self._buffer.splitlines():
            self.testrunner_log(buffered_line)

        super(TestRunnerLogStream, self).close()


def main():
    '''
    Main method. Discovers and runs tests in the 'tests' subdirectory.
    '''
    cli_argparser = get_cli_argparser()
    cli_args = cli_argparser.parse_args()

    if cli_args.list not in [None, False]:
        raise cli_argparser.error('Test listing is not yet implemented')

    configure_logging(cli_args.log_level, cli_args.log_file)

    logger.debug('initialized logger, about to load tests')
    project_dir = os.path.dirname(__file__)
    test_suite = unittest.defaultTestLoader.discover(
        'tests', pattern='*.py', top_level_dir=project_dir,
    )

    logger.info('loaded %d tests: %s', test_suite.countTestCases(),
                get_test_suite_items(test_suite))
    logger.debug('about to run tests')

    test_runner_logstream = TestRunnerLogStream()
    test_runner = unittest.TextTestRunner(
        stream=test_runner_logstream, verbosity=2,
    )

    unittest.installHandler()
    test_runner.run(test_suite)


if __name__ == '__main__':
    main()
