#!/usr/bin/env python3

'''
lib/st.py
High-level helpers for working with the sublime module.
'''

import logging

from lib.fs import (
    get_directory_name,
    resolve_abspath,
    get_common_ancestor,
    resolve_binary_path,
    default_python_binary_path,
)
from lib.ycmd import (
    get_ycmd_default_settings_path,
)

try:
    import sublime          # noqa
    import sublime_plugin   # noqa
    _HAS_LOADED_ST = True
except ImportError:
    import collections
    _HAS_LOADED_ST = False

    class SublimeDummyBase(object):
        pass
    SublimeDummy = collections.namedtuple('SublimeDummy', {
        'Settings',
        'View',
    })
    SublimePluginDummy = collections.namedtuple('SublimePluginDummy', [
        'EventListener',
        'TextCommand',
    ])

    sublime = SublimeDummy(
        SublimeDummyBase,
        SublimeDummyBase,
    )
    sublime_plugin = SublimePluginDummy(
        SublimeDummyBase,
        SublimeDummyBase,
    )
finally:
    assert isinstance(_HAS_LOADED_ST, bool)

logger = logging.getLogger('sublime-ycmd.' + __name__)

# EXPORT
SublimeEventListener = sublime_plugin.EventListener
SublimeTextCommand = sublime_plugin.TextCommand

DEFAULT_SUBLIME_SETTINGS_FILENAME = 'sublime-ycmd.sublime-settings'
DEFAULT_SUBLIME_SETTINGS_KEYS = [
    'ycmd_root_directory',
    'ycmd_default_settings_path',
    'ycmd_python_binary_path',
    'ycmd_language_whitelist',
    'ycmd_language_blacklist',
]
YCMD_SERVER_SETTINGS_KEYS = [
    'ycmd_root_directory',
    'ycmd_default_settings_path',
    'ycmd_python_binary_path',
]

# Mapping from sublime scope names to the corresponding syntax name. This is
# required for ycmd, as it does not do the mapping itself, and will instead
# complain when it is not understood.
# TODO : Move this language mapping into the settings file, so the user can
#        configure it if required.
YCMD_SCOPE_MAPPING = {
    'js': 'javascript',
    'c++': 'cpp',
}


