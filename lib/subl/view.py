#!/usr/bin/env python3

'''
lib/subl/settings.py
Plugin settings class.

Wraps the settings `dict` and exposes them as attributes on the class. Default
settings will be calculated for missing/blank settings if possible.

This is also meant to abstract the setting key names, so there aren't as many
hard-coded strings in the main plugin logic.
'''

import logging

try:
    import sublime
except ImportError:
    from lib.subl.dummy import sublime

from lib.schema.request import RequestParameters
from lib.subl.constants import SUBLIME_DEFAULT_LANGUAGE_SCOPE_MAPPING
from lib.util.fs import (
    get_common_ancestor,
    get_directory_name,
    resolve_abspath,
)

# for type annotations only:
from lib.ycmd.server import Server   # noqa: F401

logger = logging.getLogger('sublime-ycmd.' + __name__)


class View(object):
    '''
    Wrapper class that provides extra functionality over `sublime.View`.
    This allows tracking state for each view independently.
    '''

    def __init__(self, view=None):
        self._view = view   # type: sublime.View
        self._recalculate()

    def _recalculate(self):
        '''
        Pre-calculates the view properties for the internal view handle. Some
        properties, like file path, don't need to be recalculated constantly.
        They can be calculated once, and then re-used to save time.
        '''
        self._cache = {}

        if not self._view or not isinstance(self._view, sublime.View):
            return

        assert isinstance(self._view, sublime.View), \
            '[internal] view handle is not sublime.View: %r' % (self._view)

        view_path = get_path_for_view(self._view)
        view_file_types = get_file_types(self._view)

        self._cache['path'] = view_path
        self._cache['file_types'] = view_file_types

    def ready(self):
        '''
        Returns true if the underlying view handle is both primary (the main
        view for an underlying buffer), and not loading.
        This indicates that the file is ready for use with ycmd.
        '''
        if not self._view:
            logger.warning('view handle is not set, returning not ready...')
            return False

        view = self._view
        return (
            view.is_primary() and
            not view.is_scratch() and
            not view.is_loading()
        )

    def dirty(self):
        '''
        Returns true if the underlying buffer has unsaved changes.
        '''
        if not self._view:
            logger.warning('view handle is not set, returning not dirty...')
            return False

        view = self._view
        return view.is_dirty()

    def to_file_params(self):
        '''
        Generates and returns the keyword arguments required for making a call
        to a handler method on `Server`. These parameters include information
        about the file, and also the contents, and file type(s), if available.
        The result can be unpacked into a call to one of the server methods.
        '''
        logger.warning('deprecated: use View to RequestParameters instead')
        if not self._view:
            logger.error('no view handle has been set')
            return None

        view = self._view
        file_path = view.file_name()
        if not file_path:
            logger.debug(
                'view is not associated with a file, using its ID instead'
            )
            file_path = 'buffer_%s' % (str(view.buffer_id()))

        if not view.is_primary():
            logger.warning(
                'generating parameters for non-primary view, '
                'they should generally be ignored...'
            )

        if view.is_loading():
            logger.warning(
                'file is still loading, supplying empty contents for: %s',
                file_path,
            )
            file_contents = ''
            file_types = None
        else:
            file_region = sublime.Region(0, view.size())
            file_contents = view.substr(file_region)
            file_types = get_file_types(view)

        file_selections = view.sel()    # type: sublime.Selection
        if not file_selections:
            logger.warning(
                'no selections available, '
                'using default line and column numbers'
            )
            line_num = 1
            column_num = 1
        else:
            # arbitrarily use the first selection as the position
            file_region = file_selections[0]    # type: sublime.Region
            file_point = file_region.begin()
            file_row, file_col = view.rowcol(file_point)
            logger.debug('found file line, col: %s, %s', file_row, file_col)

            # ycmd expects 1-based indices, and sublime returns 0-based
            line_num = file_row + 1
            column_num = file_col + 1

        return {
            'file_path': file_path,
            'file_contents': file_contents,
            'file_types': file_types,
            'line_num': line_num,
            'column_num': column_num,
        }

    def generate_request_parameters(self):
        '''
        Generates and returns file-related `RequestParameters` for use in the
        `Server` handlers.
        These parameters include information about the file like the name,
        contents, and file type(s). Additional parameters may still be added to
        the result before passing it off to the server.

        TODO : Use cached values whenever possible.
        '''
        if not self._view:
            logger.error('no view handle has been set')
            return None

        view = self._view
        file_path = view.file_name()
        if not file_path:
            logger.debug(
                'view is not associated with a file, using its ID instead'
            )
            file_path = 'buffer_%s' % (str(view.buffer_id()))

        if not view.is_primary():
            logger.warning(
                'generating parameters for non-primary view, '
                'they should generally be ignored...'
            )

        if view.is_loading():
            logger.warning(
                'file is still loading, supplying empty contents for: %s',
                file_path,
            )
            file_contents = ''
            file_types = None
        else:
            file_region = sublime.Region(0, view.size())
            file_contents = view.substr(file_region)
            file_types = get_file_types(view)

        file_selections = view.sel()    # type: sublime.Selection
        if not file_selections:
            logger.warning(
                'no selections available, '
                'using default line and column numbers'
            )
            line_num = 1
            column_num = 1
        else:
            # arbitrarily use the first selection as the position
            file_region = file_selections[0]    # type: sublime.Region
            file_point = file_region.begin()
            file_row, file_col = view.rowcol(file_point)
            logger.debug('found file line, col: %s, %s', file_row, file_col)

            # ycmd expects 1-based indices, and sublime returns 0-based
            line_num = file_row + 1
            column_num = file_col + 1

        return RequestParameters(
            file_path=file_path,
            file_contents=file_contents,
            file_types=file_types,
            line_num=line_num,
            column_num=column_num,
        )

    @property
    def view(self):
        if not self._view:
            logger.warning('no view handle has been set')
        return self._view

    @view.setter
    def view(self, view):
        if not isinstance(view, sublime.View):
            logger.warning('view is not sublime.View: %r', view)
        self._view = view

    @property
    def path(self):
        if self._cache is None:
            self._cache = {}
        return self._cache.get('path', None)

    @property
    def file_types(self):
        if self._cache is None:
            self._cache = {}
        return self._cache.get('file_types', None)

    # helpers for using views in other collections
    def __eq__(self, other):
        if other is None:
            # corner-case: allow comparison if view handle is none
            if not self._view:
                return True

        if isinstance(other, sublime.View):
            other_id = other.id()
        elif isinstance(other, View):
            other_id = other._view.id()
        else:
            raise TypeError('view must be a View: %r' % (other))

        if not self._view:
            return False

        self_id = self._view.id()
        return self_id == other_id

    def __hash__(self):
        if not self._view:
            logger.error('no view handle has been set')
            raise TypeError
        return hash(self._view.id())

    # pass-through to underlying cache
    # this allows callers to store arbirary view-specific information, like
    # whether or not the buffer has been sent to a ycmd server
    def __getitem__(self, key):
        if self._cache is None:
            self._cache = {}
        return self._cache[key]

    def __setitem__(self, key, value):
        if self._cache is None:
            self._cache = {}
        self._cache[key] = value

    def __delitem__(self, key):
        if self._cache is None:
            self._cache = {}
        del self._cache[key]

    def __contains__(self, key):
        if self._cache is None:
            self._cache = {}
        return key in self._cache

    # pass-through to `sublime.View` methods:

    def id(self):
        if not self._view:
            logger.error('no view handle has been set')
            return None
        return self._view.id()

    def size(self):
        if not self._view:
            logger.error('no view handle has been set')
            return None
        return self._view.size()

    def window(self):
        if not self._view:
            logger.error('no view handle has been set')
            return None
        return self._view.window()

    def scope_name(self, point):
        if not self._view:
            logger.error('no view handle has been set')
            return None
        return self._view.scope_name(point)


