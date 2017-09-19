#!/usr/bin/env python3
'''
tests/test_fs.py
Unit tests for the filesystem utilities module.
'''

import logging
import os
import unittest

from lib.util.fs import get_common_ancestor
from tests.utils import (
    applytestfunction,
    logtest,
)

logger = logging.getLogger('sublime-ycmd.' + __name__)

if os.name == 'posix':
    FS_ROOT = '/'
elif os.name == 'nt':
    FS_ROOT = 'C:\\'
else:
    logger.error('unknown os type, test data might be invalid')
    FS_ROOT = ''


class TestGetCommonAncestor(unittest.TestCase):
    '''
    Unit tests for calculating the common ancestor between paths. The common
    ancestor should represent the path to a common file node between all the
    input paths.
    '''
    @logtest('get common ancestor : empty')
    def test_gca_empty(self):
        ''' Ensures that `None` is returned for an empty path list. '''
        result = get_common_ancestor([])
        self.assertEqual(None, result,
                         'common ancestor of empty paths should be None')

    @logtest('get common ancestor : single')
    def test_gca_single(self):
        ''' Ensures that a single path always results in that same path. '''
        single_paths = [
            '/',
            '/usr',
            '/usr/local/bin',
            '/var/log/foo\\bar.log',
            'C:\\',
            'D:\\',
            'C:\\Users',
            'C:\\Program Files',
            'C:\\Program Files/Sublime Text 3',
        ]
        single_path_args = [
            ([p], {}) for p in single_paths
        ]

        def test_gca_single_one(path):
            result = get_common_ancestor([path])
            self.assertEqual(path, result)

        applytestfunction(
            self, test_gca_single_one, single_path_args,
        )

    @logtest('get common ancestor : mostly similar')
    def test_gca_mostly_similar(self):
        '''
        Ensures that the common path can be found for many paths, with a long
        common prefix component.
        '''
        mostly_similar_path_args = [
            ([
                FS_ROOT + 'usr/local/lib/mypackage/bin',
                FS_ROOT + 'usr/local/lib/mypackage/lib'
            ], {
                'expected': os.path.join(
                    FS_ROOT, 'usr', 'local', 'lib', 'mypackage',
                ),
            }),

            ([
                FS_ROOT + 'var/log/mypackage/auth.log',
                FS_ROOT + 'var/log/mypackage/client1/'
            ], {
                'expected': os.path.join(
                    FS_ROOT, 'var', 'log', 'mypackage',
                ),
            }),
        ]

        def test_gca_mostly_similar_one(*paths, expected=''):
            result = get_common_ancestor(paths)
            self.assertEqual(expected, result)

        applytestfunction(
            self, test_gca_mostly_similar_one, mostly_similar_path_args,
        )
