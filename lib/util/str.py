#!/usr/bin/env python3

'''
lib/util/str.py
Contains string utility functions. This includes conversions between `str` and
`bytes`, and hash calculations.
'''

import logging

logger = logging.getLogger('sublime-ycmd.' + __name__)


def str_to_bytes(data):
    '''
    Converts `data` to `bytes`.

    If data is a `str`, it is encoded into `bytes`.
    If data is `bytes`, it is returned as-is.
    '''
    assert isinstance(data, (str, bytes)), \
        'data must be str or bytes: %r' % (data)
    if isinstance(data, bytes):
        # already bytes, yay
        return data
    return data.encode()


def bytes_to_str(data):
    '''
    Converts `data` to `str`.

    If data is a `bytes`, it is decoded into `str`.
    If data is `str`, it is returned as-is.
    '''
    assert isinstance(data, (str, bytes)), \
        'data must be str or bytes: %r' % (data)
    if isinstance(data, str):
        # already str, yay
        return data
    return data.decode()


def truncate(data, max_sz=16):
    '''
    Truncates the input `data` in a somewhat-intelligent way. The purpose of
    this function is to control the output size of logger statements when given
    really long strings.
    When `data` is a `str` or `bytes`, it is truncated to `max_sz` and the last
    3 characters are replaced with '.' (e.g. 'long string' -> 'long...').
    When `data` is a `list` or `dict`, each entry is truncated recursively. Any
    string values will be truncated as above. For dictionaries, keys will never
    get truncated, only their values.
    '''
    if data is None:
        return data

    def _truncate_str(data=data, max_sz=max_sz):
        assert isinstance(data, (str, bytes)), \
            'data must be str or bytes: %r' % (data)
        assert isinstance(max_sz, int), \
            'max size must be an int: %r' % (max_sz)
        assert max_sz > 8, 'max size must be at least 8: %r' % (max_sz)

        data_sz = len(data)
        if data_sz <= max_sz:
            # already short enough
            return data

        if isinstance(data, str):
            ellip = '...'
        elif isinstance(data, bytes):
            ellip = b'...'
        else:
            ellip = None

        ellip_sz = len(ellip) if ellip else 0
        remaining_sz = max_sz - ellip_sz
        assert remaining_sz > 0, \
            '[internal] remaining size is not positive: %r' % (remaining_sz)

        truncated = data[:remaining_sz]
        if ellip:
            truncated += ellip

        return truncated

    def _truncate_collection(data=data, max_sz=max_sz):
        assert hasattr(data, '__iter__'), \
            'data must be list or dict: %r' % (data)
        # don't actually care about max size here, so no need to type check it

        if hasattr(data, 'items') and callable(data.items):
            collection_iter = data.items()
            result = {}

            def add_result(k, v):
                result[k] = v
        else:
            collection_iter = enumerate(data)
            result = []

            def add_result(_, v):
                result.append(v)

        for k, v in collection_iter:
            truncated = truncate(data=v, max_sz=max_sz)
            add_result(k, truncated)

        return result

    if isinstance(data, (str, bytes)):
        return _truncate_str(data=data, max_sz=max_sz)
    elif hasattr(data, '__iter__'):
        return _truncate_collection(data=data, max_sz=max_sz)

    try:
        data_str = str(data)
    except ValueError:
        # don't know... return data as-is
        return data

    return _truncate_str(data=data_str, max_sz=max_sz)


def remove_prefix(data, prefix):
    '''
    Returns a copy of `data` with the leading `prefix` removed.

    The data should be either `bytes` or `str`, with a matching prefix type.

    If the prefix is not in the data, the data is returned as-is.
    '''
    if not isinstance(data, (bytes, str)):
        raise TypeError('data must be bytes or str: %r' % (data))
    if not isinstance(prefix, (bytes, str)):
        raise TypeError('prefix must be bytes or str: %r' % (prefix))

    # don't check that the types match - let the builtins complain
    if data.startswith(prefix):
        sz = len(prefix)
        return data[sz:]

    # else, return an explicit copy
    return data[:]
