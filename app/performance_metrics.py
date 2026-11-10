"""On-demand counters for the Qt diagnostics window; no polling at import time."""
import ctypes as C
import os
import sys
import time
from pathlib import Path
from dataclasses import dataclass

import psutil


class PlaybackStatistics:
    def __init__(self, now):
        self.last_time = now
        self.last_frame = None
        self.frames = self.draws = self.total = 0
        self.high = self.low = None

    def record(self, key):
        self.draws += 1
        if key != self.last_frame:
            self.frames += 1
            self.total += 1
            self.last_frame = key

    def sample(self, now):
        elapsed = now - self.last_time
        fps, draws = self.frames / elapsed, self.draws / elapsed
        self.high = fps if self.high is None else max(self.high, fps)
        self.low = fps if self.low is None else min(self.low, fps)
        self.frames = self.draws = 0
        self.last_time = now
        return fps, draws


class TaskVMInfo(C.Structure):
    # mach/task_info.h uses 4-byte packing, including ledger_swapins (rev6).
    _pack_ = 4
    _fields_ = [('virtual_size', C.c_uint64), ('region_count', C.c_int32),
                ('page_size', C.c_int32)] + [
        (name, C.c_uint64) for name in (
            'resident_size', 'resident_size_peak', 'device', 'device_peak',
            'internal', 'internal_peak', 'external', 'external_peak',
            'reusable', 'reusable_peak', 'purgeable_volatile_pmap',
            'purgeable_volatile_resident', 'purgeable_volatile_virtual',
            'compressed', 'compressed_peak', 'compressed_lifetime',
            'phys_footprint', 'min_address', 'max_address')
    ] + [('ledgers', C.c_int64 * 21), ('limit_bytes_remaining', C.c_uint64),
         ('decompressions', C.c_int32), ('ledger_swapins', C.c_int64)]


class RUsageInfoV0(C.Structure):
    # Public sys/resource.h RUSAGE_INFO_V0, supported since macOS 10.9.
    _fields_ = [('uuid', C.c_uint8 * 16)] + [
        (name, C.c_uint64) for name in (
            'user_time', 'system_time', 'pkg_idle_wkups', 'interrupt_wkups',
            'pageins', 'wired_size', 'resident_size', 'phys_footprint',
            'proc_start_abstime', 'proc_exit_abstime')]


