#!/usr/bin/env python3

'''
lib/subl/constants.py

Constants for use in sublime apis, including plugin-specific settings.
'''

'''
Settings file name.

This name is passed to sublime when loading the settings.
'''
SUBLIME_SETTINGS_FILENAME = 'sublime-ycmd.sublime-settings'

'''
Settings keys.

The "watched" keys are used for detecting changes to the settings file(s).

The "server" keys are used for configuring ycmd servers. Changes to these
settings should trigger a restart on all running ycmd servers.
'''
SUBLIME_SETTINGS_WATCHED_KEYS = [
    'ycmd_root_directory',
    'ycmd_default_settings_path',
    'ycmd_python_binary_path',
    'ycmd_language_whitelist',
    'ycmd_language_blacklist',
]
SUBLIME_SETTINGS_YCMD_SERVER_KEYS = [
    'ycmd_root_directory',
    'ycmd_default_settings_path',
    'ycmd_python_binary_path',
]

'''
Sane defaults for settings. This will be part of `SUBLIME_SETTINGS_FILENAME`
already, so it's mainly here for reference.

The scope mapping is used to map syntax scopes to ycmd file types. They don't
line up exactly, so this scope mapping defines the required transformations.
For example, the syntax defines 'c++', but ycmd expects 'cpp'.
'''
SUBLIME_DEFAULT_LANGUAGE_SCOPE_MAPPING = {
    'c++': 'cpp',
    'js': 'javascript',
}