class SYsettings(object):
    '''
    Wrapper class that exposes the loaded settings as attributes.
    This is meant to abstract the setting key names, so there aren't as many
    hard-coded strings in the main plugin logic.
    '''

    def __init__(self, settings=None):
        self._ycmd_root_directory = None
        self._ycmd_default_settings_path = None
        self._ycmd_python_binary_path = None
        self._ycmd_language_whitelist = None
        self._ycmd_language_blacklist = None

        if settings is not None:
            self.parse(settings)

    def parse(self, settings):
        '''
        Assigns the contents of `settings` to the internal instance variables.
        The settings may be provided as a `dict` or as a `sublime.Settings`
        instance.
        TODO : note the setting keys, note that all variables are reset
        '''
        assert isinstance(settings, (sublime.Settings, dict))

        # this logic relies on both instance types having a `get` method
        self._ycmd_root_directory = settings.get('ycmd_root_directory', None)
        self._ycmd_default_settings_path = \
            settings.get('ycmd_default_settings_path', None)
        self._ycmd_python_binary_path = \
            settings.get('ycmd_python_binary_path', None)
        self._ycmd_language_whitelist = \
            settings.get('ycmd_language_whitelist', None)
        self._ycmd_language_blacklist = \
            settings.get('ycmd_language_blacklist', None)

        self._normalize()

    def _normalize(self):
        '''
        Calculates and updates any values that haven't been set after parsing
        settings provided to the `parse` method.
        This will calculate things like the default settings path based on the
        ycmd root directory, or the python binary based on the system PATH.
        '''
        if not self._ycmd_default_settings_path:
            ycmd_root_directory = self._ycmd_root_directory
            if ycmd_root_directory:
                ycmd_default_settings_path = \
                    get_ycmd_default_settings_path(ycmd_root_directory)
                logger.debug(
                    'calculated default settings path from '
                    'ycmd root directory: %s', ycmd_default_settings_path
                )
                self._ycmd_default_settings_path = ycmd_default_settings_path

        if not self._ycmd_python_binary_path:
            self._ycmd_python_binary_path = default_python_binary_path()
        ycmd_python_binary_path = self._ycmd_python_binary_path

        resolved_python_binary_path = \
            resolve_binary_path(ycmd_python_binary_path)
        if resolved_python_binary_path:
            if resolved_python_binary_path != ycmd_python_binary_path:
                logger.debug(
                    'calculated %s binary path: %s',
                    ycmd_python_binary_path, resolved_python_binary_path,
                )
            self._ycmd_python_binary_path = resolved_python_binary_path
        else:
            logger.error(
                'failed to locate %s binary, '
                'might not be able to start ycmd servers',
                ycmd_python_binary_path
            )

        if self._ycmd_language_whitelist is None:
            logger.debug('using empty whitelist - enable for all scopes')
            self._ycmd_language_whitelist = []

        if self._ycmd_language_blacklist is None:
            logger.debug('using empty blacklist - disable for no scopes')
            self._ycmd_language_blacklist = []

    @property
    def ycmd_root_directory(self):
        '''
        Returns the path to the ycmd root directory.
        If set, this will be a string. If unset, this will be `None`.
        '''
        return self._ycmd_root_directory

    @property
    def ycmd_default_settings_path(self):
        '''
        Returns the path to the ycmd default settings file.
        If set, this will be a string. If unset, it is calculated based on the
        ycmd root directory. If that fails, this will be `None`.
        '''
        return self._ycmd_default_settings_path

    @property
    def ycmd_python_binary_path(self):
        '''
        Returns the path to the python executable used to start ycmd.
        If set, this will be a string. If unset, it is calculated based on the
        PATH environment variable. If that fails, this will be `None`.
        '''
        return self._ycmd_python_binary_path

    @property
    def ycmd_language_whitelist(self):
        '''
        Returns the language/scope whitelist to perform completions on.
        This will be a list of strings, but may be empty.
        '''
        return self._ycmd_language_whitelist

    @property
    def ycmd_language_blacklist(self):
        '''
        Returns the language/scope blacklist to prevent completions on.
        This will be a list of strings, but may be empty.
        '''
        return self._ycmd_language_blacklist

    def as_dict(self):
        return {
            'ycmd_root_directory': self.ycmd_root_directory,
            'ycmd_default_settings_path': self.ycmd_default_settings_path,
            'ycmd_python_binary_path': self.ycmd_python_binary_path,
            'ycmd_language_whitelist': self.ycmd_language_whitelist,
            'ycmd_language_blacklist': self.ycmd_language_blacklist,
        }

    def __eq__(self, other):
        '''
        Returns true if the settings instance `other` has the same ycmd server
        configuration as this instance.
        Other settings, like language whitelist/blacklist, are not compared.
        If `other` is not an instance of `SYsettings`, this returns false.
        '''
        if not isinstance(other, SYsettings):
            return False

        for ycmd_server_settings_key in YCMD_SERVER_SETTINGS_KEYS:
            self_setting = getattr(self, ycmd_server_settings_key)
            other_setting = getattr(other, ycmd_server_settings_key)

            if self_setting != other_setting:
                return False

        return True

    def __str__(self):
        return str(self.as_dict())

    def __repr__(self):
        return '%s(%s)' % ('SYsettings', str(self.as_dict()))

    def __bool__(self):
        return not not self._ycmd_root_directory

    def __hash__(self):
        return hash((
            self.ycmd_root_directory,
            self.ycmd_default_settings_path,
            self.ycmd_python_binary_path,
        ))


class SYview(object):
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
        to a handler method on `SYserver`. These parameters include information
        about the file, and also the contents, and file type(s), if available.
        The result can be unpacked into a call to one of the server methods.
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

        return {
            'file_path': file_path,
            'file_contents': file_contents,
            'file_types': file_types,
            'line_num': line_num,
            'column_num': column_num,
        }

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
        elif isinstance(other, SYview):
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

    '''
    # pass-through to `sublime.View` attributes:
    def __getattr__(self, name):
        if not self._view:
            logger.error(
                'no view handle has been set, cannot get attribute: %s', name,
            )
            raise AttributeError
        return getattr(self._view, name)
    '''

    # pass-through to `sublime.View` methods:
    def id(self):
        if not self._view:
            logger.error('no view handle has been set')
            return None
        return self._view.id()

    '''
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
    '''


def load_known_settings(filename=DEFAULT_SUBLIME_SETTINGS_FILENAME):
    '''
    Fetches the resolved settings file `filename` from sublime, and parses
    it into a `SYsettings` instance. The file name should be the base name of
    the file (i.e. not the absolute/relative path to it).
    '''
    if not _HAS_LOADED_ST:
        logger.debug('debug mode, returning empty values')
        return SYsettings()

    logger.debug('loading settings from: %s', filename)
    settings = sublime.load_settings(filename)

    logger.debug('parsing/extracting settings')
    return SYsettings(settings=settings)


