# Thunderstorm animation draft

Review only. The live weather cards and dependency version are unchanged.

Open `preview.html` to play or pause the composited animation, scrub the five
phases, and toggle each effect independently. It is a self-contained preview
with embedded single-frame images, and works without a server or network.

Runtime layer order, all at 320 x 720:

1. `layers/base.jpg`: one static background plate.
2. `layers/river/00.png` through `04.png`: blue-grey travelling ripple bands,
   300 ms each, clipped inside the water and clear of the banks.
3. `layers/lightning.png`: one transparent bolt layer, with two brief localized
   flashes every five seconds, using the skin's existing lightning-burst include.
4. `layers/rain/00.png` through `04.png`: transparent rain phases, 180 ms each.

There are at most five phases per moving layer, independently timed. Rain uses
a periodic lattice so the last-to-first transition has the same displacement
as the other steps. The river changes only inside an eroded water mask; the
riverbanks stay fixed. Mountains, trees, architecture and clouds remain static
in this first draft. No video, GIF, APNG, sprite sheet or runtime script is used
by the Kodi example.

Imagegen produced one clean plate from the approved artwork, removing the baked
rain and lightning. `build_draft.py` extracts the lightning from the original
approved card and creates every rain/ripple phase using deterministic alpha
compositing. Full artwork is never regenerated per animation phase.
`clean-plate-master.png` preserves that one generated plate; `source.json` and
`manifest.json` record the exact imagegen prompt and generation provenance.

`Includes_Weather_Animation_Draft.xml` demonstrates the existing skin multiimage
pattern: separate transparent PNG folders, ordered playback, no crossfade, no
pause on the last frame. Lightning reuses `Background_StartUp_LightningBurst`
from the skin. The example is not registered in the live skin. Each effect
folder contains images only, so there is nothing extra for multiimage to play.

`review/` and `five-phase-review.jpg` are offline inspection composites only;
Kodi loads the static plate and overlays directly. They are single-frame images.

Rebuild the draft using `python build_draft.py` (Pillow and numpy required).
