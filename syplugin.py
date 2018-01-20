#!/usr/bin/env python3

'''
syplugin.py
Main Sublime Text Plugin script. Starts a backend server and sends completion
requests to it.
'''

import logging
import logging.config

from .cli.args import (
    base_cli_argparser,
    log_level_str_to_enum,
)
from .lib.util.log import (
    get_smart_truncate_formatter,
    get_debug_formatter,
)
from .lib.schema import (
    Completions,
    CompletionOption,
    Diagnostics,
    DiagnosticError,
)
from .lib.subl.errors import PluginError
from .lib.subl.settings import (
    Settings,
    bind_on_change_settings,
    validate_settings,
    has_same_ycmd_settings,
    has_same_task_pool_settings,
)
from .lib.subl.view import (
    View,
    get_path_for_view,
    get_file_types,
)
from .lib.ycmd.start import StartupParameters

from .plugin.server import SublimeYcmdServerManager
from .plugin.ui import (
    display_plugin_error,
    prompt_load_extra_conf,
)
from .plugin.view import SublimeYcmdViewManager

logger = logging.getLogger('sublime-ycmd.' + __name__)

try:
    import sublime
    import sublime_plugin
    _HAS_LOADED_ST = True
except ImportError:
    from .lib.subl.dummy import sublime
    from .lib.subl.dummy import sublime_plugin
    _HAS_LOADED_ST = False
finally:
    assert isinstance(_HAS_LOADED_ST, bool)


def configure_logging(log_level=None, log_file=None):
    '''
    Configures the logging module (or plugin-specific root logger) to log at
    the given `log_level` and write log output to file `log_file`. Formatters,
    handlers, and filters are added to prettify the logging output.
    If `log_level` is not provided, logging output will be silenced. Otherwise,
    it should be one of the logging enums or a string (e.g. 'DEBUG').
    If `log_file` is not provided, this uses the default logging stream, which
    should be `sys.stderr`. Otherwise, it should be a string representing the
    file name to append log output to.
    '''
    if isinstance(log_level, str):
        log_level = log_level_str_to_enum(log_level)

    # avoid messing with the root logger
    # if running under sublime, that would affect all other plugins as well
    logger_instance = logging.getLogger('sublime-ycmd')
    if log_level is None:
        logger_instance.setLevel(logging.NOTSET)
    else:
        logger_instance.setLevel(log_level)

    # disable propagate so logging does not go above this module
    logger_instance.propagate = False

    # create the handler
    if log_level is None:
        logger_handler = logging.NullHandler()
    else:
        if isinstance(log_file, str):
            logger_handler = logging.FileHandler(filename=log_file)
        else:
            # assume it's a stream
            logger_handler = logging.StreamHandler(stream=log_file)

    def remove_handlers(logger=logger_instance):
        if logger.hasHandlers():
            handlers = list(h for h in logger.handlers)
            for handler in handlers:
                logger.removeHandler(handler)

    # remove existing handlers (in case the plugin is reloaded)
    remove_handlers(logger_instance)

    # create the formatter
    if log_file is None:
        logger_formatter = get_smart_truncate_formatter()
    else:
        # writing to a file, so don't bother pretty-printing
        logger_formatter = get_debug_formatter()

    # connect everything up
    logger_handler.setFormatter(logger_formatter)
    logger_instance.addHandler(logger_handler)


