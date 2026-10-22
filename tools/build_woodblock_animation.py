"""Build layered five-phase weather cards from fixed plates and authored masks.

No model calls or full-image regeneration occur here. One clean plate is used
for precipitation cards; all other cards retain their original static artwork.
"""
import argparse
import hashlib
import json
import math
import random
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'resources/weather-woodblock-animated'
SIZE = (320, 720)
W, H = SIZE
YY, XX = np.indices((H, W))
BLANK = Image.new('RGBA', (1, 1))
STORMS = {'3', '4', '37', '38', '39', '45', '47'}
RAIN = {'1': 1.4, '2': 1.4, '3': 1, '4': 1.1, '5': .65,
        '6': .65, '8': .25, '9': .3, '10': .7, '11': .9, '12': 1,
        '35': .9, '37': 1, '38': 1, '39': 1, '40': .7, '45': 1.2, '47': 1}
SNOW = {'5': .5, '7': .65, '13': .2, '14': .3, '15': 1.3, '16': .7,
        '41': 1.4, '42': .7, '43': 1.4, '46': .7}
ICE = {'6': .5, '7': .5, '17': 1, '18': .8, '35': .9}


def fit(path):
    with Image.open(path) as im:
        return ImageOps.fit(im.convert('RGB'), SIZE, Image.Resampling.LANCZOS)


def polygon_mask(polygons, feather=0):
    im = Image.new('L', SIZE)
    draw = ImageDraw.Draw(im)
    for points in polygons:
        draw.polygon([tuple(p) for p in points], fill=255)
    if feather:
        im = im.filter(ImageFilter.GaussianBlur(feather))
    return np.asarray(im).astype(float) / 255


def packed(rgb, alpha):
    a = np.clip(np.asarray(alpha) * 255, 0, 255).astype('uint8')
    rgba = np.zeros((H, W, 4), dtype='uint8')
    rgba[:, :, :3] = np.asarray(rgb).clip(0, 255).astype('uint8')
    rgba[:, :, 3] = a
    rgba[a == 0, :3] = 0
    return Image.fromarray(rgba)


def bilinear(rgb, dx, dy=0):
    return sample_pixels(rgb, XX+dx, YY+dy)


def sample_pixels(rgb, sx, sy):
    height, width = rgb.shape[:2]
    sx = np.clip(sx, 0, width - 1)
    sy = np.clip(sy, 0, height - 1)
    x0, y0 = sx.astype(int), sy.astype(int)
    x1, y1 = np.minimum(x0 + 1, width - 1), np.minimum(y0 + 1, height - 1)
    fx, fy = (sx - x0)[:, :, None], (sy - y0)[:, :, None]
    return ((rgb[y0, x0] * (1-fx) + rgb[y0, x1] * fx) * (1-fy)
            + (rgb[y1, x0] * (1-fx) + rgb[y1, x1] * fx) * fy)


def atmosphere(base, region, phase):
    rgb = np.asarray(base).astype(float)
    mask = np.zeros((H, W))
    dx, dy = np.zeros((H, W)), np.zeros((H, W))
    angle = phase * 2 * math.pi / 5
    # Clouds and foliage remain static; fog and existing stars have local effects.
    if 'fog' in region:
        fog = polygon_mask([region['fog']], 9)
        fog *= np.clip((rgb.mean(axis=2) - 70) / 85, 0, 1)
        mask = np.maximum(mask, fog)
        dx += np.sin(angle + YY * .008) * 1.7 * fog
    layer = packed(bilinear(rgb, dx, dy), mask) if mask.max() else BLANK.copy()
    if 'stars' in region:
        stars = twinkle(base, region['stars'], phase)
        layer = Image.alpha_composite(layer.resize(SIZE), stars)
    return layer


def twinkle(base, stars, phase):
    """Vary the existing star pixels, with staggered phases and no moon glow."""
    rgb = np.asarray(base).astype(float)
    moving, mask = rgb.copy(), np.zeros((H, W))
    for x, y, radius in stars:
        distance = np.hypot(XX-x, YY-y)
        ring = (distance >= radius+1) & (distance <= radius+3)
        background = np.median(rgb[ring], axis=0)
        local = np.clip((radius+1-distance), 0, 1)
        local *= np.clip((rgb.mean(axis=2)-background.mean()-8)/18, 0, 1)
        offset = 2*math.pi*((x*73+y*37) % 97)/97
        level = .45+.55*(.5+.5*math.cos(2*math.pi*(phase % 5)/5+offset))
        selected = local > 0
        moving[selected] = background+(rgb[selected]-background)*level
        mask = np.maximum(mask, local)
    return packed(moving, mask)


