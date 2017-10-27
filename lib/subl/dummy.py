#!/usr/bin/env python3

'''
lib/subl/dummy.py
Dummy sublime module polyfills.

Generates a dummy implementation of the module to allow the rest of the library
to still load (i.e. no import errors, and no name errors). This isn't meant to
emulate the sublime module, however. The dummy implementations do nothing.

In modules that require sublime, use the following to fall back on this module:
```
try:
    import sublime
    import sublime_plugin
except ImportError:
    from .lib.subl.dummy import sublime
    from .lib.subl.dummy import sublime_plugin
```
'''

import collections
import logging

logger = logging.getLogger('sublime-ycmd.' + __name__)


class SublimeDummyBase(object):
    pass


class SublimeDummySettings(dict):
    def clear_on_change(self, key):
        pass

    def add_on_change(self, key):
        pass


def sublime_dummy_load_settings(filename):
    logger.debug('supplying dummy data for settings file: %s', filename)
    return SublimeDummySettings()


SublimeDummy = collections.namedtuple('SublimeDummy', [
    'Settings',
    'View',
    'load_settings',
])
SublimePluginDummy = collections.namedtuple('SublimePluginDummy', [
    'EventListener',
    'TextCommand',
])


sublime = SublimeDummy(
    SublimeDummyBase,
    SublimeDummyBase,
    sublime_dummy_load_settings,
)
sublime_plugin = SublimePluginDummy(
    SublimeDummyBase,
    SublimeDummyBase,
)
