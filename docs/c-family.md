# C Family

Here are some examples and tips for C-family completions.

**NOTE:** The C-family completer requires that `ycmd` be built with the
`--clang-completer` flag.

## Compiler Flags

Basic identifier-based completions will work without any extra configuration,
but that's likely not much better than the built-in completions. To get full
semantic completions, the server needs to know the compiler flags.

Compiler flags can be loaded through an extra configuration file:
`.ycm_extra_conf.py`. Define `FlagsForFile` and have it return a dictionary
with a `'flags'` property. It should be a list containing each flag as a
string. For example:

```python
def FlagsForFile(filename, **kwargs):
    return {
        'flags': ['-x', 'c++'],
    }
```

### Relative Paths

Relative paths are calculated relative to the project root by default. The
plugin will attempt to detect the project root based on the active file.
It is also possible to override this in the `FlagsForFile` method:

```python
def FlagsForFile(filename, **kwargs):
    return {
        'flags': ['-x', 'c++', '-I', 'somedir'],
        'include_paths_relative_to_dir': '/path/to/root',
    }
```

## Global Extra Configuration

Instead of creating a `.ycm_extra_conf.py` for each project, it is possible
to create a default global extra configuration file.

First, create the extra configuration file with a `FlagsForFile` method. For
example, save the following to `~/Documents/ycm-global-conf.py`:

```python
C_EXTS = ['.c']
CPP_EXTS = ['.cpp', '.cc', '.h']

BASE_FLAGS = ['-I', '/usr/local/include', '-Wall']
C_FLAGS = BASE_FLAGS + ['-x', 'c']
CPP_FLAGS = BASE_FLAGS + ['-x', 'c++', '-std=c++11']

def has_ext(filename, exts):
    return any(filename.endswith(ext) for ext in exts)

def FlagsForFile(filename, **kwargs):
    if has_ext(filename, C_EXTS):
        # c file
        flags = C_FLAGS
    elif has_ext(filename, CPP_EXTS):
        # cpp file
        flags = CPP_FLAGS
    else:
        flags = None

    if flags is None:
        # no flags
        return None

    return {
        'flags': flags,
    }
```

Then, modify the ycmd server settings file (the default one is in the ycmd
repository at `ycmd/ycmd/default_settings.json`) to point to it with the
`"global_ycm_extra_conf"` parameter. It should look something like:

```json
{
  ...
  "global_ycm_extra_conf": "~/Documents/ycm-global-conf.py",
  ...
}
```

## Semantic Triggers

The default semantic triggers are good enough for most users, but they can be
extended to trigger on other characters as well. Add entries to the server
settings file under `"semantic_triggers"`. The value should be an object that
maps languages (keys) to a list of trigger sequences (values).

For example, the following will trigger semantic completions for includes:

```json
{
  ...
  "semantic_triggers": {
    "c,cpp": ["re!^#include\s+\""]
  },
  ...
}
```