def water_mask(base, region):
    if 'water' not in region:
        return np.zeros((H, W))
    rgb = np.asarray(base).astype(float)
    polygon = polygon_mask([region['water']])
    luminous = ((rgb[:, :, 0] > 125) & (rgb[:, :, 1] > 125)
                 & (rgb[:, :, 0]-rgb[:, :, 2] < 45)
                 & (rgb[:, :, 1]-rgb[:, :, 2] < 17))
    blue_water = ((rgb[:, :, 2] > rgb[:, :, 0] + 9)
                  & (rgb[:, :, 1] > 100) & (rgb[:, :, 0] > 58))
    selected = polygon * (luminous | blue_water)
    im = Image.fromarray((selected * 255).astype('uint8')).filter(ImageFilter.MinFilter(3))
    return np.asarray(im).astype(float) / 255


def surface(base, region, phase, code):
    rgb = np.asarray(base).astype(float)
    water = water_mask(base, region)
    layer = Image.new('RGBA', SIZE)
    if water.max():
        wave = np.maximum(0, np.cos((YY - phase * 2) * 2 * math.pi / 10)) ** 8
        broken = .55 + .45 * np.square(np.sin(XX * .13 + YY * .04))
        color = np.zeros((H, W, 3))
        color[:] = (55, 93, 116)
        color[rgb.mean(axis=2) < 125] = (226, 226, 204)
        layer = packed(color, water * wave * broken * .44)
    if 'puddles' in region:
        mask = polygon_mask([region['puddles']])
        canvas = Image.new('RGBA', (W * 3, H * 3))
        draw = ImageDraw.Draw(canvas)
        rng = random.Random(int(code) + 7919)
        for _ in range(60):
            x, y = rng.randrange(W), rng.randrange(510, H)
            if mask[y, x] < .5:
                continue
            age = (phase + rng.randrange(5)) % 5
            radius = (.8 + age * .85) * (.55 + (y-510)/300)
            opacity = int(110 * (1-age/5))
            draw.ellipse(((x-radius)*3, (y-radius*.3)*3,
                          (x+radius)*3, (y+radius*.3)*3),
                         outline=(220, 225, 210, opacity), width=2)
        rings = canvas.resize(SIZE, Image.Resampling.LANCZOS)
        a = np.asarray(rings).copy()
        a[:, :, 3] = (a[:, :, 3] * mask).astype('uint8')
        layer = Image.alpha_composite(layer, Image.fromarray(a))
    if 'heat' in region:
        mask = polygon_mask([region['heat']], 5)
        dx = np.sin(YY*.12 + phase * 2 * math.pi / 5) * .9 * mask
        heat = packed(bilinear(rgb, dx), mask * .85)
        layer = Image.alpha_composite(layer, heat)
    return layer if layer.getchannel('A').getbbox() else BLANK.copy()


def vortex(base, spec, phase):
    """Reproject separated painted clouds; never shade a stationary pattern."""
    source = Image.open(ROOT/spec['cloudLayer']).convert('RGBA')
    rgba = np.asarray(source).astype(float)
    rgba[:, :, :3] *= rgba[:, :, 3:4]/255
    if spec['type'] == 'funnel':
        return Image.open(ROOT/spec['cloudFrames'][phase % 5]).convert('RGBA')
    else:
        # A complete disc supplies previously hidden cloud artwork. Fivefold
        # sampling closes a real rotation after five frames, without a reset.
        cx, cy = spec['center']
        rx, ry = spec['radius']
        x, y = (XX-cx)/rx, (YY-cy)/ry
        distance = np.hypot(x,y)
        theta = np.arctan2(y,x)-2*math.pi*(phase % 5)/25
        height, width = rgba.shape[:2]
        samples = []
        for sector in range(5):
            a = theta+sector*2*math.pi/5
            sx = width/2+np.cos(a)*distance*width*.48
            sy = height/2+np.sin(a)*distance*height*.48
            samples.append(sample_pixels(rgba,sx,sy))
        spun = np.median(samples,axis=0)
        spun *= (distance <= 1)[:, :, None]
        mask = np.asarray(Image.open(ROOT/spec['skyMask']).convert('L'))/255
        spun *= mask[:, :, None]
    alpha = spun[:, :, 3]/255
    rgb = np.divide(spun[:, :, :3], np.maximum(alpha[:, :, None], 1/255))
    return packed(rgb, alpha)


