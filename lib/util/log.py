#!/usr/bin/env python3

'''
lib/util/log.py
Contains additional logic to help improve logging output.

TODO : Add helper to use a logfile in this project's directory.
'''

import collections
import functools
import logging
import os
import re


# NOTE : ST provides module sources from 'python3.3.zip'
#  e.g.     '/opt/st/python3.3.zip/logging/__init.pyo'
#       However while running, `sys._getframe` inspects the actual source file:
#           './python3.3/logging/__init__.py'
#       Fix it up!
try:
    # pylint: disable=unused-import
    import sublime          # noqa
    import sublime_plugin   # noqa

    # TODO : See if the one-liner solution here works:
    # logging._srcfile = os.path.normcase(addLevelName.__code__.co_filename)

    if hasattr(logging, '_srcfile') and logging._srcfile:
        _python_zip_re = re.compile(
            r'(?P<version>python(\w+)?(\.\w+)*)\.zip'
            r'(?P<path>[/\\].*$)'
        )
        _python_zip_match = _python_zip_re.search(logging._srcfile)
        if _python_zip_match:
            _python_version = _python_zip_match.group('version')
            _python_relative_file_path = _python_zip_match.group('path')

            # fix it fix it fix it
            if os.sep == '\\':
                _python_relative_posix_path = \
                    _python_relative_file_path.replace(os.sep, '/')
            else:
                _python_relative_posix_path = _python_relative_file_path[:]

            _srcfile_relative_posix_path = \
                re.sub(r'\.py[oc]$', '.py', _python_relative_posix_path)

            _srcfile_posix_path = './%s%s' % (
                _python_version, _srcfile_relative_posix_path,
            )

            _srcfile_normalized_path = os.path.normcase(_srcfile_posix_path)

            # if this doesn't calculate the right value, uncomment to debug:
            # print(
            #     'fixing logging srcfile: %s -> %s' %
            #     (logging._srcfile, _srcfile_normalized_path)
            # )

            logging._srcfile = _srcfile_normalized_path
except ImportError:
    # all good... phew
    pass

logger = logging.getLogger('sublime-ycmd.' + __name__)

LEVELNAME_MAXLEN = 1
PATHNAME_MAXLEN = 12
LINENO_MAXLEN = 4
FUNCNAME_MAXLEN = 16


def get_default_datefmt():
    '''
    Returns a datetime format string for use in logging configuration.
    '''
    return '%Y/%m/%d %H:%M:%S'


def get_default_messagefmt():
    '''
    Returns a record format string for use in logging configuration.
    '''
    return \
        '[%%(asctime)s] %%(levelname)%ds %%(pathname)%ds:%%(lineno)-%dd ' \
        '%%(funcName)-%ds %%(message)s' % \
        (LEVELNAME_MAXLEN, PATHNAME_MAXLEN, LINENO_MAXLEN, FUNCNAME_MAXLEN)


def get_default_format_props():
    '''
    Returns a map from record attribute names to desired max smart-truncation
    length. This `dict` is suitable for use in `SmartTruncateFormatter`.
    '''
    return {
        'levelname': LEVELNAME_MAXLEN,
        'pathname': PATHNAME_MAXLEN,
        # doesn't make sense to truncate ints:
        # 'lineno': LINENO_MAXLEN,
        'funcName': FUNCNAME_MAXLEN,
    }


def get_smart_truncate_formatter(fmt=None, datefmt=None, props=None):
    '''
    Generates and returns a `SmartTruncateFormatter` with defaults.
    If any parameter is omitted, a default one is calculated using the
    `get_default_` helpers above.
    '''
    if fmt is None:
        fmt = get_default_messagefmt()
    if datefmt is None:
        datefmt = get_default_datefmt()
    if props is None:
        props = get_default_format_props()

    assert isinstance(fmt, str), 'fmt must be a str: %r' % (fmt)
    assert isinstance(datefmt, str), 'datefmt must be a str: %r' % (datefmt)
    # no need to validate `props`, that's done in the constructor

    formatter = SmartTruncateFormatter(
        fmt=fmt,
        datefmt=datefmt,
        props=props,
    )

    return formatter


# Used to strip common prefixes from script paths (namely, absolute paths)
_SY_LIB_DIR = os.path.dirname(os.path.abspath(__file__))


