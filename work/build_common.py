"""Shared packaging inputs with repaired artwork and platform decoders."""
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from importlib import metadata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from version import BASE_VERSION, BRANCH, BRANCH_REVISION, VERSION
from fetch_release_assets import ensure_assets, animation_items, animation_paths


def check_python():
    if not (3, 11) <= sys.version_info[:2] <= (3, 13):
        raise SystemExit('本分支构建使用 Python 3.11～3.13；请指定对应解释器。')
    if sys.maxsize <= 2**32:
        raise SystemExit('请使用 64 位 Python。')


def build_inputs(ffmpeg_arg=None, existing_assets=False):
    if not existing_assets:
        ensure_assets()
    assets = ROOT / 'outputs/白龙桌宠素材'
    manifest_path = assets / '素材清单.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    items = animation_items(manifest)
    paths = animation_paths(manifest)
    for path in paths:
        if not (assets / path).is_file():
            raise SystemExit(f'缺少动画素材：{path}')
    for item in items:
        item.pop('source', None)
    ffmpeg = None
    if any(Path(p).suffix.lower() == '.webm' for p in paths):
        explicit = ffmpeg_arg or os.environ.get('BAILONG_BUILD_FFMPEG')
        if explicit:
            ffmpeg = Path(explicit).expanduser().resolve()
        elif sys.platform == 'darwin':
            # macOS 本地与 CI 默认使用精简解码器；首次构建自动编译，后续复用。
            arch = {'aarch64': 'arm64', 'amd64': 'x86_64'}.get(platform.machine().lower(), platform.machine().lower())
            ffmpeg = ROOT / '.build/ffmpeg' / f'darwin-{arch}' / 'bin/ffmpeg'
            if not ffmpeg.is_file():
                print('首次构建：编译 macOS 精简 FFmpeg…', flush=True)
                subprocess.run([sys.executable, str(ROOT / 'work/build_minimal_ffmpeg.py')], check=True)
        else:
            local = ROOT / 'tools' / ('ffmpeg.exe' if sys.platform == 'win32' else 'ffmpeg')
            if local.is_file():
                ffmpeg = local
            else:
                # imageio-ffmpeg wheels carry a binary for the build host.
                import imageio_ffmpeg
                ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve()
        if not ffmpeg.is_file():
            raise SystemExit(f'找不到构建用 FFmpeg：{ffmpeg}')
        result = subprocess.run([str(ffmpeg), '-hide_banner', '-decoders'],
                                capture_output=True, text=True, check=True)
        if not any(line.split()[1:2] == ['libvpx-vp9'] for line in result.stdout.splitlines()):
            raise SystemExit(f'FFmpeg 不含 libvpx-vp9 解码器：{ffmpeg}')
        print(f'打包 FFmpeg：{ffmpeg}', flush=True)
    return assets, manifest, paths, ffmpeg


