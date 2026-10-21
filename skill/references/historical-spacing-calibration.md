# Historical spacing calibration

## Evidence set

Nine previously delivered `1080×1440` posters were measured at full resolution:

- 湘八爷 / 麦记牛奶;
- 阿忠卤味;
- 茶话弄;
- 东北家常菜;
- Ruitea;
- 夸父炸串;
- bbq 炸鸡;
- 龙粉面 JPG;
- 龙粉面 GIF.

These files are spacing evidence only. Their campaign artwork, merchant identities, products, copy, and colors must not be reused in a new poster.

## Stable bottom-bar measurements

- Eight of nine references begin the solid teal footer at `y=1326–1327`; the remaining file contains decorative teal pixels immediately above the same footer alignment.
- The rounded white search control occupies the same visual position across the set. At its upper curved section, the white run is approximately `x=58–588`; through the lower body it expands toward approximately `x=47–344` before continuing as the teal search pill and white outline.
- The visible merchant-name glyphs are vertically concentrated around `y=1363–1387`.
- The measured horizontal visual center of the merchant name is consistently about `x=479`.

Production implication: keep the bundled bottom template unchanged. Render the name in text box `(390, 1354)–(568, 1395)`, which centers at `x=479`, and never move the entire footer to chase background composition.

## Top co-brand spacing

The historical posters use more than one width of white co-brand panel, so their merchant Logo coordinates must not be copied as one absolute rectangle. The stable relationship is relative:

- keep approximately `20–25 px` of clear white space after the vertical divider;
- keep approximately `20–30 px` of clear white space before the panel's right inner edge;
- center the visible merchant artwork vertically and horizontally in the remaining area;
- trim transparent Logo padding before measuring;
- preserve aspect ratio and reduce size when necessary; never stretch or crop the visible mark.

For the bundled fixed panel, this relationship maps to Logo safe box `(626, 10)–(807, 126)`. The box is intentionally wider than the example square Logo's visible bounds so wide wordmarks match the spacing seen in earlier approved posters.

## Artwork-to-overlay vertical rhythm

The reference set also establishes the spacing between the fixed overlays and the merchant artwork:

- measure the top gap from the lowest visible edge of the white co-brand panel to the first substantial glyph or outline of the main campaign title;
- target approximately `20–50 px`; use the tighter end for bold, dense recruitment headlines and the wider end only when the original composition deliberately needs breathing room;
- measure the bottom gap from the bottommost required text glyph—not the edge of its decorative card—to the top of the solid teal footer at about `y=1326`;
- target approximately `35–90 px`, with `45–75 px` preferred when the source composition allows it;
- do not center the protected artwork mechanically if that creates oversized empty bands. Crop only non-informational outer background, then scale and position the intact protected content to satisfy both gaps.

Zero obstruction is the higher-priority invariant. If the source cannot meet these target ranges without hiding, clipping, or independently moving protected elements, preserve all information and report the unavoidable spacing deviation.

## Full-bleed scale and continuity

The approved 澜记 comparison demonstrates an additional quality gate:

- fitting the entire flat poster inside the safe middle area can preserve information while still producing the wrong result if the artwork becomes a narrow inset rectangle;
- do not accept obvious generated side bands, inconsistent tile or tabletop horizons, blur discontinuities, or a different color temperature around the protected artwork;
- keep the headline and hero product group visually dominant, and keep a comparable lower information card around `885–950 px` wide on the `1080 px` canvas when its source design supports that width;
- if the source is flat, treat the headline, hero products, and information card as separate protected major groups only when their boundaries are visually clear. Move or scale each whole group without changing its internal content;
- if clean major-group separation is not reliable, request a layered source instead of delivering a visibly inset compromise.

## Acceptance judgment

At full resolution, the co-brand lockup should read as three balanced parts: Fantuan mark, divider, merchant mark. The merchant mark must not touch the divider or rounded panel edge, and a narrow/square mark should remain optically centered rather than being enlarged to fill the full width.
