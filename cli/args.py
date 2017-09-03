#!/usr/bin/env python3

'''
cli/args.py
Utilities for handling command-line arguments.
'''

import argparse
import functools
import logging


def loglevel_str_to_enum(levelstr):
    '''
    Maps a log level, in string representation, to its corresponding severity
    enumeration defined in the logging module.
    The way it performs this mapping is rather arbitrary, but should be
    intuitive enough for parsing command-line arguments.
    If the string representation does not map to anything, this returns None.
    '''
    assert isinstance(levelstr, str), \
        '[internal] levelstr is not a str: %r' % levelstr

    # use a dict to perform the mapping - uses lower-case versions of levels
    ll_ste_map = {
        'debug': logging.DEBUG,
        'd': logging.DEBUG,
        'info': logging.INFO,
        'i': logging.INFO,
        'warn': logging.WARNING,
        'warning': logging.WARNING,
        'w': logging.WARNING,
        'error': logging.ERROR,
        'e': logging.ERROR,
        'critical': logging.CRITICAL,
        'c': logging.CRITICAL
    }

    levelstr_lower = levelstr.lower()

    if levelstr_lower in ll_ste_map:
        return ll_ste_map[levelstr_lower]

    return None


def base_cli_argparser(**kwargs):
    '''
    Generates and returns an argparse.ArgumentParser instance for use with
    parsing common command-line options. So far, this just includes logging
    flags, which are compatible with the logging.basicConfig. The returned
    instance may also be extended as required.
    Keyword-arguments are forwarded to the argparse.ArgumentParser constructor.
    '''
    parser = argparse.ArgumentParser(**kwargs)

    class SYparseLogLevelAction(argparse.Action):   \
            # pylint: disable=too-few-public-methods
        '''
        Helper that can be used as an argparse action. Parses a given log level
        either by name, abbreviation, or enumeration into its corresponding
        logging severity level.
        '''

        def __call__(self, parser, namespace, values, option_string=None):
            '''
            Uses a mapping from strings to enumerations to calculate the log
            level. Updates the parsed-argument namespace appropriately.
            '''
            assert hasattr(values, '__iter__'), \
                '[internal] argparse-provided parameter "values" is '\
                'not iterable: %r' % values

            # if multiple values are present, only the last one has an effect
            lastvalue = functools.reduce(lambda i, j: j, values, None)
            if lastvalue is None:
                # weird... nothing to do though
                return

            enum_from_str = loglevel_str_to_enum(lastvalue)
            if enum_from_str is None:
                # Try to parse it as a raw number too
                try:
                    enum_from_str = int(lastvalue)
                except ValueError:
                    enum_from_str = None

            if enum_from_str is None:
                parser.error(ValueError('Invalid log level: %s' % lastvalue))
                return

            # It was valid! Update the argument namespace appropriately
            setattr(namespace, self.dest, enum_from_str)

    logging_group = parser.add_argument_group(title='logging')
    logging_group\
        .add_argument('-d', '--log-level', nargs=1,
                      action=SYparseLogLevelAction,
                      help='enables log messages of a minimum severity level')
    logging_group\
        .add_argument('-f', '--log-file', type=argparse.FileType('w'),
                      help='writes log output to specified file')

    return parser
