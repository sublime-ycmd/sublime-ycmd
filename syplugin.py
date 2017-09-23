#!/usr/bin/env python3

'''
syplugin.py
Main Sublime Text Plugin script. Starts a backend server and sends completion
requests to it.
'''

import logging
import logging.config
import os
import sys

sys.path.append(os.path.dirname(__file__))  # noqa: E402

from cli.args import base_cli_argparser
from lib.util.log import (
    get_smart_truncate_formatter,
)
from lib.schema import (
    Completions,
    CompletionOption,
)
from lib.subl.settings import (
    Settings,
    bind_on_change_settings,
)
from lib.subl.view import (
    View,
    get_view_id,
    get_path_for_view,
)
from lib.ycmd.server import Server
from lib.ycmd.start import (
    start_ycmd_server,
)

logger = logging.getLogger('sublime-ycmd.' + __name__)

try:
    import sublime
    import sublime_plugin
    _HAS_LOADED_ST = True
except ImportError:
    from lib.subl.dummy import sublime
    from lib.subl.dummy import sublime_plugin
    _HAS_LOADED_ST = False
finally:
    assert isinstance(_HAS_LOADED_ST, bool)


def configure_logging(dict_config, logger=None):
    '''
    Configures the logging module (or plugin-specific root logger) to log with
    the configuration in the given `dict_config`.
    The dictionary configuration must be compatible with `logging.config`.
    '''
    # pylint: disable=redefined-outer-name

    if logger is None:
        logger = logging.getLogger('sublime-ycmd')
    if not isinstance(logger, logging.Logger):
        raise TypeError('logger should be a Logger: %r' % (logger))

    logging.config.dictConfig(dict_config)


class SublimeYcmdServerManager(object):
    '''
    Singleton helper class. Runs, manages, and stops ycmd server instances.
    Generally, each project will have its own associated backend ycmd server.
    This is required for certain completers, like tern, that rely on the
    working directory in order to find imported files.
    '''

    def __init__(self):
        self._servers = []
        self.reset()

    def reset(self,
              ycmd_root_directory=None,
              ycmd_default_settings_path=None,
              ycmd_python_binary_path=None):
        if self._servers:
            for server in self._servers:
                if not isinstance(server, Server):
                    logger.error(
                        'invalid server handle, clearing it: %r', server
                    )
                    continue

                if not server.alive():
                    logger.debug('skipping dead server: %s', server)
                    continue

                logger.debug('stopping server: %s', server)

                # TODO : make this shutdown async - it might block...
                server.stop()

                if server.alive():
                    logger.warning(
                        'server did not stop, doing hard shutdown: %s', server
                    )
                    server.stop(hard=True)

            logger.info('all ycmd servers have been shut down')

        # server startup parameters:
        self._ycmd_root_directory = ycmd_root_directory
        self._ycmd_default_settings_path = ycmd_default_settings_path
        self._ycmd_python_binary_path = ycmd_python_binary_path

        # active servers:
        self._servers = []

        # lookup tables:
        self._view_id_to_server = {}
        self._working_directory_to_server = {}

    def get_servers(self):
        '''
        Returns a shallow-copy of the list of managed `Server` instances.
        '''
        return self._servers[:]

    def get_server_for_view(self, view):    # type (sublime.View) -> Server
        '''
        Returns a `Server` instance that has a suitable working directory for
        use with the supplied `view`.
        If one does not exist, it will be created.
        '''
        if not isinstance(view, (sublime.View, View)):
            raise TypeError('view must be a View: %r' % (view))

        view_id = get_view_id(view)
        if view_id is None:
            logger.error('failed to get view ID for view: %r', view)
            raise TypeError('view id must be an int: %r' % (view))

        view_working_dir = get_path_for_view(view)

        server = None
        if view_id is not None and view_id in self._view_id_to_server:
            server = self._view_id_to_server[view_id]
        elif view_working_dir is not None and \
                view_working_dir in self._working_directory_to_server:
            # map the view id to this server as well, for future lookups
            server = self._working_directory_to_server[view_working_dir]
            self._view_id_to_server[view_id] = server

        if server and not server.alive():
            # stale server, clear it and allocate another
            logger.info('removing stale server: %s', server.pretty_str())

            # XXX(akshay) : REMOVE - this is for grabbing startup errors
            stdout, stderr = server.communicate()
            logger.debug('[REMOVEME] stdout, stderr: %s, %s', stdout, stderr)

            self._unregister_server(server)
            server = None

        if not server:
            logger.info(
                'creating ycmd server for project directory: %s',
                view_working_dir,
            )
            server = start_ycmd_server(
                self._ycmd_root_directory,
                ycmd_settings_path=self._ycmd_default_settings_path,
                python_binary_path=self._ycmd_python_binary_path,
                working_directory=view_working_dir,
            )
            self._servers.append(server)

        self._view_id_to_server[view_id] = server
        self._working_directory_to_server[view_working_dir] = server

        return server   # type: Server

    def _unregister_server(self, server):
        assert isinstance(server, Server), \
            '[internal] server must be Server: %r' % (server)
        if server not in self._servers:
            logger.error(
                'server was never registered in server manager: %s',
                server.pretty_str(),
            )
            return False

        view_map = self._view_id_to_server
        view_keys = list(filter(
            lambda k: view_map[k] == server, view_map,
        ))
        logger.debug('clearing server for views: %s', view_keys)
        for view_key in view_keys:
            del view_map[view_key]

        working_directory_map = self._working_directory_to_server
        working_directory_keys = list(filter(
            lambda k: working_directory_map[k] == server,
            working_directory_map,
        ))
        logger.debug(
            'clearing server for working directories: %s',
            working_directory_keys,
        )
        for working_directory_key in working_directory_keys:
            del working_directory_map[working_directory_key]

        self._servers.remove(server)

    def __contains__(self, view):
        view_id = get_view_id(view)
        if view_id is None:
            logger.error('failed to get view ID for view: %r', view)
            raise TypeError('view id must be an int: %r' % (view))

        return view_id in self._view_id_to_server

    def __getitem__(self, view):
        return self.get_server_for_view(view)   # type: Server

    def __len__(self):
        return len(self._servers)


