# TODO: Subsong duration detection
# TODO: Function usage annotation in sound core (and the native software)

import argparse
import ast
import hashlib
from multiprocessing import cpu_count, Pool
import os
import os.path
from pathlib import Path
import string
import subprocess
import sys
import traceback
from typing import Dict, Optional, Tuple

from uade.typevalidator import validate2, OPTIONAL_KEY


# TODO: Write fields here
DB_META_SPEC = {
    'hexdigest': str,
    OPTIONAL_KEY('player'): str,

    'uade:content_detection': bool,
    OPTIONAL_KEY('uade:duration'): float,
    'uade:is_custom': bool,
    'uade:max_subsong': int,
    'uade:min_subsong': int,
    str: object,
}

AST_UADE_META_SPEC = {
    'uade:content_detection': bool,
    OPTIONAL_KEY('uade:duration'): float,
    'uade:is_custom': bool,
    'uade:max_subsong': int,
    'uade:min_subsong': int,
    'uade:playerfname': bytes,
    str: object,
}

UNPROCESSED_META_KEYS_TO_DROP = {'uade:playerfname', 'uade:modulefname'}

AST_UADECORE_META_SPEC = {
    OPTIONAL_KEY('uadecore:audio_start_time'): float,
    OPTIONAL_KEY('uadecore:audio_start_slow'): bool,
    str: object,
}

AST_SCORE_META_SPEC = {str: int}

AST_SPECS = {
    'eagle': AST_SCORE_META_SPEC,
    'exec': AST_SCORE_META_SPEC,
    'score': AST_SCORE_META_SPEC,

    'uade': AST_UADE_META_SPEC,

    'uadecore': AST_UADECORE_META_SPEC,
}

# These are log prefixes that are collected from score.
# Example log entry: 'score:call_start_int'.
SCORE_LIBRARIES = ['eagle', 'exec', 'score']


PLAYERS_WITHOUT_RESULTS = set([
    'ADPCM_mono',
    'Alcatraz_Packer',
    'ArtOfNoise-8V',
    'AudioSculpture',
    'ChipTracker',
    'Cinemaware',
    'DaveLoweNew',
    'DaveLowe_Deli',
    'DirkBialluch',
    'DynamicSynthesizer',
    'Janne_Salmijarvi_Optimizer',
    'JasonPage',
    'JasonPage_JP',
    'JesperOlsen_EP',
    'JochenHippel-7V',
    'JochenHippel_UADE',
    'Jochen_Hippel_ST',
    'MIDI-Loriciel',
    'MagneticFieldsPacker',
    'Mosh_Packer',
    'MugicianII',
    'MusicMaker-4V',
    'MusicMaker-8V',
    'NTSP-system',
    'NovoTradePacker',
    'Octa-MED',
    'PaulShields',
    'PaulSummers',
    'PierreAdane',
    'Pokeynoise',
    'RichardJoseph',
    'RobHubbard_ST',
    'SIDMon2.0',
    'ScottJohnston',
    'Sierra-AGI',
    'SonicArranger-pc-all',
    'SonixMusicDriver',
    'SoundMaster',
    'SoundMon2.2',
    'SoundPlayer',
    'Soundtracker-IV',
    'SynthDream',
    'SynthPack',
    'TCB_Tracker',
    'TFMX',
    'TFMX-7V',
    'TFMX-7V-TFHD',
    'TFMX-Pro-TFHD',
    'TFMX-TFHD',
    'TFMX_ST',
    'Titanics_Packer',
    'UltimateSoundtracker',
    'YM-2149',
    'onEscapee',
])


class ArgumentError(Exception):
    pass


class Result:
    def __init__(self, path: Path, unprocessed_meta: Dict, song_base_path):
        assert os.path.isfile(path)
        self.path = path
        self.rel_path = bytes(path.relative_to(song_base_path))
        self.unprocessed_meta = unprocessed_meta

        blake2b = hashlib.blake2b()
        blake2b.update(self.path.read_bytes())
        self.hexdigest = blake2b.hexdigest()

    def get_meta(self):
        if self.unprocessed_meta is None:
            return None
        meta = {
            'rel_path': self.rel_path,
            'hexdigest': self.hexdigest,
        }
        assert len(set(meta).intersection(self.unprocessed_meta)) == 0
        meta.update(self.unprocessed_meta)

        player = meta['uade:playerfname']
        if not meta['uade:is_custom'] and len(player) > 0:
            try:
                player = player.decode()
            except UnicodeDecodeError:
                print('Invalid player:', player)
                return None
            meta['player'] = os.path.basename(player)

        for key in UNPROCESSED_META_KEYS_TO_DROP:
            meta.pop(key, None)

        return meta

    def has_log_data(self) -> bool:
        if self.unprocessed_meta is not None:
            for key in self.unprocessed_meta:
                if key.startswith('score:'):
                    return True
        return False


