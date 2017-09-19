#!/usr/bin/env python3

'''
lib/util/hmac.py
Contains HMAC utility functions. The ycmd server expects an HMAC header with
all requests to verify the client's identity. The ycmd server also includes an
HMAC header in all responses to allow the client to verify the responses.
'''

import hashlib
import hmac
import logging
import os

from lib.util.str import (
    bytes_to_str,
    str_to_bytes,
)
from lib.util.format import (
    base64_encode,
)

logger = logging.getLogger('sublime-ycmd.' + __name__)


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