class SublimeYcmdViewManager(object):
    '''
    Singleton helper class. Manages wrappers around sublime view instances.
    The wrapper class `View` is used around `sublime.View` to cache certain
    calculations, and to store view-specific variables/state.
    Although this abstraction isn't strictly necessary, it can save expensive
    operations like file path calculation and ycmd event notification.
    '''

    def __init__(self):
        # maps view IDs to `View` instances
        self._views = {}
        self.reset()

    def reset(self):
        if self._views:
            view_ids = list(self._views.keys())
            for view_id in view_ids:
                self._unregister_view(view_id)

            logger.info('all views have been unregistered')

        # active views:
        self._views = {}

    def get_wrapped_view(self, view):
        '''
        Returns an instance of `View` corresponding to `view`. If one does
        not exist, it will be created, if possible.
        If the view is provided as an ID (int), then the lookup is performed
        as normal, but a `KeyError` will be raised if it does not exist.
        If the view is an instance of `sublime.View`, then the lookup is again
        performed as usual, but will be created if it does not exist.
        Finally, if the view is an instance of `View`, it is returned as-is.
        '''
        assert isinstance(view, (int, sublime.View, View)), \
            'view must be a View: %r' % (view)

        if isinstance(view, View):
            return view

        view_id = get_view_id(view)
        if view_id is None:
            logger.error('failed to get view ID for view: %r', view)
            raise TypeError('view id must be an int: %r' % (view))

        if view_id not in self._views:
            if not isinstance(view, sublime.View):
                logger.warning(
                    'view has not been registered for id: %s', view_id,
                )
                raise KeyError('view id is not registered: %r' % (view_id))

            logger.debug('view is not registered, creating a wrapper for it')
            wrapped_view = View(view)
            self._views[view_id] = wrapped_view

        assert view_id in self._views, \
            '[internal] view id was not registered properly: %r' % (view_id)
        return self._views[view_id]     # type: View

    def has_notified_ready_to_parse(self, view, server):
        '''
        Returns true if the given `view` has been parsed by the `server`. This
        must be done at least once to ensure that the ycmd server has a list
        of identifiers to offer in completion results.
        This works by storing a view-specific variable indicating the server,
        if any, that the view has been uploaded to. If this variable is not
        set, or if the variable refers to another server, this method will
        return false. In that case, the notification should probably be sent.
        '''
        view = self.get_wrapped_view(view)
        if not view:
            logger.error('unknown view type: %r', view)
            raise TypeError('view must be a View: %r' % (view))

        # TODO : Move magic string constants to a more centralized place.
        if 'last_notified_server' not in view:
            logger.debug('view has not been sent to any server: %s', view)
            return False

        # accept servers either as strings or as `Server` instances:
        supplied_server_key = str(server)
        notified_server_key = view['last_notified_server']

        logger.debug(
            'last notified server, supplied server key: %s, %s',
            notified_server_key, supplied_server_key,
        )

        if notified_server_key == supplied_server_key:
            return True

        if 'notified_servers' not in view:
            logger.debug('view has not been sent to any server: %s', view)
            return False

        notified_servers = view['notified_servers']
        assert isinstance(notified_servers, dict), \
            '[internal] notified server map is not a dict: %r' % \
            (notified_servers)

        has_notified_for_server_key = (
            supplied_server_key in notified_servers and
            notified_servers[supplied_server_key]
        )
        logger.debug(
            'has notified server: %s ? %s',
            supplied_server_key, has_notified_for_server_key,
        )

        return has_notified_for_server_key

    def set_notified_ready_to_parse(self, view, server, has_notified=True):
        '''
        Updates the variable that indicates that the given `view` has been
        parsed by the `server`.
        This works by setting a view-specific variable indicating the server,
        that the view has been uploaded to. The same variable can then be
        checked in `has_notified_ready_to_parse`.
        '''
        view = self.get_wrapped_view(view)
        if not view:
            logger.error('unknown view type: %r', view)
            raise TypeError('view must be a View: %r' % (view))

        # TODO : Move magic string constants to a more centralized place.
        if 'last_notified_server' not in view:
            # initialize, but leave it blank
            view['last_notified_server'] = None
        if 'notified_servers' not in view:
            # initialize, but leave it empty
            view['notified_servers'] = {}

        # accept servers either as strings or as `Server` instances:
        supplied_server_key = str(server)

        notified_server_key = view['last_notified_server']
        notified_servers = view['notified_servers']

        if has_notified:
            # unconditionally set with the given server key
            view['last_notified_server'] = supplied_server_key
            notified_servers[supplied_server_key] = True
            return

        # clear the variables, if set
        if notified_server_key == supplied_server_key:
            # that was the last notified, but not anymore!
            view['last_notified_server'] = None
        if supplied_server_key in notified_servers:
            # that was flagged as notified, so unflag it
            del notified_servers[supplied_server_key]

    def _register_view(self, view):
        assert isinstance(view, (sublime.View, View)), \
            'view must be a View: %r' % (view)

        view_id = get_view_id(view)
        if view_id is None:
            logger.error('failed to get view ID for view: %r', view)
            raise TypeError('view id must be an int: %r' % (view))

        if view_id in self._views:
            logger.warning('view has already been registered, id: %s', view_id)

        if isinstance(view, sublime.View):
            view = View(view)
        elif not isinstance(view, View):
            logger.error('unknown view type: %r', view)
            raise TypeError('view must be a View: %r' % (view))

        self._views[view_id] = view
        return view_id

    def _unregister_view(self, view):
        view_id = get_view_id(view)
        if view_id is None:
            logger.error('failed to get view ID for view: %r', view)
            raise TypeError('view id must be an int: %r' % (view))

        if view_id not in self._views:
            logger.debug(
                'view was never registered, ignoring id: %s', view_id,
            )
            return False

        del self._views[view_id]
        return True

    def get_views(self):
        '''
        Returns a shallow-copy of the map of managed `View` instances.
        '''
        return self._views.copy()

    def __contains__(self, view):
        view_id = get_view_id(view)
        if view_id is None:
            logger.error('failed to get view ID for view: %r', view)
            raise TypeError('view id must be an int: %r' % (view))

        return view_id in self._views

    def __getitem__(self, view):
        return self.get_wrapped_view(view)

    def __len__(self):
        return len(self._views)

    def __bool__(self):
        ''' Returns `True`, so an instance is always truthy. '''
        return True


