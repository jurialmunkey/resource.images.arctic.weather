"""Composite a five-phase weather draft from one clean plate and PNG overlays.

Imagegen is used once for the clean plate. This script only extracts, draws,
resamples and composites layers; it never calls an image model.
"""
import base64
import hashlib
import json
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent
SIZE = (320, 720)
PHASES = 5
FRAME_MS = 180


def fit(path):
    with Image.open(path) as im:
        return ImageOps.fit(im.convert('RGB'), SIZE, Image.Resampling.LANCZOS)


def data_url(path):
    mime = 'image/jpeg' if path.suffix == '.jpg' else 'image/png'
    return 'data:' + mime + ';base64,' + base64.b64encode(path.read_bytes()).decode()


def make_rain(phase):
    scale = 4
    canvas = Image.new('RGBA', (SIZE[0] * scale, SIZE[1] * scale))
    draw = ImageDraw.Draw(canvas)
    rng = random.Random(31415)
    # A periodic slanted lattice makes phase 4 -> 0 the same step as 0 -> 1.
    # A 40px period is traversed in five 8px steps, including the loop boundary.
    for column in range(-5, 24):
        u = column * 26 + rng.uniform(-7, 7)
        offset = rng.uniform(0, 40)
        length = rng.uniform(8, 15)
        opacity = rng.randint(34, 86)
        for row in range(-2, 21):
            y = row * 40 + offset + phase * 8
            x = u - y * 0.375
            strength = max(0, min(1, (y - 165) / 150))
            strength *= 0.7 if y > 500 else 1
            draw.line([(x * scale, y * scale),
                       ((x - length * 0.375) * scale, (y + length) * scale)],
                      fill=(230, 231, 215, int(opacity * strength)), width=3)
    return canvas.resize(SIZE, Image.Resampling.LANCZOS)


def make_river(base, phase):
    rgb = np.asarray(base).astype(np.int16)
    yy, xx = np.indices((SIZE[1], SIZE[0]))
    # The ivory river is selected only below the distant valley. Eroding the
    # mask keeps every animated sample inside the water, clear of the banks.
    selected = ((yy > 570) & (xx > 155) & (rgb[:, :, 0] > 143)
                & (rgb[:, :, 0] - rgb[:, :, 2] > 7))
    mask = Image.fromarray((selected * 255).astype('uint8')).filter(ImageFilter.MinFilter(3))
    safe = np.asarray(mask) / 255
    # Travelling blue-grey ripple bands change the actual water contrast.
    # Shifting nearly uniform ivory pixels was mathematically different but
    # visually ineffective. A 10px wave travels 2px in each of five phases.
    wave = np.maximum(0, np.cos((yy - phase * 2) * 2 * math.pi / 10)) ** 8
    broken = 0.55 + 0.45 * np.square(np.sin(xx * 0.13 + yy * 0.04))
    rgba = np.zeros((SIZE[1], SIZE[0], 4), dtype='uint8')
    rgba[:, :, :3] = (55, 93, 116)
    rgba[:, :, 3] = (safe * wave * broken * 112).astype('uint8')
    rgba[rgba[:, :, 3] == 0, :3] = 0
    return Image.fromarray(rgba)


def extract_lightning(original):
    # Warm ivory bolts are separated from the cool rain with a color key.
    # The region excludes the mountain snow and all river/temple highlights.
    im = original.convert('RGB')
    rgb = np.asarray(im).astype(float)
    y, x = np.indices(rgb.shape[:2])
    nx, ny = x / im.width * 320, y / im.height * 720
    region = (ny < 342) | ((nx > 277) & (ny < 371))
    confidence = np.minimum((rgb[:, :, 0] - 160) / 65,
                            (rgb[:, :, 0] - rgb[:, :, 2] - 15) / 22)
    alpha = np.clip(confidence, 0, 1) * region
    result = np.zeros((*alpha.shape, 4), dtype='uint8')
    result[:, :, :3] = (241, 225, 193)
    result[:, :, 3] = (alpha * 255).astype('uint8')
    return Image.fromarray(result).resize(SIZE, Image.Resampling.LANCZOS)


