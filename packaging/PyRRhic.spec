# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

project_root = Path(SPECPATH).resolve()
if not (project_root / 'pyrrhic').exists():
    project_root = project_root.parent

block_cipher = None

hiddenimports = collect_submodules('pubsub')
hiddenimports += [
    'pyrrhic.tests.comms.phy.phy_mock',
    'pyrrhic.tests.comms.protocol',
    'pyrrhic.tests.comms.protocol.ssm_mock',
]

datas = [
    (str(project_root / 'submodules' / 'PyJ2534'), 'submodules/PyJ2534'),
    (str(project_root / 'submodules' / 'SubaruDefs'), 'submodules/SubaruDefs'),
]

_alpha_defs = project_root / 'submodules' / 'SubaruDefs-Alpha_TD-D'
if _alpha_defs.exists():
    datas.append((str(_alpha_defs), 'submodules/SubaruDefs-Alpha_TD-D'))


a = Analysis(
    [str(project_root / 'packaging' / 'pyrrhic_launcher.py')],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='PyRRhic',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PyRRhic',
)
