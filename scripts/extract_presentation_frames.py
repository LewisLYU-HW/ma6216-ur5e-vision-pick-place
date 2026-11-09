"""Extract traceable presentation stills from published original-run videos."""
import hashlib
import io
import json
from pathlib import Path
import subprocess

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/presentation/frames'
VIDEOS = ROOT / 'docs/videos/visual-feedback-calibrated-v1'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    records = {}
    hashes = {}

    def extract(key, video, seconds, view):
        video = video.resolve()
        # Accurate seek; all source replays are 25 fps. Record the displayed frame index.
        frame = round(seconds * 25)
        data = subprocess.check_output(['ffmpeg', '-v', 'error', '-ss', str(frame / 25),
            '-i', str(video), '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-'])
        im = Image.open(io.BytesIO(data)).convert('RGB')
        box = {'overview': (0, 56, 960, 698), 'wrist': (960, 56, 1920, 698),
               'split': (0, 0, 1920, 720)}[view]
        im.crop(box).save(OUT / (key + '.jpg'), quality=95, subsampling=0)
        rel = str(video.relative_to(ROOT))
        if rel not in hashes:
            hashes[rel] = hashlib.sha256(video.read_bytes()).hexdigest()
        records[key] = {'source': rel, 'source_sha256': hashes[rel],
            'playback_seconds': frame / 25, 'frame_index_zero_based': frame,
            'crop_xyxy': box, 'view': view,
            'transform': 'Rectangular camera-panel crop; no scene content altered',
            'sha256': hashlib.sha256((OUT / (key + '.jpg')).read_bytes()).hexdigest()}

    hero = VIDEOS / 'complete__iterative__none__400.mp4'
    points = {
        'initial': 0, 'hammer_grip': 11.6, 'hammer_lift': 13.6, 'hammer_park': 21,
        'hammer_released': 25, 'feed': 29, 'driver_grip': 40.8, 'driver_lift': 43.4,
        'driver_orient': 50, 'driver_align': 54.4, 'driver_insert': 60,
        'driver_release': 67, 'driver_done': 70, 'rack_pick': 88.4,
        'rack_lift': 91, 'rack_align': 104.4, 'rack_insert': 112,
        'rack_release': 118, 'rack_done': 134.4, 'spanner_first': 142,
        'regrasp_place': 147, 'regrasp_open': 148, 'regrasp_clear': 150.4,
        'regrasp_close': 155.6, 'regrasp_lift': 158.2, 'hang_align': 171,
        'hang_thread': 179, 'hang_release': 183.4, 'final': 195,
    }
    for name, t in points.items():
        for view in ('overview', 'wrist'):
            extract(name + '_' + view, hero, t, view)
    for name, trial, t in [
        ('open_failure', 'complete__open_loop__none__400', 57.96),
        ('iter_failure', 'complete__iterative__none__401', 40.24),
        ('staged_failure', 'complete__staged__none__401', 40.24),
    ]:
        for view in ('overview', 'wrist'):
            extract(name + '_' + view, VIDEOS / (trial + '.mp4'), t, view)
    pulse = ROOT / 'docs/videos/calibrated-workshop-v1/overview-wrist.mp4'
    for name, t in [('pulse_before', 171.64), ('pulse_after', 172.76)]:
        extract(name, pulse, t, 'wrist')
    (OUT / 'manifest.json').write_text(json.dumps(records, indent=2) + '\n')
    print(f'Extracted {len(records)} traceable frames')


if __name__ == '__main__':
    main()
