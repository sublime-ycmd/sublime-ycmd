#!/usr/bin/env python3

'''
lib/util/format.py
Data formatting functions. Includes base64 encode/decode functions as well as
json parse/serialize functions.
'''

import base64
import json
import logging

from lib.util.str import (
    bytes_to_str,
    str_to_bytes,
)

logger = logging.getLogger('sublime-ycmd.' + __name__)


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


def base64_decode(data):
    '''
    Decodes the given `data` from base-64. The result will either be a `str`,
    or `bytes`, depending on the input type (same as input type).
    '''
    assert isinstance(data, (str, bytes)), \
        'data must be str or bytes: %r' % (data)

    is_str = isinstance(data, str)
    if is_str:
        data = str_to_bytes(data)

    decoded = base64.b64decode(data)

    if is_str:
        decoded = bytes_to_str(decoded)

    return decoded


def json_serialize(data):
    ''' Serializes `data` from a `dict` to a json `str`. '''
    assert isinstance(data, dict), 'data must be a dict: %r' % (data)
    serialized = json.dumps(data)
    return serialized


def json_parse(data):
    ''' Parses `data` from a json `str` a `dict`. '''
    assert isinstance(data, (str, bytes)), \
        'data must be str or bytes: %r' % (data)
    if isinstance(data, bytes):
        data = bytes_to_str(data)

    parsed = json.loads(data)
    return parsed
