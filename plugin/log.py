#!/usr/bin/env python3

'''
plugin/log.py
Global logging helpers.
'''

import logging
import logging.config

from ..cli.args import log_level_str_to_enum
from ..lib.util.log import (
    get_smart_truncate_formatter,
    get_debug_formatter,
)

logger = logging.getLogger('sublime-ycmd.' + __name__)


def configure_logging(log_level=None, log_file=None):
    '''
    Configures the logging module (or plugin-specific root logger) to log at
    the given `log_level` and write log output to file `log_file`. Formatters,
    handlers, and filters are added to prettify the logging output.
    If `log_level` is not provided, logging output will be silenced. Otherwise,
    it should be one of the logging enums or a string (e.g. 'DEBUG').
    If `log_file` is not provided, this uses the default logging stream, which
    should be `sys.stderr`. Otherwise, it should be a string representing the
    file name to append log output to.
    '''
    if isinstance(log_level, str):
        log_level = log_level_str_to_enum(log_level)

    # avoid messing with the root logger
    # if running under sublime, that would affect all other plugins as well
    logger_instance = logging.getLogger('sublime-ycmd')
    if log_level is None:
        logger_instance.setLevel(logging.NOTSET)
    else:
        logger_instance.setLevel(log_level)

    # disable propagate so logging does not go above this module
    logger_instance.propagate = False

    # create the handler
    if log_level is None:
        logger_handler = logging.NullHandler()
    else:
        if isinstance(log_file, str):
            logger_handler = logging.FileHandler(filename=log_file)
        else:
            # assume it's a stream
            logger_handler = logging.StreamHandler(stream=log_file)

    def remove_handlers(logger=logger_instance):
        if logger.hasHandlers():
            handlers = list(h for h in logger.handlers)
            for handler in handlers:
                logger.removeHandler(handler)

    # remove existing handlers (in case the plugin is reloaded)
    remove_handlers(logger_instance)

    # create the formatter
    if log_file is None:
        logger_formatter = get_smart_truncate_formatter()
    else:
        # writing to a file, so don't bother pretty-printing
        logger_formatter = get_debug_formatter()

    # connect everything up
    logger_handler.setFormatter(logger_formatter)
    logger_instance.addHandler(logger_handler)
