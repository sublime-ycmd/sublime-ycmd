#!/usr/bin/env python3
'''
tests/test_logutils.py
Unit tests for the log utils module.
'''

import logging
import unittest

from lib.util.log import (
    SmartTruncateFormatter,
    FormatField,
    parse_fields,
)
from tests.utils import (
    applytestfunction,
    logtest,
)

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
                      plus=None, width=None, point=None, type=None):
    return FormatField(
        name=name, zero=zero, minus=minus, space=space,
        plus=plus, width=width, point=point, type=type,
    )


class TestFieldIterator(unittest.TestCase):
    '''
    Unit tests for the log-format field iterator. This iterator should extract
    information about each field in a format string.
    '''

    @logtest('log-format field iterator : simple percent')
    def test_fi_simple_percent(self):
        ''' Ensures that single-item `%`-format fields are parsed. '''

        single_fields = [
            ('%(foo)15s', make_format_field(name='foo', width='15', type='s')),
            ('% 5ld', make_format_field(space=' ', width='5', type='ld')),
            ('%-2s', make_format_field(minus='-', width='2', type='s')),
        ]
        single_field_args = [
            (f, {}) for f in single_fields
        ]

        def test_lffi_single_percent(field, expected):
            result = next(parse_fields(field))
            self.assertEqual(expected, result)

        applytestfunction(
            self, test_lffi_single_percent, single_field_args,
        )


class TestTruncateFormatter(unittest.TestCase):
    '''
    Unit tests for the log smart-truncate formatter. This formatter should try
    to truncate fields that are longer than the target field width.
    '''

    @logtest('log smart-truncate formatter : simple fields')
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
        self.assertEqual(expected, formatted)
