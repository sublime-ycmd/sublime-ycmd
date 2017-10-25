#!/usr/bin/env python3

'''
lib/schema/completions.py
Schema definition for responses from completion requests.

TODO : Rename these. The naming scheme makes no sense.
'''

import logging

from lib.schema.request import RequestParameters
from lib.util.format import json_parse

logger = logging.getLogger('sublime-ycmd.' + __name__)


class CompletionResponse(object):
    '''
    Wrapper around the json response received from ycmd completions.
    Contains both the completions and the diagnostics.
    '''

    def __init__(self, completions=None, diagnostics=None):
        self._completions = completions
        self._diagnostics = diagnostics

    @property
    def completions(self):
        return self._completions

    @property
    def diagnostics(self):
        return self._diagnostics

    def __repr__(self):
        return '%s({%r})' % ('CompletionResponse', {
            'completions': self._completions,
            'diagnostics': self._diagnostics,
        })


class Completions(object):
    '''
    Wrapper around the json response received from ycmd completions.
    Contains top-level metadata like where the completion was requested, and
    what prefix was matched by ycmd. This class also acts as a collection for
    individual `CompletionOption` instances, which act as the possible
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


class Diagnostics(object):
    '''
    Wrapper around the diagnostics/errors received from ycmd completions.

    This class also contains diagnostics and/or errors that are included in the
    response of a completion request. These will indicate potential issues in
    ycmd (e.g. no flags available for clang completion), or potential issues in
    the code itself (e.g. warnings, syntax issues).

    TODO : Type checking.
    TODO : Classes for the diagnostics and errors.
    '''

    def __init__(self, diagnostics=None):
        self._diagnostics = diagnostics

    def __str__(self):
        if not self._diagnostics:
            return '[]'
        return '[ %s ]' % (
            ', '.join('%s' % (str(c)) for c in self._diagnostics)
        )

    def __repr__(self):
        if not self._diagnostics:
            return '[]'
        return '[ %s ]' % (
            ', '.join('%r' % (c) for c in self._diagnostics)
        )


class CompletionOption(object):
    '''
    Wrapper around individual json entries received from ycmd completions.
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

        menu_info = self._menu_info
        shortdesc = _shortdesc_common(menu_info)

        if shortdesc is not None:
            return shortdesc

        # else, try to get a syntax-specific description

        # TODO : Derministic language-based shortdesc.
        #        Currently, this uses a `dict` to iterate through the handlers,
        #        which has arbitrary order.
        shortdesc_handlers = {
            'python': _shortdesc_python,
            'javascript': _shortdesc_javascript,
        }

        for file_type, shortdesc_handler in shortdesc_handlers.items():
            if self._has_file_type(file_type):
                shortdesc = shortdesc_handler(menu_info)
                if shortdesc is not None:
                    return shortdesc

        # TODO : Log this once, or it'll be way too noisy.
        # logger.warning(
        #     'unknown completion option type, cannot generate '
        #     'description for option, menu info: %s, %r',
        #     self.text(), menu_info,
        # )

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
        return bool(self._insertion_text)

    def __str__(self):
        return self._insertion_text or '?'

    def __repr__(self):
        repr_params = {
            'menu_info': self._menu_info,
            'insertion_text': self._insertion_text,
        }
        if self._file_types:
            repr_params['file_types'] = self._file_types
        return '<CompletionOption %r>' % (repr_params)

    def _has_file_type(self, file_type):
        if self._file_types is None:
            logger.warning('completion option has no associated file types')
        if not self._file_types:
            return False
        assert isinstance(file_type, str), \
            '[internal] file type must be a str: %r' % (file_type)
        return file_type in self._file_types


class DiagnosticError(object):

    def __init__(self, exception_type=None, message=None, traceback=None,
                 file_types=None):
        self._exception_type = exception_type
        self._message = message
        self._traceback = traceback
        self._file_types = file_types

    def __repr__(self):
        repr_params = {
            'exception_type': self._exception_type,
            'message': self._message,
            'traceback': self._traceback,
        }
        if self._file_types:
            repr_params['file_types'] = self._file_types
        return '<DiagnosticError %r>' % (repr_params)