class MacCounters:
    def __init__(self):
        self.lib = C.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
        self.task = C.c_uint32.in_dll(self.lib, 'mach_task_self_').value
        self.lib.task_info.argtypes = [C.c_uint32, C.c_uint32, C.c_void_p,
                                       C.POINTER(C.c_uint32)]
        self.lib.task_info.restype = C.c_int
        self.lib.proc_pidinfo.argtypes = [C.c_int, C.c_int, C.c_uint64,
                                         C.c_void_p, C.c_int]
        self.lib.proc_pidinfo.restype = C.c_int
        self.lib.proc_pid_rusage.argtypes = [C.c_int, C.c_int, C.c_void_p]
        self.lib.proc_pid_rusage.restype = C.c_int
        self.gpu_usage = getattr(self.lib, 'coalition_info_resource_usage', None)
        if self.gpu_usage is not None:
            self.gpu_usage.argtypes = [C.c_uint64, C.c_void_p, C.c_size_t]
            self.gpu_usage.restype = C.c_int

    def memory(self):
        info = TaskVMInfo()
        count = C.c_uint32(C.sizeof(info) // 4)
        status = self.lib.task_info(self.task, 22, C.byref(info), C.byref(count))
        if status:
            raise OSError(f'task_info 错误 {status}')
        if count.value * 4 < TaskVMInfo.phys_footprint.offset + 8:
            raise OSError('系统未返回 phys_footprint')
        swapins = None
        if count.value * 4 >= TaskVMInfo.ledger_swapins.offset + 8:
            if info.ledger_swapins >= 0:
                swapins = info.ledger_swapins
        return info.phys_footprint, info.compressed, swapins

    def process_footprint(self, pid):
        info = RUsageInfoV0()
        if self.lib.proc_pid_rusage(pid, 0, C.byref(info)):
            code = C.get_errno()
            raise OSError(code, os.strerror(code))
        return info.phys_footprint

    def gpu(self):
        # Same application-coalition scope as the Swift window. Never report
        # system-wide GPU utilization as this application's utilization.
        if self.gpu_usage is None:
            raise OSError('系统缺少资源组接口')
        ids = (C.c_uint64 * 5)()
        received = self.lib.proc_pidinfo(os.getpid(), 20, 0, ids, C.sizeof(ids))
        if received != C.sizeof(ids):
            raise OSError(f'读取应用组失败：返回 {received}，errno {C.get_errno()}')
        if not ids[0]:
            raise OSError('进程没有资源组')
        prefix = (C.c_uint64 * 9)()
        if self.gpu_usage(ids[0], prefix, C.sizeof(prefix)):
            raise OSError(f'读取 GPU 时间失败：errno {C.get_errno()}')
        return ids[0], prefix[8]


@dataclass
class ProcessSnapshot:
    at: float
    cpu: float | None = None
    ram: int | None = None
    compressed: int | None = None
    swapins: int | None = None
    process_swap: int | None = None
    private_commit: int | None = None
    process_swap_error: str = ''
    gpu: tuple | None = None
    cpu_error: str = ''
    memory_error: str = ''
    gpu_status: str = '当前平台未接入 GPU 计数'


class ProcessStatistics:
    def __init__(self):
        self.platform = sys.platform
        self.process = psutil.Process()
        self.cores = psutil.cpu_count() or 1
        self.mac = MacCounters() if sys.platform == 'darwin' else None

    def read(self):
        result = ProcessSnapshot(at=time.monotonic())
        try:
            cpu = self.process.cpu_times()
            result.cpu = cpu.user + cpu.system
        except (psutil.Error, OSError) as error:
            result.cpu_error = str(error)
        try:
            if self.mac:
                result.ram, result.compressed, result.swapins = self.mac.memory()
            else:
                memory = self.process.memory_info()
                result.ram = memory.rss
                if self.platform == 'win32':
                    result.private_commit = memory.private
        except (psutil.Error, OSError) as error:
            result.memory_error = str(error)
        if self.platform.startswith('linux'):
            try:
                result.process_swap = linux_process_swap(self.process.pid)
            except OSError as error:
                result.process_swap_error = str(error)
        if self.mac:
            try:
                result.gpu = self.mac.gpu()
                result.gpu_status = '等待采样'
            except OSError as error:
                result.gpu_status = str(error)
        return result


def byte_text(value):
    if value is None:
        return '未提供'
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if value < 1024 or unit == 'TiB':
            return f'{value:.1f} {unit}'
        value /= 1024


def linux_process_swap(pid):
    """Current anonymous private swap, excluding shared memory (proc status)."""
    for line in Path(f'/proc/{pid}/status').read_text().splitlines():
        if line.startswith('VmSwap:'):
            fields = line.split()
            if len(fields) == 3 and fields[1].isdigit() and fields[2] == 'kB':
                return int(fields[1]) * 1024
            raise OSError('VmSwap 格式错误')
    raise OSError('系统未返回 VmSwap')


def process_paging_rows(snapshot, platform):
    if platform == 'win32':
        return [('主进程私有提交', snapshot.memory_error or
                 f'{byte_text(snapshot.private_commit)}（仅供参考）')]
    if platform == 'darwin':
        if snapshot.swapins is None:
            value = snapshot.memory_error or '系统未返回换入计数'
        elif snapshot.swapins > 0:
            value = f'有换入记录 · 累计 {byte_text(snapshot.swapins)}'
        else:
            value = '暂无换入记录'
        return [('主进程 Swap 换入', value)]
    if platform.startswith('linux'):
        if snapshot.process_swap is None:
            value = snapshot.process_swap_error or '系统未返回 VmSwap'
        elif snapshot.process_swap > 0:
            value = f'当前已换出 {byte_text(snapshot.process_swap)}'
        else:
            value = '当前无换出页'
        return [('主进程 Swap', value)]
    return []


def frame_cache_statistics(pet):
    # Count shared QPixmap storage only once; do not copy pixels into QImage.
    seen = set()
    size = 0
    for frame in pet.frames + ([pet.reference_frame] if pet.reference_frame else []):
        key = frame.cacheKey()
        if key not in seen:
            seen.add(key)
            size += frame.width() * frame.height() * frame.depth() // 8
    buffered=pet.stream.statistics()
    transition=getattr(pet,'transition',None)
    if transition:size+=transition.previous.sizeInBytes()
    clips={pet.current['id']} if pet.current else set()
    if pet.display_item:clips.add(pet.display_item['id'])
    if pet.reference_frame:clips.add(pet.idles[0]['id'])
    return size+buffered['bytes'],len(clips),len(seen)+buffered['buffered']
