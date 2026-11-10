"""Short, alpha-correct transitions between similarly aligned animation clips."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

TRANSITION_SECONDS = .2
MIN_SILHOUETTE_OVERLAP = .94


def silhouette_overlap(previous, current):
    masks = []
    for image in (previous, current):
        small = image.scaled(48, 48, Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        rgba = small.convertToFormat(QImage.Format.Format_RGBA8888)
        data = bytes(rgba.constBits())
        masks.append([value >= 96 for value in data[3::4]])
    intersection = sum(a and b for a, b in zip(*masks))
    union = sum(a or b for a, b in zip(*masks))
    return intersection / union if union else 0.0


def blend_frames(previous, current, weight):
    """Interpolate premultiplied RGBA; SourceOver alone would dim the alpha."""
    weight = max(0.0, min(1.0, weight))
    if weight == 0:
        return previous
    if weight == 1:
        return current
    if previous.size() != current.size():
        previous = previous.scaled(current.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
    result = QImage(current.size(), QImage.Format.Format_ARGB32_Premultiplied)
    result.fill(Qt.GlobalColor.transparent)
    incoming = QImage(current.size(), QImage.Format.Format_ARGB32_Premultiplied)
    incoming.fill(Qt.GlobalColor.transparent)
    layer = QPainter(incoming)
    layer.setOpacity(weight)
    layer.drawImage(0, 0, current)
    layer.end()
    painter = QPainter(result)
    painter.setOpacity(1.0 - weight)
    painter.drawImage(0, 0, previous)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    # Plus with painter opacity would clamp before applying that opacity.
    # Weight the incoming layer first, then add it at full painter opacity.
    painter.setOpacity(1.0)
    painter.drawImage(0, 0, incoming)
    painter.end()
    return result


class ClipTransition:
    def __init__(self, previous, duration=TRANSITION_SECONDS):
        self.previous = previous.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        self.duration = duration
        self.started = None

    def begin(self, current, now):
        # Large pose changes are clearer as immediate switches than double images.
        if silhouette_overlap(self.previous, current) < MIN_SILHOUETTE_OVERLAP:
            return False
        self.started = now
        return True

    def progress(self, now):
        if self.started is None:
            return 0.0
        if self.finished(now):
            return 1.0
        value = max(0.0, min(1.0, (now - self.started) / self.duration))
        return value * value * (3.0 - 2.0 * value)

    def finished(self, now):
        return self.started is not None and now >= self.started + self.duration

    def render(self, current, now):
        return blend_frames(self.previous, current, self.progress(now))
