"""Shared performance defaults and validation for every desktop platform."""

DEFAULT_RESOLUTION = 0
DEFAULT_BUFFER_FRAMES = 12
DEFAULT_FPS_LIMIT = 'full'
FPS_LIMITS = ('full', '20', '15')
RESOLUTIONS = (0, 720, 512, 384, 256)
MIN_BUFFER_FRAMES = 6
MAX_BUFFER_FRAMES = 240
WARM_CACHE_BYTES = 24 * 1024 * 1024
WARM_CACHE_FRAMES = 6
PERFORMANCE_PRESETS = (
    ('省内存', (256, 6, 'full', False)),
    ('均衡', (0, 12, 'full', False)),
    ('高清', (720, 24, 'full', False)),
)


def read_performance_preferences(settings):
    def integer(key, default):
        try:
            return int(settings.value(key, default))
        except (TypeError, ValueError, OverflowError):
            return default

    resolution = integer('animationResolution', DEFAULT_RESOLUTION)
    if resolution not in RESOLUTIONS:
        resolution = DEFAULT_RESOLUTION
    capacity = integer('animationBufferFrames', DEFAULT_BUFFER_FRAMES)
    if not MIN_BUFFER_FRAMES <= capacity <= MAX_BUFFER_FRAMES:
        capacity = DEFAULT_BUFFER_FRAMES
    fps_limit = str(settings.value('animationFPSLimit', DEFAULT_FPS_LIMIT))
    if fps_limit not in FPS_LIMITS:
        fps_limit = DEFAULT_FPS_LIMIT
    preload = settings.value('preloadWholeAnimation', False, type=bool)
    return resolution, capacity, fps_limit, preload


def decode_size(resolution, device_pixel_ratio, logical_size=256):
    # Match the actual window's physical size, capped at the source resolution.
    return resolution or min(720, max(128, round(logical_size * device_pixel_ratio / 16) * 16))


def fps_cap(limit):
    return None if limit == 'full' else int(limit)
