#!/usr/bin/env python3

'''
lib/ycmd/constants.py
Constants for use in ycmd server configuration, including routes/handlers.

All constants have the prefix `YCMD_`. The user-configurable constants have a
default value with the prefix `YCMD_DEFAULT_`.

Most constants were taken from the ycmd example client:
https://github.com/Valloric/ycmd/blob/master/examples/example_client.py

The missing ones were taken from the ycmd handler logic:
https://github.com/Valloric/ycmd/blob/master/ycmd/handlers.py
'''

'''
Log output. Use temporary spools to buffer and parse any startup errors.

Not user configurable (users can specify stdout/stderr path instead).
'''
YCMD_LOG_SPOOL_OUTPUT = True
YCMD_LOG_SPOOL_SIZE = 2048

'''
HMAC header information.

Not user configurable (likely won't change).
'''     # pylint: disable=pointless-string-statement
YCMD_HMAC_HEADER = 'X-Ycm-Hmac'
YCMD_HMAC_SECRET_LENGTH = 16

'''
Server will automatically shut down when idle for `int` seconds. This can be
set fairly low if idle resource usage is an issue. The plugin is able to detect
when a server has shut down, and will create a new one if so.

Use `0` to disable the behaviour entirely. This is definitely not recommended.
If this plugin fails to shut it down, it will continue to run indefinitely...

User configurable.
'''
# YCMD_DEFAULT_SERVER_IDLE_SUICIDE_SECONDS = 30       # 30 secs
YCMD_DEFAULT_SERVER_IDLE_SUICIDE_SECONDS = 5 * 60   # 5 mins
# YCMD_DEFAULT_SERVER_IDLE_SUICIDE_SECONDS = 3 * 60 * 60  # 3 hrs

'''
Server will poll subservers every `int` seconds to check health. This allows
the server to transparently manage semantic completers (e.g. tern, jedi).

User configurable.
'''
YCMD_DEFAULT_SERVER_CHECK_INTERVAL_SECONDS = 5

'''
Server handlers/routes. The server has an HTTP+JSON api, so these correspond to
the top-level functions available to clients (i.e. this plugin).

Not user configurable (likely won't change).
'''
YCMD_HANDLER_GET_COMPLETIONS = '/completions'
YCMD_HANDLER_RUN_COMPLETER_COMMAND = '/run_completer_command'
YCMD_HANDLER_EVENT_NOTIFICATION = '/event_notification'
YCMD_HANDLER_DEFINED_SUBCOMMANDS = '/defined_subcommands'
YCMD_HANDLER_DETAILED_DIAGNOSTIC = '/detailed_diagnostic'
YCMD_HANDLER_LOAD_EXTRA_CONF = '/load_extra_conf_file'
YCMD_HANDLER_IGNORE_EXTRA_CONF = '/ignore_extra_conf_file'
YCMD_HANDLER_DEBUG_INFO = '/debug_info'
YCMD_HANDLER_READY = '/ready'
YCMD_HANDLER_HEALTHY = '/healthy'
YCMD_HANDLER_SHUTDOWN = '/shutdown'

'''
Server request parameters, specific to `YCMD_HANDLER_RUN_COMPLETER_COMMAND`.

Not all commands are available for all file types. To get the list of commands
for a given file type, use `YCMD_HANDLER_DEFINED_SUBCOMMANDS`, along with the
intended file type in the request body.

Not user configurable (but should be, maybe).
'''
YCMD_COMMAND_GET_TYPE = 'GetType'
YCMD_COMMAND_GET_PARENT = 'GetParent'
YCMD_COMMAND_GO_TO_DECLARATION = 'GoToDeclaration'
YCMD_COMMAND_GO_TO_DEFINTION = 'GoToDefinition'
YCMD_COMMAND_GO_TO = 'GoTo'
YCMD_COMMAND_GO_TO_IMPRECISE = 'GoToImprecise'
YCMD_COMMAND_CLEAR_COMPILATION_FLAG_CACHE = 'ClearCompilationFlagCache'

'''
Server request parameters, specific to `YCMD_HANDLER_EVENT_NOTIFICATION`.

The only real required one is `YCMD_EVENT_FILE_READY_TO_PARSE`. The other ones
are optional, but help ycmd cache the data efficiently.

Not user configurable (but should be, maybe).
'''
YCMD_EVENT_FILE_READY_TO_PARSE = 'FileReadyToParse'
YCMD_EVENT_BUFFER_UNLOAD = 'BufferUnload'
YCMD_EVENT_BUFFER_VISIT = 'BufferVisit'
YCMD_EVENT_INSERT_LEAVE = 'InsertLeave'
YCMD_EVENT_CURRENT_IDENTIFIER_FINISHED = 'CurrentIdentifierFinished'