@functools.lru_cache()
def strip_common_path_prefix(basepath, relativeto=_SY_LIB_DIR):
    '''
    Strips the common prefix in a file path relative to the supplied path.
    By default, this uses the directory of this script to compare against.
    '''
    assert isinstance(basepath, str), \
        'basepath must be a string: %r' % basepath
    # Unfortunately, `os.path.commonpath` is only available in python 3.5+
    # To be compatible with 3.3, need to use commonprefix and then process it
    common_path_chars = os.path.commonprefix([basepath, relativeto])
    common_path_components = os.path.split(common_path_chars)
    # Don't use the last part (basename) - it is most likely garbage
    common_path_prefix_str = common_path_components[0]
    assert isinstance(common_path_prefix_str, str), \
        '[internal] common_path_prefix_str is not a string: %r' % \
        common_path_prefix_str
    assert basepath.startswith(common_path_prefix_str), \
        '[internal] basepath does not begin with common path prefix, ' \
        'calculation is incorrect: %r' % common_path_prefix_str
    # Since we know it starts with the prefix, just use a slice to get the rest
    common_path_prefix_len = len(common_path_prefix_str)
    tmp_stripped_prefix_path = basepath[common_path_prefix_len:]
    cleaned_stripped_prefix_path = \
        tmp_stripped_prefix_path.strip(os.path.sep + os.path.altsep)
    return cleaned_stripped_prefix_path


@functools.lru_cache()
def truncate_word_soft(word):
    '''
    Applies light truncation to a name component. So far, this just removes
    vowels (except first char). The result is probably not truncated by much.
    '''
    assert isinstance(word, str), \
        '[internal] word is not a string: %r' % word
    if not word:
        return word

    vowel_removal_re = '[aeiouAEIOU]'

    truncated_word = word[0] + re.sub(vowel_removal_re, '', word[1:])

    return truncated_word


@functools.lru_cache()
def truncate_word_hard(word):
    '''
    Applies aggressive truncation to a name component. So far, this just
    returns the first character of the supplied word. The result is very short.
    '''
    assert isinstance(word, str), \
        '[internal] word is not a string: %r' % word
    if word:
        return word[0]
    return word


@functools.lru_cache()
def delimit_name_components(basestr):
    '''
    Splits a string into a list of identifiers and separators.
    The original string can be reconstructed by joining the returned list.
    '''
    assert isinstance(basestr, str), \
        '[internal] basestr is not a string: %r' % basestr
    word_boundary_split_re = '([^a-zA-Z0-9])'

    split_components = re.split(word_boundary_split_re, basestr)

    return split_components


def smart_truncate(basestr, maxlen):
    '''
    Truncates a string while trying to maintain human-readability. The logic is
    quite limited. It can only truncate a few characters intelligently. If that
    still isn't enough, certain parts will be arbitrarily removed...
    '''
    assert isinstance(basestr, str), \
        'basestr must be a string: %r' % basestr
    assert isinstance(maxlen, int) and maxlen > 0, \
        'invalid maximum length: %r' % maxlen

    # If it looks like a path, strip away the common prefix
    if os.path.sep in basestr or os.path.altsep in basestr:
        # Yes, looks like a path
        basestr = strip_common_path_prefix(basestr)

    if len(basestr) <= maxlen:
        return basestr

    name_components = delimit_name_components(basestr)

    # Algorithm notes:
    # Loop through the name components, first applying soft truncation from
    # start to end. If, at any point, the length condition is satisfied, return
    # the reconstructed list. If, at the end, the length condition is not
    # satisfied, start again, applying hard truncation. Finally, if that
    # doesn't work, start dropping components altogether
    current_components = name_components[:]

    def get_current_length():
        ''' Returns the sum of the length of each component. '''
        return sum(map(len, current_components))

    def get_reconstructed():
        ''' Returns the string reconstructed from joining the components. '''
        return ''.join(current_components)

    def apply_truncate_until_satisfied(truncatefn):
        '''
        Applies the specified truncation function to the current working
        components until the length requirement is satisfied. Returns `True` if
        successful, and `False` if it was not enough. Either way, the current
        component state is updated after the application.
        '''
        for i, component in enumerate(current_components):
            truncated_component = truncatefn(component)
            current_components[i] = truncated_component
            if get_current_length() <= maxlen:
                return True
        return False

    if apply_truncate_until_satisfied(truncate_word_soft):
        return get_reconstructed()

    assert get_current_length() > maxlen, \
        '[internal] soft-truncate loop did not terminate properly, ' \
        'length condition already satisfied, currently at: %r' % \
        get_current_length()

    if apply_truncate_until_satisfied(truncate_word_hard):
        return get_reconstructed()

    assert get_current_length() > maxlen, \
        '[internal] hard-truncate loop did not terminate properly, ' \
        'length condition already satisfied, currently at: %r' % \
        get_current_length()

    # Well.... no choice but to remove components
    while current_components:
        del current_components[0]
        if current_components:
            # Also remove the non-word component following it
            del current_components[0]
        if get_current_length() <= maxlen:
            return get_reconstructed()

    assert False, \
        '[internal] failed to truncate, even after removing all components...'
    return ''