def _test_playback_create_jobs(args):
    jobs = []
    jobs.append((_test_playback_process,
                 os.path.join(args.files[0], 'bp', 'BP.Eternity'),
                 args))
    return jobs


def _test_playback_process(path: Path, args) -> Optional[Dict]:
    cp = subprocess.run(
        [args.uade123, '-t', '0.5', '-f', '/dev/null', str(path)],
        capture_output=True)
    if cp.returncode > 0:
        return None
    return {}


def _test_playback_check(job_return_values, args):
    ret = 0
    for unused_f, path, result in job_return_values:
        if result is None:
            print('FATAL ERROR: Unable to playback', path)
            ret = 1
    return ret


def _test_song_meta_process(path: Path, args) -> Optional[Dict]:
    cp = subprocess.run([args.uade123, '-g', str(path)], capture_output=True)
    PREFIX = b'uade_logs: '
    unprocessed_meta = None
    if cp.returncode == 0:
        for line in cp.stdout.split(b'\n'):
            if line.startswith(PREFIX):
                if unprocessed_meta is None:
                    unprocessed_meta = {}
                ast_str = line[len(PREFIX):].decode()
                ast_dict = ast.literal_eval(ast_str)

                error_msg = None

                if isinstance(ast_dict, dict):
                    spec = None
                    for key in ast_dict:
                        prefix = key.split(':')[0]
                        spec = AST_SPECS.get(prefix)
                        if spec is None:
                            spec = {}
                            error_msg = 'Unknown log prefix: {}'.format(key)
                        break
                    try:
                        validate2(spec, ast_dict)
                    except ValueError as e:
                        error_msg = str(e)
                else:
                    error_msg = 'ast_dict is not a dict'

                if error_msg is not None:
                    raise ValueError(
                        'File {} ast_dict is invalid: {} ({})'.format(
                            os.fsencode(path), ast_dict, error_msg))

                unprocessed_meta.update(ast_dict)

    return unprocessed_meta


def _call_test_on_file(*pos) -> Tuple[Path, Optional[Dict]]:
    test_func = pos[0]
    test_args = pos[1:]
    try:
        result = test_func(*test_args)
    except Exception as e:
        print('Job {} threw an exception: {}'.format(pos, e))
        traceback.print_exc()
        result = None
    return (test_func, test_args[0], result)


def _write_meta(meta: dict, db_dir: Path):
    assert isinstance(meta, dict)
    path = db_dir / Path(meta['hexdigest'])
    with open(path, 'w') as f:
        f.write(repr(meta))


def _per_song_test_error(meta: dict, db_meta: dict, key: str):
    song_value = meta.get(key)
    db_value = db_meta[key]
    print('Song {} test for {} failed. uade123 returned {}. '
          'The db has value {}.'.format(
              meta['rel_path'], key, song_value, db_value))


def _per_song_tests(meta, db_meta, log_data_available: bool):
    ret = True
    for key in set(DB_META_SPEC).intersection(db_meta):
        if meta[key] != db_meta[key]:
            _per_song_test_error(meta, db_meta, key)
            ret = False
    for key in set(db_meta) - set(DB_META_SPEC):
        if key.startswith('score:') and log_data_available:
            assert db_meta[key] > 0
            if meta.get(key, 0) == 0:
                _per_song_test_error(meta, db_meta, key)
                ret = False

    duration = db_meta.get('duration')
    if duration is not None and abs(duration - meta['duration']) >= 0.1:
        print('Discrepancy in duration: cur {} vs db {}'.format(meta, db_meta))
        ret = False

    return ret


def _read_db(args) -> Dict:
    db = {}

    # Only lowercase hexdigits
    HEX_DIGITS = set(string.hexdigits.lower())

    for path in args.db_dir.iterdir():
        if not path.is_file():
            continue
        if not set(str(path.name)).issubset(HEX_DIGITS):
            continue
        meta_text = path.read_text()
        try:
            meta = ast.literal_eval(meta_text)
        except (SyntaxError, ValueError):  # Really!
            print('Invalid db entry {}: {}'.format(path, meta_text.encode()))
            continue
        validate2(DB_META_SPEC, meta)
        if meta['hexdigest'] != path.name:
            print('db entry hexdigest does not match name. '
                  'Path name is {}. hexdigest is {}.'.format(
                      path, meta['hexdigest']))
            continue
        db[meta['hexdigest']] = meta

    return db


