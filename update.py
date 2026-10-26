"""Fetch an official alpha package without touching the running installation."""
import hashlib
import json
from pathlib import Path
import tempfile
import urllib.request
import zipfile

API = 'https://api.github.com/repos/Kokunekosan/N8Vision/releases?per_page=100'


def choose_release(releases):
    for release in releases:
        if release.get('draft'):
            continue
        for asset in release.get('assets', []):
            name = asset.get('name', '')
            if name.startswith('N8Vision-Alpha-') and name.endswith('.zip'):
                return release, asset
    raise ValueError('No complete official package found')


def fetch_package(asset, folder, opener=urllib.request.urlopen):
    name = asset['name']
    if Path(name).name != name or '/' in name or '\\' in name:
        raise ValueError('Invalid package filename')
    folder.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=folder, suffix='.part', delete=False) as output:
            temporary = Path(output.name)
            digest = hashlib.sha256()
            with opener(asset['browser_download_url'], timeout=60) as response:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
        if temporary.stat().st_size != int(asset['size']):
            raise ValueError('Incomplete download')
        expected = asset.get('digest')
        if expected and expected != 'sha256:' + digest.hexdigest():
            raise ValueError('Package checksum mismatch')
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise ValueError('Damaged package')
        target = folder / name
        temporary.replace(target)
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    root = Path(__file__).resolve().parent
    current = json.loads((root / 'SOURCE-MANIFEST.json').read_text(encoding='utf-8')).get('release', 'unknown')
    request = urllib.request.Request(API, headers={'User-Agent': 'N8Vision-updater', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        release, asset = choose_release(json.load(response))
    print('Installed:', current)
    print('Available:', release['tag_name'])
    print(release['html_url'])
    if release['tag_name'].removeprefix('v') == current:
        print('You have the current official release.')
        return
    if input('Download the complete package? [y/N] ').strip().lower() != 'y':
        return
    target = fetch_package(asset, root / 'updates')
    print('Downloaded:', target)
    print('Finish active jobs and stop Vision before installing. Preserve .venv, data, cache, models and settings.')
    print('This fetcher has not changed your installation.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Update fetch failed:', error)
        raise SystemExit(1)
