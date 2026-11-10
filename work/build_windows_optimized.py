"""Build a complete Windows onedir folder, including assets and FFmpeg."""
import argparse
from pathlib import Path
import platform
import shutil
from build_common import build_desktop
from version import VERSION


def archive_build(output):
    """Archive the freshly built directory, without running the legacy release script."""
    arch = platform.machine().lower()
    arch = {'amd64': 'x86_64', 'x64': 'x86_64', 'aarch64': 'arm64'}.get(arch, arch)
    name = output.parent.parent / f'bailong-desktop-pet-v{VERSION}-windows-{arch}'
    name.parent.mkdir(parents=True, exist_ok=True)
    archive = Path(shutil.make_archive(str(name), 'zip', root_dir=output.parent,
                                      base_dir=output.name))
    print(f'本地 ZIP：{archive}', flush=True)
    return archive


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg', help='本机 FFmpeg 可执行文件路径')
    parser.add_argument('--zip', action='store_true', help='构建完成后生成本地 ZIP')
    parser.add_argument('--existing-assets', action='store_true', help='使用已安装的完整素材，不下载或替换动画')
    args = parser.parse_args(argv)
    output = build_desktop('windows', ffmpeg_arg=args.ffmpeg, existing_assets=args.existing_assets)
    if args.zip:
        archive_build(output)


if __name__ == '__main__':
    main()
