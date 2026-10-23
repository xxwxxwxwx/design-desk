---
name: create-fantuan-xiaohongshu-recruitment-poster
description: Create one final 1080×1440 Fantuan Xiaohongshu merchant recruitment poster with the v5.2 central-creative, vertical-outpaint and deterministic brand-composition pipeline.
---

# 饭团小红书招募海报 v5.2

将真实商家素材和活动事实制作为一张可下载的 `1080×1440` PNG。

## 输入合同

- 1–9 张“真实产品”或“风格参考”图片。
- 商家 Logo 单独输入，不占素材额度，也不发送给图片模型。
- 商家名、招募类型、人数、时间、地址、体验内容和报名规则。
- `overlay_mode` 为 `co_brand` 或 `fantuan_only`；联名模式必须提供真实商家 Logo。

真实产品必须保留身份、容器、包装、数量、比例和识别特征。风格参考只迁移视觉语言，不得带入其产品、商家身份、价格、Logo、旧文案或活动事实。

## 执行流程

1. 查看全部素材，确认真实产品、数量、名称对应和风格参考。
2. 按 [v5.2 版式规则](references/layout-rules.md) 组织逐字活动事实。
3. 获得 2 次 Sunburst 1K、预计 12 credits 的明确授权。
4. 生成 8:9 中央完整创意；上下各 30 px 只能是连续背景缓冲。
5. 裁出 1080×1155 中央内容，原比例放入最终画布 `y=160–1314`。
6. 第二次调用只扩展顶部与底部背景，不得新增文字、产品、Logo 或活动元素。
7. 按 [生产验收](references/production-qa.md) 查看中央图和扩展图。
8. 使用 `scripts/compose_poster.py` 确定性合成品牌资产，并运行 `scripts/validate_output.py`。
9. 机械检查与人工视觉检查分开报告；未看图必须标记为待验收。

不得自动付费重试。任何重生成或修正都要重新说明次数、预计费用并取得授权。

## 不可妥协的边界

- 活动事实逐字保留，未提供的信息不得补造。
- 产品与包装以真实素材为权威。
- 图片模型不得生成饭团 Logo、商家 Logo、联名面板或底部搜索条。
- 中央信息框必须包含活动时间、完整地址和完整报名规则。
- 上下扩展区只能延续环境背景。
- 固定品牌模板不得由图片模型重绘。
- 机械验证成功不等于文案、产品和视觉已经人工验收。
