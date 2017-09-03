#!/usr/bin/env python3
'''
tests/__init__.py
Unit test index.
Imports all sub-tests so that unittest.TestSuite can easily find them.
'''

import tests.test_logutils

__all__ = ['test_logutils']
