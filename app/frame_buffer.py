"""Bounded streaming plus a byte-limited cache of common clips' opening frames."""
from collections import OrderedDict, deque
from pathlib import Path
import threading

from PIL import Image
from video_frames import rgba_frames
from performance_preferences import (DEFAULT_BUFFER_FRAMES, DEFAULT_RESOLUTION,
    DEFAULT_FPS_LIMIT, WARM_CACHE_BYTES, WARM_CACHE_FRAMES, decode_size, fps_cap)


class FrameBuffer:
    def __init__(self):
        self.condition = threading.Condition()
        self.frames = deque()
        self.generation = 0
        self.request = None
        self.closed = False
        self.paused = False
        self.capacity = DEFAULT_BUFFER_FRAMES
        self.size = decode_size(DEFAULT_RESOLUTION, 1)
        self.duration = 0
        self.rate = self.count = self.error = None
        self.ended = False
        self.preload_whole = False
        self.process = self.prefetch_process = None
        self.common_paths = set()
        self.warm_cache = OrderedDict()
        self.warm_bytes = 0
        self.prefetch = deque(maxlen=6)
        self.active_key = None
        self.cache_hits = 0
        self.worker = threading.Thread(target=self.run, name='pet-frame-decoder', daemon=True)
        self.worker.start()

    @staticmethod
    def key(path, size, fps):
        return str(Path(path)), size, fps

    def set_common_paths(self, paths):
        with self.condition:
            self.common_paths = {str(Path(path)) for path in paths}

    def _remember(self, key, rate, frames):
        if not frames or rate is None or key[0] not in self.common_paths:
            return
        frames = tuple(frames[:WARM_CACHE_FRAMES])
        size = sum(map(len, frames))
        if size > WARM_CACHE_BYTES:
            return
        old = self.warm_cache.pop(key, None)
        if old:
            self.warm_bytes -= sum(map(len, old[1]))
        self.warm_cache[key] = (rate, frames)
        self.warm_bytes += size
        while self.warm_bytes > WARM_CACHE_BYTES:
            _, (_, removed) = self.warm_cache.popitem(last=False)
            self.warm_bytes -= sum(map(len, removed))

    def prepare(self, path, size, duration, fps=None):
        key = self.key(path, size, fps)
        with self.condition:
            if (self.closed or key in self.warm_cache or key == self.active_key
                    or key[0] not in self.common_paths
                    or any(job[0] == key for job in self.prefetch)):
                return
            self.prefetch.append((key, Path(path), size, duration, fps))
            self.condition.notify_all()

    def clear_other_sizes(self, size):
        with self.condition:
            self.warm_cache = OrderedDict((key, value) for key, value in self.warm_cache.items()
                                          if key[1] == size)
            self.warm_bytes = sum(len(raw) for _, frames in self.warm_cache.values() for raw in frames)
            self.prefetch = deque((job for job in self.prefetch if job[2] == size), maxlen=6)

    def play(self, path, size, duration, capacity, fps=fps_cap(DEFAULT_FPS_LIMIT), preload_whole=False):
        key = self.key(path, size, fps)
        with self.condition:
            if self.closed:
                raise RuntimeError('动画解码器已关闭')
            self.generation += 1
            self.frames.clear()
            self.rate = self.count = self.error = None
            self.ended = False
            self.size, self.duration, self.capacity = size, duration, capacity
            self.preload_whole = preload_whole
            self.active_key = key
            cached = self.warm_cache.get(key)
            skip = 0
            if cached:
                self.warm_cache.move_to_end(key)
                self.rate = cached[0]
                self.count = round(duration * self.rate)
                for index, raw in enumerate(cached[1][:capacity]):
                    self.frames.append((index, index / self.rate, raw))
                skip = len(self.frames)
                self.cache_hits += 1
            self.request = (self.generation, Path(path), size, duration, fps, skip)
            for process in (self.process, self.prefetch_process):
                if process and process.poll() is None:
                    process.kill()
            self.process = self.prefetch_process = None
            self.condition.notify_all()

    def pause(self, paused):
        with self.condition:
            self.paused = paused
            self.condition.notify_all()

    def take(self, elapsed):
        with self.condition:
            if self.error:
                raise RuntimeError(self.error)
            if self.preload_whole and not self.ended:
                return None
            result = None
            while self.frames and self.frames[0][1] <= elapsed:
                result = self.frames.popleft()
            if result is not None:
                self.condition.notify_all()
            return result

    def statistics(self):
        with self.condition:
            return dict(buffered=len(self.frames), bytes=sum(len(frame[2]) for frame in self.frames),
                capacity=self.capacity, rate=self.rate, count=self.count, ended=self.ended,
                preloadWhole=self.preload_whole, warmBytes=self.warm_bytes,
                warmClips=len(self.warm_cache), cacheHits=self.cache_hits,
                pid=self.process.pid if self.process and self.process.poll() is None else None)

    def close(self):
        with self.condition:
            if self.closed:
                return
            self.closed = True
            self.generation += 1
            self.request = None
            self.frames.clear()
            self.warm_cache.clear()
            self.warm_bytes = 0
            for process in (self.process, self.prefetch_process):
                if process and process.poll() is None:
                    process.kill()
            self.condition.notify_all()
        self.worker.join(timeout=3)
        if self.worker.is_alive():
            raise RuntimeError('动画解码线程未能结束')

    def process_changed(self, token, process, prefetch=False):
        with self.condition:
            if token == self.generation and not self.closed:
                if prefetch:
                    self.prefetch_process = process
                else:
                    self.process = process
            elif process and process.poll() is None:
                process.kill()

    def rate_changed(self, token, rate):
        with self.condition:
            if token == self.generation:
                self.rate = rate
                self.count = round(self.duration * rate)

    def decode(self, token, path, size, duration, fps):
        if path.suffix.lower() == '.webm':
            yield from rgba_frames(path, size,
                process_changed=lambda process: self.process_changed(token, process),
                rate_changed=lambda rate: self.rate_changed(token, rate), fps=fps)
        else:
            with Image.open(path) as source:
                source_rate = source.n_frames / duration
                output_rate = source_rate if fps is None else min(source_rate, fps)
                self.rate_changed(token, output_rate)
                for index in range(max(1, round(duration * output_rate))):
                    source.seek(min(source.n_frames - 1, int(index * source_rate / output_rate)))
                    yield source.convert('RGBA').resize((size, size), Image.Resampling.LANCZOS).tobytes()

    def _prepare(self, token, job):
        key, path, size, duration, fps = job
        rate = []
        frames = rgba_frames(path, size,
            process_changed=lambda process: self.process_changed(token, process, prefetch=True),
            rate_changed=lambda value: rate.append(value), fps=fps)
        opening = []
        try:
            for _ in range(WARM_CACHE_FRAMES):
                with self.condition:
                    if self.closed or token != self.generation or self.paused:
                        return
                raw = next(frames, None)
                if raw is None:
                    break
                opening.append(raw)
            with self.condition:
                if token == self.generation and not self.closed:
                    self._remember(key, rate[0] if rate else None, opening)
        except (OSError, ValueError, RuntimeError):
            # Optional prefetch never interrupts the current animation.
            pass
        finally:
            frames.close()

    def run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.closed or self.request is not None)
                if self.closed:
                    return
                token, path, size, duration, fps, skip = self.request
                self.request = None
                key = self.key(path, size, fps)
            frames = self.decode(token, path, size, duration, fps)
            index = 0
            opening = []
            try:
                while True:
                    with self.condition:
                        self.condition.wait_for(lambda: self.closed or token != self.generation or
                            (not self.paused and (index < skip or self.preload_whole or
                             len(self.frames) < self.capacity or bool(self.prefetch))))
                        if self.closed or token != self.generation:
                            break
                        job = (self.prefetch.popleft() if self.prefetch and index >= skip
                               and not self.preload_whole and len(self.frames) >= self.capacity else None)
                    if job:
                        with self.condition:
                            cached = job[0] in self.warm_cache
                        if not cached:
                            self._prepare(token, job)
                        continue
                    raw = next(frames, None)
                    with self.condition:
                        if token != self.generation or self.closed:
                            break
                        if raw is None:
                            if not index:
                                raise RuntimeError('动画没有可播放帧：' + str(path))
                            self.count = index
                            self.ended = True
                            break
                        if index < WARM_CACHE_FRAMES and key[0] in self.common_paths:
                            opening.append(raw)
                            if len(opening) == WARM_CACHE_FRAMES:
                                self._remember(key, self.rate, opening)
                        if index >= skip:
                            self.frames.append((index, index / self.rate, raw))
                        index += 1
            except (OSError, ValueError, RuntimeError) as error:
                with self.condition:
                    if token == self.generation and not self.closed:
                        self.error = str(error)
            finally:
                frames.close()
