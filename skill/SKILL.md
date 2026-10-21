---
name: create-fantuan-xiaohongshu-recruitment-poster
description: Create one final 1080×1440 Fantuan Xiaohongshu merchant recruitment poster from up to nine real product or reference images and structured activity facts, then deterministically add the approved Fantuan co-brand header and bottom information bar. Use for 招募官、品鉴官、体验官、试喝官、霸王餐 or 饭团周末 recruitment-poster requests. Do not use for ordinary copywriting, unrelated posters, menus, or multi-size adaptations.
---

# 饭团小红书招募海报

面向非设计运营人员，将真实商家素材和活动事实制作为一张可下载的 `1080×1440` PNG。对外是一个 Skill，内部分为主视觉生成和固定信息条合成两个阶段。

## 输入合同

- `1–9` 张生成素材，每张标记为真实产品、商家参考、风格参考、版式参考、吉祥物或其他。
- 商家 Logo 单独输入，不占 9 张素材额度，不发给图片模型重绘。
- 商家名、招募类型、人数、时间、地址、体验内容或额度、报名条件、报名方式和通知说明。
- `overlay_mode` 为 `co_brand` 或 `fantuan_only`。`co_brand` 必须提供真实商家 Logo。

## 执行流程

1. 识别每张图片的角色，将用户填写的事实与创意偏好分开。
2. 选择版式时读取 [版式规则](references/layout-rules.md)。
3. 构建主视觉生成请求。图片模型不得生成或仿造 Logo 和固定信息条；顶部 160 px 和底部 126 px 保留自然背景。
4. 将模型输出安全适配为 `1080×1440`，不得拉伸、压扁或改变真实产品身份。
5. 读取 [生产验收](references/production-qa.md)，检查事实、产品、安全区和阅读层级。
6. 读取 [固定模板保真](references/template-fidelity.md)，通过 `scripts/compose_poster.py` 原样合成商家 Logo、商家名和饭团固定信息条。
7. 运行 `scripts/validate_output.py`；只有机械验证通过后才能返回最终 PNG。

## 不可妥协的边界

- 活动事实逐字保留，未提供的日期、地址、人数、额度或福利不得补造。
- 产品、容器、包装、数量和宽高比以真实素材为权威；参考图中的商品、价格和旧文案不得混入。
- 图片模型不得生成饭团 Logo、商家 Logo、联名面板或底部搜索条。
- 固定模板不得通过生成模型重绘、变形、变色或近似模仿。
- 安全区检查、固定像素检查与最终视觉验收是不同层次；机械验证成功不等于业务视觉验收已完成。

