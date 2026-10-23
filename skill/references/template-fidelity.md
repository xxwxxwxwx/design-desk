# 固定品牌模板保真

v5.2 的品牌资产由本地程序确定性合成。

## 正式资产

- `assets/fantuan-info-overlay-1080x1440.svg`
- `assets/fantuan-info-overlay-1080x1440.png`
- `assets/fantuan-only-info-overlay-1080x1440.svg`
- `assets/fantuan-only-info-overlay-1080x1440.png`
- `assets/fantuan-lockup-transparent.png`
- `assets/fonts/AlimamaFangYuanTiVF-Thin-2.ttf`

## 合同

- 画布固定为 1080×1440。
- 中央透明区域为 `y=160–1313`。
- 联名模式必须使用真实商家 Logo。
- 商家 Logo 先裁透明边与满足条件的外围白底，再按 contain 保持比例。
- 商家名称使用项目字体的 SemiBold 实例；超出槽位必须报错，不自动缩小、截断或换行。
- 输出不得覆盖底图、模板、SVG、Logo 或字体输入。
- `validate_output.py` 只证明尺寸和固定像素正确，不能替代视觉验收。
