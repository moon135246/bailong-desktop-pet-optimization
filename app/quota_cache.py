"""Persist only quota display values, invalidating them when login data changes."""
import json
import math
import os
from pathlib import Path
import time

QUOTA_TTL = 60
QUOTA_REFRESH_INTERVAL_MS = 300_000
QUOTA_RETRY_SECONDS = 15


def account_revision():
    home = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex')
    try:
        stat = (home / 'auth.json').stat()
        return [stat.st_mtime_ns, stat.st_size]
    except OSError:
        return None


def validate_windows(windows):
    if not isinstance(windows, list) or not 1 <= len(windows) <= 8:
        raise ValueError('额度窗口数据无效')
    result = []
    for window in windows:
        if not isinstance(window, dict) or not isinstance(window.get('name'), str):
            raise ValueError('额度窗口数据无效')
        remaining = window.get('remaining')
        if remaining is not None:
            remaining = float(remaining)
            if not math.isfinite(remaining) or not 0 <= remaining <= 100:
                raise ValueError('额度数值无效')
        reset = window.get('resetsAt')
        if reset is not None:
            reset = float(reset)
            if not math.isfinite(reset) or reset < 0 or reset > 32_503_680_000:
                raise ValueError('额度重置时间无效')
        result.append({'name': window['name'][:40], 'remaining': remaining, 'resetsAt': reset})
    return result


class QuotaCache:
    def __init__(self, path, clock=time.time, revision=account_revision):
        self.path = Path(path)
        self.clock = clock
        self.revision = revision
        self.windows = []
        self.updated_at = None
        self.account = revision()
        self.storage_error = None
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            updated = float(data['updatedAt'])
            if data.get('accountRevision') == self.account and 0 < updated <= clock() + 5:
                self.windows = validate_windows(data['windows'])
                self.updated_at = updated
        except (OSError, ValueError, TypeError, KeyError):
            pass

    def validate_account(self):
        account = self.revision()
        if account != self.account:
            self.windows = []
            self.updated_at = None
            self.account = account

    def fresh(self):
        self.validate_account()
        return bool(self.windows and self.updated_at is not None
                    and 0 <= self.clock() - self.updated_at < QUOTA_TTL
                    and not any(w['resetsAt'] and w['resetsAt'] <= self.clock()
                                for w in self.windows))

    def update(self, windows):
        self.windows = validate_windows(windows)
        self.updated_at = self.clock()
        self.account = self.revision()
        self.storage_error = None
        temporary = self.path.with_name(self.path.name + f'.{os.getpid()}.tmp')
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps({'updatedAt': self.updated_at,
                'accountRevision': self.account, 'windows': self.windows},
                ensure_ascii=False, allow_nan=False), encoding='utf-8')
            os.replace(temporary, self.path)
        except OSError as error:
            # A failed disk write must not discard a successful live response.
            self.storage_error = str(error)
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
