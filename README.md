# PyRRhic
A Python-based RomRaider derivative

## Getting Started with Development

1. Install Python 3.8 32-bit (32-bit is necessary for J2534 drivers)
2. Clone repository (including submodules) to directory of your choice
3. In the repository top level directory, setup the virtual environment
    to the directory `./venv`:

```
.../PyRRhic/ $ python -m venv venv
```

4. Activate the virtual environment, and install all required libraries
```
.../PyRRhic/ $ ./venv/Scripts/activate
(venv) .../PyRRhic/ $ python -m pip install -r requirements.txt
```

5. [_**Optional, but recommended**_] VSCode settings have been included
    in the repository. To use them, simply open the root directory of
    the repository in VSCode as a folder. Settings include the debug
    launch configurations, and some basic settings to facilitate style
    consistencies (e.g. vertical rulers at 72 and 79 chars, per PEP8,
    auto-trim whitespace, 4 spaces as tabs, etc.)

## Starting PyRRhic
To start the program from command-line, simply call it as a module:
```
.../PyRRhic/ $ python -m pyrrhic
```

## Building a Windows EXE + Installer

PyRRhic can be packaged as a Windows executable that already includes
Python and required modules. End users do not need to install Python.

### 1) Build standalone app folder (PyInstaller)

From PowerShell in repository root:

```
./packaging/build_windows.ps1 -Python python
```

Output is generated at:

```
./dist/PyRRhic/
```

### 2) Build installer EXE (Inno Setup)

Install Inno Setup and run:

```
iscc ".\packaging\PyRRhic.iss"
```

Installer output:

```
./dist_installer/PyRRhic-Setup.exe
```

### One-command release (app + installer)

```
./packaging/release.ps1 -Python python
```

With explicit version:

```
./packaging/release.ps1 -Python python -Version 1.2.0
```

Keep previous installers (disable automatic cleanup):

```
./packaging/release.ps1 -Python python -Version 1.2.0 -KeepAllInstallers
```

Keep previous versioned release folders:

```
./packaging/release.ps1 -Python python -Version 1.2.0 -KeepAllReleaseFolders
```

If `-Version` is omitted, the script tries the latest git tag (for
example `v1.2.0` -> `1.2.0`) and falls back to `0.1.0`.

### Notes

- Build with Python 3.8 32-bit to preserve J2534 compatibility.
- The packaged app includes repository submodules required at runtime:
    `submodules/PyJ2534` and `submodules/SubaruDefs`.
- If present in the repo, `submodules/SubaruDefs-Alpha_TD-D` is also
    included in the packaged app and installer.
- Installer output is versioned as `PyRRhic-Setup-<version>.exe`.
- By default, old `PyRRhic-Setup*.exe` files in `dist_installer` are
    removed after a successful release (use `-KeepAllInstallers` to keep all).
- Each release creates `dist_releases/<version>/` with the installer and a ZIP
    of the app folder; old version folders are removed by default (use
    `-KeepAllReleaseFolders` to keep history).
