"""Conservative alpha denoising without blurring connected character details."""
import re

from PIL import Image

# Keep normal antialiasing unchanged; ease out only the faintest codec residue.
ALPHA_CURVE = tuple(0 if value <= 8 else round(value * (value - 8) / 16)
                    if value < 24 else value for value in range(256))
OPAQUE_RUN = re.compile(b'\xff+')


def clean_alpha(alpha):
    """Remove tiny eight-connected islands, retaining larger independent effects."""
    width, height = alpha.size
    alpha = alpha.point(ALPHA_CURVE)
    mask = alpha.point([0] + [255] * 255).tobytes()
    parents = []
    runs = []
    previous = []

    def root(label):
        while parents[label] != label:
            parents[label] = parents[parents[label]]
            label = parents[label]
        return label

    # Scan foreground runs in C, then join touching runs between adjacent rows.
    # Eight-connectivity protects diagonal hair, wing and tail outlines.
    for y in range(height):
        current = []
        start = 0
        offset = y * width
        for match in OPAQUE_RUN.finditer(mask, offset, offset + width):
            left, right = match.start() - offset, match.end() - offset
            label = len(parents)
            parents.append(label)
            while start < len(previous) and previous[start][1] < left:
                start += 1
            index = start
            while index < len(previous) and previous[index][0] <= right:
                above, here = root(previous[index][2]), root(label)
                if above != here:
                    parents[here] = above
                index += 1
            current.append((left, right, label))
            runs.append((label, left, right, y))
        previous = current

    groups = {}
    for label, left, right, y in runs:
        label = root(label)
        group = groups.setdefault(label, [0, left, right, y, y + 1])
        group[0] += right - left
        group[1] = min(group[1], left)
        group[2] = max(group[2], right)
        group[3] = min(group[3], y)
        group[4] = max(group[4], y + 1)

    scale = min(width, height) / 720
    area_limit = max(1, round(16 * scale * scale))
    extent_limit = max(2, round(8 * scale))
    discard = {label for label, (area, left, right, top, bottom) in groups.items()
               if area <= area_limit and right - left <= extent_limit
               and bottom - top <= extent_limit}
    if not discard:
        return alpha
    result = bytearray(alpha.tobytes())
    for label, left, right, y in runs:
        if root(label) in discard:
            result[y * width + left:y * width + right] = b'\0' * (right - left)
    return Image.frombytes('L', alpha.size, bytes(result))


def clean_rgba(raw, size):
    image = Image.frombytes('RGBA', (size, size), raw)
    image.putalpha(clean_alpha(image.getchannel('A')))
    return image.tobytes()
