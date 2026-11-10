# Keep the author's base version; local.N identifies this private Windows build.
import platform
import sys

BASE_VERSION = '0.5.1'
BRANCH = 'local/windows'
BRANCH_REVISION = 4
VERSION = f'{BASE_VERSION}-local.{BRANCH_REVISION}'


def platform_version():
    name = {'win32': 'Windows', 'darwin': 'macOS', 'linux': 'Linux'}.get(sys.platform, sys.platform)
    machine = platform.machine().lower()
    machine = {'amd64': 'x86_64', 'x64': 'x86_64', 'aarch64': 'arm64'}.get(machine, machine)
    return f'{VERSION} · {name} · {machine}'
