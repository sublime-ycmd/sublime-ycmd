# Sublime Text YouCompleteMe

sublime-ycmd is a Sublime Text 3 plugin that leverages ycmd to generate
autocomplete suggestions. To use this plugin, **ycmd must be installed**.

## Language-Specific Features
### C Family
This requires that ycmd be built with clang completer support. This also
requires a project-specific/global configuration file for ycmd. The easiest
way to do that is to create a `.ycm_extra_conf.py` in the root of the project
tree and add the required `FlagsForFile` method in it.

**TODO** YCM docs for `.ycm_extra_conf.py`.

### Python
This does not require any special setup. Since ycmd uses Jedi as the python
semantic completer, it may be necessary to configure things like python version.

**TODO** Jedi docs for configuration.

### JavaScript
This requires that ycmd be built with tern completer support. This also requires
a project-specific configuration file for Tern itself. Create a `.tern-project`
file in the root of the project and add the necessary configuration there.

**TODO** Tern docs for configuration.

## Configuration
**TODO** Configuration options.

## Logging
**TODO** Logging configuration file.

## Tests
To run the unit-test suite, simply execute `runtests.py`:

```
python runtests.py
```

The tests are not yet complete. It tests some basic low-level operations, but
does not test any of the plugin behaviour.

**TODO** Flags for controlling test list and logging.

## Contributing
Ensure that unit tests still pass, and that `pylint` does not report issues.

**TODO** Fix code so it actually passes `pylint`...
