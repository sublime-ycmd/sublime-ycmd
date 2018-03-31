#!/usr/bin/env python3

'''
plugin/state.py
Global state class.

Provides top-level APIs for handling events along with access to the server
manager and view manager.
'''

import logging

from ..lib.schema import (
    Completions,
    CompletionOption,
    Diagnostics,
    DiagnosticError,
)
from ..lib.subl.errors import PluginError
from ..lib.subl.settings import (
    Settings,
    validate_settings,
    has_same_ycmd_settings,
    has_same_task_pool_settings,
)
from ..lib.subl.view import (
    View,
    get_file_types,
)
from ..lib.ycmd.start import StartupParameters

from ..plugin.log import configure_logging
from ..plugin.server import SublimeYcmdServerManager
from ..plugin.ui import (
    display_plugin_error,
    prompt_load_extra_conf,
)
from ..plugin.view import SublimeYcmdViewManager

logger = logging.getLogger('sublime-ycmd.' + __name__)

try:
    import sublime
except ImportError:
    from ..lib.subl.dummy import sublime


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

            server_idle_suicide_seconds=settings.ycmd_idle_suicide_seconds,
            server_check_interval_seconds=settings.ycmd_check_interval_seconds,
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
        view = self._view_manager[view]     # type: View
        if not view:
            logger.debug('no view wrapper, ignoring activate event')
            return False

        if not view.ready():
            logger.debug('file is not ready for parsing, ignoring')
            return False
        if not get_file_types(view):
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
        view = self._view_manager[view]     # type: View
        if not view:
            logger.debug('no view wrapper, ignoring deactivate event')
            return False

        if not view.ready():
            logger.debug('file is not ready for parsing, ignoring')
            return False
        if not get_file_types(view):
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
        view = self._view_manager[view]     # type: View
        if not view:
            logger.debug('no view wrapper, cannot create request parameters')
            return None

        if not view.ready():
            logger.debug('file is not ready for parsing, abort')
            return None
        if get_file_types(view) and not self.enabled_for_scopes(view):
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
            # TODO : Allow configurable completion timeout.
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
        server = self._server_manager[view]   # type: Server
        return server

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
            server = server_manager[view]   # type: Server
            return server
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
# variable to simplify the logic in the plugin hooks and text commands. The
# state data needs to be available in both.
# When defined, the state should be a self-contained `SublimeYcmdState`. No
# other global variables should exist! Keep everything in one place...
_SY_PLUGIN_STATE = None     # type: SublimeYcmdState


def reset_plugin_state():
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


def get_plugin_state():
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
