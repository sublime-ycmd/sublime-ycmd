#!/usr/bin/env python3

'''
lib/subl/errors.py

Custom exception classes and error codes.
These errors represent environment/configuration issues to be resolved by the
user and/or client.
'''


class PluginError(Exception):
    '''
    Base class for all plugin errors.
    Specialized plugin errors derive from this.
    '''

    def __init__(self, msg):
        super(PluginError, self).__init__(msg)

    def desc(self):
        '''
        Generic description for error type.

        This is a broad description based on the class/sub-type. To be used
        along side the message.
        '''
        return 'Plugin error'

    def __str__(self):
        return self._msg

    def __repr__(self):
        return '%s(%r)' % ('PluginError', self._msg)


class SettingsError(PluginError):
    '''
    Settings-related error class.
    Represents an issue with the plugin settings/configuration.
    '''
    MISSING = 'missing configuration'
    TYPE = 'type mismatch'

    def __init__(self, msg, type=None, key=None, value=None):
        super(SettingsError, self).__init__(msg)
        self._type = type
        self._msg = msg
        self._key = key
        self._value = value

    def desc(self):
        if self._type == SettingsError.MISSING:
            desc_prefix = 'Missing value'
        elif self._type == SettingsError.TYPE:
            desc_prefix = 'Type mismatch'
        else:
            desc_prefix = 'Settings error'

        desc = '%s for key "%s"' % (desc_prefix, self._key)
        return desc

    def __repr__(self):
        return '%s(%r)' % ('SettingsError', {
            'type': self._type,
            'msg': self._msg,
            'key': self._key,
            'value': self._value,
        })