def copy_resources(destination, inputs):
    assets, manifest, paths, _ = inputs
    target = destination / 'outputs/白龙桌宠素材'
    target.mkdir(parents=True, exist_ok=True)
    for relative in sorted(paths):
        output = target / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(assets / relative, output)
    (target / '素材清单.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
    shutil.copytree(ROOT / 'app/sounds', destination / 'app/sounds', dirs_exist_ok=True)
    for name in ('README.md', 'CHANGELOG.md', 'ASSETS.md', 'BUILDING.md', 'DEVELOPMENT.md', '优化说明.md'):
        shutil.copy2(ROOT / name, destination / name)
    (destination / 'docs').mkdir(exist_ok=True)
    for name in ('原作者版本改动对照.md', '修复素材备选包.md'):
        shutil.copy2(ROOT / 'docs' / name, destination / 'docs' / name)
    (destination / 'VERSION.txt').write_text(VERSION + '\n', encoding='utf-8')
    licenses = destination / 'licenses'
    licenses.mkdir(exist_ok=True)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if python_license.is_file():
        shutil.copy2(python_license, licenses / 'Python.txt')
    for name in ('PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6',
                 'Pillow', 'psutil', 'PyInstaller'):
        package = metadata.distribution(name)
        for relative in package.files or []:
            if 'license' in str(relative).lower() or 'copying' in str(relative).lower():
                source = package.locate_file(relative)
                if source.is_file():
                    target = licenses / name / Path(relative)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    shutil.copy2(ROOT / 'app/sounds/Kenney-License.txt', licenses / 'Kenney-License.txt')


def place_ffmpeg(output, target, source):
    """Expose the decoder at its runtime path without duplicating its bytes."""
    resources = output / 'Contents/Resources' if target == 'macos' else output
    collected = (resources if target == 'macos' else output / '_internal') / 'tools' / source.name
    bundled = resources / 'tools' / ('ffmpeg.exe' if target == 'windows' else 'ffmpeg')
    bundled.parent.mkdir(exist_ok=True)
    if collected.resolve() == bundled.resolve():
        return
    if target == 'windows':
        # The existing Windows runtime already launches tools/ffmpeg.exe.
        collected.replace(bundled)
    else:
        # Keep PyInstaller's library-relative paths and macOS bundle layout intact.
        bundled.symlink_to(os.path.relpath(collected, bundled.parent))


def build_desktop(target, ffmpeg_arg=None, existing_assets=False):
    expected = {'windows': 'win32', 'macos': 'darwin'}[target]
    if sys.platform != expected:
        raise SystemExit(f'{target} 包必须在对应系统构建，不支持交叉编译。')
    check_python()
    inputs = build_inputs(ffmpeg_arg, existing_assets=existing_assets)
    arch = platform.machine().lower()
    arch = {'amd64': 'x86_64', 'x64': 'x86_64', 'aarch64': 'arm64'}.get(arch, arch)
    if target == 'windows':
        dist = ROOT / 'dist-windows' / f'build-v{VERSION}'
        work = ROOT / '.build/work/windows' / f'work-v{VERSION}'
    else:
        dist = ROOT / 'dist-macos'
        work = ROOT / '.build/work' / target / arch
    options = ['--noconfirm', '--clean', '--onedir', '--name', 'BailongPet',
               '--distpath', str(dist), '--workpath', str(work), '--specpath', str(work),
               '--hidden-import', 'autostart', '--hidden-import', 'selftest',
               '--hidden-import', 'version']
    options += ['--hidden-import', 'PySide6.QtMultimedia']
    if target == 'windows':
        options += ['--additional-hooks-dir', str(ROOT / 'work/hooks/windows'),
                    '--exclude-module', 'PIL.AvifImagePlugin', '--exclude-module', 'PIL._avif']
    options.append('--windowed')
    from build_icons import build_icon
    options += ['--icon', str(build_icon(target))]
    if target == 'macos':
        options += ['--osx-bundle-identifier', 'com.bailongpet.desktop',
                    '--hidden-import', 'mac_autostart', '--hidden-import', 'AppKit',
                    '--hidden-import', 'Quartz']
    if inputs[3]:
        options += ['--add-binary', f'{inputs[3]}:tools']
    import PyInstaller.__main__
    PyInstaller.__main__.run(options + [str(ROOT / 'app/pet.py')])
    output = dist / ('BailongPet.app' if target == 'macos' else 'BailongPet')
    resources = output / 'Contents/Resources' if target == 'macos' else output
    copy_resources(resources, inputs)
    if inputs[3]:
        place_ffmpeg(output, target, inputs[3])
        decoder_dir = inputs[3].parent
        metadata = decoder_dir / 'ffmpeg-build.json'
        if metadata.is_file():
            shutil.copy2(metadata, resources / 'tools/ffmpeg-build.json')
            shutil.copytree(decoder_dir / 'ffmpeg-licenses', resources / 'tools/ffmpeg-licenses',
                            dirs_exist_ok=True)
    info = {'version': VERSION, 'branch': BRANCH, 'platform': target, 'architecture': arch,
            'python': platform.python_version(),
            'animationFiles': len(inputs[2]), 'validation': 'built; runtime acceptance pending'}
    (resources / 'BUILD_INFO.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
    if target == 'macos':
        import plistlib
        plist = output / 'Contents/Info.plist'
        data = plistlib.loads(plist.read_bytes())
        data.update(LSUIElement=True, CFBundleShortVersionString=BASE_VERSION,
                    CFBundleVersion=str(BRANCH_REVISION), BailongBranchVersion=VERSION)
        plist.write_bytes(plistlib.dumps(data))
        subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(output)], check=True)
    size = sum(path.stat().st_size for path in output.rglob('*')
               if not path.is_symlink() and path.is_file())
    print(f'构建完成：{output}\n目录体积：{size / 2**20:.2f} MiB', flush=True)
    return output


if __name__ == '__main__':
    check_python()