def _parse_json_response(json, ignore_errors=False):
    if not isinstance(json, (str, bytes, dict)):
        raise TypeError('json must be a str or dict: %r' % (json))

    if isinstance(json, (str, bytes)):
        logger.debug('parsing json string into a dict')
        parsed_json = json_parse(json)
    else:
        parsed_json = json.copy()

    assert isinstance(parsed_json, dict), \
        '[internal] parsed json is not a dict: %r' % (parsed_json)

    # TODO : Use a concrete class for type checking.
    def _is_error_list(errors):
        if not isinstance(errors, list):
            return False
        return all(map(
            lambda e: isinstance(e, dict), errors
        ))

    # TODO : Use a concrete class for type checking.
    def _is_completions(completions):
        if not isinstance(completions, list):
            return False
        return all(map(
            lambda c: isinstance(c, dict), completions
        ))

    if not ignore_errors:
        # check errors
        if 'errors' not in parsed_json or \
                not _is_error_list(parsed_json['errors']):
            raise ValueError('json is missing "errors" list')

    if 'completions' not in parsed_json or \
            not _is_completions(parsed_json['completions']):
        raise ValueError('json is missing "completions" list')

    return parsed_json


def _parse_completion_option(node, file_types=None):
    '''
    Parses a single item in the completions list at `node` into an
    `CompletionOption` instance.
    If `file_types` is provided, it should be a list of strings indicating the
    file types of the original source code. This will be used to post-process
    and normalize the ycmd descriptions depending on the syntax.
    '''
    assert isinstance(node, dict), \
        'completion node must be a dict: %r' % (node)
    assert file_types is None or \
        isinstance(file_types, (tuple, list)), \
        'file types must be a list: %r' % (file_types)

    menu_info = node.get('extra_menu_info', None)
    insertion_text = node.get('insertion_text', None)
    extra_data = node.get('extra_data', None)
    detailed_info = node.get('detailed_info', None)

    return CompletionOption(
        menu_info=menu_info, insertion_text=insertion_text,
        extra_data=extra_data, detailed_info=detailed_info,
        file_types=file_types,
    )


def parse_compoptions(json, request_parameters=None):
    '''
    Parses a `json` response from ycmd into an `Completions` instance.
    This expects a certain format in the input json, or it won't be able to
    properly build the completion options.
    If `request_parameters` is provided, it should be an instance of
    `RequestParameters`. It may be used to post-process the completion options
    depending on the syntax of the file. For example, this will attempt to
    normalize differences in the way ycmd displays functions.
    '''
    json = _parse_json_response(json, ignore_errors=True)
    if request_parameters is not None and \
            not isinstance(request_parameters, RequestParameters):
        raise TypeError(
            'request parameters must be RequestParameters: %r' %
            (request_parameters)
        )

    json_completions = json['completions']
    json_start_column = json['completion_start_column']

    file_types = request_parameters.file_types if request_parameters else None
    assert file_types is None or isinstance(file_types, (tuple, list)), \
        '[internal] file types is not a list: %r' % (file_types)

    completion_options = list(
        _parse_completion_option(o, file_types=file_types)
        for o in json_completions
    )
    # just assume it's an int
    start_column = json_start_column

    return Completions(
        completion_options=completion_options, start_column=start_column,
    )


def _parse_diagnostic(node, file_types=None):
    assert isinstance(node, dict), \
        'diagnostic node must be a dict: %r' % (node)
    assert file_types is None or \
        isinstance(file_types, (tuple, list)), \
        'file types must be a list: %r' % (file_types)

    message = node.get('message', None)
    exc = node.get('exception', None)
    exception_type = exc.get('TYPE') if exc else None
    traceback = node.get('traceback', None)

    if exception_type:
        return DiagnosticError(
            exception_type=exception_type,
            message=message, traceback=traceback,
        )

    raise NotImplementedError('unimplemented: diagnostic warnings')