def get_view_id(view):
    '''
    Returns the id of a given `view`.

    If the view is already a number, it is returned as-is. It is assumed to be
    the view id already.

    If the view is a `sublime.View` or `View`, the `view.id()` method is called
    to get the id.
    '''
    if isinstance(view, int):
        # already a view ID, so return it as-is
        return view

    assert isinstance(view, (sublime.View, View)), \
        'view must be a View: %r' % (view)

    # duck type, both support the method:
    return view.id()


def _get_path_from_window(window):
    if window is None:
        logger.debug('no window data available, cannot determine project path')
        return None
    assert isinstance(window, sublime.Window)

    logger.debug('extracting project path from window: %s', window)

    project_data = window.project_data()
    if project_data is None:
        logger.debug('no folders in window, cannot determine project path')
        return None
    assert isinstance(project_data, dict)

    # a window with open folders will always have project data available
    # if a project file is loaded, the project data may include relative paths
    # in that case, we also need the project file path to resolve it
    project_file_path = window.project_file_name()
    project_file_directory = None

    if project_file_path is None:
        logger.debug('no project file loaded in that window')
    else:
        logger.debug(
            'found project file, resolving paths relative to it: %s',
            project_file_path,
        )
        project_file_directory = get_directory_name(project_file_path)

    folders = project_data.get('folders', [])
    folder_paths = [
        resolve_abspath(
            folder.get('path'), start=project_file_directory,
        ) for folder in folders
        if isinstance(folder, dict) and 'path' in folder
    ]

    if not folder_paths:
        logger.warning(
            'failed to extract folder paths from folders: %s', folders
        )
        return None

    logger.debug('found directory paths: %s', folder_paths)
    folder_common_ancestor = get_common_ancestor(folder_paths)

    if folder_common_ancestor is None:
        logger.debug('could not determine root directory from directories...')
    else:
        logger.debug(
            'calculated common folder ancestor: %s', folder_common_ancestor
        )

    return folder_common_ancestor


