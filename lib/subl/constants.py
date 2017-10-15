#!/usr/bin/env python3

'''
lib/subl/constants.py

Constants for use in sublime apis, including plugin-specific settings.
'''

'''
Settings file name.

This name is passed to sublime when loading the settings.
'''     # pylint: disable=pointless-string-statement
SUBLIME_SETTINGS_FILENAME = 'sublime-ycmd.sublime-settings'

'''
Settings keys.

The "watch" key is used to register an on-change event for the settings.

The "recognized" keys are used for debugging and logging/pretty-printing.

The "server" keys are used for configuring ycmd servers. Changes to these
settings should trigger a restart on all running ycmd servers.
'''
SUBLIME_SETTINGS_WATCH_KEY = 'syplugin'
SUBLIME_SETTINGS_RECOGNIZED_KEYS = [
    'ycmd_root_directory',
    'ycmd_default_settings_path',
    'ycmd_python_binary_path',
    'ycmd_language_whitelist',
    'ycmd_language_blacklist',
    'ycmd_language_filetype',
    'ycmd_log_level',
    'ycmd_log_file',
    'ycmd_keep_logs',
    'sublime_ycmd_background_threads',
    'sublime_ycmd_logging_dictconfig_overrides',
    'sublime_ycmd_logging_dictconfig_base',
]
SUBLIME_SETTINGS_YCMD_SERVER_KEYS = [
    'ycmd_root_directory',
    'ycmd_default_settings_path',
    'ycmd_python_binary_path',
    'ycmd_language_filetype',
    'ycmd_log_level',
    'ycmd_log_file',
    'ycmd_keep_logs',
]
SUBLIME_SETTINGS_TASK_POOL_KEYS = [
    'sublime_ycmd_background_threads',
]

'''
Sane defaults for settings. This will be part of `SUBLIME_SETTINGS_FILENAME`
already, so it's mainly here for reference.

The scope mapping is used to map syntax scopes to ycmd file types. They don't
line up exactly, so this scope mapping defines the required transformations.
For example, the syntax defines 'c++', but ycmd expects 'cpp'.

The language scope prefix is stripped off any detected scopes to get the syntax
base name (e.g. 'c++'). The scope mapping is applied after this step.
'''

SUBLIME_DEFAULT_LANGUAGE_FILETYPE_MAPPING = {
    'c++': 'cpp',
    'js': 'javascript',
}

SUBLIME_LANGUAGE_SCOPE_PREFIX = 'source.'
