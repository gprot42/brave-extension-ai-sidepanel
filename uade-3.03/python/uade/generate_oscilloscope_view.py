# TODO: Figure out a faster ffmpeg video mode

import argparse
import ast
from multiprocessing import cpu_count, Pool
import os
import os.path
import pathlib
import random
import subprocess
import tempfile
import time
import traceback
from typing import List

from . import write_audio


TMP_PREFIX = '_ignore_tmp_'
DEFAULT_FFMPEG_VIDEO_ARGS = ['-pix_fmt', 'yuv420p']


class ArgumentError(Exception):
    pass


def _get_target_dir(songfile: str, args):
    if args.base_dir is None:
        return pathlib.Path(args.target_dir)
    base_dir = pathlib.Path(args.base_dir).absolute()
    target_dir = pathlib.Path(args.target_dir).absolute()
    song_dir = pathlib.Path(songfile).absolute().parent
    try:
        relative_path = song_dir.relative_to(base_dir)
    except ValueError:
        print('Warning: {} is not relative to {}'.format(song_dir, base_dir))
        return target_dir
    return target_dir.joinpath(relative_path)


def _encode_audio(encoded_audio_file: str, wave_file: str, args):
    if args.encode_audio == 'mp3':
        cp = subprocess.run(['lame',
                             '-b', str(args.audio_bitrate),
                             wave_file,
                             encoded_audio_file],
                            capture_output=True)
        if cp.returncode != 0:
            print('lame failed. STDOUT:\n\n{}\nSTDERR:\n\n{}\n'.format(
                    cp.stdout.decode(), cp.stderr.decode()))
            print()
            print('Failed to encode audio for {}'.format(wave_file))
            return 1
    else:
        raise NotImplementedError('Encoding {} not implemented'.format(
            args.encode_audio))
    return 0


def _process_songfile(songfile: str,
                      args,
                      uade123_arg_list: List[str],
                      write_audio_options_list: List[str]) -> int:

    with tempfile.TemporaryDirectory(prefix=TMP_PREFIX,
                                     dir=args.target_dir) as tmpdir:
        bname = os.path.basename(songfile)
        regfile = os.path.join(tmpdir, bname + '.reg')

        target_dir = _get_target_dir(songfile, args)
        video_file = os.path.join(target_dir, bname + '.mp4')
        if args.no_overwrite and os.path.exists(video_file):
            print('Skip {} because {} exists'.format(songfile, video_file))
            return 0

        print('Generating register dump for {}...'.format(songfile))
        cp = subprocess.run([
            args.uade123,
            '-f', '/dev/null',
            '--write-audio', regfile] + uade123_arg_list + [songfile],
            stdout=subprocess.DEVNULL)
        if cp.returncode != 0:
            print('Failed to play {}'.format(songfile))
            return 1

        wavefile = os.path.join(tmpdir, bname + '.wav')

        if args.base_dir is not None:
            os.makedirs(target_dir, exist_ok=True)

        explanation = 'oscilloscope_images'
        if args.no_video:
            explanation = 'wave file'
        print('Generating {} from {}'.format(explanation, regfile))

        write_audio_args = ['--target-dir', tmpdir,
                            '--wave', wavefile,
                            '--fps', str(args.fps),
                            ] + write_audio_options_list + [regfile]
        if args.no_video:
            write_audio_args.append('--no-images')

        if write_audio.main(write_audio_args) != 0:
            print('write_audio.main() failed')
            return 1

        if args.encode_audio is not None:
            assert os.path.exists(wavefile)
            tmp_audio_file = os.path.join(tmpdir,
                                          bname + '.' + args.encode_audio)
            encoded_audio_file = os.path.join(target_dir,
                                              bname + '.' + args.encode_audio)
            audio_ret = _encode_audio(tmp_audio_file, wavefile, args)
            if audio_ret != 0:
                try:
                    os.remove(tmp_audio_file)
                except OSError:
                    pass
                return audio_ret
            # Atomic replace
            try:
                os.replace(tmp_audio_file, encoded_audio_file)
            except OSError as e:
                print('Unable to replace {}: {}'.format(encoded_audio_file, e))
                try:
                    os.remove(tmp_audio_file)
                except OSError:
                    pass
                return 1

        if not args.no_video:
            print('Generating video file {}'.format(video_file))

            image_pattern = os.path.join(tmpdir, 'output_%06d.png')

            video_temp_file = tempfile.NamedTemporaryFile(
                prefix=TMP_PREFIX, suffix='.mp4', dir=target_dir, delete=False)

            ffmpeg_cmd = [
                args.ffmpeg,
                '-i', wavefile,
                '-framerate', str(args.fps),
                '-i', image_pattern,
                '-y'] + list(args.ffmpeg_video_args) + [video_temp_file.name]
            cp = subprocess.run(ffmpeg_cmd, capture_output=True)

            if cp.returncode != 0:
                try:
                    os.remove(video_temp_file.name)
                except FileNotFoundError:
                    pass
                except OSError as e:
                    print('Unabled to remove: {}'.format(e))

                print('ffmpeg failed. STDOUT:\n\n{}\n\nSTDERR:\n\n{}\n'.format(
                    cp.stdout.decode(), cp.stderr.decode()))
                print()
                print('Failed to create video for {}'.format(songfile))
                return 1

            # Atomic replace of the target file for easier snapshotting of
            # accumulated videos and avoid partial videos
            try:
                os.replace(video_temp_file.name, video_file)
            except OSError as e:
                print('Unable to replace {}: {}'.format(video_file, e))
                try:
                    os.remove(video_temp_file.name)
                except OSError:
                    pass
                return 1

    return 0