class SublimeYcmdState(object):
    '''
    Singleton helper class. Stores the global state, and provides utilities
    to the plugin handlers.
    '''

    def __init__(self):
        self._server_manager = SublimeYcmdServerManager()
        self._view_manager = SublimeYcmdViewManager()
        self.reset()

    def reset(self):
        ''' Stops all ycmd servers and clears all settings. '''
        self._server_manager.reset()
        self._view_manager.reset()
        self._settings = None

    def configure(self, settings):
        '''
        Receives a `settings` object and reconfigures the state from it.
        The settings should be an instance of `Settings`. See `lib.st` for
        helpers to generate these settings.
        If there are changes to the ycmd server settings, then the state will
        automatically stop all currently running servers. They will be
        relaunched with the new parameters when a completion request is made.
        If there are changes to the logging settings, then the state will
        reconfigure the logger without messing with any ycmd servers.
        The inspected settings are:
            ycmd_root_directory (str): Path to ycmd root directory.
            ycmd_default_settings_path (str): Path to default ycmd settings.
                If omitted, it is calculated based on the ycmd root directory.
            ycmd_python_binary_path (str): Path to the python binary used to
                run the ycmd module (i.e. start the server).
                This should match the version that was used to build ycmd.
                If omitted, the system PATH is used to find it.
            ycmd_language_whitelist (list of str): Scope selectors to enable
                ycmd completion for.
                If omitted, or empty, all scopes are whitelisted.
            ycmd_language_blacklist (list of str): Scope selectors to disable
                ycmd completion for. These scopes are checked after the
                whitelist, so the blacklist has higher priority.
                If omitted, or empty, no scopes are blacklisted.
            sy_log_level (str): Minimum severity level to log at. Should be one
                of the constants from the `logging` module: 'DEBUG', 'INFO',
                'WARNING', 'ERROR', 'CRITICAL'.
        '''
        assert isinstance(settings, Settings), \
            'settings must be Settings: %r' % (settings)

        requires_restart = self._requires_ycmd_restart(settings)
        if requires_restart:
            logger.debug('new settings require ycmd server restart, resetting')
            self.reset()

        self._server_manager.reset(
            ycmd_root_directory=settings.ycmd_root_directory,
            ycmd_default_settings_path=settings.ycmd_default_settings_path,
            ycmd_python_binary_path=settings.ycmd_python_binary_path,
        )
        logging_dictconfig = settings.sublime_ycmd_logging_dictconfig
        if logging_dictconfig:
            configure_logging(logging_dictconfig)

        logger.debug('successfully configured with settings: %s', settings)
        self._settings = settings

    def activate_view(self, view):
        '''
        Registers and notifies the ycmd server to prepare for events on the
        given `view`. The first time a view is passed in, it is parsed by the
        server to generate the initial list of identifiers. Then, an event
        notification is sent to the server to indicate that the view is open
        in the editor (and any unsaved buffer data is sent over for additional
        parsing).
        '''
        state = _get_plugin_state()
        if not state:
            logger.debug('no plugin state, ignoring activate event')
            return False

        server = self._server_manager[view]     # type: Server
        view = self._view_manager[view]         # type: View
        if not server:
            logger.debug('no server for view, ignoring activate event')
            return False
        if not view:
            logger.debug('no view wrapper, ignoring activate event')
            return False

        if not view.ready():
            logger.debug('file is not ready for parsing, ignoring')
            return False

        request_params = view.generate_request_parameters()
        if not request_params:
            logger.debug('failed to generate request params, abort')
            return False

        if not self._view_manager.has_notified_ready_to_parse(view, server):
            logger.debug(
                'file has not been sent to the server yet, doing that first'
            )
            server.notify_file_ready_to_parse(request_params)
            self._view_manager.set_notified_ready_to_parse(view, server)
        else:
            logger.debug(
                'file has been sent to the server previously, skipping that'
            )

        logger.debug('sending notification for entering buffer')
        server.notify_buffer_enter(request_params)
        return True

    def deactivate_view(self, view):
        '''
        Registers and notifies the ycmd server that the given `view` has been
        unloaded (closed, or switched out of). This allows the server to
        release resources for the buffer, since it won't need to handle events
        on it until it is re-activated.
        '''
        state = _get_plugin_state()
        if not state:
            logger.debug('no plugin state, ignoring deactivate event')
            return False

        server = self._server_manager[view]     # type: Server
        view = self._view_manager[view]         # type: View
        if not server:
            logger.debug('no server for view, ignoring deactivate event')
            return False
        if not view:
            logger.debug('no view wrapper, ignoring deactivate event')
            return False

        if not view.ready():
            logger.debug('file is not ready for parsing, ignoring')
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
            if self._view_manager.has_notified_ready_to_parse(view, server):
                logger.debug(
                    'removing flag, it will be re-uploaded when selected again'
                )
                self._view_manager.set_notified_ready_to_parse(
                    view, server, has_notified=False,
                )

        logger.debug('sending notification for unloading buffer')
        server.notify_buffer_leave(request_params)
        return True

    def completions_for_view(self, view):
        '''
        Registers and notifies the ycmd server to prepare for events on the
        given `view`. The first time a view is passed in, it is parsed by the
        server to generate the initial list of identifiers. Then, an event
        notification is sent to the server to indicate that the view is open
        in the editor (and any unsaved buffer data is sent over for additional
        parsing).
        '''
        state = _get_plugin_state()
        if not state:
            logger.debug('no plugin state, cannot provide completions')
            return None

        server = self._server_manager[view]     # type: Server
        view = self._view_manager[view]         # type: View
        if not server:
            logger.debug('no server for view, cannot request completions')
            return None
        if not view:
            logger.debug('no view wrapper, cannot create request parameters')
            return None

        if not view.ready():
            logger.debug('file is not ready for parsing, abort')
            return None

        request_params = view.generate_request_parameters()
        if not request_params:
            logger.debug('failed to generate request params, abort')
            return False

        if not self._view_manager.has_notified_ready_to_parse(view, server):
            logger.debug(
                'file has not been sent to the server yet, '
                'probably missed a view event'
            )
            server.notify_file_ready_to_parse(request_params)
            self._view_manager.set_notified_ready_to_parse(view, server)

        logger.debug('sending completion request for view')
        completions = server.get_code_completions(request_params)
        logger.debug('got completions for view: %s', completions)

        # TODO : Gracefully handle this by returning None
        assert isinstance(completions, Completions), \
            '[TODO] completions must be Completions: %r' % (completions)

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
        logger.critical(
            '[REMOVEME] generated completion data: %s', st_completion_list,
        )

        # TODO : Turn it on after disabling anaconda
        if 'python' in view.file_types:
            logger.critical('[TODO] enable for python, disable anaconda')
            return None

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
        ''' Dummy implementation, to prevent usage of `len` for truthyness. '''
        return True

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

        return self._settings != settings

    def _enabled_for_scopes(self, view, locations):
        '''
        Returns true if completions should be performed at the scopes contained
        in `locations`. This will apply the language whitelist and blacklist
        on all points in `locations` using the given `view`.
        If there is more than one location, this will apply the scope check
        to all locations, and only return true if all pass.
        Locations may be given as any of the following types:
            `sublime.Selection`, `sublime.Region`, `[sublime.Region]`,
            Point/`int`, `[int]`, RowCol/`(int, int)`, `[(int, int)]`
        '''

        if not self._settings:
            logger.error('plugin has not been configured: %s', self._settings)
            return False

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

                is_blacklisted = not check_blacklist or any(map(
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
        returns None.
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
    if _SY_PLUGIN_STATE:
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
    if not _SY_PLUGIN_STATE:
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

        completion_options = None
        try:
            # TODO : Check if enabled for scopes at `locations`.
            # TODO : Use `locations` instead of the cursor position.
            completion_options = state.completions_for_view(view)
        except Exception as e:
            logger.debug('failed to get completions: %s', e, exc_info=e)

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


class SublimeYcmdListServersCommand(sublime_plugin.TextCommand):
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

        raise NotImplementedError('unimplemented: display servers')

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

        def on_select_info(selection_index):
            pass

        window.show_quick_panel([
            ['Server', server_desc],
            ['Directory', view_working_directory],
        ], on_select_info)


class SublimeYcmdStartServer(sublime_plugin.TextCommand):
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

        def on_select_server(selection_index):
            pass

        window.show_quick_panel([
            ['Server', server.pretty_str()],
        ], on_select_server)


class SublimeYcmdReloadPlugin(sublime_plugin.TextCommand):
    def run(self, edit):
        def defer_reload():
            try:
                from imp import reload
                from types import ModuleType
            except ImportError:
                logger.error('failed to reload plugin: no reload method found')
                return

            PKG_NAME = 'sublime-ycmd'
            if PKG_NAME in sys.modules:
                pkg_module = sys.modules[PKG_NAME]

                def recursive_reload(current_module=pkg_module, tally=set()):
                    # type: (ModuleType, set) -> None
                    logger.info('reloading %s', current_module.__name__)
                    reload(current_module)
                    for module_local_name in dir(current_module):
                        submodule = getattr(current_module, module_local_name)
                        if type(submodule) is not ModuleType:
                            continue

                        submodule_name = submodule.__name__

                        if submodule_name in tally:
                            continue
                        tally.add(submodule_name)

                        if not hasattr(submodule, '__file__'):
                            continue
                        submodule_file = submodule.__file__

                        if PKG_NAME not in submodule_file:
                            continue

                        recursive_reload(
                            submodule, tally=tally,
                        )

                try:
                    plugin_unloaded()
                except Exception as e:
                    logger.warning('failed to unload, ignoring: %s', e)
                recursive_reload()
                plugin_loaded()

        sublime.set_timeout(defer_reload, 0)


class SublimeYcmdListCompleterCommandsCommand(sublime_plugin.TextCommand):
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

    if not state:
        logger.critical('cannot reconfigure plugin, no plugin state exists')
    else:
        logger.debug('reconfiguring plugin state')
        state.configure(settings)


DEBUG_LOGGING_DICT_CONFIG = {
    'version': 1,
    'filters': {
        '': {
            'level': 'DEBUG',
        }
    },
    'handlers': {
        'default': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
            'level': 'DEBUG',
            'stream': 'ext://sys.stderr',
        }
    },
    'formatters': {
        'default': {
            '()': 'lib.util.log.get_smart_truncate_formatter',
        }
    },
    'loggers': {
        'sublime-ycmd': {
            'level': 'DEBUG',
            'handlers': ['default'],
            'propagate': False,
        }
    }
}


def plugin_loaded():
    ''' Callback, triggered when the plugin is loaded. '''
    logger.info('initializing sublime-ycmd')
    configure_logging(DEBUG_LOGGING_DICT_CONFIG)
    _reset_plugin_state()
    logger.info('starting sublime-ycmd')
    bind_on_change_settings(on_change_settings)


def plugin_unloaded():
    ''' Callback, triggered when the plugin is unloaded. '''
    logger.info('unloading sublime-ycmd')
    _reset_plugin_state()
    logging.info('stopped sublime-ycmd')


def _configure_logging(log_level=None, output_stream=None):
    '''
    Configures the logging module (or plugin-specific root logger) to log at
    the given `log_level` on stream `output_stream`. Formatters, handlers, and
    filters are added to prettify the logging output.
    If `log_level` is not provided, it defaults to `logging.WARNING`.
    If `output_stream` is not provided, it defaults to `sys.stdout`.
    This is only meant for debugging. Not for use in the actual plugin logic.
    '''
    if log_level is None:
        log_level = logging.WARNING
    if output_stream is None:
        output_stream = sys.stdout

    # avoid messing with the root logger
    # if running under sublime, that would affect all other plugins as well
    logger_instance = logging.getLogger('sublime-ycmd')

    logger.debug('disabling propagate, and setting level')
    # disable propagate so logging does not go above this module
    logger_instance.propagate = False

    # enable all log levels on the top-level logger
    # the handler/filter will decide what to reject
    logger_instance.setLevel(logging.DEBUG)

    if logger_instance.hasHandlers():
        logger_handlers_old = [h for h in logger_instance.handlers]
        for logger_handler in logger_handlers_old:
            logger_instance.removeHandler(logger_handler)

    # Don't log after here! Extension filters not set up yet
    logger_stream = logging.StreamHandler(stream=output_stream)
    logger_stream.setLevel(log_level)
    logger_formatter = get_smart_truncate_formatter()
    logger_stream.setFormatter(logger_formatter)
    logger_instance.addHandler(logger_stream)
    # Safe to log again

    logger.debug('successfully configured logging')


def main():
    ''' Main function. Executed when this script is executed directly. '''
    cli_argparser = base_cli_argparser(
        description='sublime-ycmd plugin loader',
    )
    cli_args = cli_argparser.parse_args()
    _configure_logging(cli_args.log_level, cli_args.log_file)

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
