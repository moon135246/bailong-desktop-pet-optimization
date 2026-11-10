"""Build a complete Windows onedir folder, including assets and FFmpeg."""
import argparse
from pathlib import Path
import platform
import shutil
import zipfile
from build_common import build_desktop
from version import VERSION


def archive_build(output):
    """Archive the freshly built directory, without running the legacy release script."""
    forbidden={'auth.json','conversations.json','conversations.tmp','quota-cache.json',
               '运行状态.json','自启动状态.json','显示诊断.json','检查报告.json',
               '额度接口检查报告.json','对话接口检查报告.json','本机验证结果.json',
               '检查预览.png','桌宠窗口预览.png'}
    forbidden={name.casefold() for name in forbidden}
    for path in output.rglob('*'):
        if path.is_file() and (path.name.casefold() in forbidden or path.suffix.casefold() in ('.jsonl','.log')
                              or any(part in ('.git','__pycache__') or part.startswith(('.venv','.build'))
                                     for part in path.relative_to(output).parts)):
            raise RuntimeError(f'运行目录包含本机状态或检查产物，不能打包：{path.relative_to(output)}')
    arch = platform.machine().lower()
    arch = {'amd64': 'x86_64', 'x64': 'x86_64', 'aarch64': 'arm64'}.get(arch, arch)
    name = output.parent.parent / f'bailong-desktop-pet-v{VERSION}-windows-{arch}'
    name.parent.mkdir(parents=True, exist_ok=True)
    archive = Path(shutil.make_archive(str(name), 'zip', root_dir=output.parent,
                                      base_dir=output.name))
    with zipfile.ZipFile(archive) as bundle:
        bad=bundle.testzip()
        if bad:raise RuntimeError(f'ZIP 校验失败：{bad}')
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
