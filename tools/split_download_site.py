from __future__ import annotations

import json
import shutil
from pathlib import Path

main_site = Path(r'D:\桌面\版本更新检查')
download_site = Path(r'D:\桌面\版本更新检查-下载')
download_root = download_site / 'downloads'
app_root = Path(r'D:\桌面\服务器协议转换')
release_dir = app_root / '发布文件'

download_site.mkdir(parents=True, exist_ok=True)
download_root.mkdir(parents=True, exist_ok=True)

exe_main = main_site / 'downloads' / 'Server Protocol Bridge.exe'
exe_release = release_dir / 'Server Protocol Bridge.exe'
exe_app = app_root / 'dist' / 'Server Protocol Bridge.exe'
source_main = main_site / 'downloads' / 'ServerProtocolBridge-1.1.5.2-source.zip'
source_release = release_dir / 'ServerProtocolBridge-1.1.5.2-source.zip'
source_app = app_root / 'ServerProtocolBridge-1.1.5.2-source.zip'

# Move/copy final artifacts into the standalone download site.
for source, destination in (
    (exe_main, download_root / 'Server Protocol Bridge.exe'),
    (exe_release, download_root / 'Server Protocol Bridge.exe'),
    (exe_app, download_root / 'Server Protocol Bridge.exe'),
    (source_main, download_root / 'ServerProtocolBridge-1.1.5.2-source.zip'),
    (source_release, download_root / 'ServerProtocolBridge-1.1.5.2-source.zip'),
    (source_app, download_root / 'ServerProtocolBridge-1.1.5.2-source.zip'),
):
    if source.is_file():
        shutil.copy2(source, destination)

# Remove binary downloads from the main website so it remains only the static UI/API.
main_downloads = main_site / 'downloads'
if main_downloads.is_dir():
    shutil.rmtree(main_downloads)

# A minimal index for the standalone download site. This makes the upload target
# a normal static website instead of a bare folder.
(download_site / 'index.html').write_text(
    '<!doctype html>\n'
    '<html lang="en">\n'
    '<head>\n'
    '  <meta charset="utf-8">\n'
    '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
    '  <title>Server Protocol Bridge Downloads</title>\n'
    '  <style>\n'
    '    body{margin:0;font-family:Arial,Helvetica,sans-serif;color:#1f2937;background:#f5f7fb}\n'
    '    header{background:#0b3d91;color:white;padding:24px}\n'
    '    main{max-width:900px;margin:24px auto;padding:0 18px}\n'
    '    a{display:block;background:white;border:1px solid #d7deea;border-radius:12px;padding:18px;margin:14px 0;text-decoration:none;color:#0b3d91;box-shadow:0 1px 3px rgba(0,0,0,.06)}\n'
    '    a strong{display:block;font-size:16px;margin-bottom:6px}\n'
    '    a span{color:#526173;font-size:13px}\n'
    '  </style>\n'
    '</head>\n'
    '<body>\n'
    '  <header><h1>Server Protocol Bridge 1.1.5.1</h1><p>Download artifacts</p></header>\n'
    '  <main>\n'
    '    <a href="downloads/Server%20Protocol%20Bridge.exe"><strong>Server Protocol Bridge.exe</strong><span>Windows 10/11 x64 single-file executable</span></a>\n'
    '    <a href="downloads/ServerProtocolBridge-1.1.5.1-source.zip"><strong>ServerProtocolBridge-1.1.5.1-source.zip</strong><span>Source package</span></a>\n'
    '  </main>\n'
    '</body>\n'
    '</html>\n',
    encoding='utf-8',
)

# Record how the site should reference this download site once its domain is known.
# The domain is unknown until uploaded, so leave the placeholder explicit.
manifest = main_site / 'api' / 'version.json'
data = json.loads(manifest.read_text(encoding='utf-8-sig'))
data['download_base_url'] = 'https://YOUR-DOWNLOAD-PAGES-DOMAIN/'
data['download_url'] = '/downloads/Server%20Protocol%20Bridge.exe'
data['source_url'] = '/downloads/ServerProtocolBridge-1.1.5.1-source.zip'
manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

print('download site:', download_site)
for item in sorted(download_root.iterdir()):
    print(' ', item.name, item.stat().st_size)
print('main downloads removed:', not (main_site / 'downloads').exists())
print('manifest download_base_url:', data.get('download_base_url'))