def _get_path_from_view(view):
    if view is None:
        logger.debug('no view provided, cannot determine file path')
        return None
    assert isinstance(view, sublime.View)

    logger.debug('extracting file path from view: %s', view)

    file_name = view.file_name()
    if file_name is None:
        logger.debug('no file name in view, cannot determine directory name')
        return None
    assert isinstance(file_name, str)

    file_directory = get_directory_name(file_name)
    logger.debug('extracted directory path: %s', file_directory)

    return file_directory


def get_path_for_view(view):
    '''
    Attempts to calculate the project directory for a given `view`.
    First, the containing window is inspected. If an active project is loaded,
    then the project path will be returned. Otherwise, if folders are open,
    the highest-level/root directory is returned.
    Second, the view's file name is inspected. If available, the directory
    component is returned.
    Finally, if the path cannot be determined by either of the two strategies
    above, then this will just return `None`.
    '''
    assert isinstance(view, (sublime.View, View)), \
        'view must be a View: %r' % (view)

    if isinstance(view, View):
        cached_path = view.path
        if cached_path is not None:
            return cached_path
        # no pre-calculated value, grab the underlying view to calculate it
        view = view.view

    logger.debug('calculating project directory for view: %s', view)
    window = view.window()

    path_from_window = _get_path_from_window(window)
    if path_from_window is not None:
        logger.debug('found project directory from active project/folders')

    path_from_view = _get_path_from_view(view)
    if path_from_view is not None:
        logger.debug('found directory for file from view')

    # use the two paths (one from window, one from view) as follows:
    #   1 - both are None
    #       cannot determine, so return None
    #   2 - window path is None, view path is not None
    #       return view path as-is
    #   3 - window path is not None, view path is None
    #       return window path as-is
    #   4 - both are not None
    #       take common ancestor directory of the two
    #       it's likely that the view path is a descendent of the window path
    #       if not, that's fine, the common ancestor will take care of that
    if path_from_window is None and path_from_view is None:
        logger.debug('could not determine directory from window or view')
        return None

    if path_from_window is not None and path_from_view is not None:
        logger.debug('returning common ancestor of window and view paths')
        path_common_ancestor = get_common_ancestor([
            path_from_window, path_from_view,
        ])
        if path_common_ancestor:
            return path_common_ancestor
        # otherwise, prefer to use the view's directory
        return path_from_view

    if path_from_window is not None:
        logger.debug('no path from view, so using path from window as-is')
        return path_from_window

    if path_from_view is not None:
        logger.debug('no path from window, so using path from view as-is')
        return path_from_view

    assert False, \
        'unhandled case, path from window, view: %r, %r' % \
        (path_from_window, path_from_view)
    return None


def get_file_types(view, scope_position=0):
    '''
    Returns a list of file types extracted from the scope names in a given
    `view`. The scope is extracted from `scope_position`, which defaults to the
    first character in the view.
    All scopes that start with 'source' will be extracted, after removing the
    'source.' prefix. For example, if 'source.python' is found, then 'python'
    will appear in the result. If no 'source' scopes are found, an empty list
    is returned.
    '''
    assert isinstance(view, (sublime.View, View)), \
        'view must be a View: %r' % (view)
    assert isinstance(scope_position, int), \
        'scope position must be an int: %r' % (scope_position)

    if isinstance(view, View):
        if scope_position == 0:
            cached_file_types = view.file_types
            if cached_file_types is not None:
                return cached_file_types
        # no pre-calculated value, grab the underlying view to calculate it
        view = view.view

    view_size = view.size()
    if scope_position == 0 and view_size == 0:
        # corner-case: view is empty
        logger.debug('empty view, no file types')
        return []
    assert \
        scope_position >= 0 and scope_position < view_size, \
        'scope position must be an int(0, %d): %r' % \
        (view_size, scope_position)

    scope_names = view.scope_name(scope_position).split()   # type: list

    SOURCE_PREFIX = 'source.'
    source_scope_names = list(filter(
        lambda s: s.startswith(SOURCE_PREFIX), scope_names
    ))

    source_names = list(map(
        lambda s: s[len(SOURCE_PREFIX):], source_scope_names
    ))

    # TODO : Use `Settings` to get the scope mapping dynamically.
    source_types = list(map(
        lambda s: SUBLIME_DEFAULT_LANGUAGE_SCOPE_MAPPING.get(s, s),
        source_names
    ))
    logger.debug(
        'extracted source scope names: %s -> %s -> %s',
        source_scope_names, source_names, source_types,
    )

    return source_types
