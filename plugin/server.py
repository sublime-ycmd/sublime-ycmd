#!/usr/bin/env python3

'''
plugin/server.py
Server manager class.

Manages ycmd server processes. This class uses a task pool to help offload
blocking calls whenever possible.
'''

import logging
import tempfile
import threading

# for type annotations only:
import concurrent                   # noqa: F401

from ..lib.subl.view import (
    View,
    get_view_id,
    get_path_for_window,
    get_path_for_view,
)
from ..lib.task.pool import (
    Pool,
    disown_task_pool,
)
from ..lib.util.lock import lock_guard
from ..lib.ycmd.server import Server
from ..lib.ycmd.start import (
    StartupParameters,
    check_startup_parameters,
)

logger = logging.getLogger('sublime-ycmd.' + __name__)

try:
    import sublime
except ImportError:
    from ..lib.subl.dummy import sublime


class SublimeYcmdServerManager(object):
    '''
    Singleton helper class. Runs, manages, and stops ycmd server instances.
    Generally, each project will have its own associated backend ycmd server.
    This is required for certain completers, like tern, that rely on the
    working directory in order to find imported files.
    '''

    def __init__(self):
        self._servers = set()

        self._startup_parameters = None     # type: StartupParameters
        self._task_pool = None              # type: Pool

        self._lock = threading.RLock()

        # lookup tables:
        self._view_id_to_server = {}
        self._working_directory_to_server = {}

    @lock_guard()
    def shutdown(self, hard=False, timeout=None):
        '''
        Shuts down all managed servers.

        If `hard` is true, then the server processes will be killed via a kill
        signal instead of the standard shutdown http request. If `timeout` is
        omitted, this method waits indefinitely for the process to exit.
        Otherwise, each server process is given `timeout` seconds to exit. If
        a process does not exit within the timeout, then it will be ignored.
        This is not ideal, as it may result in zombie processes.

        If `hard` is false, then the servers will be shut down gracefully using
        the shutdown http handler. If `timeout` is omitted, this method waits
        indefinitely for the servers to shut down. Otherwise, each server is
        given `timeout` seconds to shutdown gracefully. If it fails to shut
        down in that time, this method returns without doing anything extra.

        The return value will be true if all servers were successfully shut
        down, and false otherwise. This can be useful when attempting to do
        a graceful shutdown followed by a hard shutdown if any servers remain.
        '''
        if hard:
            def shutdown_server(server):
                assert isinstance(server, Server), \
                    '[internal] server is not a Server: %r' % (server)
                server.kill()
                server.wait(timeout=timeout)
                return server
        else:
            def shutdown_server(server):
                assert isinstance(server, Server), \
                    '[internal] server is not a Server: %r' % (server)
                server.stop(timeout=timeout)
                return server

        if not self._servers:
            # no servers to shutdown, so done
            logger.debug('no servers to shut down, done')
            return True

        shutdown_futures = [
            self._task_pool.submit(shutdown_server, server)
            for server in self._servers
        ]
        finished_futures, unfinished_futures = concurrent.futures.wait(
            shutdown_futures, timeout=timeout,
        )

        all_shutdown_successfully = True
        # unregister servers that were successfully shutdown
        for finished_future in finished_futures:
            assert finished_future.done(), \
                '[internal] finished future is not actually finished: %r' % \
                (finished_future)
            if finished_future.exception(timeout=0) is None:
                # `shutdown_server` returns the specific server instance that
                # was shut down, so grab it from the future
                stopped_server = finished_future.result(timeout=0)
                assert isinstance(stopped_server, Server), \
                    '[internal] async shutdown did not return a Server: %r' % \
                    (stopped_server)
                assert stopped_server in self._servers, \
                    '[internal] server is not in managed server set: %r' % \
                    (stopped_server)

                logger.debug('server has shut down: %r', stopped_server)
                self._unregister_server(stopped_server)
            else:
                all_shutdown_successfully = False

        if unfinished_futures:
            all_shutdown_successfully = False

        return all_shutdown_successfully

    @lock_guard()
    def get(self, view):
        '''
        Returns a `Server` instance that has a suitable working directory for
        use with the supplied `view`.
        If one does not exist, it will be created asynchronously. In that case,
        the caller should inspect the returned instance and ensure it is ready.
        '''
        if not isinstance(view, (sublime.View, View)):
            raise TypeError('view must be a View: %r' % (view))

        view_id = get_view_id(view)
        if view_id is None:
            logger.error('failed to get view ID for view: %r', view)
            raise TypeError('view id must be an int: %r' % (view))

        view_working_dir = get_path_for_view(view)

        # also inspect the window for a working directory
        # this is used to decide how to cache the lookup
        should_cache_view_id = get_path_for_window(view) is not None

        def lookup_by_view_id(view_id=view_id):
            if view_id is not None and view_id in self._view_id_to_server:
                return self._view_id_to_server[view_id]
            return None

        def lookup_by_working_dir(working_dir):
            if working_dir is not None and \
                    working_dir in self._working_directory_to_server:
                return self._working_directory_to_server[working_dir]
            return None

        def cache_for_view_id(view_id=view_id, server=None):
            if not view_id:
                raise ValueError('view id must be an int: %r' % (view_id))
            if view_id not in self._view_id_to_server:
                logger.debug(
                    'caching server by view id: %r -> %r', view_id, server,
                )
            self._view_id_to_server[view_id] = server

        def cache_for_working_dir(working_dir, server=None):
            if not working_dir:
                raise ValueError(
                    'working directory must be a str: %r' % (working_dir)
                )
            if working_dir not in self._working_directory_to_server:
                logger.debug(
                    'caching server by working dir: %r -> %r',
                    working_dir, server,
                )
            self._working_directory_to_server[working_dir] = server

        server = lookup_by_view_id(view_id)
        if server is None:
            logger.debug('no cached entry for view id: %r', view_id)
            server = lookup_by_working_dir(view_working_dir)
            if server is None:
                logger.debug(
                    'no cached entry for working directory: %r',
                    view_working_dir,
                )

        if server is not None:
            # ensure server is either starting, or running
            is_server_live = (
                server.is_starting() or server.is_alive(timeout=0)
            )

            if not is_server_live:
                logger.info('removing stale server: %s', server.pretty_str())

                stdout = read_spooled_output(server.stdout)
                stderr = read_spooled_output(server.stderr)

                logger.debug(
                    'server process stdout, stderr: %r, %r', stdout, stderr,
                )

                self._unregister_server(server)
                server = None

        if not server:
            logger.info(
                'creating ycmd server for project directory: %s',
                view_working_dir,
            )

            server_startup_parameters = self._generate_startup_parameters(view)
            # give them a quick non-blocking check to catch potential errors
            try:
                check_startup_parameters(server_startup_parameters)
            except Exception as e:
                logger.warning(
                    'invalid parameters, cannot start server: %r', e
                )
                # abort, don't follow through and set it up
                return None

            logger.debug(
                'using startup parameters: %r', server_startup_parameters,
            )

            # create an empty handle and then fill it in off-thread
            server = Server()
            self._servers.add(server)

            self._task_pool.submit(server.start, server_startup_parameters)
            logger.debug('initializing server off-thread: %r', server)

        if should_cache_view_id:
            cache_for_view_id(view_id, server)
        cache_for_working_dir(view_working_dir, server)

        return server   # type: Server

    @lock_guard()
    def set_startup_parameters(self, startup_parameters):
        '''
        Sets the server startup parameters. This is used whenever a server is
        started by this manager.

        The startup parameters should be an instance of `StartupParameters`.
        These contain all the necessary information, like path to the ycmd
        installation.

        This method will not modify any existing server instances. To clear the
        servers and have them relaunched with these new parameters, use
        `shutdown` as well.
        '''
        if not isinstance(startup_parameters, StartupParameters):
            raise TypeError(
                'startup parameters must be StartupParameters: %r' %
                (startup_parameters)
            )

        self._startup_parameters = startup_parameters

    @lock_guard()
    def set_background_threads(self, background_threads):
        '''
        Sets the number of background threads used for running tasks.

        These tasks are run off-thread so they won't block the main thread. It
        includes process management (starting and shutting down the servers),
        and sending event notifications (loading and unloading buffers).

        When called, the pre-existing task pool is shut down. This is done on
        a detached thread, so it won't block the caller. All tasks in that pool
        will run to completion, and then the pool will be terminated. The old
        task pool will no longer be accessible via this instance.

        If `background_threads` is omitted, this method then returns without
        re-allocating a new task pool.

        Otherwise, a new task pool will be allocated, and `background_threads`
        workers are automatically started for it. This task pool will then be
        used for all subsequent operations by this manager.
        '''
        if self._task_pool is not None:
            logger.debug('discarding current task pool')
            disown_task_pool(self._task_pool)
            del self._task_pool

        if background_threads is None:
            logger.debug('not starting another task pool, returning')
            return

        logger.debug(
            'creating new task pool with %d workers', background_threads,
        )

        self._task_pool = Pool(
            max_workers=background_threads,
            thread_name_prefix='sublime-ycmd-background-thread-',
        )

    @lock_guard()
    def set_server_logging(self,
                           log_level=None, log_file=None, keep_logs=False):
        '''
        Adds startup options when starting servers to enable logging.

        If `log_level` is omitted, the default ycmd log level is used (no
        additional startup flags are added). Otherwise, it should be one of:
            "debug", "info", "warning", "error", or "critical"

        If `log_file` is omitted, no log files will be created. The server
        outputs are captured in a spooled temporary file (max 2kb memory).
        If provided, it should follow the rules specified in the settings. See
        the settings file for a comment explaining all options.

        If `keep_logs` is false, then the ycmd server will delete log files
        when it exits. Otherwise, these log files are retained. This parameter
        is ignored if `log_file` is `None` or `False`.
        '''
        if self._startup_parameters is None:
            logger.warning(
                'startup parameters are not set, '
                'ignoring log level configuration: %r',
                log_level,
            )
            return

        self._startup_parameters.log_level = log_level
        self._startup_parameters.keep_logs = keep_logs

        # The server manager must implement the high-level functionality for
        # the supported options. It cannot be pre-calculated, as some options
        # are based on other inputs (e.g. working directory).
        self._log_file = log_file

    @lock_guard()
    def get_servers(self):
        '''
        Returns a shallow-copy of the set of managed `Server` instances.
        '''
        return self._servers.copy()

    @lock_guard()
    def notify_enter(self, view, parse_file=True):
        '''
        Sends a notification to the ycmd server that the file for `view` has
        been activated. This will create and cache file-specific identifiers.

        If `parse_file` is true, an additional notification will be sent to
        indicate that the file should be parsed for identifiers. Otherwise,
        this step is skipped. This is optional, but gives better completions.

        The actual request is sent asynchronously via a task pool, so this
        won't block the caller.
        '''
        if not isinstance(view, View):
            raise TypeError('view must be a View: %r' % (view))

        request_params = view.generate_request_parameters()
        if not request_params:
            logger.debug('failed to generate request params, abort')
            return None

        server = self.get(view)
        if not server:
            logger.warning('failed to get server for view: %r', view)
            return None

        def notify_ready_to_parse(server=server,
                                  request_params=request_params):
            server.notify_file_ready_to_parse(request_params)

        def notify_buffer_enter(server=server,
                                request_params=request_params):
            server.notify_buffer_enter(request_params)

        if parse_file:
            def notify_enter_async(server=server,
                                   request_params=request_params):
                notify_ready_to_parse(
                    server=server, request_params=request_params,
                )
                notify_buffer_enter(
                    server=server, request_params=request_params,
                )
        else:
            def notify_enter_async(server=server,
                                   request_params=request_params):
                notify_buffer_enter(
                    server=server, request_params=request_params,
                )

        notify_future = self._task_pool.submit(
            notify_enter_async,
            server=server, request_params=request_params,
        )   # type: concurrent.futures.Future
        return notify_future

    @lock_guard()
    def notify_exit(self, view):
        '''
        Sends a notification to the ycmd server that the file for `view` has
        been deactivated. This will allow the server to release caches.

        The actual request is sent asynchronously via a task pool, so this
        won't block the caller.
        '''
        if not isinstance(view, View):
            raise TypeError('view must be a View: %r' % (view))

        request_params = view.generate_request_parameters()
        if not request_params:
            logger.debug('failed to generate request params, abort')
            return None

        server = self.get(view)
        if not server:
            logger.warning('failed to get server for view: %r', view)
            return None

        def notify_buffer_leave(server=server,
                                request_params=request_params):
            server.notify_buffer_leave(request_params)

        notify_exit_async = notify_buffer_leave
        notify_future = self._task_pool.submit(
            notify_exit_async,
            server=server, request_params=request_params,
        )   # type: concurrent.futures.Future

        return notify_future

    @lock_guard()
    def notify_use_extra_conf(self, view, extra_conf_path, load=True):
        '''
        Sends a notification to the ycmd server that the extra configuration
        file at `extra_conf_path` may be used.

        If `load` is `True`, then the extra configuration file is loaded.
        Otherwise, the server is notified to ignore the file instead.
        '''
        if not isinstance(extra_conf_path, str):
            raise TypeError(
                'extra conf path must be a str: %r' % (extra_conf_path)
            )

        server = self.get(view)
        if not server:
            logger.warning('failed to get server for view: %r', view)
            return None

        if load:
            def notify_use_conf(server=server,
                                extra_conf_path=extra_conf_path):
                server.load_extra_conf(extra_conf_path)
        else:
            def notify_use_conf(server=server,
                                extra_conf_path=extra_conf_path):
                server.ignore_extra_conf(extra_conf_path)

        notify_use_conf_async = notify_use_conf
        notify_future = self._task_pool.submit(
            notify_use_conf_async,
            server=server, extra_conf_path=extra_conf_path,
        )   # type: concurrent.futures.Future

        return notify_future

    @lock_guard()
    def _lookup_server(self, view):
        '''
        Looks up an available server for the given `view`. This calculation is
        based on whether or not a server exists with a working directory
        suitable for use with the underlying file.

        If no server is available, this returns `None`.
        '''
        view_id = get_view_id(view)
        if view_id is None:
            logger.error('failed to get view id for view: %r', view)
            raise TypeError('view must be a View: %r' % (view))

        # check each cache, from fastest lookup to slowest
        if view_id in self._view_id_to_server:
            server = self._view_id_to_server[view_id]   # type: Server
            assert isinstance(server, Server), \
                '[internal] server is not a Server: %r' % (server)
            return server

        view_path = get_path_for_view(view)
        if view_path is None:
            # can't do the lookup for working directory
            logger.debug('could not get path for view, ignoring: %r', view)
        elif view_path in self._working_directory_to_server:
            # add the mapping in view id as well
            wdts = self._working_directory_to_server
            server = wdts[view_path]    # type: Server
            assert isinstance(server, Server), \
                '[internal] server is not a Server: %r' % (server)
            return server

        # not in a cache, so assume no server exists for that view
        return None

    @lock_guard()
    def _unregister_server(self, server):
        if not isinstance(server, Server):
            raise TypeError('server must be a Server: %r' % (server))

        if server not in self._servers:
            logger.error(
                'server was never registered in server manager: %s',
                server.pretty_str(),
            )
            return False

        view_map = self._view_id_to_server
        view_keys = list(filter(
            lambda k: view_map[k] == server, view_map,
        ))
        if view_keys:
            logger.debug('clearing server for views: %s', view_keys)
        for view_key in view_keys:
            del view_map[view_key]

        working_directory_map = self._working_directory_to_server
        working_directory_keys = list(filter(
            lambda k: working_directory_map[k] == server,
            working_directory_map,
        ))
        if working_directory_keys:
            logger.debug(
                'clearing server for working directories: %s',
                working_directory_keys,
            )
        for working_directory_key in working_directory_keys:
            del working_directory_map[working_directory_key]

        self._servers.remove(server)

    def _generate_startup_parameters(self, view):
        '''
        Generates and returns `StartupParameters` derived from the base startup
        parameters set via `set_startup_parameters` and customized for `view`.
        '''
        with self._lock:
            if not self._startup_parameters:
                logger.error(
                    'no server startup parameters have been set, '
                    'cannot generate ycmd command-line options'
                )
                return None

            # create a copy of all necessary data so we can release the lock
            startup_parameters = self._startup_parameters.copy()
            log_file = self._log_file

        # now mess with the copy and fill in information from the view
        view_working_dir = get_path_for_view(view)
        if view_working_dir:
            startup_parameters.working_directory = view_working_dir
        # else, whatever, we tried

        add_log_file_parameters(
            startup_parameters, log_file=log_file,
        )

        return startup_parameters

    def __contains__(self, view):
        ''' Checks if a server is available for a given `view`. '''
        return self._lookup_server(view) is not None

    def __getitem__(self, view):
        ''' Looks up the server for a given `view`. '''
        server = self._lookup_server(view)
        if server is None:
            raise KeyError(view,)
        return server

    @lock_guard()
    def __delitem__(self, view):
        ''' Clears the server for a given `view`, if there is one. '''
        server = self._lookup_server(view)
        if server is None:
            # weird, nothing to delete, so ignore
            return
        self._unregister_server(server)

    @lock_guard()
    def __len__(self):
        ''' Returns the number of servers held in the manager. '''
        return len(self._servers)

    def __bool__(self):
        ''' Returns true. Meant to prevent `len` from being used. '''
        return True


