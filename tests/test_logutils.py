#!/usr/bin/env python3
'''
tests/test_logutils.py
Unit tests for the log utils module.
'''

import logging
import unittest

import lib.logutils
import tests.utils

logger = logging.getLogger('sublime-ycmd.' + __name__)


def get_dummy_log_record():
    '''
    Generates and returns a dummy log record for use in tests. These dummy
    records contain a couple of extra parameters to play around with.
    '''
    dummy_log_record = \
        logging.LogRecord(name=__name__, level=logging.DEBUG,
                          pathname=__file__, lineno=1,
                          msg='dummy log record! x = %(x)s, y = %(y)s',
                          args={'x': 'hello', 'y': 'world'},
                          exc_info=None, func=None, sinfo=None)
    setattr(dummy_log_record, 'x', 'hello')
    setattr(dummy_log_record, 'y', 'world')

    return dummy_log_record


class SYTlogPropertyShortener(unittest.TestCase):
    '''
    Unit tests for the log-property shortening filter. This filter will shorten
    a LogRecord property to a target length.
    '''

    @tests.utils.logtest('log-property shortener : in-place shorten property')
    def test_lps_valid_property(self):
        ''' Ensures that valid properties/target-lengths get shortened. '''
        x_shortener = lib.logutils.SYlogPropertyShortener()
        x_shortener.set_property('x').set_length(1)

        dummy = get_dummy_log_record()
        initial_x = getattr(dummy, 'x')

        result = x_shortener.filter(dummy)
        self.assertTrue(result, 'utility filter should always return True')

        result_x = getattr(dummy, 'x')
        expected_x = initial_x[0]

        self.assertEqual(expected_x, result_x,
                         'filter did not shorten property to 1 letter')
