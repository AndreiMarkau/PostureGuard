# posture_guard.spec — fast build, no console window

import sys
import os
from pathlib import Path

block_cipher = None
SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
sys.path.insert(0, SPEC_DIR)

from PyInstaller.utils.hooks import collect_data_files

# ── Hidden imports ──────────────────────────────────────────────────────────
hidden = [
    # local packages
    'ui', 'ui.main_window', 'ui.calibration_window',
    'ui.leaderboard_window', 'ui.settings', 'ui.tray',
    'core', 'core.engine', 'core.detector', 'core.calibration',
    'core.session_tracker', 'core.away_detector',
    'audio', 'audio.player',
    # PyQt6 — only what we actually import
    'PyQt6', 'PyQt6.QtWidgets', 'PyQt6.QtCore', 'PyQt6.QtGui',
    'PyQt6.QtSvg', 'PyQt6.sip',
    # stdlib — PyInstaller sometimes misses these
    'wave', 'json', 'threading', 'math', 'dataclasses', 'struct',
    # sounddevice + soundfile — used by AudioPlayer (MP3/WAV support)
    'sounddevice', 'sounddevice._sounddevice',
    'soundfile',
    # required by numpy.random (bit_generator / mtrand)
    'secrets', 'hmac', 'hashlib', '_hashlib',
    # numpy Cython extensions PyInstaller misses
    'numpy.random', 'numpy.random.mtrand', 'numpy.random._pickle',
    'numpy.random._common', 'numpy.random._bounded_integers',
    'numpy.random._generator', 'numpy.random.bit_generator',
    # urllib + pathlib are required by zipfile runtime hook (pyi_rth_inspect)
    'urllib', 'urllib.parse', 'urllib.request', 'urllib.error',
    # mediapipe runtime
    'mediapipe.python.solutions.pose',
    'mediapipe.python.solutions.drawing_utils',
    'mediapipe.python.solutions.drawing_styles',
    # mediapipe pulls matplotlib + PIL transitively
    'matplotlib', 'matplotlib.pyplot', 'matplotlib.colors',
    'PIL', 'PIL.Image',
]

# ── Datas ───────────────────────────────────────────────────────────────────
def collect_mediapipe_data():
    try:
        import mediapipe
        mp_dir = Path(mediapipe.__file__).parent
        datas = []
        for ext in ['*.binarypb', '*.tflite', '*.pbtxt', '*.pb']:
            for f in mp_dir.rglob(ext):
                rel = f.parent.relative_to(mp_dir.parent)
                datas.append((str(f), str(rel)))
        modules_dir = mp_dir / 'modules'
        if modules_dir.exists():
            for f in modules_dir.rglob('*'):
                if f.is_file():
                    rel = f.parent.relative_to(mp_dir.parent)
                    datas.append((str(f), str(rel)))
        return datas
    except Exception as e:
        print(f"WARNING: mediapipe data collection: {e}")
        return []

extra_datas = collect_mediapipe_data()

alert_wav = os.path.join(SPEC_DIR, 'assets', 'alert.wav')
if os.path.exists(alert_wav):
    extra_datas.append((alert_wav, 'assets'))

# Bundle app icon
icon_svg = os.path.join(SPEC_DIR, 'assets', 'app_icon.svg')
icon_ico = os.path.join(SPEC_DIR, 'assets', 'app_icon.ico')
if os.path.isfile(icon_svg):
    extra_datas.append((icon_svg, 'assets'))
if os.path.isfile(icon_ico):
    extra_datas.append((icon_ico, 'assets'))

config_json = os.path.join(SPEC_DIR, 'config.json')
if os.path.exists(config_json):
    extra_datas.append((config_json, '.'))

# ── Analysis ────────────────────────────────────────────────────────────────
a = Analysis(
    [os.path.join(SPEC_DIR, 'main.py')],
    pathex=[SPEC_DIR],
    binaries=[],
    datas=extra_datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # GUI toolkits we don't use
        'tkinter', 'PyQt5', 'PySide2', 'PySide6',
        # Heavy data-science libs — not needed at runtime
        'IPython', 'notebook', 'scipy',
        'pandas',
        # Dev/test tools
        'pydoc', 'doctest',
        # Rarely needed stdlib
        'xmlrpc', 'curses', 'readline',
        # pygame excluded — we use wave/struct directly
        'pygame',
    ],
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
    name='PostureGuard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX отключён: экономит 1-3 мин на сжатии, не влияет на работу
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(SPEC_DIR, 'assets', 'app_icon.ico'),
    version=None,
)
