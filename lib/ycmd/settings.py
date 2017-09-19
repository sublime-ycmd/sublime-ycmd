#!/usr/bin/env python3

'''
lib/ycmd/settings.py
Utility functions for ycmd settings.
'''

import logging
import os

from lib.util.format import base64_encode
from lib.util.fs import (
    is_directory,
    is_file,
    load_json_file,
)
from lib.util.str import bytes_to_str

logger = logging.getLogger('sublime-ycmd.' + __name__)


def get_default_settings_path(ycmd_root_directory):
    '''
    Generates the path to the default settings json file from the ycmd module.
    The `ycmd_root_directory` should refer to the path to the repository.
    '''
    if not is_directory(ycmd_root_directory):
        logger.warning('invalid ycmd root directory: %s', ycmd_root_directory)
        # but whatever, fall through and provide the expected path anyway

    return os.path.join(ycmd_root_directory, 'ycmd', 'default_settings.json')


def generate_settings_data(ycmd_settings_path, hmac_secret):
    '''
    Generates and returns a settings `dict` containing the options for
    starting a ycmd server. This settings object should be written to a json
    file and supplied as a command-line argument to the ycmd module.
    The `hmac_secret` argument should be the binary-encoded HMAC secret. It
    will be base64-encoded before adding it to the settings object.
    '''
    assert isinstance(ycmd_settings_path, str), \
        'ycmd settings path must be a str: %r' % (ycmd_settings_path)
    if not is_file(ycmd_settings_path):
        logger.warning(
            'ycmd settings path appears to be invalid: %r', ycmd_settings_path
        )

    ycmd_settings = load_json_file(ycmd_settings_path)
    logger.debug('loaded ycmd settings: %s', ycmd_settings)

    assert isinstance(ycmd_settings, dict), \
        'ycmd settings should be valid json: %r' % (ycmd_settings)

    # WHITELIST
    # Enable for everything. This plugin will decide when to send requests.
    if 'filetype_whitelist' not in ycmd_settings:
        logger.warning(
            'ycmd settings template is missing the '
            'filetype_whitelist placeholder'
        )
    ycmd_settings['filetype_whitelist'] = {}
    ycmd_settings['filetype_whitelist']['*'] = 1

    # BLACKLIST
    # Disable for nothing. This plugin will decide what to ignore.
    if 'filetype_blacklist' not in ycmd_settings:
        logger.warning(
            'ycmd settings template is missing the '
            'filetype_blacklist placeholder'
        )
    ycmd_settings['filetype_blacklist'] = {}

    # HMAC
    # Pass in the hmac parameter. It needs to be base-64 encoded first.
    if 'hmac_secret' not in ycmd_settings:
        logger.warning(
            'ycmd settings template is missing the hmac_secret placeholder'
        )

    if not isinstance(hmac_secret, bytes):
        logger.warning(
            'hmac secret was not passed in as binary, it might be incorrect'
        )
    else:
        logger.debug('converting hmac secret to base64')
        hmac_secret_binary = hmac_secret
        hmac_secret_encoded = base64_encode(hmac_secret_binary)
        hmac_secret_str = bytes_to_str(hmac_secret_encoded)
        hmac_secret = hmac_secret_str

    ycmd_settings['hmac_secret'] = hmac_secret

    # MISC
    # Settings to ensure that the ycmd server is enabled whenever possible.
    ycmd_settings['min_num_of_chars_for_completion'] = 0
    ycmd_settings['min_num_identifier_candidate_chars'] = 0
    ycmd_settings['collect_identifiers_from_comments_and_strings'] = 1
    ycmd_settings['complete_in_comments'] = 1
    ycmd_settings['complete_in_strings'] = 1

    return ycmd_settings
