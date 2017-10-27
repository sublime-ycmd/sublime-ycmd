#!/usr/bin/env python3

'''
plugin/view.py
View manager class.

Manages and organizes views. The main purpose of this class is to help
determine which views/files belong to the same project. Views in the same
project may all share a single ycmd server backend.
'''

import logging
import threading

from ..lib.subl.view import (
    View,
    get_view_id,
)
from ..lib.util.lock import lock_guard

logger = logging.getLogger('sublime-ycmd.' + __name__)

try:
    import sublime
except ImportError:
    from ..lib.subl.dummy import sublime


class SublimeYcmdViewManager(object):
    '''
    Singleton helper class. Manages wrappers around sublime view instances.
    The wrapper class `View` is used around `sublime.View` to cache certain
    calculations, and to store view-specific variables/state.
    Although this abstraction isn't strictly necessary, it can save expensive
    operations like file path calculation and ycmd event notification.

    All APIs are thread-safe.
    '''

    def __init__(self):
        # maps view IDs to `View` instances
        self._views = {}
        self._lock = threading.RLock()
        self.reset()

    @lock_guard()
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
        if not isinstance(view, (int, sublime.View, View)):
            raise TypeError('view must be a View: %r' % (view))

        if isinstance(view, View):
            return view

        view_id = get_view_id(view)
        if view_id is None:
            logger.error('failed to get view ID for view: %r', view)
            raise TypeError('view id must be an int: %r' % (view))

        with self._lock:
            if view_id not in self._views:
                # create a wrapped view, if possible
                if not isinstance(view, sublime.View):
                    # not possible... view given with just its id
                    logger.warning(
                        'view has not been registered, id: %r', view_id,
                    )
                    raise KeyError(view,)

                # else, we have a usable view for the wrapper
                logger.debug(
                    'view has not been registered, registering it: %r', view,
                )
                self._register_view(view, view_id)

            assert view_id in self._views, \
                '[internal] view id has not been registered: %r' % (view_id)
            wrapped_view = self._views[view_id]     # type: View
            return wrapped_view

    @lock_guard()
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

        init_notified_server_set(view)
        return has_notified_server(view, server)

    @lock_guard()
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

        init_notified_server_set(view)
        if has_notified:
            add_notified_server(view, server)
        else:
            remove_notified_server(view, server)

    def _register_view(self, view, view_id=None):
        if not isinstance(view, sublime.View):
            raise TypeError('view must be a sublime.View: %r' % (view))

        if view_id is None:
            view_id = get_view_id(view)
        if not isinstance(view_id, int):
            raise TypeError('view id must be an int: %r' % (view))

        logger.debug('registering view with id: %r, %r', view_id, view)
        view = View(view)
        with self._lock:
            self._views[view_id] = view

        return view_id

    def _unregister_view(self, view):
        view_id = get_view_id(view)
        if view_id is None:
            logger.error('failed to get view ID for view: %r', view)
            raise TypeError('view id must be an int: %r' % (view))

        with self._lock:
            if view_id not in self._views:
                logger.debug(
                    'view was never registered, ignoring id: %s', view_id,
                )
                return False

            del self._views[view_id]
            return True

    @lock_guard()
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

        with self._lock:
            return view_id in self._views

    @lock_guard()
    def __getitem__(self, view):
        return self.get_wrapped_view(view)

    @lock_guard()
    def __len__(self):
        return len(self._views)

    def __bool__(self):
        ''' Returns `True`, so an instance is always truthy. '''
        return True


NOTIFIED_SERVERS_KEY = 'notified_servers'


def init_notified_server_set(view, key=NOTIFIED_SERVERS_KEY):
    '''
    Initializes the set of notified servers for a given `view` if it has not
    already been initialized.

    This does nothing if it has been initialized already.
    '''
    if not isinstance(view, View):
        logger.warning('view does not appear valid: %r', view)

    if key not in view:
        logger.debug('view has not been sent to any server, creating metadata')
        view[key] = set()


def get_server_key(server):
    '''
    Returns a unique key for `server` to use as an id for it.
    '''
    server_key = str(server)
    return server_key


def has_notified_server(view, server, key=NOTIFIED_SERVERS_KEY):
    '''
    Checks if a given `server` is in the notified server set for a `view`.
    '''
    if not isinstance(view, View):
        logger.warning('view does not appear valid: %r', view)

    if key not in view:
        logger.error(
            'notified server set is not initialized for view: %r', view,
        )

    notified_servers = view[key]
    assert isinstance(notified_servers, set), \
        '[internal] notified server set is not a set: %r' % (notified_servers)

    server_key = get_server_key(server)
    return server_key in notified_servers


def add_notified_server(view, server, key=NOTIFIED_SERVERS_KEY):
    '''
    Adds `server` to the notified server set for `view`.
    '''
    if not isinstance(view, View):
        logger.warning('view does not appear valid: %r', view)

    if key not in view:
        logger.error(
            'notified server set is not initialized for view: %r', view,
        )

    notified_servers = view[key]
    assert isinstance(notified_servers, set), \
        '[internal] notified server set is not a set: %r' % (notified_servers)

    server_key = get_server_key(server)
    notified_servers.add(server_key)


def remove_notified_server(view, server, key=NOTIFIED_SERVERS_KEY):
    '''
    Removes `server` to the notified server set for `view`.

    If the server is not in the notified server set, this does nothing.
    '''
    if not isinstance(view, View):
        logger.warning('view does not appear valid: %r', view)

    if key not in view:
        logger.error(
            'notified server set is not initialized for view: %r', view,
        )

    notified_servers = view[key]
    assert isinstance(notified_servers, set), \
        '[internal] notified server set is not a set: %r' % (notified_servers)

    server_key = get_server_key(server)
    notified_servers.discard(server_key)
