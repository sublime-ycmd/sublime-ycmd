#!/usr/bin/env python3

'''
lib/util/log.py
Tests for logging utility functions.
'''

import logging
import unittest

from lib.util.log import (
    SmartTruncateFormatter,
    FormatField,
    parse_fields,
)
from tests.lib.decorator import log_function
from tests.lib.subtest import map_test_function

logger = logging.getLogger('sublime-ycmd.' + __name__)


def make_log_record(msg='', **kwargs):
    log_record = logging.LogRecord(
        name=__name__, pathname=__file__, lineno=1,
        level=logging.DEBUG, msg=msg, args=kwargs,
        exc_info=None, func=None, sinfo=None,
    )

    for k, v in kwargs.items():
        setattr(log_record, k, v)

    return log_record


def make_format_field(name=None, zero=None, minus=None, space=None,
                      plus=None, width=None, point=None, conv=None):
    return FormatField(
        name=name, zero=zero, minus=minus, space=space,
        plus=plus, width=width, point=point, conv=conv,
    )


class TestFieldIterator(unittest.TestCase):
    '''
    Unit tests for the log-format field iterator. This iterator should extract
    information about each field in a format string.
    '''

    @log_function('[percent : simple]')
    def test_fi_simple_percent(self):
        ''' Ensures that single-item `%`-format fields are parsed. '''

        single_fields = [
            ('%(foo)15s', make_format_field(
                name='foo', width='15', conv='s'
            )),
            ('% 5ld', make_format_field(
                space=' ', width='5', conv='ld'
            )),
            ('%-2s', make_format_field(
                minus='-', width='2', conv='s'
            )),
        ]

        def test_lffi_single_percent(field, expected):
            result = next(parse_fields(field))
            self.assertEqual(expected, result)

        map_test_function(self, test_lffi_single_percent, single_fields)


class TestTruncateFormatter(unittest.TestCase):
    '''
    Unit tests for the log smart-truncate formatter. This formatter should try
    to truncate fields that are longer than the target field width.
    '''

    @log_function('[smart-truncate : simple]')
    def test_tf_simple_percent_fields(self):
        ''' Ensures that simple %-style field widths are handled. '''

        format_string = '%(short)4s %(long)-8s'
        formatter = SmartTruncateFormatter(fmt=format_string, props={
            'short': 4,
            'long': 8,
        })

        record = make_log_record(short='hello', long='world')
        formatted = formatter.format(record)

        expected = ' hll world   '
        logger.debug('expected, truncated: %r, %r', expected, formatted)
        self.assertEqual(expected, formatted)
