#!/usr/bin/env python3

'''
lib/util/sys.py
Operating system utilities.
'''

import logging
import multiprocessing
import socket

logger = logging.getLogger('sublime-ycmd.' + __name__)


def get_cpu_count():
    ''' Returns the core count of the current system. '''
    try:
        return multiprocessing.cpu_count()
    except (AttributeError, NotImplementedError):
        return 1


def get_unused_port(interface='127.0.0.1'):
    ''' Finds an available port for a server process to listen on. '''
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((interface, 0))

    port = sock.getsockname()[1]
    logger.debug('found unused port: %d', port)

    sock.close()
    return port
