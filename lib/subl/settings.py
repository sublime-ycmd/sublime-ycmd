#!/usr/bin/env python3

'''
lib/subl/settings.py
Plugin settings class.

Wraps the settings `dict` and exposes them as attributes on the class. Default
settings will be calculated for missing/blank settings if possible.

This is also meant to abstract the setting key names, so there aren't as many
hard-coded strings in the main plugin logic.
'''

import logging

try:
    import sublime
except ImportError:
    from lib.subl.dummy import sublime

from lib.subl.constants import (
    SUBLIME_SETTINGS_FILENAME,
    SUBLIME_SETTINGS_WATCHED_KEYS,
    SUBLIME_SETTINGS_YCMD_SERVER_KEYS,
)
from lib.util.fs import (
    resolve_binary_path,
    default_python_binary_path,
)
from lib.ycmd.settings import get_default_settings_path

logger = logging.getLogger('sublime-ycmd.' + __name__)


class Settings(object):
    '''
    Wrapper class that exposes the loaded settings as attributes.
    '''

    def __init__(self, settings=None):
        self._ycmd_root_directory = None
        self._ycmd_default_settings_path = None
        self._ycmd_python_binary_path = None
        self._ycmd_language_whitelist = None
        self._ycmd_language_blacklist = None

        if settings is not None:
            self.parse(settings)

    def parse(self, settings):
        '''
        Assigns the contents of `settings` to the internal instance variables.
        The settings may be provided as a `dict` or as a `sublime.Settings`
        instance.
        TODO : note the setting keys, note that all variables are reset
        '''
        assert isinstance(settings, (sublime.Settings, dict))

        # this logic relies on both instance types having a `get` method
        self._ycmd_root_directory = settings.get('ycmd_root_directory', None)
        self._ycmd_default_settings_path = \
            settings.get('ycmd_default_settings_path', None)
        self._ycmd_python_binary_path = \
            settings.get('ycmd_python_binary_path', None)
        self._ycmd_language_whitelist = \
            settings.get('ycmd_language_whitelist', None)
        self._ycmd_language_blacklist = \
            settings.get('ycmd_language_blacklist', None)

        self._normalize()

    def _normalize(self):
        '''
        Calculates and updates any values that haven't been set after parsing
        settings provided to the `parse` method.
        This will calculate things like the default settings path based on the
        ycmd root directory, or the python binary based on the system PATH.
        '''
        if not self._ycmd_default_settings_path:
            ycmd_root_directory = self._ycmd_root_directory
            if ycmd_root_directory:
                ycmd_default_settings_path = \
                    get_default_settings_path(ycmd_root_directory)
                logger.debug(
                    'calculated default settings path from '
                    'ycmd root directory: %s', ycmd_default_settings_path
                )
                self._ycmd_default_settings_path = ycmd_default_settings_path

        if not self._ycmd_python_binary_path:
            self._ycmd_python_binary_path = default_python_binary_path()
        ycmd_python_binary_path = self._ycmd_python_binary_path

        resolved_python_binary_path = \
            resolve_binary_path(ycmd_python_binary_path)
        if resolved_python_binary_path:
            if resolved_python_binary_path != ycmd_python_binary_path:
                logger.debug(
                    'calculated %s binary path: %s',
                    ycmd_python_binary_path, resolved_python_binary_path,
                )
            self._ycmd_python_binary_path = resolved_python_binary_path
        else:
            logger.error(
                'failed to locate %s binary, '
                'might not be able to start ycmd servers',
                ycmd_python_binary_path
            )

        if self._ycmd_language_whitelist is None:
            logger.debug('using empty whitelist - enable for all scopes')
            self._ycmd_language_whitelist = []

        if self._ycmd_language_blacklist is None:
            logger.debug('using empty blacklist - disable for no scopes')
            self._ycmd_language_blacklist = []

    @property
    def ycmd_root_directory(self):
        '''
        Returns the path to the ycmd root directory.
        If set, this will be a string. If unset, this will be `None`.
        '''
        return self._ycmd_root_directory

    @property
    def ycmd_default_settings_path(self):
        '''
        Returns the path to the ycmd default settings file.
        If set, this will be a string. If unset, it is calculated based on the
        ycmd root directory. If that fails, this will be `None`.
        '''
        return self._ycmd_default_settings_path

    @property
    def ycmd_python_binary_path(self):
        '''
        Returns the path to the python executable used to start ycmd.
        If set, this will be a string. If unset, it is calculated based on the
        PATH environment variable. If that fails, this will be `None`.
        '''
        return self._ycmd_python_binary_path

    @property
    def ycmd_language_whitelist(self):
        '''
        Returns the language/scope whitelist to perform completions on.
        This will be a list of strings, but may be empty.
        '''
        return self._ycmd_language_whitelist

    @property
    def ycmd_language_blacklist(self):
        '''
        Returns the language/scope blacklist to prevent completions on.
        This will be a list of strings, but may be empty.
        '''
        return self._ycmd_language_blacklist

    def as_dict(self):
        logger.warning('deprecated: call dict() on Settings directly')
        return {
            'ycmd_root_directory': self.ycmd_root_directory,
            'ycmd_default_settings_path': self.ycmd_default_settings_path,
            'ycmd_python_binary_path': self.ycmd_python_binary_path,
            'ycmd_language_whitelist': self.ycmd_language_whitelist,
            'ycmd_language_blacklist': self.ycmd_language_blacklist,
        }

    def __eq__(self, other):
        '''
        Returns true if the settings instance `other` has the same ycmd server
        configuration as this instance.
        Other settings, like language whitelist/blacklist, are not compared.
        If `other` is not an instance of `Settings`, this returns false.
        '''
        if not isinstance(other, Settings):
            return False

        for ycmd_server_settings_key in SUBLIME_SETTINGS_YCMD_SERVER_KEYS:
            self_setting = getattr(self, ycmd_server_settings_key)
            other_setting = getattr(other, ycmd_server_settings_key)

            if self_setting != other_setting:
                return False

        return True

    def __bool__(self):
        return not not self._ycmd_root_directory

    def __hash__(self):
        return hash((
            self.ycmd_root_directory,
            self.ycmd_default_settings_path,
            self.ycmd_python_binary_path,
        ))

    def __iter__(self):
        ''' Dictionary-compatible iterator. '''
        return iter([
            ('ycmd_root_directory', self.ycmd_root_directory),
            ('ycmd_default_settings_path', self.ycmd_default_settings_path),
            ('ycmd_python_binary_path', self.ycmd_python_binary_path),
            ('ycmd_language_whitelist', self.ycmd_language_whitelist),
            ('ycmd_language_blacklist', self.ycmd_language_blacklist),
        ])

    def __str__(self):
        return str(dict(self))

    def __repr__(self):
        return '%s(%r)' % ('Settings', dict(self))