def precipitation(code, region, phase):
    if code not in RAIN and code not in SNOW and code not in ICE:
        return BLANK.copy()
    canvas = Image.new('RGBA', (W*3, H*3))
    draw = ImageDraw.Draw(canvas)
    rng = random.Random(int(code) * 1009 + 149)
    kinds = [('rain', RAIN.get(code, 0)), ('snow', SNOW.get(code, 0)), ('ice', ICE.get(code, 0))]
    for kind, intensity in kinds:
        if not intensity:
            continue
        spacing = 29 / max(.4, intensity) if kind == 'rain' else 39 / max(.4, intensity)
        slope = -0.375
        if code in {'1', '2'}:
            slope = -.75
        if code == '15':
            slope = 2.2
        for column in range(-65, 65):
            u = column * spacing + rng.uniform(-spacing*.4, spacing*.4)
            offset, length = rng.uniform(0, 40), rng.uniform(8, 15)
            radius = rng.uniform(.55, 1.6) if kind == 'snow' else rng.uniform(.45, 1.15)
            if kind == 'ice' and code in {'17', '35'}:
                radius = rng.uniform(1, 1.8)
            opacity = rng.randint(38, 100) if kind == 'rain' else rng.randint(100, 205)
            for row in range(-3, 22):
                y = row*40 + offset + phase*8
                x = u + y*slope
                if not (-30 < x < W+30 and -30 < y < H+30):
                    continue
                fade = min(1, max(0, (y-70)/100))
                a = int(opacity * fade)
                if kind == 'rain':
                    draw.line([(x*3, y*3), ((x+length*slope)*3, (y+length)*3)],
                              fill=(228, 231, 218, a), width=2 if intensity < .5 else 3)
                else:
                    draw.ellipse(((x-radius)*3, (y-radius)*3,
                                  (x+radius)*3, (y+radius)*3),
                                 fill=(239, 232, 211, a))
    im = canvas.resize(SIZE, Image.Resampling.LANCZOS)
    if 'precipitation' in region:
        rgba = np.asarray(im).copy()
        rgba[:, :, 3] = (rgba[:, :, 3] * polygon_mask(region['precipitation'], 2)).astype('uint8')
        rgba[rgba[:, :, 3] == 0, :3] = 0
        im = Image.fromarray(rgba)
    return im


