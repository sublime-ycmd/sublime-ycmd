#!/usr/bin/env python3

'''
lib/task/task.py
Task abstraction.

Defines a task which should be run off-thread in a task pool.
'''

import logging

logger = logging.getLogger('sublime-ycmd.' + __name__)


class Task(object):

    INVALID = 'Task.INVALID'
    PENDING = 'Task.PENDING'
    ACTIVE = 'Task.ACTIVE'
    COMPLETED = 'Task.COMPLETED'
    CANCELLED = 'Task.CANCELLED'

    def __init__(self, fn=None, *args, **kwargs):
        # task status, one of the enum properties above
        self._status = Task.INVALID

        # task runner and args
        self._fn = fn           # type: function
        self._args = args
        self._kwargs = kwargs

        # result of running task, if any (may be an exception as well)
        self._result = None

        # updated to true if an exception happened during run, false otherwise
        self._had_error = None

        # used for debugging only:
        self._owner = None

    @property
    def result(self):
        return self._result

    @result.setter
    def result(self, result):
        self._result = result

    def is_invalid(self):
        '''
        Returns `True` if the task has not been registered in a task pool.
        '''
        return self._status == Task.INVALID

    def is_pending(self):
        '''
        Returns `True` if the task is pending execution in a task pool.
        '''
        return self._status == Task.PENDING

    def set_pending(self, owner=None):
        '''
        Sets the task state to pending. A task pool should be doing this when
        it accepts the task.
        If `owner` is provided, the task keeps a reference to it. This class
        treats it as an opaque pointer. It may be used for debugging, but
        that's about it.
        '''
        self._transition_state(Task.PENDING)
        self._owner = owner

    def is_active(self):
        '''
        Returns `True` if the task is currently being executed in a task pool.
        '''
        return self._status == Task.ACTIVE

    def is_cancelled(self):
        '''
        Returns `True` if the task has been cancelled, before being executed.
        '''
        return self._status == Task.CANCELLED

    def set_cancelled(self):
        '''
        Sets the task state to cancelled. A task worker will skip over tasks
        that are flagged as cancelled.
        '''
        self._transition_state(Task.CANCELLED)

    def is_completed(self):
        '''
        Returns `True` if the task has finished execution in its task pool.

        This does not necessarily imply it was successful. It may have thrown
        errors, which will be stored in the result.
        '''
        return self._status == Task.COMPLETED

    @property
    def result(self):
        '''
        The result of executing the task. May be an `Exception` if an exception
        was caught during execution. See `had_error` as well.
        '''
        return self._result

    @property
    def had_error(self):
        '''
        Whether or not an error happened during execution of the task. Will be
        `None` if the task has not yet been executed.
        '''
        return self._had_error

    def _transition_state(self, to_state):
        '''
        Handles transitioning from a task state to another task state. Performs
        additional checks with the previous task state, and issues warnings if
        it appears invalid (e.g. going from completed to pending).
        '''
        if to_state == Task.PENDING:
            # enter pending state from invalid (unregistered) state
            valid_previous_states = [Task.INVALID]
        elif to_state == Task.ACTIVE:
            # should only transition to active from pending
            valid_previous_states = [Task.PENDING]
        elif to_state == Task.CANCELLED:
            # due to race conditions, allow transition from completed state
            valid_previous_states = [
                Task.PENDING, Task.ACTIVE, Task.COMPLETED, Task.CANCELLED,
            ]
        elif to_state == Task.COMPLETED:
            # special case: cancellation has priority
            # this isn't strictly necessary, but should seem more intuitive
            if self._status == Task.CANCELLED:
                logger.debug(
                    'rejecting transition from %r -> %r',
                    self._status, to_state,
                )
                return

            # otherwise, enter completed state from active state only
            valid_previous_states = [Task.ACTIVE]
        else:
            logger.warning(
                'task transition undefined for target state: %r', to_state,
            )
            # fall through and do it anyway
            valid_previous_states = None

        if valid_previous_states:
            if self._status not in valid_previous_states:
                logger.warning(
                    'invalid task state transition, %r -> %r',
                    self._status, to_state,
                )

        self._status = to_state

    def __call__(self):
        self._transition_state(Task.ACTIVE)

        try:
            result = self._fn(*self._args, **self._kwargs)
            had_error = False
        except Exception as e:
            result = e
            had_error = True

        self._result = result
        self._had_error = had_error

        self._transition_state(Task.COMPLETED)

        return result

    def __repr__(self):
        return '%s(%r)' % ('Task', {
            'status': self._status,
            'fn': self._fn,
            'args': self._args,
            'kwargs': self._kwargs,
            'result': self._result,
            'owner': self._owner,
        })
