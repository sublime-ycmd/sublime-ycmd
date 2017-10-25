# Sublime Text YouCompleteMe

sublime-ycmd is a Sublime Text 3 plugin that leverages ycmd to generate
autocomplete suggestions. To use this plugin, **ycmd must be installed**.

## Language-Specific Features
### C Family
This requires that ycmd be built with clang completer support. This also
requires a project-specific/global configuration file for ycmd. The easiest
way to do that is to create a `.ycm_extra_conf.py` in the root of the project
tree and add the required `FlagsForFile` method in it.

See the [ycmd README][ycmd-ycm-extra-conf] for more information.

### Python
This should not require any special setup, as ycmd will use Jedi to perform
python semantic completions.

If the python binary used to build and run ycmd is not the same as the python
binary used in the project/environment, the completions may be slightly off.
This can be corrected by updating the `"python_binary_path"` variable in the
ycmd default settings file (`ycmd/ycmd/default_settings.json`).

### JavaScript
This requires that ycmd be built with tern completer support. This also requires
a project-specific configuration file for Tern itself. Create a `.tern-project`
file in the root of the project and add the necessary configuration there.

See the [Tern docs][ternjs-configuration] for more information.

## Configuration
The supported options are listened in the default settings file. See
`sublime-ycmd.sublime-settings` for more information.

## Issues
When submitting issues, try to collect log output relating to the problem. This
includes log output from both the plugin, and from ycmd itself.

## Tests
To run the unit-test suite, simply execute `runtests.py`:

```
python runtests.py
```

The tests are not yet complete. It tests some basic low-level operations, but
does not test any of the plugin behaviour.

## Contributing
Ensure that unit tests still pass. If possible, ensure that `pylint` does not
report issues.

[ycmd-ycm-extra-conf]: https://github.com/Valloric/ycmd#ycm_extra_confpy-specification
[ternjs-configuration]: http://ternjs.net/doc/manual.html#configuration
