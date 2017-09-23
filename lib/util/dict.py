#!/usr/bin/env python3

'''
lib/util/dict.py
Contains dictionary utility functions.
'''

import copy
import logging

logger = logging.getLogger('sublime-ycmd.' + __name__)


def is_collection(value):
    '''
    Returns true if `value` is a collection-like object.

    Examples of these are lists and dictionaries.
    Examples of non-collection objects are numbers and strings.
    '''
    if isinstance(value, (tuple, list, dict)):
        # collections for sure
        return True

    collection_attrs = (
        '__getitem__', '__setitem__', '__delitem__',
        # this is not necessarily true, but required for the implementation
        # of `merge_dicts` below:
        '__iter__', '__contains__',
    )
    for collection_attr in collection_attrs:
        if not hasattr(value, collection_attr):
            # nope - collections must include all of them
            return False

    # not sure, say yes since it supports all operations needed to merge
    return True


def _is_sequence(value):
    return hasattr(value, 'index') and callable(getattr(value, 'index'))


def _is_itemized(value):
    return hasattr(value, 'items') and callable(getattr(value, 'items'))


def _merge_recursively(dest, src):
    assert is_collection(dest), \
        '[internal] dest must be a collection: %r' % (dest)
    assert is_collection(src), \
        '[internal] src must be a collection: %r' % (src)

    unknown_type = 0
    sequence_type = 1
    itemized_type = 2

    def _get_type(value):
        if _is_sequence(value):
            return sequence_type
        if _is_itemized(value):
            return itemized_type
        return unknown_type

    dest_type = _get_type(dest)
    src_type = _get_type(src)

    if dest_type == unknown_type and src_type == unknown_type:
        # don't know the types... can't merge it
        raise ValueError('unsure how to merge dest, src: %r, %r' % (dest, src))

    if dest_type != src_type:
        # mismatched types, overwrite it
        src_copy = copy.deepcopy(src)
        dest = src_copy
        return dest

    # matched types, figure out how to merge them

    if dest_type == sequence_type:
        # list-like, append it
        src_copy = copy.deepcopy(src)
        dest += src_copy
        return dest

    if dest_type == itemized_type:
        # dict-like, recursively merge
        for key, value in src.items():

            def _overwrite_value(key=key, value=value, make_copy=True):
                value_ref = copy.deepcopy(value) if make_copy else value
                dest[key] = value_ref

            if key not in dest:
                # not present, so always write it in
                _overwrite_value()
                continue

            # merge values, allowing overwrites when necessary
            # consider merging
            # if they're both collections, a merge might be possible
            # otherwise, that's a mismatch, so overwrite
            dest_value = dest[key]
            src_value = value

            is_dest_value_collection = is_collection(dest_value)
            is_src_value_collection = is_collection(src_value)

            if is_dest_value_collection and is_src_value_collection:
                # recurse - the next call will decide to merge or overwrite
                merged_value = _merge_recursively(dest_value, src_value)
                _overwrite_value(value=merged_value, make_copy=False)
            else:
                # mismatch - can't merge, so always overwrite
                _overwrite_value()

        return dest

    raise ValueError('unknown dest type: %r' % (dest))


def merge_dicts(base, *rest):
    '''
    Recursively merges `base`, which should be a `dict`, with `rest`.

    The result first starts out being equal to `base` (a deep copy). Then for
    each item in `rest`, the keys are merged into the result. If the mapped
    value is not a collection, it overwrites the key in the result. If the
    mapped value is a collection, it is recursed into to overwrite the result.

    Examples:
        merge_dicts({
            'foo': 'bar',
        }, {
            'foo': 'baz',
        })
        # --> { 'foo': 'baz' }

    NOTE : This method creates deep copies of input data. Do not supply objects
           that contain cyclic references. Do not supply large objects.
    '''

    result = copy.deepcopy(base)
    for src in rest:
        _merge_recursively(result, src)

    return result