def main():
    source = json.loads((ROOT / 'source.json').read_text())
    for folder in ('layers/rain', 'layers/river', 'review'):
        (ROOT / folder).mkdir(parents=True, exist_ok=True)
    master = ROOT / 'clean-plate-master.png'
    if not master.exists():
        master.write_bytes(Path(source['source']).read_bytes())
    base = fit(master)
    base.save(ROOT / 'layers/base.jpg', quality=93, subsampling=0)
    base = Image.open(ROOT / 'layers/base.jpg').convert('RGBA')
    with Image.open(source['original']) as original:
        lightning = extract_lightning(original)
    lightning.save(ROOT / 'layers/lightning.png', optimize=True)
    frames = []
    for phase in range(PHASES):
        rain = make_rain(phase)
        river = make_river(base.convert('RGB'), phase)
        rain.save(ROOT / f'layers/rain/{phase:02}.png', optimize=True)
        river.save(ROOT / f'layers/river/{phase:02}.png', optimize=True)
        composite = Image.alpha_composite(base, river)
        bolt = lightning.copy()
        bolt.putalpha(bolt.getchannel('A').point(lambda a: round(a * [0, 0.8, 0.26, 0.56, 0][phase])))
        composite = Image.alpha_composite(composite, bolt)
        composite = Image.alpha_composite(composite, rain)
        composite.convert('RGB').save(ROOT / f'review/{phase:02}.jpg', quality=93, subsampling=0)
        frames.append(composite)
    sheet = Image.new('RGB', (320 * PHASES, 754), '#172a36')
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 15)
    for i, frame in enumerate(frames):
        sheet.paste(frame, (i * 320, 0))
        draw.text((i * 320 + 12, 730), f'Phase {i + 1} / 5', fill='#f4e6d1', font=font)
    sheet.save(ROOT / 'five-phase-review.jpg', quality=92, subsampling=0)
    layers = ROOT / 'layers'
    assets = {'base': data_url(layers / 'base.jpg'),
              'lightning': data_url(layers / 'lightning.png'),
              'rain': [data_url(layers / f'rain/{i:02}.png') for i in range(PHASES)],
              'river': [data_url(layers / f'river/{i:02}.png') for i in range(PHASES)]}
    template = (ROOT / 'preview.template.html').read_text(encoding='utf-8')
    (ROOT / 'preview.html').write_text(template.replace('__ASSETS__', json.dumps(assets)), encoding='utf-8')
    pngs = sorted(layers.rglob('*.png'))
    for path in pngs:
        with Image.open(path) as im:
            assert im.size == SIZE and im.mode == 'RGBA'
            assert getattr(im, 'n_frames', 1) == 1
            assert im.getchannel('A').getextrema()[0] == 0
    for name in ('rain', 'river'):
        paths = sorted((layers / name).glob('*.png'))
        assert len(paths) == PHASES
        assert len({hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}) == PHASES
    manifest = {'condition': 'severe thunderstorms', 'code': '3', 'status': 'draft for review only',
                'dimensions': SIZE, 'phases': PHASES, 'frameDurationMs': FRAME_MS,
                'rainLoopMs': PHASES * FRAME_MS, 'riverLoopMs': 5 * 300,
                'generator': 'one imagegen clean plate; deterministic alpha compositing for every phase',
                'layers': [{'file': 'layers/base.jpg', 'kind': 'static', 'frames': 1},
                           {'folder': 'layers/river', 'kind': 'animated overlay', 'frames': 5, 'frameDurationMs': 300},
                           {'file': 'layers/lightning.png', 'kind': 'single alpha overlay', 'frames': 1,
                            'cycleTimeMs': 5000, 'attackMs': [1200, 1480], 'decayMs': [1250, 1530],
                            'fadeInMs': 30, 'fadeOutMs': 220, 'peakOpacity': [0.8, 0.56]},
                           {'folder': 'layers/rain', 'kind': 'animated overlay', 'frames': 5, 'frameDurationMs': 180}],
                'cleanPlatePrompt': source['cleanPlatePrompt'],
                'notes': ['Five phase images per moving layer; no regenerated full-scene frames.',
                          'Lightning is extracted from the approved artwork; brief localized double flash every five seconds.',
                          'River mask excludes the banks; trees, architecture and mountains remain static.',
                          'Review JPGs are offline inspection composites, not assets needed by Kodi.',
                          'Draft include is unregistered; live weather cards are unchanged.'],
                'runtimeAssetBytes': sum(p.stat().st_size for p in layers.rglob('*') if p.is_file())}
    (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'Validated 1 static JPG, 1 lightning PNG, and 2 x 5 transparent single-frame PNGs; {manifest["runtimeAssetBytes"]:,} bytes.')
    print(ROOT / 'preview.html')


if __name__ == '__main__':
    main()
