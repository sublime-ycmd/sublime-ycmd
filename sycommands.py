#!/usr/bin/env python3

'''
sycommands.py
Main Sublime Text Commands. Utilities for controlling or querying ycmd.
'''

import logging
import logging.config

from .lib.subl.view import (
    get_path_for_view,
    get_file_types,
)
from .lib.util.format import (
    json_pretty_print,
    json_flat_iterator,
)

from .plugin.state import get_plugin_state
from .plugin.ui import display_plugin_message

logger = logging.getLogger('sublime-ycmd.' + __name__)

try:
    import sublime_plugin
except ImportError:
    from .lib.subl.dummy import sublime_plugin


class SublimeYcmdEditSettings(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        window = view.window()

        if not window:
            logger.error('no window, cannot launch settings')
            return

        settings_base_file = \
            '${packages}/YouCompleteMe/sublime-ycmd.sublime-settings'
        settings_placeholder = (
            '{\n'
            '\t\"ycmd_root_directory\": \"$0\"\n'
            '}\n'
        )
        window.run_command('edit_settings', {
            'base_file': settings_base_file,
            'default': settings_placeholder,
        })


class SublimeYcmdListServers(sublime_plugin.TextCommand):
    def run(self, edit):
        state = get_plugin_state()
        if not state:
            return

        window = self.view.window()
        if not window:
            logger.warning('failed to get window, cannot display servers')
            return

        servers = state.servers
        if not servers:
            logger.debug('no servers are active')

            def on_select_empty(selection_index):
                pass

            window.show_quick_panel([
                ['empty', 'no servers are running']
            ], on_select_empty)
            return

        panel_options = [
            [server.label or '', server.pretty_str()] for server in servers
        ]

        def on_select_server(selection_index):
            # do nothing for now
            # in the future, this may be used for server management as well
            pass

        window.show_quick_panel(panel_options, on_select_server)

    def description(self):
        return 'list ycmd servers'


class SublimeYcmdShowViewInfo(sublime_plugin.TextCommand):
    def run(self, edit):
        state = get_plugin_state()
        if not state:
            return

        view = self.view
        window = view.window()

        if not window:
            logger.warning('no window, cannot display info')
            return

        server = state.lookup_server(view)
        if server:
            server_desc = server.pretty_str()
        else:
            server_desc = 'none'

        view_working_directory = get_path_for_view(view)
        if not view_working_directory:
            view_working_directory = 'none'

        view_file_types = get_file_types(view)
        if not view_file_types:
            view_file_types = []
        if hasattr(view_file_types, '__iter__'):
            view_file_types = ', '.join(view_file_types)
        else:
            view_file_types = str(view_file_types)

        def on_select_info(selection_index):
            pass

        window.show_quick_panel([
            ['Server', server_desc],
            ['Directory', view_working_directory],
            ['Type', view_file_types],
        ], on_select_info)


class SublimeYcmdGetDebugInfo(sublime_plugin.TextCommand):
    def run(self, edit):
        state = get_plugin_state()
        if not state:
            return

        view = state.lookup_view(self.view)
        window = self.view.window()

        if not view or not view.ready():
            logger.info('view has not been seen by plugin, ignoring it')
            display_plugin_message('view is ignored, cannot get debug info')
            return

        server = state.lookup_server(view)
        if not server:
            logger.info('no server for view, cannot get debug info')
            display_plugin_message('view has no associated ycmd server')
            return

        if not (server.is_starting() or server.is_alive(timeout=0)):
            logger.info('server is unavailable, cannot get debug info')
            display_plugin_message('server is unavailable: %s' % (server))
            return

        request_params = view.generate_request_parameters()
        if not request_params:
            logger.info('failed to generate request params, abort')
            display_plugin_message('failed to generate parameters from view')
            return

        logger.info('sending request for server debug info: %r', server)
        try:
            debug_info = server.get_debug_info(request_params, timeout=1)
        except TimeoutError:    # noqa
            logger.info('request timed out...')
            display_plugin_message('request timed out, server: %s' % (server))
            return

        if debug_info:
            pretty_debug_info = json_pretty_print(debug_info)
            display_plugin_message('got debug info: %s' % (pretty_debug_info))
        else:
            display_plugin_message('got debug info: %s' % (debug_info))

        def on_select_info(selection_index):
            pass

        if window and debug_info:
            # NOTE : Quick panel API is very picky, needs to be `list` & `str`:
            flattened_properties = list(sorted(
                ([str(k), str(v)] for k, v in json_flat_iterator(debug_info)),
                key=lambda i: i[0],
            ))
            window.show_quick_panel(flattened_properties, on_select_info)


class SublimeYcmdManageServer(sublime_plugin.TextCommand):
    def run(self, edit):
        state = get_plugin_state()
        if not state:
            return

        view = state.lookup_view(self.view)
        window = self.view.window()
        if not view or not view.ready():
            logger.debug('view has not been seen by plugin, ignoring it')
            display_plugin_message('view is ignored, cannot manage its server')
            return

        server = state.lookup_server(view)
        if not server:
            logger.debug('no server for view, cannot manage it')
            display_plugin_message('view has no associated ycmd server')
            return

        if not (server.is_starting() or server.is_alive(timeout=0)):
            logger.debug('server is unavailable, cannot manage it')
            display_plugin_message('server is unavailable: %s' % (server))
            return

        startup_parameters = server.startup_parameters
        stdout_log_path = startup_parameters.stdout_log_path
        stderr_log_path = startup_parameters.stderr_log_path

        def _describe_log_path():
            if not stdout_log_path or not stderr_log_path:
                return 'buffered in-memory'
            if startup_parameters.keep_logs:
                return 'retained temporary files'
            return 'auto-deleted temporary files'

        server_desc = server.pretty_str()
        process_desc = 'process id: %s' % (server.pid)
        log_desc = _describe_log_path()

        def on_select_item(selection_index):
            if selection_index == -1:
                pass
            elif selection_index == 0:
                shutdown_server()
            elif selection_index == 1:
                kill_server()
            elif selection_index == 2:
                open_logs()
            else:
                logger.warning(
                    'unhandled selection index for manage server: %r',
                    selection_index,
                )
                raise ValueError(
                    'unknown selection, index: %r' % (selection_index)
                )

        def shutdown_server():
            server.stop(hard=False, timeout=1)

        def kill_server():
            server.stop(hard=True, timeout=1)

        def open_logs():
            if not stdout_log_path or not stderr_log_path:
                display_plugin_message('cannot display in-memory logs')
                # TODO : Use `read_spooled_output` to extract logs and display.
                raise NotImplementedError

            window.open_file(stdout_log_path)
            window.open_file(stderr_log_path)

        window.show_quick_panel([
            ['Shutdown', server_desc],
            ['Kill', process_desc],
            ['Logs', log_desc],
        ], on_select_item)
