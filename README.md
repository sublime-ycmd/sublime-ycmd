# Sublime Text YouCompleteMe

sublime-ycmd is a Sublime Text 3 plugin that leverages ycmd to generate
autocomplete suggestions. To use this plugin, **ycmd must be installed**.

**Alternatives**

[YcmdCompletion][alt-ycmd-completion] - Based off the ycmd example client.
Uses most of the ycmd API. This plugin still does not support all the
same features, but there are plans to add them all. Like the example client,
this alternative does everything on the main thread, which may lock up the
editor.

[CppYCM][alt-cpp-ycm] *(No longer maintained)* - Supports "GoTo" and error
highlighting. Again, this plugin still does not support that, but it will
be added in later releases. This alternative is limited to C++, but does a
really good job at it.

## Quick-Start
Ensure that ycmd is installed before installing this plugin. See the
[ycmd README][ycmd-building] for more information.

Here is an example setup using `brew`:

```
brew install cmake

cd ~/Documents
git clone https://github.com/Valloric/ycmd.git
cd ycmd
git submodule update --init --recursive
./build.py --clang-completer
```

Once that's done, install the plugin (search for `YouCompleteMe`) and
edit the settings (Preferences > Package Settings > YouCompleteMe >
Preferences). Fill in the path to the ycmd repository, and save it.

For the example above, the settings would look like:

```
{
  "ycmd_root_directory": "~/Documents/ycmd"
}
```

## Language-Specific Features
### C Family
This requires that ycmd be built with clang completer support. This also
requires a project-specific/global configuration file for ycmd. The easiest
way to do that is to create a `.ycm_extra_conf.py` in the root of the project
tree and add the required `FlagsForFile` method in it.

See the [ycmd README][ycmd-ycm-extra-conf] for more information.

Here is a minimal example to start with:

```
def FlagsForFile(*args, **kwargs):
    return {
        'flags': [
            '-std=c++11',
            '-Wall',
        ],
    }
```

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

Here is a minimal example for `node` environments:

```
{
  "plugins": {
    "node": {}
  }
}
```

## Configuration
### Plugin Settings
The supported options are listed in the default settings file. See
`sublime-ycmd.sublime-settings` for more information.

The only required setting is `"ycmd_root_directory"`. Set this to the ycmd
repository path, and the plugin will automatically launch it when needed.

**NOTE:** If YouCompleteMe is already installed for vim, this plugin can
use the ycmd repository installed along with it. If installed with Vundle,
it would look something like:

```
{
  "ycmd_root_directory": "~/.vim/bundle/YouCompleteMe/third_party/ycmd"
}
```

### YCMD Settings
Server settings are loaded from a separate JSON file. The ycmd repository
includes a good set of defaults at `ycmd/ycmd/default_settings.json`. Either
modify that file, or create a copy of it, and use the plugin setting
`"ycmd_default_settings_path"` to point to the copy.

For example, create a copy with custom settings:

```
cd ~/Documents/ycmd
cp ycmd/default_settings.json ycmd/custom_settings.json
```

The corresponding plugin settings would be:

```
{
  "ycmd_root_directory": "~/Documents/ycmd",
  "ycmd_default_settings_path": "~/Documents/ycmd/ycmd/custom_settings.json"
}
```

Eventually, these settings will be brought into the plugin settings. The
plugin would then be able to generate the ycmd settings file automatically.

## Issues
When submitting issues, try to collect log output relating to the problem. Logs
can be collected for both the plugin and for ycmd itself.

Use the following plugin settings to collect plugin logs in a separate file:

```
{
  "sublime_ycmd_log_level": "debug",
  "sublime_ycmd_log_file": "/tmp/sublime-ycmd.log",
}
```

Verbose logs will be appended to `"sublime_ycmd_log_file"`
(`/tmp/sublime-ycmd.log` in this example). It's likely that the issue will
have related errors in these logs.

Use the following plugin settings to generate ycmd logs as well:

```
{
  "ycmd_log_level": "debug",
  "ycmd_log_file": true,
  "ycmd_keep_logs": true,
}
```

Temporary log files will be generated for each server and retained even after
the server exits. These logs are generally not required, but may be useful.

## Tests
To run the unit-test suite, simply execute `tests/runtests.py`:

```
python3 tests/runtests.py
```

The tests are not yet complete. It tests some basic low-level operations, but
does not test any of the plugin behaviour.

## Contributing
Ensure that unit tests still pass. If possible, ensure that `pylint` does not
report issues.

[alt-ycmd-completion]: https://github.com/LuckyGeck/YcmdCompletion
[alt-cpp-ycm]: https://github.com/glymehrvrd/CppYCM
[ycmd-building]: https://github.com/Valloric/ycmd#building
[ycmd-ycm-extra-conf]: https://github.com/Valloric/ycmd#ycm_extra_confpy-specification
[ternjs-configuration]: http://ternjs.net/doc/manual.html#configuration
