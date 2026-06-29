# PyInstaller build specification for macOS
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

ICON_PATH = str(Path('assets/app_icon.icns').resolve())
DEMUCS_DATA = collect_data_files('demucs', includes=['remote/*'])

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=DEMUCS_DATA,
    hiddenimports=[
        'PyQt6',
        'torch',
        'torchaudio',
        'demucs',
        'librosa',
        'sounddevice',
        'soundfile',
        'mutagen',
        'mutagen.mp3',
        'mutagen.mp4',
        'mutagen.flac',
        'mutagen.oggvorbis',
        'mutagen.wave',
        'numpy',
        'scipy',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludedimports=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AIStemSeparator',
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
    icon=ICON_PATH,
)

app = BUNDLE(
    exe,
    name='AIStemSeparator.app',
    icon=ICON_PATH,
    bundle_identifier='com.ai.stemseparator',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': True,
        'CFBundleShortVersionString': '1.1.1',
        'CFBundleVersion': '1.1.1',
    },
)