def read_spooled_output(spool):
    def has_method(obj, method):
        return hasattr(obj, method) and callable(getattr(obj, method))

    if spool is None:
        # handle might not be available, so just return nothing
        return None

    if not has_method(spool, 'read'):
        raise TypeError('file must support reading: %r' % (spool))

    try:
        if has_method(spool, 'seek'):
            # rewind to grab all output
            spool.seek(0)

        return spool.read()
    except Exception as e:
        logger.warning('failed to read output: %r', e)
        return None


def add_log_file_parameters(startup_parameters, log_file=None):
    if not isinstance(startup_parameters, StartupParameters):
        raise TypeError(
            'startup parameters must be StartupParameters: %r' %
            (startup_parameters)
        )

    if log_file is None:
        # nothing special to do, process output will be spooled
        return (None, None)

    if log_file is False:
        raise NotImplementedError('need access to process handle')

    if log_file is True:
        # generate temporary files for stdout and stderr
        stdout_file_object = tempfile.NamedTemporaryFile(
            prefix='ycmd_stdout_', suffix='.log', delete=False,
        )
        stderr_file_object = tempfile.NamedTemporaryFile(
            prefix='ycmd_stderr_', suffix='.log', delete=False,
        )

        stdout_file_name = stdout_file_object.name
        stderr_file_name = stderr_file_object.name
        stdout_file_object.close()
        stderr_file_object.close()

        # add the temporary file names to the startup options
        startup_parameters.stdout_log_path = stdout_file_name
        startup_parameters.stderr_log_path = stderr_file_name

        return (stdout_file_name, stderr_file_name)

    if isinstance(log_file, str):
        # tempdir = tempfile.gettempdir()
        # alnum_working_directory = \
        #     ''.join(c if c.isalnum() else '_' for c in working_directory)
        # stdout_file_name = os.path.join(
        #     tempdir, 'ycmd_stdout_%s.log' % (alnum_working_directory)
        # )
        # stderr_file_name = os.path.join(
        #     tempdir, 'ycmd_stderr_%s.log' % (alnum_working_directory)
        # )
        raise NotImplementedError('need access to working directory')

    raise ValueError('log file configuration unrecognized: %r' % (log_file))
