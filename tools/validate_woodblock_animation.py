"""Validate layered card coverage, visible motion, loop closure and skin paths."""
import argparse
import copy
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image

import build_woodblock_animation as build

ROOT = build.ROOT
ART = build.OUT
SKIN = ROOT.parent/'skin.arctic.fuse.3'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--animated-only', action='store_true', help='Validate animated cards without the separate landscape set.')
    args = parser.parse_args()
    manifest = json.loads((ART/'manifest.json').read_text())
    assert manifest['cloudMotion'] is False and manifest['foliageMotion'] is False
    assert {c['code'] for c in manifest['cards']} == {str(i) for i in range(48)} | {'na'}
    hashes, metrics, count = set(), [], 0
    for card in manifest['cards']:
        code = card['code']
        base_path = ART/card['base']
        with Image.open(base_path) as im:
            assert im.size == (320, 720) and im.mode == 'RGB'
            base = im.convert('RGBA')
        digest = hashlib.sha256(base.tobytes()).hexdigest()
        assert digest not in hashes, (code, 'duplicate static plate')
        hashes.add(digest)
        if not card['cleanPlate']:
            assert base_path.read_bytes() == (ROOT/'resources/weather-woodblock'/f'{code}.jpg').read_bytes()
        count += 1
        for name, paths in card['frames'].items():
            assert len(paths) == 5
            frames, raw = [], []
            for path in paths:
                with Image.open(ART/path) as im:
                    assert im.mode == 'RGBA' and im.size in ((320, 720), (1, 1))
                    assert getattr(im, 'n_frames', 1) == 1
                    assert im.getchannel('A').getextrema()[0] == 0
                    if name == 'atmosphere' and not any(k in card['regions'] for k in ('fog','stars','vortex')):
                        assert im.getchannel('A').getbbox() is None, (code, 'cloud or foliage motion remains')
                    if name == 'weather' and code in {'0', '23'}:
                        assert im.getchannel('A').getbbox() is None, (code, 'drifting leaves remain')
                    raw.append(im.tobytes())
                    frames.append(np.asarray(Image.alpha_composite(base, im.resize(base.size))).astype(int))
                count += 1
            if name in card['effects']:
                assert len(set(raw)) == 5, (code, name, 'stuck images')
                difference = np.max(frames, axis=0)-np.min(frames, axis=0)
                changed = int((difference[:, :, :3].max(axis=2) > 10).sum())
                assert changed > 0, (code, name, 'no visible motion')
                metrics.append({'code': code, 'effect': name, 'pixelsChangingOver10': changed})
                if name == 'surface' and 'water' in card['regions']:
                    assert changed >= 50, (code, 'water effect too faint', changed)
        with Image.open(ART/card['lightning']) as bolt:
            assert getattr(bolt, 'n_frames', 1) == 1 and bolt.mode == 'RGBA'
            active = bolt.getchannel('A').getbbox() is not None
            assert active == (code in build.STORMS), (code, 'incorrect lightning condition')
            count += 1
        if code in build.RAIN or code in build.SNOW or code in build.ICE:
            if code != '3':
                assert np.array_equal(np.asarray(build.precipitation(code, card['regions'], 0)),
                                      np.asarray(build.precipitation(code, card['regions'], 5))), (code, 'precipitation loop')
        if 'vortex' in card['regions']:
            spec = card['regions']['vortex']
            assert 'atmosphere' in card['effects']
            for source in ('cloudLayer','skyPlate','sceneReference'):
                assert (ROOT/spec[source]).is_file()
            assert np.array_equal(np.asarray(build.vortex(base.convert('RGB'), spec, 0)),
                                  np.asarray(build.vortex(base.convert('RGB'), spec, 5))), (code, 'vortex loop')
            limit = 490 if spec['type'] == 'funnel' else 350
            for phase in range(5):
                alpha = np.asarray(build.vortex(base.convert('RGB'), spec, phase))[:, :, 3]
                assert not alpha[limit:].any(), (code, 'vortex moves landscape')
            if code == '0':
                assert 'water' not in card['regions']
                for path in card['frames']['atmosphere']:
                    with Image.open(ART/path) as im:
                        assert not np.asarray(im)[:, :, 3][490:].any(), 'tornado ground ripple remains'
        if 'stars' in card['regions']:
            stars = card['regions']['stars']
            assert 'atmosphere' in card['effects'] and stars
            allowed = np.zeros((720,320), dtype=bool)
            for x,y,radius in stars:
                allowed |= np.hypot(build.XX-x,build.YY-y) < radius+1
            assert np.array_equal(np.asarray(build.twinkle(base.convert('RGB'), stars, 0)),
                                  np.asarray(build.twinkle(base.convert('RGB'), stars, 5))), (code, 'star loop')
            for path in card['frames']['atmosphere']:
                with Image.open(ART/path) as im:
                    assert not np.asarray(im)[:, :, 3][~allowed].any(), (code, 'twinkle moves surrounding artwork')
    assert count == 833
    addon = ET.parse(ROOT/'addon.xml').getroot()
    skin = ET.parse(SKIN/'addon.xml').getroot()
    required = next(e.get('version') for e in skin.findall('./requires/import') if e.get('addon') == addon.get('id'))
    assert required == addon.get('version') == '1.0.3'
    trees = {name: ET.parse(SKIN/'1080i'/name).getroot() for name in
             ('Includes_Weather.xml','Includes_StartUp_Weather.xml','MyWeather.xml','Dialog_DialogWeather.xml')}
    definitions = {e.get('name'): e for root in trees.values() for e in root.findall('include') if e.get('name')}

    def substitute(text, params):
        return re.sub(r'\$PARAM\[([^]]+)\]', lambda m: params.get(m[1], m[0]), text or '')

    def expand(name, supplied):
        definition = definitions[name]
        params = {p.get('name'): p.text or '' for p in definition.findall('param')}
        params.update(supplied)
        result = []
        container = definition.find('definition')
        for node in container:
            def walk(current):
                if substitute(current.get('condition'), params) in ('false', '!true'):
                    return
                if current.tag == 'include' and current.get('content') in definitions:
                    child_params = {p.get('name'): substitute(p.text, params) for p in current.findall('param')}
                    result.extend(expand(current.get('content'), child_params))
                else:
                    if current.tag in ('texture','imagepath'):
                        result.append((current.tag, substitute(current.text, params),
                                       {k: substitute(v, params) for k,v in current.attrib.items()}))
                    for child in current:
                        walk(child)
            walk(node)
        return result

    prefix = 'special://home/addons/resource.images.arctic.weather/'
    for card in manifest['cards']:
        textures = expand('Weather_Card_Artwork', {'fanartcode':card['code'], 'diffuse':'diffuse/tall_w320_h720.png'})
        assert len([t for t in textures if t[0]=='imagepath']) == 4
        for tag, text, attrs in textures:
            assert '$PARAM[' not in text
            if text.startswith(prefix):
                path = ROOT/text.removeprefix(prefix)
                assert path.exists(), path
                if tag == 'imagepath':
                    assert len(list(path.glob('*.png'))) == 5
            if 'fallback' in attrs:
                assert (ROOT/attrs['fallback'].removeprefix(prefix)).is_file()
        if args.animated_only:
            continue
        landscapes = expand('Weather_Card_Artwork', {'fanartcode':card['code'], 'landscape':'true',
                                                   'diffuse':'diffuse/landscape_w480_h270.png'})
        assert len(landscapes) == 1 and landscapes[0][0] == 'texture'
        _, path, attrs = landscapes[0]
        assert path == prefix + 'resources/weather-woodblock-landscape/' + card['code'] + '.jpg'
        with Image.open(ROOT/path.removeprefix(prefix)) as landscape:
            assert landscape.size == (1280, 720) and landscape.mode == 'RGB'
            assert getattr(landscape, 'n_frames', 1) == 1
        assert (ROOT/attrs['fallback'].removeprefix(prefix)).is_file()
    dialog_artwork = next(i for i in trees['Dialog_DialogWeather.xml'].iter('include')
                          if i.get('content') == 'Weather_Card_Artwork')
    assert dialog_artwork.find("param[@name='landscape']").text == 'true'
    for window in ('MyWeather.xml','Dialog_DialogWeather.xml'):
        assert any(i.get('content') == ('Weather_Details_HighLow' if window=='MyWeather.xml' else 'Weather_Card_Artwork')
                   for i in trees[window].iter('include'))
    report = {'cards':49, 'singleFrameImages':count,
              'scope':'animated cards' if args.animated_only else 'animated and landscape cards',
              'runtimeBytes':sum(p.stat().st_size for p in ART.rglob('*') if p.is_file()),
              'dependencyVersion':required, 'motionMetrics':metrics,
              'checks':['complete distinct coverage','PNG alpha and single-frame format','five distinct active phases',
                        'static clouds and foliage',
                        'localized looping vortices and static tornado ground',
                        'localized staggered star twinkles',
                        'visible water motion','periodic precipitation','matching dependency version',
                        'shared include expansion and resolved layer paths',
                        'static landscape dialog, 1280 x 720 coverage and fallback','XML parsing'],
              'limitation':'Kodi playback was not visually inspected in a running skin.'}
    (ROOT/'tools/woodblock-animation-validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'Validated {report["cards"]} cards, {count} single-frame images, {report["runtimeBytes"]:,} bytes; dependency {required}.')
    print('Coverage, motion visibility, loop closure, XML and expanded runtime paths passed.')


if __name__ == '__main__':
    main()
