#!/usr/bin/env python3

'''
plugin/ui.py
Plugin UI helpers.

Allows displaying error messages, prompts, and other messages that may require
user interaction.
TODO : Add linting handlers here to display linting errors from completers.
'''

import logging

from ..lib.schema import (
    DiagnosticError,
)
from ..lib.subl.errors import (
    PluginError,
    SettingsError,
)

logger = logging.getLogger('sublime-ycmd.' + __name__)

try:
    import sublime
except ImportError:
    from ..lib.subl.dummy import sublime

PLUGIN_MESSAGE_PREFIX = '[sublime-ycmd]'


def display_plugin_error(err):
    if not isinstance(err, PluginError):
        logger.warning(
            'unknown plugin error, not going to display it: %r', err,
        )
        return

    if isinstance(err, SettingsError):
        # invalid settings, format and display the message
        error_details = _format_settings_error(err)
    else:
        # other error, stringify and hope it's a reasonable explanation
        error_details = str(err)

    if not error_details:
        logger.debug('could not calculate an error message, so ignoring')
        return

    error_message = '%s %s' % (PLUGIN_MESSAGE_PREFIX, error_details)
    # grab first line (for pretty printing)
    status_line = error_message.split('\n', 1)[0]

    logger.critical('%s\n%s', status_line, error_message)

    def get_window():
        try:
            return sublime.active_window()
        except (AttributeError, TypeError):
            return None

    window = get_window()
    if window:

        # display it in active window's status line
        window.status_message(status_line)


def display_diagnostic_error(err):
    if not isinstance(err, DiagnosticError):
        logger.warning(
            'unknown diagnostic error, not going to display it: %r', err,
        )
        return

    raise NotImplementedError('unimplemented: display diagnostic error')


def prompt_load_extra_conf(path):
    if isinstance(path, DiagnosticError):
        # calculate extra conf path from diagnostic error
        path = path.unknown_extra_conf_path()
        if not path:
            logger.warning(
                'failed to calculate path of unknown extra conf file, ignoring'
            )
            return False

    if not isinstance(path, str):
        raise TypeError('path must be a str: %r' % (path))

    prompt_details = 'Load extra configuration file?\n\n%s' % (path)
    prompt_message = '%s %s' % (PLUGIN_MESSAGE_PREFIX, prompt_details)

    return sublime.ok_cancel_dialog(prompt_message, 'Load')


def _format_settings_error(err):
    '''
    Generates and returns an error message for the given `SettingsError`.
    This message will includes details and a fix, so it is suitable to display
    to a user.
    '''
    assert isinstance(err, SettingsError)
    error_reason = 'Invalid plugin settings.'
    error_description = '%s.' % (err.desc())
    error_message = str(err)
    error_fix = (
        'Please modify the plugin settings to correct the issue '
        '(Preferences > Package Settings > YouCompleteMe > Preferences).'
    )

    return '%s\n\n%s\n%s\n\n%s' % (
        error_reason,
        error_description,
        error_message,
        error_fix,
    )