def _generate_video(*pos) -> int:
    try:
        return _process_songfile(*pos)
    except Exception as e:
        print('Job {} threw an exception: {}'.format(pos, e))
        traceback.print_exc()
        return 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('files', metavar='FILE', nargs='*')
    parser.add_argument('--accelerator')
    parser.add_argument('--audio-bitrate', type=int, default=192)
    parser.add_argument(
        '--base-dir',
        help=('Write video files relative to target directory the same as the '
              'song file is relative to the given base dir. E.g. song file '
              '/foo/bar/song.mod and base dir /foo causes the video to be '
              'written as TARGET_DIR/bar/song.mod.mp4.'))
    parser.add_argument('--color-mode', type=int, default=0)
    # TODO: Add vorbis, opus, flac
    parser.add_argument('--encode-audio', choices=['mp3'])
    parser.add_argument('--ffmpeg', default='ffmpeg', help='Path to ffmpeg')
    parser.add_argument(
        '--ffmpeg-video-args', type=ast.literal_eval,
        default=DEFAULT_FFMPEG_VIDEO_ARGS,
        help=('A python list of strings that are passed as arguments for '
              'ffmpeg. Default: {}'.format(repr(DEFAULT_FFMPEG_VIDEO_ARGS))))
    parser.add_argument(
        '--fps', type=int, default=60,
        help=('Set framerate. Recommended values are 50, 60 and anything '
              'higher that is supported by the display and streaming '
              'technology.'))
    parser.add_argument(
        '--multiprocessing', action='store_true',
        help='Encode videos in parallel with all threads available.')
    parser.add_argument(
        '--no-overwrite', '-n', action='store_true',
        help='If a video file already exists for the song, skip the song.')
    parser.add_argument(
        '--no-video', action='store_true',
        help=('Do not generate a video. This is useful when '
              '--encode-audio is used.'))
    parser.add_argument('--panning', type=float, default=0.7)
    parser.add_argument(
        '--parallelism', '-p', type=int,
        help=('Sets the amount of parallelism encoded. '
              'Same as --multiprocessing but specifies the amount of '
              'parallelism explicitly.'))
    parser.add_argument(
        '--random-order', action='store_true',
        help='Process song files in random order')
    parser.add_argument(
        '--recursive', '-r', action='store_true',
        help='Scan directories recursively')
    parser.add_argument('--target-dir', '-t', required=True)
    parser.add_argument('--uade123', default='uade123', help='Path to uade123')
    parser.add_argument(
        '--uade123-args', type=ast.literal_eval, default={},
        help=('Pass given argument to uade123. This is written as a Python '
              'dictionary. E.g. passing -t 60 for uade123 means giving '
              'argument --uade123-args "{\'-t\': 60, \'-1\': None}". '
              'If dictionary '
              'value is None, the argument is interpreted to have no value. '
              'Values are automatically converted into strings. '
              'Note: Python dictionary '
              'preserves the order of dictionary entries, so the order of '
              'arguments is also preserved for uade123. '
              'Note: Giving --uade123-args "{\'-t\': 1}" is good for '
              'testing.'))

    args = parser.parse_args()
    assert args.fps > 0

    if not isinstance(args.ffmpeg_video_args, (list, tuple)):
        raise ArgumentError('ffmpeg_video_args must be a list or tuple of '
                            'strings')
    for ffmpeg_video_arg in args.ffmpeg_video_args:
        if not isinstance(ffmpeg_video_arg, str):
            raise ArgumentError('ffmpeg_video_arg must be a string: {}'.format(
                ffmpeg_video_arg))

    if args.accelerator is None:
        from . import uade_config
        args.accelerator = uade_config.WRITE_AUDIO_ACCELERATOR

    if not os.path.isdir(args.target_dir):
        raise ArgumentError('{} is not a directory'.format(args.target_dir))

    uade123_arg_list = []
    for key, value in args.uade123_args.items():
        if not isinstance(key, str):
            raise ArgumentError('Given key {} should be a string'.format(key))

        if value is None:
            uade123_arg_list.append(key)
        else:
            uade123_arg_list.extend((key, str(value)))

    if args.parallelism is not None:
        if args.parallelism < 1:
            raise ArgumentError('Invalid parallelism: {}'.format(
                args.parallelism))
        num_processes = args.parallelism
    elif args.multiprocessing:
        num_processes = cpu_count()
    else:
        num_processes = 1

    write_audio_options_list = [
        '--accelerator', args.accelerator,
        '--color-mode', str(args.color_mode),
        '--panning', str(args.panning),
    ]
    if num_processes > 1:
        write_audio_options_list.append('--batch')

    jobs = []
    for path in args.files:
        if os.path.isdir(path):
            if args.recursive:
                for dirpath, dirnames, filenames in os.walk(path):
                    for filename in filenames:
                        songfile = os.path.join(dirpath, filename)
                        jobs.append((songfile, args, uade123_arg_list,
                                     write_audio_options_list))
            else:
                print('Ignoring {} because it is a directory. Use -r to scan '
                      'directories.'.format(path))
                return 1
        else:
            jobs.append((path, args, uade123_arg_list,
                         write_audio_options_list))

    if args.random_order:
        random.shuffle(jobs)

    with Pool(processes=num_processes) as pool:
        try:
            job_retcodes = pool.starmap(_generate_video, jobs)
        except KeyboardInterrupt:
            print('Keyboard interrupt raised..')
            # TODO: sleep() is a workaround that does not really fix the
            # problem that tmp directories are not deleted when CTRL-C is
            # pressed.
            time.sleep(1 + 0.1 * num_processes)
            raise

    for job_retcode in job_retcodes:
        if job_retcode != 0:
            return job_retcode

    return 0
