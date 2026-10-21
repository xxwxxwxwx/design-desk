# Template fidelity status

## Current verified assets

- `assets/fixed-overlay-reference-1080x1440.png` is an untouched copy of the user-uploaded complete RGBA overlay. It includes the example merchant Logo and the placeholder merchant name.
- `assets/fixed-overlay-blank-1080x1440.png` combines the approved wide co-brand header geometry with the exact fixed lower strip; only the merchant Logo and merchant-name regions are variable.
- `assets/fixed-top-template-1080x160.png` is the approved wide header and `assets/fixed-bottom-template-1080x126.png` is the exact fixed lower-strip crop.
- `assets/reference/` preserves the separately uploaded top and bottom screenshots plus exact crops containing the example variable content.
- `assets/template-manifest.json` records dimensions, variable boxes, provenance, and SHA-256 hashes.
- `references/historical-spacing-calibration.md` records measurements from nine earlier 1080×1440 finished posters and explains how those measurements constrain Logo and merchant-name placement.
- `assets/source/fantuan-info-bar-authoritative-source.psd` is the preserved editable Photoshop source supplied by the user. Its inspected structure is recorded in `references/source-psd.md` and `assets/source/psd-source-manifest.json`.

The full overlay is `1080×1440`, has an alpha channel, and its center from `y=160` through `y=1313` is transparent. This makes deterministic layer composition possible without recreating fixed artwork.

## Typography is now resolved

The later-supplied editable PSD resolves the merchant-name typography:

- PostScript named instance: `AlimamaFangYuanTiVF-SemiBold`;
- family: `Alimama FangYuanTi VF` / `阿里妈妈方圆体 VF`;
- size: `22`;
- tracking: `0`;
- horizontal and vertical scale: `1.0`;
- faux bold and faux italic: disabled.

The matching variable font is bundled at `assets/fonts/AlimamaFangYuanTiVF-Thin-2.ttf`; its named `SemiBold` instance has weight coordinate `600` and bevel coordinate `80`. Its SHA-256 is `b0b8c4c057af7dbc6ccb52a3ad00138fed41d1ad37d4f4a666b6cd431c913d94`.

## Portability gate

The font file is embedded in the Skill package and resolved automatically by the composition script. Do not use the preview fallback as final.

## Geometry precedence

The PSD contains Chinese and English source layouts side by side and a curved lower information treatment. The currently approved raster overlay and historical finished posters use the fixed flat lower strip. Therefore preserve both assets: use the PSD for editable structure, exact font, and source-layer measurements; use `fixed-overlay-blank-1080x1440.png` for the approved final flat-strip pixels unless the user explicitly asks to switch to the curved PSD layout.
