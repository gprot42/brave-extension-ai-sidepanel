import argparse
from collections import deque
import more_itertools
import os
import struct
import subprocess
import sys
from tqdm import tqdm
from typing import List

from uade import plot_image


EPSILON = 1e-10

NUM_AMIGA_CHANNELS = 4

SAMPLES_PER_FRAME = None
PIXELS_PER_SAMPLE = 2


class Normalisator:
    def __init__(self, normalisation_length: int):
        assert normalisation_length >= 0
        self.normalisation_length = normalisation_length
        if self.normalisation_length == 0:
            self.normalisers = deque([1.0])
        else:
            self.normalisers = deque([1.0], maxlen=self.normalisation_length)

    def add_normaliser(self, normaliser: float):
        if self.normalisation_length > 0:
            self.normalisers.append(normaliser)
        return min(self.normalisers)


def _plot_samples(normalisator: Normalisator, samples: List[float],
                  channel_metas: List[int]):
    abs_max = max(EPSILON, max([abs(x) for x in samples]))
    normaliser = normalisator.add_normaliser(1.0 / abs_max)

    fi = plot_image.FrameImage(SAMPLES_PER_FRAME, PIXELS_PER_SAMPLE,
                               NUM_AMIGA_CHANNELS)

    signals = list(more_itertools.chunked(samples, SAMPLES_PER_FRAME))
    assert len(signals) == NUM_AMIGA_CHANNELS

    separate_channel_metas = list(more_itertools.chunked(channel_metas,
                                                         SAMPLES_PER_FRAME))
    assert len(separate_channel_metas) == NUM_AMIGA_CHANNELS

    for channel, signal in enumerate(signals):
        assert len(signal) == SAMPLES_PER_FRAME
        normalised_signal = [normaliser * x for x in signal]
        plot_image.plot_channel(fi, channel, normalised_signal,
                                separate_channel_metas[channel])

    return fi.im


def _read_value(proc, struct_type, value_name):
    try:
        b = proc.stdout.read(struct.calcsize(struct_type))
    except struct.error as e:
        print('Error reading {}: {}'.format(value_name, e))
        proc.kill()
        proc.communicate()
        proc.wait()
        return None
    return struct.unpack(struct_type, b)[0]


def main(main_args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('file', nargs=1,
                        help='Register dump file (.reg) produced by uadecode.')
    parser.add_argument('--accelerator', required=True)
    parser.add_argument('--batch', action='store_true')
    parser.add_argument(
        '--color-mode', type=int, default=0, choices=plot_image.COLOR_MODES,
        help=('Enable coloring and set palette with --color-mode x '
              'where x > 0. If x == 0, no coloring is done.'))
    parser.add_argument('--color-test-image', action='store_true')
    parser.add_argument('--fps', type=int, default=60, help='Set framerate')
    parser.add_argument('--image-prefix', default='output_')
    parser.add_argument('--image-format', default='png')
    parser.add_argument('--manual', action='store_true')
    parser.add_argument('--no-images', action='store_true')
    parser.add_argument('--normalisation-length', type=int, default=50)
    parser.add_argument('--panning', type=float, default=0.7)
    parser.add_argument('--sampling-rate', default=44100)
    parser.add_argument('--target-dir', required=True)
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--wave', required=True)
    args = parser.parse_args(args=main_args)

    assert os.path.isdir(args.target_dir)

    plot_image.init_colors(args.color_mode)

    if args.color_test_image:
        im = plot_image.test_image(640, PIXELS_PER_SAMPLE, NUM_AMIGA_CHANNELS)
        im.show()
        return 0

    proc = subprocess.Popen([args.accelerator,
                             '--wave', args.wave,
                             '--fps', str(args.fps),
                             '--panning', str(args.panning),
                             args.file[0]],
                            stdout=subprocess.PIPE)

    fps = _read_value(proc, 'i', 'fps')
    if fps is None:
        return 1
    if fps <= 0:
        raise ValueError('fps value is non-positive')

    global SAMPLES_PER_FRAME
    SAMPLES_PER_FRAME = _read_value(proc, 'N', 'SAMPLES_PER_FRAME')
    if SAMPLES_PER_FRAME is None:
        return 1
    assert (SAMPLES_PER_FRAME * PIXELS_PER_SAMPLE) == 1280

    num_frames = _read_value(proc, 'N', 'num_frames')
    if num_frames is None:
        return 1

    progress_bar = None
    if num_frames > 0:
        progress_bar = tqdm(total=num_frames, disable=args.batch)

    num_images = 0

    normalisator = Normalisator(args.normalisation_length)

    SAMPLES_PER_IMAGE = NUM_AMIGA_CHANNELS * SAMPLES_PER_FRAME
    SIGNAL_BYTES_PER_IMAGE = SAMPLES_PER_IMAGE * struct.calcsize('f')
    META_BYTES_PER_IMAGE = SAMPLES_PER_IMAGE * struct.calcsize('H')

    while True:
        # See src/write_audio.c: struct uade_write_audio_frame. It describes
        # the data format of the frame.
        unpacked_list = struct.iter_unpack(
            'f', proc.stdout.read(SIGNAL_BYTES_PER_IMAGE))
        samples = [f[0] for f in unpacked_list]
        if len(samples) == 0:
            break
        assert len(samples) == SAMPLES_PER_IMAGE

        unpacked_list = struct.iter_unpack(
            'H', proc.stdout.read(META_BYTES_PER_IMAGE))
        channel_metas = [buffer_nr[0] for buffer_nr in unpacked_list]

        if not args.no_images:
            im = _plot_samples(normalisator, samples, channel_metas)

            if args.manual:
                print('image frame', num_images)
                im.show()
                input('Enter to continue...')

            basename = '{}{:06d}.{}'.format(
                args.image_prefix, num_images, args.image_format)
            image_path = os.path.join(args.target_dir, basename)
            im.save(image_path, args.image_format, compress_level=1)

        num_images += 1

        if num_frames > 0:
            progress_bar.update(1)

    proc.communicate()

    if proc.wait() != 0:
        print('write-audio binary returned: {}'.format(proc.returncode))
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
