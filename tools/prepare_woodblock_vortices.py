"""Prepare fixed sky plates and isolated cloud sources for vortex animation.

Masters are generated once with built-in imagegen. Frame files are prepared
deterministically from those cloud layers, never regenerated full scenes.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parents[1]
SIZE = (320, 720)
FOLDER = ROOT/'tools/woodblock-vortex-layers'


def main():
    path = ROOT/'tools/woodblock-animation-regions.json'
    regions = json.loads(path.read_text())
    for code in ('0', '2'):
        folder = FOLDER/code
        original = Image.open(folder/'scene-reference.jpg').convert('RGB')
        sky = ImageOps.fit(Image.open(folder/'sky-master.png').convert('RGB'), SIZE, Image.Resampling.LANCZOS)
        source = Image.open(folder/'cloud-master.png').convert('RGBA')
        spec = regions[code]['vortex']
        if code == '0':
            # Keep the original land and trees; the new sky is only behind
            # the detached cloud crown and funnel.
            sky_pixels = np.asarray(sky).copy()
            original_pixels = np.asarray(original)
            sky_pixels[490:] = original_pixels[490:]
            sky_pixels[410:, :180] = original_pixels[410:, :180]
            sky = Image.fromarray(sky_pixels)
            sources = [folder/'cloud-master.png']+[folder/f'pose-{i:02}-master.png' for i in range(1,5)]
            frames = []
            for index, master in enumerate(sources):
                pose = ImageOps.fit(Image.open(master).convert('RGBA'), SIZE, Image.Resampling.LANCZOS)
                alpha = np.asarray(pose)[:,:,3]
                ys,xs = np.nonzero(alpha>128)
                tip = int(ys.max())
                tip_x = float(xs[ys>=tip-3].mean())
                # Anchor each painterly pose to one shared funnel tip.
                height = round(720*477/max(tip,1))
                resized = pose.resize((320,height),Image.Resampling.LANCZOS)
                aligned = Image.new('RGBA',SIZE)
                aligned.alpha_composite(resized,dest=(round(241-tip_x),0))
                rgba = np.asarray(aligned).copy()
                rgba[490:,:,3] = 0
                rgba[rgba[:,:,3]==0,:3] = 0
                frame = folder/f'cloud-{index:02}.png'
                Image.fromarray(rgba).save(frame,optimize=True)
                frames.append(frame.relative_to(ROOT).as_posix())
            source = Image.open(folder/'cloud-00.png').convert('RGBA')
            spec['cloudFrames'] = frames
            spec.pop('rows',None)
            spec.pop('material',None)
        else:
            mask = Image.new('L', SIZE)
            ImageDraw.Draw(mask).polygon([(0,0),(320,0),(320,342),
                (278,343),(240,340),(200,326),(175,322),(150,334),
                (125,337),(100,326),(65,315),(0,299)],fill=255)
            mask = mask.filter(ImageFilter.GaussianBlur(1))
            mask.save(folder/'sky-mask.png')
            sky = Image.composite(sky,original,mask)
            source = source.resize((768,768),Image.Resampling.LANCZOS)
            spec['radius'] = [350,210]
            spec['skyMask'] = str((folder/'sky-mask.png').relative_to(ROOT)).replace('\\','/')
        sky.save(folder/'sky-plate.png',optimize=True)
        source.save(folder/'clouds.png',optimize=True)
        spec['cloudLayer'] = str((folder/'clouds.png').relative_to(ROOT)).replace('\\','/')
        spec['skyPlate'] = str((folder/'sky-plate.png').relative_to(ROOT)).replace('\\','/')
        spec['sceneReference'] = str((folder/'scene-reference.jpg').relative_to(ROOT)).replace('\\','/')
        spec['method'] = 'separated painted cloud layer over static sky'
    path.write_text(json.dumps(regions,indent=2)+'\n',encoding='utf-8')
    print('Prepared isolated tornado/cyclone clouds and fixed sky/landscape plates.')


if __name__ == '__main__':
    main()
