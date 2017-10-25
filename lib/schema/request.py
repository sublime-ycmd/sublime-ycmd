#!/usr/bin/env python3

'''
lib/schema/request.py
Schema definition for request parameters.

The request parameter class wraps the json parameters required in most ycmd
handlers. These parameters are required for the ycmd server to even consider
handling. Without them, an error response is sent during the validation stage.

Some handlers will end up ignoring these required parameters, which is slightly
annoying. In that case, this class is able to fill in default values if they
are not filled in by the time it gets serialized to json. Setting parameters
will also automatically validate that they are the correct type.

TODO : Add handler-specific checks, like additional required parameters.
Certain handlers use additional parameters, e.g. event notifications require
the event type as part of the request body. These parameters can also get
checked when specifying the target handler.
'''

import logging

logger = logging.getLogger('sublime-ycmd.' + __name__)


class RequestParameters(object):
    '''
    Wrapper around json parameters used in ycmd requests. Supports arbitrary
    extra parameters using a `dict`-like interface.
    '''

    def __init__(self, file_path=None, file_contents=None, file_types=None,
                 line_num=None, column_num=None, force_semantic=None):
        # copy-paste of reset:
        self._file_path = None
        self._file_contents = None
        self._file_types = None
        self._line_num = None
        self._column_num = None
        self._force_semantic = None
        self._extra_params = {}

        self.file_path = file_path
        self.file_contents = file_contents
        self.file_types = file_types
        self.line_num = line_num
        self.column_num = column_num
        self.force_semantic = force_semantic

    def reset(self):
        ''' Deletes all stored parameters. '''
        self._file_path = None
        self._file_contents = None
        self._file_types = None
        self._line_num = None
        self._column_num = None
        self._force_semantic = None
        self._extra_params = {}

    def to_json(self):
        '''
        Generates and returns a `dict` representing all stored parameters, for
        use in sending the request.
        This will additionally validate all parameters, and generate defaults
        for any missing ones.
        '''
        file_path = self.file_path
        file_contents = self.file_contents
        file_types = self.file_types
        line_num = self.line_num
        column_num = self.column_num
        extra_params = self._extra_params
        force_semantic = self._force_semantic

        # validate
        if not file_path:
            raise ValueError('no file path specified')
        if not isinstance(file_path, str):
            raise TypeError('file path must be a str: %r' % (file_path))

        if not file_contents:
            file_contents = ''
        if not isinstance(file_contents, str):
            raise TypeError(
                'file contents must be a str: %r' % (file_contents)
            )

        if file_types is None:
            file_types = []
        if not isinstance(file_types, (tuple, list)):
            raise TypeError('file types must be a list: %r' % (file_types))

        if line_num is None:
            line_num = 1
        if not isinstance(line_num, int):
            raise TypeError('line num must be an int: %r' % (line_num))

        if column_num is None:
            column_num = 1
        if not isinstance(column_num, int):
            raise TypeError('column num must be an int: %r' % (column_num))

        optional_params = {}
        if force_semantic is not None:
            if not isinstance(force_semantic, bool):
                raise TypeError(
                    'force-semantic must be a bool: %r' % (force_semantic)
                )

            optional_params['force_semantic'] = force_semantic

        if extra_params is None:
            extra_params = {}
        if not isinstance(extra_params, dict):
            raise TypeError(
                'extra parameters must be a dict: %r' % (extra_params)
            )

        json_params = {
            'filepath': file_path,
            'file_data': {
                file_path: {
                    'filetypes': file_types,
                    'contents': file_contents,
                },
            },

            'line_num': line_num,
            'column_num': column_num,
        }
        json_params.update(optional_params)
        json_params.update(extra_params)

        return json_params

    @property
    def file_path(self):
        if not self._file_path:
            logger.warning('no file path set')
            return ''
        return self._file_path

    @file_path.setter
    def file_path(self, file_path):
        if file_path is not None and not isinstance(file_path, str):
            raise TypeError
        self._file_path = file_path

    @property
    def file_contents(self):
        if not self._file_contents:
            logger.warning('no file contents set')
            return ''
        return self._file_contents

    @file_contents.setter
    def file_contents(self, file_contents):
        if file_contents is not None and not isinstance(file_contents, str):
            raise TypeError
        self._file_contents = file_contents

    @property
    def file_types(self):
        if not self._file_types:
            logger.warning('no file types set')
            return []
        return self._file_types

    @file_types.setter
    def file_types(self, file_types):
        if isinstance(file_types, str):
            file_types = [file_types]
        if file_types is not None and \
                not isinstance(file_types, (tuple, list)):
            raise TypeError
        # create a shallow copy
        self._file_types = list(file_types)

    @property
    def line_num(self):
        if not self._line_num:
            logger.warning('no line number set')
            return 1
        return self._line_num

    @line_num.setter
    def line_num(self, line_num):
        if line_num is not None and not isinstance(line_num, int):
            raise TypeError
        if line_num <= 0:
            raise ValueError
        self._line_num = line_num

    @property
    def column_num(self):
        if not self._column_num:
            logger.warning('no column number set')
            return 1
        return self._column_num

    @column_num.setter
    def column_num(self, column_num):
        if column_num is not None and not isinstance(column_num, int):
            raise TypeError
        if column_num <= 0:
            raise ValueError
        self._column_num = column_num

    @property
    def force_semantic(self):
        return self._force_semantic

    @force_semantic.setter
    def force_semantic(self, force_semantic):
        if force_semantic is not None and not isinstance(force_semantic, bool):
            raise TypeError
        self._force_semantic = force_semantic

    def __getitem__(self, key):
        ''' Retrieves `key` from the extra parameters. '''
        if self._extra_params is None:
            self._extra_params = {}
        return self._extra_params[key]

    def get(self, key, default=None):
        '''
        Retrieves `key` from the extra parameters. Returns `default` if unset.
        '''
        if self._extra_params is None:
            self._extra_params = {}
        return self._extra_params.get(key, default)

    def __setitem__(self, key, value):
        '''
        Sets `key` in the extra parameters. These parameters have higher
        priority than the file-based parameters, and may overwrite them if the
        same key is used.
        '''
        if self._extra_params is None:
            self._extra_params = {}
        self._extra_params[key] = value

    def __delitem__(self, key):
        ''' Clears the `key` extra parameter. '''
        if self._extra_params is None:
            return
        del self._extra_params[key]

    def __iter__(self):
        ''' Dictionary-compatible iterator. '''
        base_items = [
            ('file_path', self._file_path),
            ('file_contents', self._file_contents),
            ('file_types', self._file_types),
            ('line_num', self._line_num),
            ('column_num', self._column_num),
        ]
        if not self._extra_params:
            return iter(base_items)

        extra_items = self._extra_params.items()

        all_items = list(base_items) + list(extra_items)
        return iter(all_items)

    def __str__(self):
        return str(dict(self))

    def __repr__(self):
        return '%s(%r)' % ('RequestParameters', dict(self))
