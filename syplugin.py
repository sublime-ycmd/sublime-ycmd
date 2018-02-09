#!/usr/bin/env python3

'''
syplugin.py
Main Sublime Text Plugin script. Listens for events and forwards it to plugin
state to handle.
'''

import logging
import logging.config

from .cli.args import base_cli_argparser
from .lib.subl.settings import bind_on_change_settings

from .plugin.log import configure_logging
from .plugin.state import (
    get_plugin_state,
    reset_plugin_state,
)

logger = logging.getLogger('sublime-ycmd.' + __name__)

try:
    import sublime_plugin
    _HAS_LOADED_ST = True
except ImportError:
    from .lib.subl.dummy import sublime_plugin
    _HAS_LOADED_ST = False
finally:
    assert isinstance(_HAS_LOADED_ST, bool)


class SublimeYcmdCompleter(sublime_plugin.EventListener):
    '''
    Completion plugin. Receives completion requests to forward to ycmd.
    '''

    def on_query_completions(self, view, prefix, locations):
        state = get_plugin_state()
        if not state:
            logger.debug('no plugin state, ignoring query completions')
            return None

        if not state.enabled_for_scopes(view, locations):
            logger.debug('not enabled for view, ignoring completion request')
            return None

        try:
            completion_options = state.completions_for_view(view)
        except Exception as e:
            logger.debug('failed to get completions: %s', e, exc_info=e)
            completion_options = None

        logger.debug('got completions: %s', completion_options)
        return completion_options

    def on_load(self, view):    # type: (sublime.View) -> None
        state = get_plugin_state()
        if not state:
            logger.debug('no plugin state, ignoring on-load event')
            return

        if not state.activate_view(view):
            logger.warning('failed to activate view: %r', view)

    def on_activated(self, view):       # type: (sublime.View) -> None
        state = get_plugin_state()
        if not state:
            logger.debug('no plugin state, ignoring activate event')
            return

        if not state.activate_view(view):
            logger.warning('failed to activate view: %r', view)

    def on_deactivated(self, view):     # type: (sublime.View) -> None
        state = get_plugin_state()
        if not state:
            logger.debug('no plugin state, ignoring deactivate event')
            return

        if not state.deactivate_view(view):
            logger.warning('failed to deactivate view: %r', view)


def on_change_settings(settings):
    ''' Callback, triggered when settings are loaded/modified. '''
    logger.info('loaded settings: %s', settings)

    state = get_plugin_state()

    if state is None:
        logger.critical('cannot reconfigure plugin, no plugin state exists')
    else:
        logger.debug('reconfiguring plugin state')
        state.configure(settings)


def plugin_loaded():
    ''' Callback, triggered when the plugin is loaded. '''
    logger.info('initializing sublime-ycmd')
    configure_logging(log_level=logging.CRITICAL)
    reset_plugin_state()
    logger.info('starting sublime-ycmd')
    bind_on_change_settings(on_change_settings)


def plugin_unloaded():
    ''' Callback, triggered when the plugin is unloaded. '''
    logger.info('unloading sublime-ycmd')
    reset_plugin_state()
    logging.info('stopped sublime-ycmd')


def main():
    ''' Main function. Executed when this script is executed directly. '''
    cli_argparser = base_cli_argparser(
        description='sublime-ycmd plugin loader',
    )
    cli_args = cli_argparser.parse_args()
    configure_logging(cli_args.log_level, cli_args.log_file)

    logger.info('starting main function')

    if _HAS_LOADED_ST:
        logger.info('running in Sublime Text, starting plugin')
    else:
        logger.info('not running in Sublime Text, setting up debug tests')

    try:
        plugin_loaded()
    finally:
        plugin_unloaded()


if __name__ == '__main__':
    main()
