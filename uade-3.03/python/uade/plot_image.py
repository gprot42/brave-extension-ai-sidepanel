import math
from PIL import Image, ImageDraw
import random
from typing import List


COLORS = None
COLOR_MODES = tuple(range(4))

MARGIN = 8


class FrameImage:
    def __init__(self, samples_per_frame: int, pixels_per_sample: int,
                 num_amiga_channels: int):
        self.pixels_per_sample = pixels_per_sample
        self.vertical_dim = 720 // num_amiga_channels - MARGIN
        self.im = Image.new(
            'RGB',
            (samples_per_frame * self.pixels_per_sample,
             (self.vertical_dim + MARGIN) * num_amiga_channels))
        self.px = self.im.load()  # For drawing pixels
        self.im_line = ImageDraw.Draw(self.im)  # For drawing lines


def init_colors(color_mode: int):
    global COLORS

    old_state = random.getstate()
    random.seed(0)

    COLORS = {}
    if color_mode == 0:
        COLORS[0] = (255, 255, 255)
    elif color_mode == 1:
        for i in range(64):
            col = [255, 0, int(256 * random.random())]
            random.shuffle(col)
            COLORS[i] = tuple(col)
    elif color_mode == 2:
        for i in range(64):
            x = int(256 * random.random())
            col = [255, (x * 31) % 128, x]
            random.shuffle(col)
            COLORS[i] = tuple(col)
    elif color_mode == 3:
        for i in range(64):
            col = [0, 0, 0]
            while (col[0] + col[1]) < 64:
                col = [255, 0, int(256 * random.random())]
                random.shuffle(col)
            COLORS[i] = tuple(col)
    else:
        raise ValueError('Invalid color mode: {}'.format(color_mode))

    random.setstate(old_state)


def plot_channel(fi: FrameImage, channel: int, signal: List[float],
                 channel_meta: List[int]):
    base_y = channel * (fi.vertical_dim + MARGIN) + fi.vertical_dim // 2

    for x in range(len(signal)):
        y = base_y + int(signal[x] * (fi.vertical_dim // 2 - 1))

        color = COLORS[channel_meta[x] % len(COLORS)]

        if (x + 1) < len(signal):
            next_y = base_y + int(signal[x + 1] * (fi.vertical_dim // 2 - 1))

            shape = [(fi.pixels_per_sample * x, y),
                     (fi.pixels_per_sample * (x + 1), next_y)]
            fi.im_line.line(shape, fill=color)
        else:
            fi.px[fi.pixels_per_sample * x, y] = color


def test_image(samples_per_frame: int, pixels_per_sample: int,
               num_amiga_channels: int):
    fi = FrameImage(samples_per_frame, pixels_per_sample, num_amiga_channels)
    color = 0
    steps = 0
    for ch in range(num_amiga_channels):
        signal = []
        channel_meta = []
        for i in range(samples_per_frame):
            signal.append(math.sin(0.05 * i * (1.0 + ch) + ch * math.pi / 3))
            channel_meta.append(color)
            steps += 1
            if (steps % 32) == 0:
                color += 1

        plot_channel(fi, ch, signal, channel_meta)

    return fi.im