class SublimeYcmdState(object):
    '''
    Singleton helper class. Stores the global state, and provides utilities
    to the plugin handlers.
    '''

    def __init__(self):
        self._server_manager = SublimeYcmdServerManager()
        self._view_manager = SublimeYcmdViewManager()
        self._settings = None
        self.reset()

    def reset(self):
        ''' Stops all ycmd servers and clears all settings. '''
        self._server_manager.shutdown(hard=True, timeout=0)
        self._server_manager.set_background_threads(1)

        self._view_manager.reset()

        self._settings = None

    def configure(self, settings):
        '''
        Receives a `settings` object and reconfigures the state from it.
        The settings should be an instance of `Settings`. See `lib.subl` for
        helpers to generate these settings.

        If there are changes to the ycmd server settings, then the state will
        automatically stop all currently running servers. They will be
        relaunched with the new parameters when a completion request is made.
        If there are changes to the task pool settings, then the worker threads
        will be shut down and recreated according to the new settings.
        If there are changes to the logging settings, then the state will
        reconfigure the logger without messing with any ycmd servers.
        '''
        assert isinstance(settings, Settings), \
            'settings must be Settings: %r' % (settings)

        try:
            validate_settings(settings)
        except PluginError as e:
            # always treat it as fatal, don't continue after displaying it
            display_plugin_error(e)
            return

        try:
            configure_logging(
                log_level=settings.sublime_ycmd_log_level,
                log_file=settings.sublime_ycmd_log_file,
            )
            logger.debug(
                'successfully reconfigured logging with level, file: %r, %r',
                settings.sublime_ycmd_log_level,
                settings.sublime_ycmd_log_file,
            )
        except Exception as e:
            logger.warning(
                'failed to reconfigure logging, ignoring: %r', e, exc_info=e,
            )

        if self._requires_ycmd_restart(settings):
            logger.debug(
                'shutting down existing ycmd servers, '
                'they will be restarted as required'
            )
            self._server_manager.shutdown(hard=False, timeout=0)

        # generate ycmd server startup parameters based on settings
        startup_parameters = StartupParameters(
            settings.ycmd_root_directory,
            ycmd_settings_path=settings.ycmd_default_settings_path,
            python_binary_path=settings.ycmd_python_binary_path,

            # leave `working_directory` blank, it gets filled in later
            working_directory=None,

            # TODO : Allow settings to override the defaults for these:
            server_idle_suicide_seconds=None,
            max_server_wait_time_seconds=None,
        )
        logger.info(
            'new servers will start with parameters: %s', startup_parameters,
        )
        self._server_manager.set_startup_parameters(startup_parameters)
        self._server_manager.set_server_logging(
            log_level=settings.ycmd_log_level,
            log_file=settings.ycmd_log_file,
            keep_logs=settings.ycmd_keep_logs,
        )

        if self._requires_task_pool_restart(settings):
            logger.debug('shutting down and recreating task pool')
            background_threads = settings.sublime_ycmd_background_threads
            self._server_manager.set_background_threads(background_threads)

        logger.debug('successfully configured with settings: %s', settings)
        self._settings = settings

    def is_configured(self):
        return self._settings is not None

    def activate_view(self, view):
        '''
        Registers and notifies the ycmd server to prepare for events on the
        given `view`. The first time a view is passed in, it is parsed by the
        server to generate the initial list of identifiers. Then, an event
        notification is sent to the server to indicate that the view is open
        in the editor (and any unsaved buffer data is sent over for additional
        parsing).

        NOTE : This does not respect the language whitelist/blacklist.
        '''
        state = _get_plugin_state()
        if not state:
            logger.debug('no plugin state, ignoring activate event')
            return False

        view = self._view_manager[view]     # type: View

        if not view:
            logger.debug('no view wrapper, ignoring activate event')
            return False

        if not view.ready():
            logger.debug('file is not ready for parsing, ignoring')
            return False
        if not view.file_types:
            logger.debug('file has no associated file types, ignoring it')
            # in this case, return true to indicate that this is acceptable
            return True
        if not self.enabled_for_scopes(view):
            logger.debug('not enabled for view, ignoring activate event')
            return True

        server = self._server_manager.get(view)     # type: Server
        if not server:
            logger.debug('no server for view, ignoring activate event')
            return False

        # TODO : Use view manager to determine when file needs to be re-parsed.
        parse_file = True

        notify_future = self._server_manager.notify_enter(
            view, parse_file=parse_file,
        )

        def on_notified_ready_to_parse(future):
            ''' Called by `Future.add_done_callback` after completion. '''
            if future.cancelled():
                logger.debug('notification was cancelled, ignoring result')
                return

            if future.exception():
                logger.debug('notification failed, ignoring result')
                return

            logger.debug(
                'finished notifying server, marking view as having been sent'
            )
            self._view_manager.set_notified_ready_to_parse(
                view, server, has_notified=True,
            )

        # As noted above, always notify, so always set the flag
        notify_future.add_done_callback(on_notified_ready_to_parse)

        return True

    def deactivate_view(self, view):
        '''
        Registers and notifies the ycmd server that the given `view` has been
        unloaded (closed, or switched out of). This allows the server to
        release resources for the buffer, since it won't need to handle events
        on it until it is re-activated.

        NOTE : This does not respect the language whitelist/blacklist.
        '''
        state = _get_plugin_state()
        if not state:
            logger.debug('no plugin state, ignoring deactivate event')
            return False

        view = self._view_manager[view]     # type: View
        if not view:
            logger.debug('no view wrapper, ignoring deactivate event')
            return False

        if not view.ready():
            logger.debug('file is not ready for parsing, ignoring')
            return False
        if not view.file_types:
            logger.debug('file has no associated file types, ignoring it')
            # in this case, return true to indicate that this is acceptable
            return True
        if not self.enabled_for_scopes(view):
            logger.debug('not enabled for view, ignoring deactivate event')
            return True

        server = self._server_manager.get(view)     # type: Server
        if not server:
            logger.debug('no server for view, ignoring deactivate event')
            return False

        request_params = view.generate_request_parameters()
        if not request_params:
            logger.debug('failed to generate request params, abort')
            return False

        # NOTE : Technically, this only has to be done when the buffer is
        #        different than it was when it was activated. But to keep it
        #        simple, we'll just check if it's dirty...
        #        (Not optimal, but good enough.)
        # TODO : Store the last `view.change_count()` to do the comparison.
        if view.dirty():
            logger.debug(
                'file has unsaved changes, '
                'so it will need to be sent to the server again'
            )
            # unlike the buffer enter event, we can unflag immediately, instead
            # of asynchronously after the notification has been sent
            # worst case: have to notify ready-to-parse more than required
            self._view_manager.set_notified_ready_to_parse(
                view, server, has_notified=False,
            )

        logger.debug('sending notification for unloading buffer')
        self._server_manager.notify_exit(view)

        return True

    def completions_for_view(self, view):
        '''
        Sends a completion request to the ycmd server for a given `view`.
        The response will be parsed and provided in a format that is compatible
        with what `sublime` expects (i.e. an iterable of completion tuples).

        This call will block, so it should ideally be run off-thread.
        '''
        state = _get_plugin_state()
        if not state:
            logger.debug('no plugin state, cannot provide completions')
            return None

        view = self._view_manager[view]     # type: View
        if not view:
            logger.debug('no view wrapper, cannot create request parameters')
            return None

        if not view.ready():
            logger.debug('file is not ready for parsing, abort')
            return None
        if view.file_types and not self.enabled_for_scopes(view):
            logger.debug('not enabled for view, abort')
            return None

        server = self._server_manager.get(view)     # type: Server
        if not server:
            logger.debug('no server for view, cannot request completions')
            return None

        # don't do a full health check, just check the status and process:
        if not server.is_alive(timeout=0):
            logger.debug('server is not running, abort')
            return None

        request_params = view.generate_request_parameters()
        if not request_params:
            logger.debug('failed to generate request params, abort')
            return None

        if not self._view_manager.has_notified_ready_to_parse(view, server):
            logger.debug(
                'file has not been sent to the server yet, '
                'may have missed a view event'
            )
            # send a notification, but don't wait around
            # this may result in poor completions this time around, but at
            # least the identifiers will be handy for the next time
            self.activate_view(view)

        # apply any view/server-specific settings:
        if self._settings is not None:
            force_semantic = self._settings.ycmd_force_semantic_completion
            request_params.force_semantic = force_semantic

        logger.debug('sending completion request for view')
        try:
            # NOTE : This call blocks!!
            completion_response = server.get_code_completions(
                request_params, timeout=0.2,
            )
            completions = completion_response.completions
            diagnostics = completion_response.diagnostics
        except TimeoutError:    # noqa
            logger.debug('completion request timed out')
            completions = None
            diagnostics = None
        logger.debug('got completions for view: %s', completions)

        if diagnostics:
            self._handle_diagnostics(view, server, diagnostics)

        if not completions:
            logger.debug('no completions, returning none')
            return None

        assert isinstance(completions, Completions), \
            '[internal] completions must be Completions: %r' % (completions)

        def _st_completion_tuple(completion):
            assert isinstance(completion, CompletionOption), \
                '[internal] completion is not CompletionOption: %r' % \
                (completion)
            # TODO : Calculate trigger properly
            st_trigger = completion.text()
            st_shortdesc = completion.shortdesc()
            st_insertion_text = completion.text()

            return (
                '%s\t%s' % (st_trigger, st_shortdesc),
                '%s' % (st_insertion_text),
            )

        st_completion_list = [_st_completion_tuple(c) for c in completions]
        return st_completion_list

    def __contains__(self, view):
        ''' Wrapper around server manager. '''
        return view in self._server_manager

    def __getitem__(self, view):
        ''' Wrapper around server manager. '''
        return self._server_manager[view]   # type: Server

    def __len__(self):
        ''' Wrapper around server manager. '''
        return len(self._server_manager)

    def __bool__(self):
        ''' Returns `True` if plugin is configured and ready. '''
        return self._settings is not None

    def _requires_ycmd_restart(self, settings):
        '''
        Returns true if the given `settings` would require a restart of any
        ycmd servers. This basically just compares the settings to the internal
        copy of the settings, and returns true if any ycmd parameters differ.
        '''
        assert isinstance(settings, Settings), \
            '[internal] settings must be Settings: %r' % (settings)

        if not self._settings:
            # no settings - always trigger restart
            return True
        assert isinstance(self._settings, Settings), \
            '[internal] settings must be Settings: %r' % (self._settings)

        return has_same_ycmd_settings(self._settings, settings)

    def _requires_task_pool_restart(self, settings):
        '''
        Returns true if the given `settings` would require a restart of any
        task workers. Same logic as `_requires_ycmd_restart`.
        '''
        assert isinstance(settings, Settings), \
            '[internal] settings must be Settings: %r' % (settings)

        if not self._settings:
            # no settings - always trigger restart
            return True
        assert isinstance(self._settings, Settings), \
            '[internal] settings must be Settings: %r' % (self._settings)

        return has_same_task_pool_settings(self._settings, settings)

    def _handle_diagnostics(self, view, server, diagnostics):
        '''
        Inspects the results of a completion request for diagnostics and
        displays them appropriately.
        If the diagnostic is a server error, this may display a popup to alert
        the user. If the diagnostic is a linting error, this may display a lint
        outline at the related file position.
        '''
        assert isinstance(diagnostics, Diagnostics), \
            '[internal] diagnostics must be Diagnostics: %r' % (diagnostics)
        for diagnostic in diagnostics:
            if not isinstance(diagnostic, DiagnosticError):
                logger.debug('unknown diagnostic, ignoring: %r', diagnostic)
                continue

            if diagnostic.is_unknown_extra_conf():
                # TODO : Prompt UnknownExtraConf with debounce.
                extra_conf_path = diagnostic.unknown_extra_conf_path()
                load_extra_conf = prompt_load_extra_conf(extra_conf_path)
                self._server_manager.notify_use_extra_conf(
                    view, extra_conf_path, load=load_extra_conf,
                )
            else:
                logger.debug('unhandled diagnostic, ignoring: %r', diagnostic)

    def enabled_for_scopes(self, view, locations=0):
        '''
        Returns `True` if completions should be performed at the scopes
        contained in `locations`. This will apply the language whitelist and
        blacklist on all points in `locations` using the given `view`.

        If there is more than one location, this will apply the scope check
        to all locations, and only return true if all pass.

        Locations may be given as any of the following types:
            `sublime.Selection`, `sublime.Region`, `[sublime.Region]`,
            Point/`int`, `[int]`, RowCol/`(int, int)`, `[(int, int)]`
        The default of `0` will check against the scope at the first character
        of the view (which is a good approximation for the view's language).
        '''
        if not self._settings:
            logger.error('plugin has not been configured: %r', self._settings)
            return False

        if isinstance(view, View):
            # remove wrapper, we need the raw view APIs
            view = view.view

        if not view or not isinstance(view, sublime.View):
            raise TypeError('view must be sublime.View: %r' % (view))

        language_whitelist = self._settings.ycmd_language_whitelist
        language_blacklist = self._settings.ycmd_language_blacklist

        check_whitelist = not not language_whitelist
        check_blacklist = not not language_blacklist

        if not check_whitelist and not check_blacklist:
            logger.debug('no whitelist/blacklist, always returning true')
            return True

        def _enabled_for_location(location):
            if isinstance(location, sublime.Region):
                # check each end of the region
                start = location.begin()
                if not _enabled_for_location(start):
                    return False

                if not location.empty():
                    end = location.end()
                    return _enabled_for_location(end)

            if hasattr(location, '__len__') and len(location) == 2:
                row, col = location
                assert isinstance(row, int), 'row must be an int: %r' % (row)
                assert isinstance(col, int), 'col must be an int: %r' % (col)

                point = view.text_point(row, col)
                return _enabled_for_location(point)

            if isinstance(location, int):
                is_whitelisted = not check_whitelist or any(map(
                    lambda scope: view.match_selector(location, scope),
                    language_whitelist
                ))
                if not is_whitelisted:
                    return False

                is_blacklisted = check_blacklist and any(map(
                    lambda scope: view.match_selector(location, scope),
                    language_blacklist
                ))
                return not is_blacklisted

            raise TypeError('invalid location: %r' % (location))

        if hasattr(locations, '__iter__'):
            return all(map(_enabled_for_location, locations))
        return _enabled_for_location(locations)

    # NOTE : Rest of the methods are for debugging/testing.
    #        Do not build on top of them!
    @property
    def server_manager(self):
        ''' Returns a reference to the server manager instance. '''
        return self._server_manager

    @property
    def servers(self):
        ''' Returns a shallow copy of the list of active servers. '''
        return self._server_manager.get_servers()

    def lookup_server(self, view):
        '''
        Returns the server that would handle completion requests for the given
        view, if one exists. Does NOT create one if it doesn't exist, just
        returns None.
        '''
        server_manager = self._server_manager
        if view in server_manager:
            return server_manager[view]
        return None

    @property
    def view_manager(self):
        ''' Returns a reference to the view manager instance. '''
        return self._view_manager

    @property
    def views(self):
        ''' Returns a shallow copy of the map of active views. '''
        return self._view_manager.get_views()

    def lookup_view(self, view):
        '''
        Returns a wrapped `View` for the given `sublime.View` in the view
        manager, if one exists. Does NOT create one if it doesn't exist, just
        returns `None`.
        If `view` is already a `View`, it is returned as-is.
        '''
        view_manager = self._view_manager
        if view in view_manager:
            return view_manager[view]
        return None