class SmartTruncateFormatter(logging.Formatter):
    '''
    Logging formatter that shortens property values to the target length
    indicated by the format-code length.
    '''

    def __init__(self, fmt=None, datefmt=None, style='%', props=None):
        super(SmartTruncateFormatter, self).__init__(
            fmt=fmt, datefmt=datefmt, style=style,
        )
        if props and not isinstance(props, dict):
            logger.error('invalid property map: %r', props)
            # fall through and use it anyway
        self._props = props if props is not None else {}
        self._debug = False

    def format(self, record):
        def format_record_entry(name, length):
            '''
            Formats the entry for `name` by truncating it to a maximum of
            `length` characters. Updates the `record` in place.
            '''
            if not isinstance(name, str):
                if self._debug:
                    logger.error('invalid formattable field: %r', name)
                return
            if not isinstance(length, int):
                if self._debug:
                    logger.error('invalid format field width: %r', length)
                return

            if not hasattr(record, name):
                # name not in it, so nothing to format
                return

            value = getattr(record, name)
            if not isinstance(value, str):
                # not a str, don't format it, it's hard to handle it right...
                if self._debug:
                    logger.warning(
                        'cannot format value for %s: %r', name, value
                    )
                return

            truncated = smart_truncate(value, length)
            if not truncated:
                if self._debug:
                    logger.warning(
                        'failed to truncate value, size: %s, %d',
                        value, length,
                    )
                return

            setattr(record, name, truncated)

        for k, v in self._props.items():
            format_record_entry(k, v)

        return super(SmartTruncateFormatter, self).format(record)

    def __getitem__(self, key):
        if not hasattr(self._props, '__getitem__'):
            logger.error('invalid props, cannot get item: %r', self._props)
        if not self._props:
            raise KeyError(key,)

        return self._props[key]

    def __setitem__(self, key, value):
        if not hasattr(self._props, '__setitem__'):
            logger.error('invalid props, cannot set item: %r', self._props)
        if not isinstance(value, int):
            logger.error('invalid length, should be int: %r', value)

        self._props[key] = value

    def __contains__(self, key):
        if not hasattr(self._props, '__contains__'):
            logger.error('invalid props, : %r', self._props)

    def __iter__(self):
        ''' Dictionary-compatible iterator. '''
        for key in self._props:
            value = self._props[key]

            yield (key, value)

    def __repr__(self):
        return '%s(%r)' % ('SmartTruncateFormatter', dict(self))


FormatField = collections.namedtuple('FormatField', [
    'name',
    'zero',
    'minus',
    'space',
    'plus',
    'width',
    'point',
    'conv',
])


def parse_fields(fmt, style='%', default=None):
    '''
    Parses and yields template fields in a format string.

    For %-style formatting, these look like: '%(foo)15s', where '15' refers to
    the field width for 'foo'.

    NOTE : This is a best-effort implementation. It might not work 100%.
    '''
    if style != '%':
        raise NotImplementedError(
            'unimplemented: field width for non %%-style formats' % ()
        )

    def _get_parser():
        '''
        Compiles and returns a regex parser for parsing fields.

        The regex matches something in the form: '%(foo) 15s'
          %       - prefix
          (name)  - named field (optional)
          0       - for numbers, left pad with 0, override space (optional)
          -       - left-pad, override 0 (optional)
          space   - whitespace before before positive numbers (optional)
          +       - for numbers, always include +/- sign (optional)
          number  - field width

        NOTE : Attribute names must match regex parameter names.
        '''

        field_pattern = ''.join((
            r'%',
            r'(?:\((?P<name>\w+)\))?',
            r'(?P<zero>0)?',
            r'(?P<minus>-)?',
            r'(?P<space>\s)?',
            r'(?P<plus>\+)?',
            r'(?P<width>\d+)?',
            r'(?P<point>(?:\.\d+))?',
            r'(?P<conv>[hlL]*[srxXeEfFdiou])',
        ))

        return re.compile(field_pattern)

    try:
        field_parser = _get_parser()
    except re.error as e:
        logger.error('field width parser is invalid: %r', e)
        return None

    def _match_to_field(match):
        return FormatField(**match.groupdict())

    return map(_match_to_field, field_parser.finditer(fmt))