def parse_diagnostics(json, request_parameters=None):
    '''
    Parses a `json` response from ycmd and extracts `Diagnostics` from it.
    Similar to `parse_completions`, the input json needs to be in a specific
    format, or the diagnostics will not be found.
    If no errors or diagnostics are in the response, this will return `None`.
    '''
    json = _parse_json_response(json, ignore_errors=False)
    if request_parameters is not None and \
            not isinstance(request_parameters, RequestParameters):
        raise TypeError(
            'request parameters must be RequestParameters: %r' %
            (request_parameters)
        )

    json_errors = json.get('errors', [])

    file_types = request_parameters.file_types if request_parameters else None
    assert file_types is None or isinstance(file_types, (tuple, list)), \
        '[internal] file types is not a list: %r' % (file_types)

    if not json_errors:
        logger.debug('no errors or diagnostics to report')
        return Diagnostics(diagnostics=None)

    diagnostics = list(
        _parse_diagnostic(m, file_types=file_types) for m in json_errors
    )

    return Diagnostics(diagnostics=diagnostics)


def parse_completions(json, request_parameters=None):
    '''
    Wrapper around `parse_compoptions` and `parse_diagnostics`. Uses both to
    generate and return a `CompletionResponse`.
    '''

    def _attempt_parse(parser, *args, **kwargs):
        try:
            return parser(*args, **kwargs)
        except ValueError as e:
            logger.warning('response has unexpected format: %r', e)
        except NotImplementedError as e:
            logger.warning('unhandled response format: %r', e)
        except Exception as e:
            logger.error('error while parsing response: %r', e)
        return None

    completions = _attempt_parse(parse_compoptions, json, request_parameters)
    diagnostics = _attempt_parse(parse_diagnostics, json, request_parameters)

    return CompletionResponse(
        completions=completions, diagnostics=diagnostics,
    )


'''
Syntax-specific utilities.

`shortdesc` : Returns a short description of a completion option type given the
    ycmd server's menu description of it. The format of this menu description
    is not consistent across languages, hence these specialized helpers.
    If the helper does not understand the menu info, it should return `None`.
'''     # pylint: disable=pointless-string-statement


SHORTDESC_UNKNOWN = '?'
SHORTDESC_KEYWORD = 'keywd'
SHORTDESC_IDENTIFIER = 'ident'
SHORTDESC_VARIABLE = 'var'
SHORTDESC_FUNCTION = 'fn'
SHORTDESC_DEFINITION = 'defn'
SHORTDESC_ATTRIBUTE = 'attr'
SHORTDESC_MODULE = 'mod'

SHORTDESC_TYPE_CLASS = 'class'
SHORTDESC_TYPE_STRING = 'str'
SHORTDESC_TYPE_NUMBER = 'num'


def _shortdesc_common(menu_info):
    '''
    Common/generic `shortdesc` function. This handles file-type agnostic menu
    info items, like identifiers.
    '''
    assert menu_info is None or isinstance(menu_info, str), \
        '[internal] menu info is not a str: %r' % (menu_info)

    if not menu_info:
        # weird, ycmd doesn't know...
        # return an explicit '?' to prevent other `shortdesc` calls
        return SHORTDESC_UNKNOWN

    if menu_info == '[ID]':
        return SHORTDESC_IDENTIFIER

    # else, unknown, let another `shortdesc` try to handle it
    return None


def _shortdesc_python(menu_info):
    ''' Python-specific `shortdesc` function. '''
    assert isinstance(menu_info, str), \
        '[internal] menu info is not a str: %r' % (menu_info)

    if ' = ' in menu_info or menu_info.startswith('instance'):
        # TODO : Not sure if this is 100% correct... Might not be attributes.
        return SHORTDESC_ATTRIBUTE

    if menu_info.startswith('keyword'):
        return SHORTDESC_KEYWORD

    if menu_info.startswith('def'):
        return SHORTDESC_FUNCTION

    if menu_info.startswith('module'):
        return SHORTDESC_MODULE

    if menu_info.startswith('class'):
        return SHORTDESC_TYPE_CLASS

    return None


def _shortdesc_javascript(menu_info):
    ''' JavaScript-specific `shortdesc` function. '''
    assert isinstance(menu_info, str), \
        '[internal] menu info is not a str: %r' % (menu_info)

    if menu_info == '?':
        return SHORTDESC_UNKNOWN

    if menu_info.startswith('fn'):
        return SHORTDESC_FUNCTION

    if menu_info == 'string':
        return SHORTDESC_TYPE_STRING
    if menu_info == 'number':
        return SHORTDESC_TYPE_NUMBER

    return None