# Plugin state object. Although it's pretty bad form, this is kept as a global
# variable to simplify the logic in the `plugin_loaded`, and `plugin_unloaded`
# hooks. The state data needs to be available in both.
# When defined, the state should be a self-contained `SublimeYcmdState`. No
# other global variables should exist! Keep everything in one place...
_SY_PLUGIN_STATE = None     # type: SublimeYcmdState


def _reset_plugin_state():
    ''' Clears the existing plugin state, and reinitializes a new one. '''
    global _SY_PLUGIN_STATE
    if _SY_PLUGIN_STATE is not None:
        logger.info('clearing previous plugin state')
        assert isinstance(_SY_PLUGIN_STATE, SublimeYcmdState), \
            '[internal] inconsistent plugin state, ' \
            'should be SublimeYcmdState: %r' % (_SY_PLUGIN_STATE)

        _SY_PLUGIN_STATE.reset()
    else:
        logger.debug('no plugin state, already cleared')

    logger.info('initializing new plugin state')
    _SY_PLUGIN_STATE = SublimeYcmdState()


def _get_plugin_state():
    '''
    Returns the global `SublimeYcmdState` instance.
    If an instance hasn't been initialized yet, this will return `None`.
    '''
    global _SY_PLUGIN_STATE
    if _SY_PLUGIN_STATE is None:
        logger.error('no plugin state has been initialized')
        return None

    assert isinstance(_SY_PLUGIN_STATE, SublimeYcmdState), \
        '[internal] inconsistent plugin state, ' \
        'should be SublimeYcmdState: %r' % (_SY_PLUGIN_STATE)
    return _SY_PLUGIN_STATE


