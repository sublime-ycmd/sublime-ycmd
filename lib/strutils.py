#!/usr/bin/env python3

'''
lib/strutils.py
Contains string utility functions. This includes conversions between `str` and
`bytes`, and hash calculations.
'''

import base64
import hashlib
import hmac
import json
import logging
import os

logger = logging.getLogger('sublime-ycmd.' + __name__)


def str_to_bytes(data):
    assert isinstance(data, (str, bytes)), \
        'data must be str or bytes: %r' % (data)
    if isinstance(data, bytes):
        # already bytes, yay
        return data
    return data.encode()


def bytes_to_str(data):
    assert isinstance(data, (str, bytes)), \
        'data must be str or bytes: %r' % (data)
    if isinstance(data, str):
        # already str, yay
        return data
    return data.decode()


def base64_encode(data):
    '''
    Encodes the given `data` in base-64. The result will either be a `str`,
    or `bytes`, depending on the input type (same as input type).
    '''
    assert isinstance(data, (str, bytes)), \
        'data must be str or bytes: %r' % (data)

    is_str = isinstance(data, str)
    if is_str:
        data = str_to_bytes(data)

    encoded = base64.b64encode(data)

    if is_str:
        encoded = bytes_to_str(encoded)

    return encoded


def new_hmac_secret(num_bytes=32):
    ''' Generates and returns an HMAC secret in binary encoding. '''
    hmac_secret_binary = os.urandom(num_bytes)
    return hmac_secret_binary


def _calculate_hmac(hmac_secret, data, digestmod=hashlib.sha256):
    assert isinstance(hmac_secret, (str, bytes)), \
        'hmac secret must be str or bytes: %r' % (hmac_secret)
    assert isinstance(data, (str, bytes)), \
        'data must be str or bytes: %r' % (data)

    hmac_secret = str_to_bytes(hmac_secret)
    data = str_to_bytes(data)

    hmac_instance = hmac.new(hmac_secret, msg=data, digestmod=digestmod)
    hmac_digest_bytes = hmac_instance.digest()
    assert isinstance(hmac_digest_bytes, bytes), \
        '[internal] hmac digest should be bytes: %r' % (hmac_digest_bytes)

    return hmac_digest_bytes


def calculate_hmac(hmac_secret, *content, digestmod=hashlib.sha256):
    '''
    Calculates the HMAC for the given `content` using the `hmac_secret`.
    This is calculated by first generating the HMAC for each item in
    `content` separately, then concatenating them, and finally running another
    HMAC on the concatenated intermediate result. Finally, the result of that
    is base-64 encoded, so it is suitable for use in headers.
    '''
    assert isinstance(hmac_secret, (str, bytes)), \
        'hmac secret must be str or bytes: %r' % (hmac_secret)
    hmac_secret = str_to_bytes(hmac_secret)

    content_hmac_digests = map(
        lambda data: _calculate_hmac(
            hmac_secret, data=data, digestmod=digestmod,
        ), content,
    )

    concatenated_hmac_digests = b''.join(content_hmac_digests)

    hmac_digest_binary = _calculate_hmac(
        hmac_secret, data=concatenated_hmac_digests, digestmod=digestmod,
    )

    hmac_digest_bytes = base64_encode(hmac_digest_binary)
    hmac_digest_str = bytes_to_str(hmac_digest_bytes)

    return hmac_digest_str


def format_json(data):
    assert isinstance(data, dict), 'data must be a dict: %r' % (data)
    serialized = json.dumps(data)
    return serialized


def parse_json(data):
    assert isinstance(data, (str, bytes)), \
        'data must be str or bytes: %r' % (data)
    if isinstance(data, bytes):
        data = bytes_to_str(data)

    parsed = json.loads(data)
    return parsed


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

            def add_result(k, v):
                result.append(v)

        for k, v in collection_iter:
            tv = truncate(data=v, max_sz=max_sz)
            add_result(k, tv)

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
