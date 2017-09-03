#!/usr/bin/env python3

'''
lib/jsonmodels.py
Wrappers around the JSON messages passed between this plugin and ycmd. Provides
concrete classes with attributes to make it easier to work with the arbitrary
keys in the ycmd API.
'''

import logging

from lib.strutils import (
    parse_json,
)

logger = logging.getLogger('sublime-ycmd.' + __name__)


# TODO : Use this instead of the `dict` in `SYserver`.
class SYrequestParameters(object):
    '''
    Wrapper around JSON parameters used in ycmd requests.
    All requests need to have certain parameters for the server to even pass
    into a handler. These parameters are given default values if they are not
    filled in by the time it gets serialized to JSON. Setting parameters will
    also automatically validate that they are the right type.

    TODO :
    Certain handlers use additional parameters, e.g. event notifications
    require the event type as part of the request body. These parameters are
    checked when specifying the handler, and an error is raised if they are
    not provided.
    '''

    def __init__(self, handler=None):
        self._handler = handler
        self.clear()

    def clear(self):
        ''' Deletes all stored parameters, but retains the handler. '''
        self._file_path = None
        self._file_contents = None
        self._file_types = None
        self._line_num = None
        self._column_num = None

    @property
    def file_path(self):
        if not self._file_path:
            logger.warning('no file path set')
            return ''
        return self._file_path

    @file_path.setter
    def file_path(self, file_path):
        if not isinstance(file_path, str):
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
        if not isinstance(file_contents, str):
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
        if not isinstance(file_types, (tuple, list)):
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
        if not isinstance(line_num, int):
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
        if not isinstance(column_num, int):
            raise TypeError
        if column_num <= 0:
            raise ValueError
        self._column_num = column_num


class SYcompletions(object):
    '''
    Wrapper around the JSON response received from ycmd completions.
    Contains top-level metadata like where the completion was requested, and
    what prefix was matched by ycmd. This class also acts as a collection for
    individual `SYcompletionOption` instances, which act as the possible
    choices for finishing the current identifier.

    This class behaves like a list. The completion options are ordered by ycmd,
    and this class maintains that ordering.

    TODO : Type checking.
    '''

    def __init__(self, completion_options=None, start_column=None):
        self._completion_options = completion_options
        self._start_column = start_column

    def __len__(self):
        if self._completion_options is None:
            return 0
        return len(self._completion_options)

    def __getitem__(self, key):
        if self._completion_options is None:
            raise IndexError
        return self._completion_options[key]

    def __iter__(self):
        return iter(self._completion_options)

    def __str__(self):
        if not self._completion_options:
            return '[]'
        return '[ %s ]' % (
            ', '.join('%s' % (str(c)) for c in self._completion_options)
        )

    def __repr__(self):
        if not self._completion_options:
            return '[]'
        return '[ %s ]' % (
            ', '.join('%r' % (c) for c in self._completion_options)
        )


class SYcompletionOption(object):
    '''
    Wrapper around individual JSON entries received from ycmd completions.
    All completion options have metadata indicating what kind of symbol it is,
    and how they can be displayed. This base class is used to define the common
    attributes available in all completion options. Subclasses further include
    the metadata specific to each option type.

    TODO : Type checking.
    '''

    def __init__(self, menu_info=None, insertion_text=None,
                 extra_data=None, detailed_info=None, file_types=None):
        self._menu_info = menu_info
        self._insertion_text = insertion_text
        self._extra_data = extra_data
        self._detailed_info = detailed_info
        self._file_types = file_types

    def shortdesc(self):
        '''
        Returns a short description indicating what type of completion this
        option represents. The result will be a single word, suitable for
        display in the auto-complete list.
        '''
        if not self._menu_info:
            return 'null'

        if self._menu_info == '[ID]':
            return 'var'

        # TODO : This is way too noisy. Maybe just log it once?
        logger.warning(
            'unknown completion option type, '
            'cannot generate description: %r',
            self._menu_info,
        )

        return '?'

    def text(self):
        '''
        Returns the insertion text for this completion option. This is the text
        that should be written into the buffer when the user selects it.
        '''
        if not self._insertion_text:
            logger.error('completion option is not initialized')
            return ''
        return self._insertion_text

    def __bool__(self):
        return not not self._insertion_text

    def __str__(self):
        return self._insertion_text or '?'

    def __repr__(self):
        return '<SYcompletionOption {menu_info=%r, insertion_text=%r}>' % (
            self._menu_info, self._insertion_text,
        )


def _parse_completion_option(node, file_types=None):
    '''
    Parses a single item in the completions list at `node` into an
    `SYcompletionOption` instance.
    If `file_types` is provided, it should be a list of strings indicating the
    file types of the original source code. This will be used to post-process
    and normalize the ycmd descriptions depending on the syntax.
    '''
    assert isinstance(node, dict), \
        'completion node must be a dict: %r' % (node)
    assert file_types is None or \
        isinstance(file_types, (tuple, list)), \
        'file types must be a list: %r' % (file_types)

    menu_info = node['extra_menu_info']
    insertion_text = node['insertion_text']
    extra_data = node.get('extra_data', None)
    detailed_info = node.get('detailed_info', None)

    return SYcompletionOption(
        menu_info=menu_info, insertion_text=insertion_text,
        extra_data=extra_data, detailed_info=detailed_info,
        file_types=file_types,
    )


def parse_completion_options(json, request_parameters=None):
    '''
    Parses a `json` response from ycmd into an `SYcompletions` instance.
    This expects a certain format in the input JSON, or it won't be able to
    properly build the completion options.
    If `request_parameters` is provided, it should be an instance of
    `SYrequestParameters`. It may be used to post-process the completion
    options depending on the syntax of the file. For example, this will attempt
    to normalize differences in the way ycmd displays functions.
    '''
    assert isinstance(json, (str, bytes, dict)), \
        'json must be a dict: %r' % (json)
    assert request_parameters is None or \
        isinstance(request_parameters, SYrequestParameters), \
        'request parameters must be SYrequestParameters: %r' % \
        (request_parameters)

    if isinstance(json, (str, bytes)):
        logger.debug('parsing json string into a dict')
        json = parse_json(json)

    if 'errors' not in json or not isinstance(json['errors'], list):
        raise TypeError('json is missing "errors" list')

    def _is_completions(completions):
        if not isinstance(completions, list):
            return False
        return all(map(
            lambda c: isinstance(c, dict), completions
        ))

    if 'completions' not in json or not _is_completions(json['completions']):
        raise TypeError('json is missing "completions" list')

    # TODO : Type validation. The classes above should be doing the validation.
    json_errors = json['errors']
    json_completions = json['completions']
    json_start_column = json['completion_start_column']

    if json_errors:
        raise NotImplementedError('unimplemented: parse errors')

    if request_parameters:
        raise NotImplementedError('unimplemented: extract file types')
    file_types = None

    completion_options = list(map(
        lambda c: _parse_completion_option(c, file_types=file_types),
        json_completions
    ))
    # just assume it's an int
    start_column = json_start_column

    return SYcompletions(
        completion_options=completion_options, start_column=start_column,
    )