class SublimeYcmdCompleter(sublime_plugin.EventListener):
    '''
    Completion plugin. Receives completion requests to forward to ycmd.
    '''

    def on_query_completions(self, view, prefix, locations):
        state = _get_plugin_state()
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
        state = _get_plugin_state()
        if not state:
            logger.debug('no plugin state, ignoring on-load event')
            return

        if not state.activate_view(view):
            logger.warning('failed to activate view: %r', view)

    def on_activated(self, view):       # type: (sublime.View) -> None
        state = _get_plugin_state()
        if not state:
            logger.debug('no plugin state, ignoring activate event')
            return

        if not state.activate_view(view):
            logger.warning('failed to activate view: %r', view)

    def on_deactivated(self, view):     # type: (sublime.View) -> None
        state = _get_plugin_state()
        if not state:
            logger.debug('no plugin state, ignoring deactivate event')
            return

        if not state.deactivate_view(view):
            logger.warning('failed to deactivate view: %r', view)


class SublimeYcmdListServers(sublime_plugin.TextCommand):
    def run(self, edit):
        state = _get_plugin_state()
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
        state = _get_plugin_state()
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


class SublimeYcmdEditSettings(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        window = view.window()

        if not window:
            logger.error('no window, cannot launch settings')
            return

        settings_base_file = \
            '${packages}/sublime-ycmd/sublime-ycmd.sublime-settings'
        settings_placeholder = (
            '{\n'
            '\t\"ycmd_root_directory\": \"$0\"\n'
            '}\n'
        )
        window.run_command('edit_settings', {
            'base_file': settings_base_file,
            'default': settings_placeholder,
        })


class SublimeYcmdListCompleterCommands(sublime_plugin.TextCommand):
    def run(self, edit):
        state = _get_plugin_state()
        if not state:
            return

        view = self.view
        window = view.window()

        if not window:
            logger.warning('no window, cannot display info')
            return

        server = state.server_manager.get_server_for_view(view)
        completer_commands = server.get_debug_info()

        logger.info('completer commands: %s', completer_commands)
        raise NotImplementedError('unimplemented: show completer commands')


def on_change_settings(settings):
    ''' Callback, triggered when settings are loaded/modified. '''
    logger.info('loaded settings: %s', settings)

    state = _get_plugin_state()

    if state is None:
        logger.critical('cannot reconfigure plugin, no plugin state exists')
    else:
        logger.debug('reconfiguring plugin state')
        state.configure(settings)


def plugin_loaded():
    ''' Callback, triggered when the plugin is loaded. '''
    logger.info('initializing sublime-ycmd')
    configure_logging()
    _reset_plugin_state()
    logger.info('starting sublime-ycmd')
    bind_on_change_settings(on_change_settings)


def plugin_unloaded():
    ''' Callback, triggered when the plugin is unloaded. '''
    logger.info('unloading sublime-ycmd')
    _reset_plugin_state()
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
