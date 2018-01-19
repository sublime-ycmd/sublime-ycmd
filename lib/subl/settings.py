#!/usr/bin/env python3

'''
lib/subl/settings.py
Plugin settings class.

Wraps the settings `dict` and exposes them as attributes on the class. Default
settings will be calculated for missing/blank settings if possible.

This is also meant to abstract the setting key names, so there aren't as many
hard-coded strings in the main plugin logic.
'''

import itertools
import logging

try:
    import sublime
except ImportError:
    from ..subl.dummy import sublime

from ..subl.constants import (
    SUBLIME_SETTINGS_FILENAME,
    SUBLIME_SETTINGS_RECOGNIZED_KEYS,
    SUBLIME_SETTINGS_WATCH_KEY,
    SUBLIME_SETTINGS_YCMD_SERVER_KEYS,
    SUBLIME_SETTINGS_TASK_POOL_KEYS,
)
from ..subl.errors import (
    SettingsError,
)
from ..util.dict import merge_dicts
from ..util.fs import (
    resolve_abspath,
    resolve_binary_path,
    default_python_binary_path,
)
from ..util.sys import get_cpu_count
from ..ycmd.settings import get_default_settings_path

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
        self._ycmd_language_filetype = {}

        self._ycmd_log_level = None
        self._ycmd_log_file = None
        self._ycmd_keep_logs = False

        self._ycmd_force_semantic_completion = False

        self._sublime_ycmd_background_threads = None

        self._sublime_ycmd_logging_dictconfig_overrides = {}
        self._sublime_ycmd_logging_dictconfig_base = {}

        if settings is not None:
            self.parse(settings)

    def parse(self, settings):
        '''
        Assigns the contents of `settings` to the internal instance variables.
        The settings may be provided as a `dict` or as a `sublime.Settings`
        instance.
        TODO : note the setting keys, note that all variables are reset
        '''
        if not isinstance(settings, (sublime.Settings, dict)):
            raise TypeError(
                'settings must be sublime.Settings or dict: %r' % settings
            )

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
        self._ycmd_language_filetype = \
            settings.get('ycmd_language_filetype', {})

        self._ycmd_log_level = settings.get('ycmd_log_level', None)
        self._ycmd_log_file = settings.get('ycmd_log_file', None)
        self._ycmd_keep_logs = settings.get('ycmd_keep_logs', False)

        self._ycmd_force_semantic_completion = \
            settings.get('ycmd_force_semantic_completion', False)

        self._sublime_ycmd_background_threads = \
            settings.get('sublime_ycmd_background_threads', None)

        self._sublime_ycmd_logging_dictconfig_overrides = \
            settings.get('sublime_ycmd_logging_dictconfig_overrides', {})
        self._sublime_ycmd_logging_dictconfig_base = \
            settings.get('sublime_ycmd_logging_dictconfig_base', {})

        try:
            self._normalize()
        except (TypeError, ValueError):
            # whatever, we tried
            pass

    def _normalize(self):
        '''
        Calculates and updates any values that haven't been set after parsing
        settings provided to the `parse` method.
        This will calculate things like the default settings path based on the
        ycmd root directory, or the python binary based on the system PATH.
        '''
        if not self._ycmd_root_directory:
            logger.debug(
                'no ycmd root directory set, skipping setting normalization'
            )
            return

        resolved_ycmd_root_directory = \
            resolve_abspath(self._ycmd_root_directory)
        if resolved_ycmd_root_directory != self._ycmd_root_directory:
            logger.debug(
                'resolved ycmd root directory: %r -> %r',
                self._ycmd_root_directory, resolved_ycmd_root_directory,
            )
            self._ycmd_root_directory = resolved_ycmd_root_directory

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

        if self._ycmd_language_filetype is None:
            logger.debug(
                'using empty language to filetype mapping, '
                'the "source." scope will be used as-is for the file type'
            )
            self._ycmd_language_filetype = {}

        if self._ycmd_keep_logs is None:
            self._ycmd_keep_logs = False

        if not self._sublime_ycmd_background_threads:
            # Default is the same as in `concurrent.futures.ThreadPoolExecutor`
            cpu_count = get_cpu_count()
            thread_count = cpu_count * 5
            logger.debug(
                'calculated default background thread count: %r', thread_count,
            )
            self._sublime_ycmd_background_threads = thread_count

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

    @property
    def ycmd_language_filetype(self):
        '''
        Returns the mapping used to translate source scopes to filetypes.
        This will be a dictionary, but may be empty.
        '''
        return self._ycmd_language_filetype

    @property
    def ycmd_log_level(self):
        '''
        Returns the log level to enable on the ycmd server.
        If set, this will be a string. If unset, this will be `None`, which
        should leave the log level unspecified (i.e. default ycmd logging).
        '''
        return self._ycmd_log_level

    @property
    def ycmd_log_file(self):
        '''
        Returns the log file to be used by the ycmd server for logging.
        If set, it may be either a boolean, or a string. If unset, this will
        be `None`. See the settings file for what these values mean.
        '''
        return self._ycmd_log_file

    @property
    def ycmd_keep_logs(self):
        '''
        Returns whether or not log files should be retained when ycmd exits.
        This will be a boolean. If unset, this returns a default of `False`.
        '''
        if self._ycmd_keep_logs is None:
            return False
        return self._ycmd_keep_logs

    @property
    def ycmd_force_semantic_completion(self):
        '''
        Returns whether or not semantic completion should be forced.
        This will be a boolean. If unset, this returns a default of `False`.
        '''
        if self._ycmd_force_semantic_completion is None:
            return False
        return self._ycmd_force_semantic_completion

    @property
    def sublime_ycmd_background_threads(self):
        '''
        Returns the number of background threads to use for task pools.
        This will be a positive integer.
        '''
        return self._sublime_ycmd_background_threads

    @property
    def sublime_ycmd_logging_dictconfig_base(self):
        '''
        Returns the base logging dictionary configuration for the library.
        This will be a dictionary, but may be empty.
        '''
        return self._sublime_ycmd_logging_dictconfig_base.copy()

    @property
    def sublime_ycmd_logging_dictconfig_overrides(self):
        '''
        Returns the override logging dictionary configuration for the library.
        This will be a dictionary, but may be empty.
        '''
        return self._sublime_ycmd_logging_dictconfig_overrides.copy()

    @property
    def sublime_ycmd_logging_dictconfig(self):
        '''
        Resolves the base and override logging dictionary configuration into
        a complete configuration for the library.
        This will be a dictionary, valid for `logging.config.dictConfig`.
        '''
        return merge_dicts(
            {},
            self.sublime_ycmd_logging_dictconfig_base,
            self.sublime_ycmd_logging_dictconfig_overrides,
        )

    def __eq__(self, other):
        '''
        Returns true if the settings instance `other` has the same ycmd server
        configuration and system configuration as this instance.
        Other settings, like language whitelist/blacklist, are not compared.
        If `other` is not an instance of `Settings`, this returns false.
        '''
        if not isinstance(other, Settings):
            return False

        comparison_keys = itertools.chain(
            SUBLIME_SETTINGS_YCMD_SERVER_KEYS,
            SUBLIME_SETTINGS_TASK_POOL_KEYS,
        )
        for settings_key in comparison_keys:
            self_setting = getattr(self, settings_key)
            other_setting = getattr(other, settings_key)

            if self_setting != other_setting:
                return False

        return True

    def __bool__(self):
        return bool(self._ycmd_root_directory)

    def __hash__(self):
        return hash((
            self.ycmd_root_directory,
            self.ycmd_default_settings_path,
            self.ycmd_python_binary_path,
        ))

    def __iter__(self):
        ''' Dictionary-compatible iterator. '''
        return iter([
            (setting_key, getattr(self, setting_key))
            for setting_key in SUBLIME_SETTINGS_RECOGNIZED_KEYS
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
    settings = sublime.load_settings(filename)

    logger.debug('parsing/extracting settings')
    return Settings(settings=settings)


def bind_on_change_settings(callback,
                            filename=SUBLIME_SETTINGS_FILENAME):
    '''
    Binds `callback` to the on-change-settings event. The settings are loaded
    from `filename`, which should be the base name of the file (i.e. not the
    path to it). When loading, the settings are parsed into a `Settings`
    instance, and this instance is supplied as an argument to the callback.
    When called, this will automatically load the settings for the first time,
    and immediately invoke `callback` with the initial settings.
    '''
    logger.debug('loading settings from: %s', filename)
    settings = sublime.load_settings(filename)

    def on_change_settings():
        logger.debug('settings have changed, reloading them')
        settings = sublime.load_settings(filename)
        extracted_settings = Settings(settings=settings)
        callback(extracted_settings)

    logger.debug(
        'binding on-change handler using key: %r', SUBLIME_SETTINGS_WATCH_KEY,
    )
    settings.clear_on_change(SUBLIME_SETTINGS_WATCH_KEY)
    settings.add_on_change(SUBLIME_SETTINGS_WATCH_KEY, on_change_settings)

    logger.debug('loading initial settings')
    initial_settings = Settings(settings=settings)

    logger.debug(
        'triggering callback with initial settings: %s', initial_settings
    )
    callback(initial_settings)

    return initial_settings


def validate_settings(settings):
    '''
    Checks `settings` for invalid/missing values. May raise `SettingsError`.
    This only checks for type-mismatches and missing settings. It does not
    check anything on the file system, as that could block.
    If there are no issues, this returns without doing anything. Otherwise,
    this will raise an exception of type `SettingsError`.
    '''
    if not isinstance(settings, Settings):
        raise TypeError('settings must be Settings: %r' % (settings))

    ycmd_root_directory = settings.ycmd_root_directory

    ycmd_default_settings_path = settings.ycmd_default_settings_path
    ycmd_python_binary_path = settings.ycmd_python_binary_path
    ycmd_language_whitelist = settings.ycmd_language_whitelist
    ycmd_language_blacklist = settings.ycmd_language_blacklist
    ycmd_language_filetype = settings.ycmd_language_filetype
    ycmd_log_level = settings.ycmd_log_level
    ycmd_log_file = settings.ycmd_log_file
    ycmd_keep_logs = settings.ycmd_keep_logs
    ycmd_force_semantic_completion = \
        settings.ycmd_force_semantic_completion
    # sublime_ycmd_background_threads = \
    #     settings.sublime_ycmd_background_threads
    # sublime_ycmd_logging_dictconfig_overrides = \
    #     settings.sublime_ycmd_logging_dictconfig_overrides
    # sublime_ycmd_logging_dictconfig_base = \
    #     settings.sublime_ycmd_logging_dictconfig_base

    # required settings
    if not ycmd_root_directory:
        raise SettingsError(
            'ycmd root directory must be provided, got: %r' %
            (ycmd_root_directory),
            type=SettingsError.MISSING,
            key='ycmd_root_directory', value=ycmd_root_directory,
        )

    # types
    def _desc_from_key(key):
        ''' Calculates a description from a settings key. '''
        return key.replace('_', ' ')

    def check_str(key, value, optional=True):
        if optional and value is None:
            return

        if not isinstance(value, str):
            raise SettingsError(
                '%s must be a str: %r' % (_desc_from_key(key), value),
                type=SettingsError.TYPE, key=key, value=value,
            )

    def check_bool(key, value, optional=True):
        if optional and value is None:
            return

        if not (value is True or value is False):
            raise SettingsError(
                '%s must be a bool: %r' % (_desc_from_key(key), value),
                type=SettingsError.TYPE, key=key, value=value,
            )

    def check_list_str(key, value, optional=True):
        if optional and value is None:
            return

        if not isinstance(value, (list, tuple)):
            raise SettingsError(
                '%s must be a list: %r' % (_desc_from_key(key), value),
                type=SettingsError.TYPE, key=key, value=value,
            )

        bad_items = list(v for v in value if not isinstance(v, str))
        if not bad_items:
            # everything is valid
            return

        raise SettingsError(
            '%s must have str entries: [ %s ]' % (
                _desc_from_key(key),
                ', '.join('%r' % (v,) for v in bad_items),
            ),
            type=SettingsError.TYPE, key=key, value=value,
        )

    def check_dict_str(key, value, optional=True):
        if optional and value is None:
            return

        if not isinstance(value, (dict)):
            raise SettingsError(
                '%s must be a dict: %r' % (_desc_from_key(key), value),
                type=SettingsError.TYPE, key=key, value=value,
            )

        bad_keys = list(
            k for k in value if not isinstance(value.get(k, None), str)
        )
        if not bad_keys:
            # everything is valid
            return

        raise SettingsError(
            '%s must have str entries: { %s }' % (
                _desc_from_key(key),
                ', '.join('%r: %r' % (k, value[k]) for k in bad_keys),
            ),
            type=SettingsError.TYPE, key=key, value=value,
        )

    check_str('ycmd_root_directory', ycmd_root_directory)
    check_str('ycmd_default_settings_path', ycmd_default_settings_path)
    check_str('ycmd_python_binary_path', ycmd_python_binary_path)
    check_list_str('ycmd_language_whitelist', ycmd_language_whitelist)
    check_list_str('ycmd_language_blacklist', ycmd_language_blacklist)
    check_dict_str('ycmd_language_filetype', ycmd_language_filetype)
    check_str('ycmd_log_level', ycmd_log_level)
    # TODO : Once log file path is supported, allow string values for log file.
    check_bool('ycmd_log_file', ycmd_log_file)
    check_bool('ycmd_keep_logs', ycmd_keep_logs)
    check_bool(
        'ycmd_force_semantic_completion', ycmd_force_semantic_completion,
    )
    # TODO : Check remaining setting values.


def has_same_ycmd_settings(settings1, settings2):
    '''
    Returns true if `settings1` and `settings2` have the same ycmd server
    configuration, and false otherwise.

    This can be used to detect when setting changes require ycmd restarts.
    '''
    if not isinstance(settings1, Settings):
        raise TypeError('settings are not Settings: %r' % (settings1))
    if not isinstance(settings2, Settings):
        raise TypeError('settings are not Settings: %r' % (settings2))

    for ycmd_setting_key in SUBLIME_SETTINGS_YCMD_SERVER_KEYS:
        ycmd_setting_value1 = getattr(settings1, ycmd_setting_key)
        ycmd_setting_value2 = getattr(settings2, ycmd_setting_key)

        if ycmd_setting_value1 != ycmd_setting_value2:
            return False

    # else, everything matched!
    return True


def has_same_task_pool_settings(settings1, settings2):
    '''
    Returns true if `settings1` and `settings2` have the same task pool
    configuration, and false otherwise.

    This can be used to detect when setting changes require worker restarts.
    '''
    if not isinstance(settings1, Settings):
        raise TypeError('settings are not Settings: %r' % (settings1))
    if not isinstance(settings2, Settings):
        raise TypeError('settings are not Settings: %r' % (settings2))

    for ycmd_setting_key in SUBLIME_SETTINGS_YCMD_SERVER_KEYS:
        ycmd_setting_value1 = getattr(settings1, ycmd_setting_key)
        ycmd_setting_value2 = getattr(settings2, ycmd_setting_key)

        if ycmd_setting_value1 != ycmd_setting_value2:
            return False

    # else, everything matched!
    return True
