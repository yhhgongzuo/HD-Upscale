"""Prepare only the current platform from bundled, hash-verified resources."""
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def verify_bundle():
    manifest = ROOT / 'MANIFEST.sha256.json'
    if not manifest.is_file():
        raise RuntimeError('完整性清单缺失，请重新完整解压安装包。')
    records = json.loads(manifest.read_text(encoding='utf-8'))['files']
    for relative, expected in records.items():
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file() or digest(path) != expected:
            raise RuntimeError('安装包文件缺失或校验失败：' + relative)


def system_key():
    machine = platform.machine().lower()
    arch = {'amd64': 'x86_64', 'x86_64': 'x86_64', 'arm64': 'aarch64', 'aarch64': 'aarch64'}.get(machine)
    system = {'win32': 'windows', 'darwin': 'macos', 'linux': 'linux'}.get(sys.platform)
    if not system or not arch or (system == 'windows' and arch != 'x86_64'):
        raise RuntimeError('当前系统/芯片没有匹配的离线资源：' + sys.platform + '/' + machine)
    return system + '-' + arch


def cache_dir(key):
    explicit = os.environ.get('AHUI_HD_CACHE')
    if explicit:
        base = Path(explicit).expanduser()
    elif sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'ahui-hd-upscale'
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library/Caches/ahui-hd-upscale'
    else:
        base = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'ahui-hd-upscale'
    target = (base / 'v1' / key).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target


def extract_tar(source, target):
    with tarfile.open(source) as archive:
        archive.extractall(target, filter='data')


def unpack_engine(resource, state, key):
    target = state / ('art-' + resource['sha256'][:16])
    marker = target / '.ready'
    if not marker.is_file():
        with tempfile.TemporaryDirectory(prefix='art-stage-', dir=state) as td:
            stage = Path(td)
            if key.startswith('macos-'):
                mount = stage / 'mount'
                mount.mkdir()
                proc = subprocess.run(['hdiutil', 'attach', '-readonly', '-nobrowse', '-plist', '-mountpoint', str(mount), str(resource['path'])], capture_output=True, timeout=120)
                if proc.returncode:
                    raise RuntimeError('ART 镜像无法挂载：' + proc.stderr.decode('utf-8', errors='replace')[-1200:])
                try:
                    plistlib.loads(proc.stdout)
                    apps = list(mount.glob('*.app'))
                    if len(apps) != 1:
                        raise RuntimeError('ART 镜像中的应用目录不符合预期。')
                    prepared = stage / 'prepared'
                    prepared.mkdir()
                    subprocess.run(['ditto', str(apps[0]), str(prepared / apps[0].name)], check=True, capture_output=True, timeout=180)
                finally:
                    subprocess.run(['hdiutil', 'detach', str(mount)], capture_output=True, timeout=60, check=True)
            else:
                prepared = stage / 'prepared'
                prepared.mkdir()
                extract_tar(resource['path'], prepared)
            # Atomically publish a complete version; never remove an unrelated directory.
            (prepared / '.ready').write_text(resource['sha256'], encoding='ascii')
            if target.exists():
                raise RuntimeError('发现不完整缓存，请选择新的 AHUI_HD_CACHE 路径后重试：' + str(target))
            prepared.rename(target)
    candidates = sorted(p for p in target.rglob('ART-cli') if p.is_file())
    if not candidates:
        raise RuntimeError('ART 离线资源中未找到命令行入口。')
    # Prefer the official launcher over an internal executable.
    candidates.sort(key=lambda p: (len(p.parts), str(p)))
    return candidates[0]


def prepare():
    key = system_key()
    state = cache_dir(key)
    legacy = ROOT / 'assets/legacy-doubao/assets/art-fixed-enhance-win64'
    context = {'root': ROOT, 'key': key, 'state': state, 'preset': legacy / 'preset', 'legacy': legacy}
    if key == 'windows-x86_64':
        context['engine'] = legacy / 'engine/ART-cli.exe'
        if not context['engine'].is_file():
            raise RuntimeError('Windows ART 资源缺失，请重新完整解压安装包。')
        return context
    rows = json.loads((ROOT / 'assets/resources.json').read_text(encoding='utf-8'))
    chosen = {}
    for entry in rows:
        if entry['platform'] != key:
            continue
        entry = dict(entry)
        entry['path'] = ROOT / 'assets/platforms' / key / entry['filename']
        if digest(entry['path']) != entry['sha256']:
            raise RuntimeError('离线资源校验失败：' + entry['filename'])
        chosen[entry['kind']] = entry
    if set(chosen) != {'python', 'pillow', 'art'}:
        raise RuntimeError('当前系统离线资源不完整。')
    wheel = chosen['pillow']
    vendor = state / ('pillow-' + wheel['sha256'][:16])
    if not (vendor / '.ready').is_file():
        with tempfile.TemporaryDirectory(prefix='pillow-stage-', dir=state) as td:
            stage = Path(td)
            with zipfile.ZipFile(wheel['path']) as archive:
                for name in archive.namelist():
                    if not (stage / name).resolve().is_relative_to(stage.resolve()):
                        raise RuntimeError('Pillow 资源存在异常路径。')
                archive.extractall(stage)
            (stage / '.ready').write_text(wheel['sha256'], encoding='ascii')
            if vendor.exists():
                raise RuntimeError('Pillow 缓存不完整，请更换 AHUI_HD_CACHE。')
            stage.rename(vendor)
    sys.path.insert(0, str(vendor))
    context['engine'] = unpack_engine(chosen['art'], state, key)
    return context


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    try:
        if len(sys.argv) > 1 and sys.argv[1] == 'doctor':
            verify_bundle()
        context = prepare()
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import pipeline
        raise SystemExit(pipeline.main(context))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, tarfile.TarError, zipfile.BadZipFile, ImportError) as exc:
        print(json.dumps({'ok': False, 'ready': False, 'installation_status': 'blocked', 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
