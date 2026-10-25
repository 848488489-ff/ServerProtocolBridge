"""Third-party components shown in the About window.

Keep this list in sync with the runtime imports and with
``THIRD_PARTY_NOTICES.txt`` (regenerate it with ``tools/collect_licenses.py``).
The About window only lists the component, its license and a project link;
the full license texts live in the source package.
"""

from __future__ import annotations

STDLIB_MODULES = (
    'argparse',
    'asyncio',
    'base64',
    'concurrent',
    'dataclasses',
    'datetime',
    'hashlib',
    'html',
    'ipaddress',
    'json',
    'math',
    'os',
    'pathlib',
    'platform',
    'queue',
    'random',
    're',
    'secrets',
    'shutil',
    'socket',
    'ssl',
    'struct',
    'subprocess',
    'sys',
    'threading',
    'time',
    'tkinter',
    'traceback',
    'typing',
    'urllib',
    'uuid',
    'warnings',
    'webbrowser',
    'winreg',
    'zlib',
)

COMPONENTS = (
    {'name': 'Python', 'license': 'PSF-2.0', 'url': 'https://www.python.org/'},
    {'name': 'CPython interpreter', 'license': 'PSF-2.0',
     'url': 'https://github.com/python/cpython'},
    {'name': 'Tcl/Tk (Tkinter)', 'license': 'BSD-style (Tcl/Tk)',
     'url': 'https://www.tcl.tk/software/tcltk/license.html'},
    {'name': 'CustomTkinter', 'license': 'MIT',
     'url': 'https://github.com/TomSchimansky/CustomTkinter'},
    {'name': 'darkdetect', 'license': 'MIT',
     'url': 'https://github.com/Cascadeapps/darkdetect'},
    {'name': 'OpenSSL (bundled)', 'license': 'Apache-2.0',
     'url': 'https://www.openssl.org/'},
    {'name': 'websockets', 'license': 'BSD-3-Clause', 'url': 'https://github.com/python-websockets/websockets'},
    {'name': 'cryptography', 'license': 'Apache-2.0 OR BSD-3-Clause',
     'url': 'https://github.com/pyca/cryptography'},
    {'name': 'cffi', 'license': 'MIT-0', 'url': 'https://github.com/python-cffi/cffi'},
    {'name': 'pycparser', 'license': 'BSD-3-Clause', 'url': 'https://github.com/eliben/pycparser'},
    {'name': 'mcauth3', 'license': 'MIT', 'url': 'https://github.com/GongSunFangYun/mcauth3'},
    {'name': 'requests', 'license': 'Apache-2.0', 'url': 'https://github.com/psf/requests'},
    {'name': 'urllib3', 'license': 'MIT', 'url': 'https://github.com/urllib3/urllib3'},
    {'name': 'charset-normalizer', 'license': 'MIT',
     'url': 'https://github.com/jawah/charset_normalizer'},
    {'name': 'certifi', 'license': 'MPL-2.0', 'url': 'https://github.com/certifi/python-certifi'},
    {'name': 'idna', 'license': 'BSD-3-Clause', 'url': 'https://github.com/kjd/idna'},
    {'name': 'Flask', 'license': 'BSD-3-Clause', 'url': 'https://github.com/pallets/flask'},
    {'name': 'Werkzeug', 'license': 'BSD-3-Clause', 'url': 'https://github.com/pallets/werkzeug'},
    {'name': 'Jinja2', 'license': 'BSD-3-Clause', 'url': 'https://github.com/pallets/jinja'},
    {'name': 'PyInstaller', 'license': 'GPL-2.0-or-later WITH bootloader-exception',
     'url': 'https://pyinstaller.org/'},
)