def _test_song_meta_create_jobs(args):
    jobs = []
    for path in args.files:
        if path.is_dir():
            for dirpath, dirnames, filenames in os.walk(path):
                for filename in filenames:
                    song_file = Path(os.path.join(dirpath, filename))
                    jobs.append((_test_song_meta_process, song_file, args))
        else:
            song_file = Path(path)
            jobs.append((_test_song_meta_process, song_file, args))
    return jobs


def _test_song_meta_check(job_return_values, args):
    players = {}
    for path in args.player_dir.iterdir():
        if path.is_file():
            players[path.name] = path.name

    log_data_available = False

    results = {}
    song_base_path = Path(args.song_base_path).resolve()
    for unused_f, path, unprocessed_meta in job_return_values:
        path = path.resolve()
        if path in results:
            print('Duplicate path:', os.fsencode(path))
            continue
        if not path.is_relative_to(song_base_path):
            print('Skipping {} because it is not relative to {}'.format(
                os.fsencode(path), os.fsencode(song_base_path)))
            continue
        result = Result(path, unprocessed_meta, song_base_path)
        results[path] = result

        log_data_available |= result.has_log_data()

    print('log data available:', log_data_available)

    if args.create_db:
        for result in results.values():
            meta = result.get_meta()
            # Note: if meta is None, it was not possible to acquire meta
            # for the path related to the result object. This can be because
            # of many reasons, including a bug in uade123 or the song format
            # is unknown.
            if meta is not None:
                _write_meta(meta, args.db_dir)
        return 0

    db = _read_db(args)

    ret = 0
    result_players = set()
    for result in results.values():
        # The song is not in the test database, so ignore it
        db_meta = db.get(result.hexdigest)
        if db_meta is None:
            continue

        meta = result.get_meta()
        if meta is None:
            print('Failed to acquire meta for {}'.format(
                os.fsencode(result.path)))
            ret = 1
            continue

        if 'player' in meta:
            result_players.add(meta['player'])

        if not _per_song_tests(meta, db_meta, log_data_available):
            ret = 1

    unsupported_players = sorted(result_players - set(players))
    if len(unsupported_players) > 0:
        print('Unsupported players: {}'.format(unsupported_players))
        ret = 1

    untested_players = set(players) - result_players
    if len(untested_players) > 0:
        print('FYI: no results for:', sorted(untested_players))

    unapproved = untested_players - PLAYERS_WITHOUT_RESULTS
    if len(unapproved) > 0:
        print('FATAL ERROR: No results for:', sorted(unapproved))
        ret = 1

    for_approval = PLAYERS_WITHOUT_RESULTS.intersection(result_players)
    if len(for_approval) > 0:
        print('Player to remove from PLAYERS_WITHOUT_RESULTS list:',
              sorted(for_approval))
        ret = 1

    return ret


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('files', metavar='FILE', nargs='*', type=Path)
    parser.add_argument('--db-dir', required=True, type=Path)
    parser.add_argument(
        '--parallelism', '-p', type=int,
        help=('Sets the amount of parallelism encoded. '
              'If zero given, the amount of cpus is used.'))
    parser.add_argument('--song-base-path', required=True, type=Path)
    parser.add_argument('--player-dir', required=True, type=Path)
    parser.add_argument('--uade123', default='uade123', help='Path to uade123')
    parser.add_argument('--create-db', action='store_true')

    args = parser.parse_args()

    assert args.db_dir.is_dir()
    assert args.player_dir.is_dir()
    assert args.song_base_path.is_dir()

    num_processes = 1
    if args.parallelism is not None:
        if args.parallelism < 0:
            raise ArgumentError('Invalid parallelism: {}'.format(
                args.parallelism))
        elif args.parallelism == 0:
            num_processes = cpu_count()
        else:
            num_processes = args.parallelism

    jobs = _test_song_meta_create_jobs(args)
    jobs += _test_playback_create_jobs(args)

    # Maps test_*_process func to a list of results for the func
    return_value_dict = {}
    with Pool(processes=num_processes) as pool:
        for value in pool.starmap(_call_test_on_file, jobs):
            return_value_dict.setdefault(value[0], []).append(value)

    ret = 0

    if _test_song_meta_check(return_value_dict[_test_song_meta_process],
                             args) != 0:
        ret = 1

    if _test_playback_check(return_value_dict[_test_playback_process],
                            args) != 0:
        ret = 1

    return ret


if __name__ == '__main__':
    sys.exit(main())
