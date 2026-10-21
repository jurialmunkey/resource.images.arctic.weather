# Arctic Weather

Kodi image resource add-on `resource.images.arctic.weather`, version 1.0.0.

## Weather cards

`resources/weather/` contains 49 full-bleed 320 x 720 portrait JPEG cards:
one distinct Japanese illustration for each Kodi weather fanart code `0` through
`47`, plus `na` for unavailable conditions. Scenes include Mount Fuji, cherry
blossoms, Tokyo streets, Kyoto temples, mountain villages, gardens and coasts.
The artwork depicts the code's precipitation, visibility, wind, cloud cover,
temperature or day/night condition in the same painted style as the splash.

Use unpadded code filenames, matching Kodi's standard fanart codes:

`special://home/addons/resource.images.arctic.weather/resources/weather/32.jpg`

The skin uses direct add-on paths, following the layered splash pattern, and
avoids resource-handler loading failures observed for the cards and fallback.

Unavailable weather uses `weather/na.jpg`. `resources/weather/manifest.json`
records all code meanings, scenes, individual weather prompts and the common
style prompt. The mapping follows the
[official Kodi weather codes](https://kodi.wiki/view/Weather_addons#Weather_Codes).
The cards are generated individually using built-in imagegen with the Tokyo
alley illustration from this project as a style reference. They are opaque RGB
JPEGs at quality 90 with no chroma subsampling, borders or overlay labels.

`tools/weather-cards-preview.jpg` provides a labeled contact sheet. Run
`python tools/prepare_weather_cards.py` to validate coverage, dimensions and
distinct artwork and recreate the contact sheet (Pillow required). To prepare
new built-in imagegen outputs, pass `--sources sources.json`, containing a list
of objects with `code` and absolute original image `path` fields. Existing cards
are preserved; resizing uses proportional center fitting and Lanczos sampling.

## Watercolour weather cards

`resources/weather-watercolour/` contains a separate set of 49 full-bleed
320 x 720 portrait cards for the same codes `0` through `47` and `na`.
The original illustrated set remains in `resources/weather/` with its existing
filenames and artwork intact. Each style has its own manifest and contact sheet.

The watercolours use broad transparent washes, soft edges, paper texture and
simplified architecture and foliage, matching the approved Sunny / code 32
draft. The shared prompt and per-code scene and weather requirements are recorded
in `resources/weather-watercolour/manifest.json`. Every card is authored with
built-in imagegen; code 32 uses the approved draft itself.

The forecast cards use the watercolour set, including its `na.jpg` fallback:

`special://home/addons/resource.images.arctic.weather/resources/weather-watercolour/32.jpg`

`tools/weather-watercolour-preview.jpg` shows the full labeled set. Validate it
and regenerate the preview with
`python tools/prepare_weather_cards.py --style watercolour`.
Pass `--sources sources.json` to prepare newly generated originals. The
preparation tool defaults to the original illustrated set, so both styles
can be maintained separately without overwriting existing cards.

The skin requires this add-on. Install it in Kodi's user add-ons directory.
The image resource uses type="weather" and compile="false" to preserve the JPEG files.
