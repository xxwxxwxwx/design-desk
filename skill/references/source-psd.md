# Authoritative PSD source facts

## Preserved source

- Skill path: `assets/source/fantuan-info-bar-authoritative-source.psd`
- Original filename: `小红书-1080_1440px 横条版本.psd`
- SHA-256: `3c41c490545d21fddc1ff973e9c112a1a0059d49ad134bbca78035dbeac92b24`
- Photoshop document: version 1, RGB, 8-bit, 4 channels, `2260×1440`, 24 layers
- Last known creator metadata: Adobe Photoshop 25.3 on macOS

The canvas contains two parallel layouts: Chinese at approximately `x=0–1080`, and English at approximately `x=1180–2260`.

## Chinese top co-brand layers

Coordinates are PSD top-left layer bounds:

| Layer | Bounds |
|---|---|
| 白色底框 | `(227, -134)–(853, 157)` |
| 饭团logo | `(279, 46)–(556, 122)` |
| 分割线 | `(577, 45)–(583, 123)` |
| 商家logo | `(603, 48)–(800, 122)` |

These source coordinates confirm the historical spacing rule: the merchant artwork begins about `20 px` after the divider and ends with about `50 px` before the source panel edge, depending on the Logo's visible width. Preserve optical centering and aspect ratio rather than enlarging every Logo to fill the full source slot.

## Chinese merchant-name text

The editable layer is named `元气森林`. Photoshop text-engine data records:

- font named instance: `AlimamaFangYuanTiVF-SemiBold`;
- size: `22`;
- font weight axis: `600` for the installed named instance;
- bevel axis: `80`;
- tracking: `0`;
- horizontal scale: `1.0`;
- vertical scale: `1.0`;
- faux bold: false;
- faux italic: false.

The matching variable font is bundled at `assets/fonts/AlimamaFangYuanTiVF-Thin-2.ttf`. The filename says Thin because it is a variable-font container; its internal named instances include `SemiBold` and `AlimamaFangYuanTiVF-SemiBold`.

## English source

The English side contains matching editable groups and uses `Poppins-SemiBold` for its English text treatment. This Skill's ordinary output remains the Chinese 1080×1440 format unless the user explicitly requests the English version.

## Compatibility note

The PSD composite contains a curved lower information treatment starting around `y=1154`, whereas the approved raster template and prior finished posters use the flat teal footer at approximately `y=1326–1327`. Do not silently swap between them. The PSD is authoritative for editable layer structure and typography; the bundled blank raster overlay remains authoritative for the currently approved flat-strip output pixels.