def load_settings(filename=SUBLIME_SETTINGS_FILENAME):
    '''
    Fetches the resolved settings file `filename` from sublime, and parses
    it into a `Settings` instance. The file name should be the base name of
    the file (i.e. not the absolute/relative path to it).
    '''
    logger.debug('loading settings from: %s', filename)
    logger.critical('load_settings reference: %r', sublime.load_settings)
    try:
        logger.critical('source: %s', sublime._source)
    finally:
        pass
    settings = sublime.load_settings(filename)

    logger.debug('parsing/extracting settings')
    return Settings(settings=settings)


def bind_on_change_settings(callback,
                            filename=SUBLIME_SETTINGS_FILENAME,
                            setting_keys=SUBLIME_SETTINGS_WATCHED_KEYS):
    '''
    Binds `callback` to the on-change-settings event. The settings are loaded
    from `filename`, which should be the base name of the file (i.e. not the
    path to it). When loading, the settings are parsed into a `Settings`
    instance, and this instance is supplied as an argument to the callback.
    The keys in `setting_keys` are used to bind an event listener. Changes to
    settings that use these keys will trigger a reload.
    When called, this will automatically load the settings for the first time,
    and immediately invoke `callback` with the initial settings.
    '''
    logger.debug('loading settings from: %s', filename)
    settings = sublime.load_settings(filename)

    def generate_on_change_settings(key,
                                    callback=callback,
                                    settings=settings):
        def on_change_settings():
            logger.debug('settings changed, name: %s', key)
            extracted_settings = Settings(settings=settings)
            callback(extracted_settings)
        return on_change_settings

    logger.debug('binding on-change handlers for keys: %s', setting_keys)
    for setting_key in setting_keys:
        settings.clear_on_change(setting_key)
        settings.add_on_change(
            setting_key, generate_on_change_settings(setting_key)
        )

    logger.debug('loading initial settings')
    initial_settings = Settings(settings=settings)

    logger.debug(
        'triggering callback with initial settings: %s', initial_settings
    )
    callback(initial_settings)

    return initial_settings