def lightning(original, code, region):
    if code not in STORMS:
        return BLANK.copy()
    rgb = np.asarray(original).astype(float)
    confidence = np.minimum((rgb[:, :, 0]-160)/65,
                            (rgb[:, :, 0]-rgb[:, :, 2]-15)/22)
    confidence *= (rgb[:, :, 1] > rgb[:, :, 0]*.85)
    if 'lightning' in region:
        confidence *= polygon_mask(region['lightning'])
    else:
        confidence *= YY < 365
    candidates = confidence > .25
    visited = np.zeros((H, W), dtype=bool)
    accepted = np.zeros((H, W))
    # Reject broad white sky/cloud gaps; keep the slender vertical branches.
    for sy, sx in zip(*np.nonzero(candidates)):
        if visited[sy, sx]:
            continue
        points, pending = [], deque([(sy, sx)])
        visited[sy, sx] = True
        while pending:
            y, x = pending.popleft()
            points.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y+dy, x+dx
                    if 0 <= ny < H and 0 <= nx < W and candidates[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        pending.append((ny, nx))
        ys, xs = zip(*points)
        height, width = max(ys)-min(ys)+1, max(xs)-min(xs)+1
        if len(points) > 7 and height > 12 and height > width*.7 and (len(points)/(height*width) < .38 or height > width*4):
            for y, x in points:
                accepted[y, x] = np.clip(confidence[y, x], 0, 1)
    return packed((241, 225, 193), accepted)


def composite(base, layers, phase, flash=False):
    im = base.convert('RGBA')
    for name in ('atmosphere', 'surface'):
        im = Image.alpha_composite(im, layers[name][phase].resize(SIZE))
    if flash:
        bolt = layers['lightning'].resize(SIZE).copy()
        bolt.putalpha(bolt.getchannel('A').point(lambda a: round(a * .8)))
        im = Image.alpha_composite(im, bolt)
    return Image.alpha_composite(im, layers['weather'][phase].resize(SIZE))


def trim_lightning(im):
    """Keep the two main bolt components, excluding keyed rain/window specks."""
    rgba = np.asarray(im).copy()
    candidates = rgba[:, :, 3] > 16
    visited = np.zeros(candidates.shape, dtype=bool)
    components = []
    for sy, sx in zip(*np.nonzero(candidates)):
        if visited[sy, sx]:
            continue
        pending, points = deque([(sy, sx)]), []
        visited[sy, sx] = True
        while pending:
            y, x = pending.popleft()
            points.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y+dy, x+dx
                    if 0 <= ny < H and 0 <= nx < W and candidates[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        pending.append((ny, nx))
        if len(points) >= 25 and max(p[0] for p in points)-min(p[0] for p in points) >= 20:
            components.append(points)
    keep = Image.new('L', SIZE)
    draw = ImageDraw.Draw(keep)
    for points in sorted(components, key=len, reverse=True)[:2]:
        for y, x in points:
            draw.point((x, y), fill=255)
    keep = keep.filter(ImageFilter.MaxFilter(3))
    rgba[:, :, 3] *= (np.asarray(keep) > 0)
    rgba[rgba[:, :, 3] == 0, :3] = 0
    return Image.fromarray(rgba)


def save_frame(im, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not im.getchannel('A').getbbox():
        im = BLANK
    im.save(destination, optimize=True)


def image_digest(im):
    return hashlib.sha256(im.tobytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--partial', action='store_true')
    parser.add_argument('--codes', nargs='*')
    args = parser.parse_args()
    plan = json.loads((ROOT/'tools/woodblock-animation-plan.json').read_text())
    regions = json.loads((ROOT/'tools/woodblock-animation-regions.json').read_text())
    cache = ROOT/'tools/woodblock-animation-plates'
    cache.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    cards = plan['cards']
    records, reviews, missing = [], [], []
    existing_manifest = OUT/'manifest.json'
    old_records = {}
    if existing_manifest.exists():
        old_records = {c['code']: c for c in json.loads(existing_manifest.read_text())['cards']}
    for card in cards:
        code = card['code']
        if args.codes and code not in args.codes:
            if code in old_records:
                records.append(old_records[code])
            continue
        original_path = ROOT/'resources/weather-woodblock'/card['file']
        original = fit(original_path)
        plate_path = cache/f'{code}.png'
        needs_clean = code in plan['cleanPlateCodes'] or code == '3'
        if needs_clean and not plate_path.exists():
            source = plan['sources'].get(code)
            if not source:
                missing.append(code)
                continue
            source_path = Path(source)
            if not source_path.is_absolute():
                source_path = ROOT/source_path
            fit(source_path).save(plate_path, optimize=True)
        destination = OUT/code
        destination.mkdir(exist_ok=True)
        region = regions[code]
        if 'vortex' in region:
            fit(ROOT/region['vortex']['skyPlate']).save(destination/'base.jpg', quality=93, subsampling=0, optimize=True)
            needs_clean = True
        elif code == '3':
            destination.joinpath('base.jpg').write_bytes((ROOT/'tools/drafts/woodblock-animation-3/layers/base.jpg').read_bytes())
        elif needs_clean:
            fit(plate_path).save(destination/'base.jpg', quality=93, subsampling=0, optimize=True)
        else:
            destination.joinpath('base.jpg').write_bytes(original_path.read_bytes())
        base = fit(destination/'base.jpg')
        motion_source = fit(ROOT/region['vortex']['sceneReference']) if 'vortex' in region else base
        layers = {'atmosphere': [], 'surface': [], 'weather': []}
        for phase in range(5):
            layers['atmosphere'].append(vortex(motion_source,region['vortex'],phase)
                                        if 'vortex' in region else atmosphere(base, region, phase))
            layers['surface'].append(surface(motion_source, region, phase, code))
            layers['weather'].append(precipitation(code, region, phase))
        layers['lightning'] = lightning(original, code, region)
        if code == '3':
            draft = ROOT/'tools/drafts/woodblock-animation-3/layers'
            layers['surface'] = [Image.open(draft/'river'/f'{i:02}.png').convert('RGBA') for i in range(5)]
            layers['weather'] = [Image.open(draft/'rain'/f'{i:02}.png').convert('RGBA') for i in range(5)]
            layers['lightning'] = Image.open(draft/'lightning.png').convert('RGBA')
        if code in STORMS:
            layers['lightning'] = trim_lightning(layers['lightning'])
        effects = []
        for name in ('atmosphere', 'surface', 'weather'):
            active = any(im.getchannel('A').getbbox() for im in layers[name])
            if active:
                assert len({image_digest(im) for im in layers[name]}) == 5, (code, name, 'stuck frames')
                effects.append(name)
            for phase, im in enumerate(layers[name]):
                save_frame(im, destination/name/f'{phase:02}.png')
        save_frame(layers['lightning'], destination/'lightning.png')
        if code in STORMS:
            assert layers['lightning'].getchannel('A').getbbox(), (code, 'missing lightning')
            effects.append('lightning')
        native = [composite(base, layers, i, flash=code in STORMS and i in (1, 3)) for i in range(5)]
        reviews.append((code, card['condition'], native[1]))
        review_dir = ROOT/'tools/woodblock-animation-review'/code
        review_dir.mkdir(parents=True, exist_ok=True)
        for phase, im in enumerate(native):
            im.convert('RGB').save(review_dir/f'{phase:02}.jpg', quality=90, subsampling=0)
        records.append({'code': code, 'condition': card['condition'], 'base': f'{code}/base.jpg',
                        'effects': effects, 'cleanPlate': needs_clean,
                        'frames': {n: [f'{code}/{n}/{i:02}.png' for i in range(5)] for n in ('atmosphere', 'surface', 'weather')},
                        'lightning': f'{code}/lightning.png', 'regions': region})
        print(f'{code}: {", ".join(effects)}')
    expected = {str(i) for i in range(48)} | {'na'}
    if not args.partial and not args.codes:
        assert {c['code'] for c in records} == expected, f'Missing clean plates: {missing}'
    manifest = {'version': 1, 'dimensions': SIZE, 'phasesPerMovingLayer': 5,
                'cloudMotion': False,
                'foliageMotion': False,
                'rotatingCloudCodes': ['0','2'],
                'frameDurationMs': {'atmosphere': 1200, 'surface': 300, 'weather': 180},
                'rotatingCloudDurationMs': 300,
                'rotatingCloudFadeMs': 100,
                'lightning': {'cycleTimeMs': 5000, 'attackMs': [1200, 1480], 'decayMs': [1250, 1530],
                              'fadeInMs': 30, 'fadeOutMs': 220, 'peakOpacity': [.8, .56]},
                'generator': 'one fixed plate per card; authored masks and deterministic alpha compositing',
                'cleanPlatePrompt': plan['cleanPlatePrompt'],
                'approvedReference': 'tools/drafts/woodblock-animation-3',
                'cards': records}
    existing_manifest.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    if records:
        columns, tw, th, label_h = 7, 160, 360, 34
        sheet = Image.new('RGB', (columns*tw, 7*(th+label_h)), '#152632')
        draw = ImageDraw.Draw(sheet)
        font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 11)
        for record in records:
            code, condition = record['code'], record['condition']
            im = Image.open(ROOT/'tools/woodblock-animation-review'/code/'01.jpg')
            index = 48 if code == 'na' else int(code)
            x, y = index % columns * tw, index // columns * (th+label_h)
            sheet.paste(im.convert('RGB').resize((tw, th), Image.Resampling.LANCZOS), (x, y))
            draw.text((x+4, y+th+4), code+'  '+condition, font=font, fill='#eee3cf')
        sheet.save(ROOT/'tools/weather-woodblock-animated-preview.jpg', quality=91, subsampling=0)
    count = 0
    for record in records:
        folder = OUT/record['code']
        with Image.open(folder/'base.jpg') as im:
            assert im.size == SIZE and im.mode == 'RGB'
            count += 1
        for path in folder.rglob('*.png'):
            with Image.open(path) as im:
                assert im.mode == 'RGBA' and im.size in (SIZE, (1, 1)), path
                assert getattr(im, 'n_frames', 1) == 1, path
                assert im.getchannel('A').getextrema()[0] == 0, path
                count += 1
    total = sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())
    print(f'Validated {len(records)}/49 layered cards; {count} single-frame images; {total:,} bytes. Missing: {missing}')


if __name__ == '__main__':
    main()