def bind_on_change_settings(callback,
                            filename=DEFAULT_SUBLIME_SETTINGS_FILENAME,
                            setting_keys=DEFAULT_SUBLIME_SETTINGS_KEYS):
    '''
    Binds `callback` to the on-change-settings event. The settings are loaded
    from `filename`, which should be the base name of the file (i.e. not the
    path to it). When loading, the settings are parsed into a `SYsettings`
    instance, and this instance is supplied as an argument to the callback.
    The keys in `setting_keys` are used to bind an event listener. Changes to
    settings that use these keys will trigger a reload.
    When called, this will automatically load the settings for the first time,
    and immediately invoke `callback` with the initial settings.
    '''
    if not _HAS_LOADED_ST:
        logger.debug('debug mode, will only trigger initial load event')
        initial_settings = SYsettings()
    else:
        logger.debug('loading settings from: %s', filename)
        settings = sublime.load_settings(filename)

        def generate_on_change_settings(key,
                                        callback=callback,
                                        settings=settings):
            def on_change_settings():
                logger.debug('settings changed, name: %s', key)
                extracted_settings = SYsettings(settings=settings)
                callback(extracted_settings)
            return on_change_settings

        logger.debug('binding on-change handlers for keys: %s', setting_keys)
        for setting_key in setting_keys:
            settings.clear_on_change(setting_key)
            settings.add_on_change(
                setting_key, generate_on_change_settings(setting_key)
            )

        logger.debug('loading initial settings')
        initial_settings = SYsettings(settings=settings)

    logger.debug(
        'triggering callback with initial settings: %s', initial_settings
    )
    callback(initial_settings)

    return initial_settings


def get_view_id(view):
    if isinstance(view, int):
        # already a view ID, so return it as-is
        return view

    assert isinstance(view, (sublime.View, SYview)), \
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
    assert isinstance(view, (sublime.View, SYview)), \
        'view must be a View: %r' % (view)

    if isinstance(view, SYview):
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
    assert isinstance(view, (sublime.View, SYview)), \
        'view must be a View: %r' % (view)
    assert isinstance(scope_position, int), \
        'scope position must be an int: %r' % (scope_position)

    if isinstance(view, SYview):
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

    source_types = list(map(
        lambda s: YCMD_SCOPE_MAPPING.get(s, s), source_names
    ))
    logger.debug(
        'extracted source scope names: %s -> %s -> %s',
        source_scope_names, source_names, source_types,
    )

    return source_types

# DEPRECATED:


def sublime_defer(callback, *args, **kwargs):
    '''
    Calls the supplied `callback` asynchronously, when running under sublime.
    In debug mode, the `callback` is executed immediately.
    '''
    def bound_callback():
        return callback(*args, **kwargs)

    if _HAS_LOADED_ST:
        sublime.set_timeout(bound_callback, 0)
    else:
        bound_callback()


def is_sublime_type(value, expected):
    '''
    Checks to see if a provided value is of the expected type. This wraps
    classes in the sublime module to allow noops when in debug mode.
    Returns True if it is as expected, and False otherwise. This also logs a
    warning when returning False.
    '''
    if not _HAS_LOADED_ST:
        # return True always - this is for debugging
        return True

    def try_get_module(cls):
        ''' Returns the class `__module__` attribute, if defined, or None. '''
        try:
            return cls.__module__
        except AttributeError:
            return None

    def try_get_name(cls):
        ''' Returns the class `__name__` attribute, if defined, or None. '''
        try:
            return cls.__name__
        except AttributeError:
            return None

    expected_from_module = try_get_module(expected)
    if expected_from_module not in ['sublime', 'sublime_plugin']:
        logger.warning(
            'invalid sublime type, expected "sublime" or "sublime_plugin", '
            'got: %r', expected_from_module,
        )

    if isinstance(value, expected):
        return True

    expected_classname = try_get_name(expected)

    if expected_from_module is not None and expected_classname is not None:
        expected_description = \
            '%s.%s' % (expected_from_module, expected_classname)
    elif expected_classname is not None:
        expected_description = expected_classname
    else:
        expected_description = '?'

    logger.warning(
        'value is not an instance of %s: %r', expected_description, value
    )
    return False
