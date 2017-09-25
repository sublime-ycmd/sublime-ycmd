#!/usr/bin/env python3

'''
tests/util/dict.py
Tests for dictionary utility functions.
'''

import logging
import unittest

from lib.util.dict import merge_dicts
from tests.lib.decorator import log_function
from tests.lib.subtest import map_test_function

logger = logging.getLogger('sublime-ycmd.' + __name__)


class TestMergeDictionaries(unittest.TestCase):
    '''
    Unit tests for the dictionary merge algorithm. This should recursively
    merge the structure of dictionaries, overwriting leaf nodes instead of
    branches whenever possible.
    '''

    @log_function('[merge : shallow]')
    def test_md_shallow(self):
        ''' Tests dictionary merges with max depth 1. '''
        shallow_dictionary_cases = [(
            ({'a': 1}, {'b': 2}),
            {'expected': {'a': 1, 'b': 2}},
        ), (
            ({'a': 1}, {'b': 2}, {'a': 3}),
            {'expected': {'a': 3, 'b': 2}},
        ), (
            ({'a': 1}, {'b': 2}, {'c': 3}, {'a': 4, 'b': 5, 'c': 6}),
            {'expected': {'a': 4, 'b': 5, 'c': 6}},
        ), (
            ({'a': 1}, {'b': 2}, {'a': 3, 'b': 4}, {'a': 1, 'c': 5}),
            {'expected': {'a': 1, 'b': 4, 'c': 5}},
        ), (
            ({'a': 1}, {'b': 2}, {}, {'a': []}, {}, {'b': {}}),
            {'expected': {'a': [], 'b': {}}},
        )]

        def test_md_shallow_one(base, *rest, expected=''):
            result = merge_dicts(base, *rest)
            logger.debug('expected, result: %r, %r', expected, result)
            self.assertEqual(expected, result)

        map_test_function(
            self, test_md_shallow_one, shallow_dictionary_cases,
        )

    @log_function('[merge : deep]')
    def test_md_deep(self):
        ''' Tests dictionary merges with max depth >1. '''
        deep_dictionary_cases = [(
            (
                {
                    'outer': {
                        'inner': {'a': 1},
                    },
                }, {
                    'outer': {
                        'inner': {'b': 2},
                    },
                },
            ), {
                'expected': {
                    'outer': {
                        'inner': {'a': 1, 'b': 2},
                    },
                },
            },
        ), (
            (
                {
                    'outer': {
                        'a': {'x': 1},
                        'b': {'y': 2},
                    },
                }, {
                    'outer': {
                        'a': {'y': 3},
                        'b': {'x': 4},
                    },
                },
            ), {
                'expected': {
                    'outer': {
                        'a': {'x': 1, 'y': 3},
                        'b': {'x': 4, 'y': 2},
                    },
                },
            },
        )]

        def test_md_deep_one(base, *rest, expected=''):
            result = merge_dicts(base, *rest)
            logger.debug('expected, result: %r, %r', expected, result)
            self.assertEqual(expected, result)

        map_test_function(
            self, test_md_deep_one, deep_dictionary_cases,
        )

    @log_function('[merge : list]')
    def test_md_list(self):
        ''' Tests dictionary merges when lists are involved. '''
        list_cases = [(
            ({'l': [1]}, {'l': [2]}),
            {'expected': {'l': [1, 2]}},
        ), (
            ({'l': [1]}, {'l': [2]}, {'l': [3]}, {'l': [4]}, {'l': [5]}),
            {'expected': {'l': [1, 2, 3, 4, 5]}},
        ), (
            ({'l': [1, 2, 3]}, {'l': [4, 5]}),
            {'expected': {'l': [1, 2, 3, 4, 5]}},
        ), (
            ({'l': None}, {'l': [1, 2, 3]}),
            {'expected': {'l': [1, 2, 3]}},
        )]

        def test_md_list_one(base, *rest, expected=''):
            result = merge_dicts(base, *rest)
            logger.debug('expected, result: %r, %r', expected, result)
            self.assertEqual(expected, result)

        map_test_function(
            self, test_md_list_one, list_cases,
        )

    @log_function('[merge : overwrite]')
    def test_md_overwrite(self):
        ''' Tests dictionary merges with non-mergable items (overwrite it). '''
        overwrite_cases = [(
            ({'a': 1}, {'a': {'b': 2}}, {'a': {'c': 3}}),
            {'expected': {'a': {'b': 2, 'c': 3}}},
        ), (
            ({'a': 1}, {'a': [2]}, {'a': [3]}),
            {'expected': {'a': [2, 3]}},
        ), (
            ({'a': 1}, {'a': [2]}, {'a': {'b': 3}}),
            {'expected': {'a': {'b': 3}}},
        )]

        def test_md_overwrite_one(base, *rest, expected=''):
            result = merge_dicts(base, *rest)
            logger.debug('expected, result: %r, %r', expected, result)
            self.assertEqual(expected, result)

        map_test_function(
            self, test_md_overwrite_one, overwrite_cases,
        )
