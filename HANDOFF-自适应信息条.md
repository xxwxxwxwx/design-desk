# 饭团小红书海报工作台交接

## 当前目标

继续调整顶部饭团＋商家联名信息条，使其从固定宽度模板变成由商家 Logo 内容驱动的自适应布局，同时保持底部饭团信息条与商家名称的确定性合成。

## 已完成

- 前端支持最多 9 张图片、活动表单、视觉方向、重点突出、信息条模式、商家 Logo 和 KIE API Key。
- 后端已切换为 KIE API。
- 当前模型：`gpt-image-2-5-sunburst-image-to-image`。
- KIE 流程：验证 Key/积分 → 上传图片 → 创建异步任务 → 轮询结果 → 下载图片 → 本地合成固定信息条。
- Key 仅保存在当前服务进程内存中；服务重启后需要重新填写。
- 用户提供的 SVG 已接入：`skill/assets/fantuan-info-overlay-1080x1440.svg`。
- SVG 动态区域：
  - `merchant-logo-slot`
  - `merchant-name-slot`
- 商家名称坐标从 SVG 自动读取。
- 顶部联名条已改为自适应：
  - 白色面板高度：148 px，底部圆角 36 px；仍清空完整顶部 160 px 区域
  - 左右 Padding：42 px
  - 饭团标志与商家 Logo 间距：20 px
  - 商家 Logo 按宽高比分档，上限为 260 × 64 px；超宽 Logo 高度上限 52 px
  - Logo 裁透明边和近白色外围画布，保持比例、不拉伸，彩色底不自动删除
  - 白色联名条根据 Logo 显示宽度自动变化并整体居中
- 已用方形、竖版、横版、超宽和大白边画布五类本地测试 Logo 检查宽高比适配。
- 真实澜记 Logo 的新版本地重合成：`data/jobs/20261021-151607-98604b67/final-adaptive-header-v2.png`。
- 本地重合成和固定像素验证已通过，未因布局测试再次调用 KIE；这不等于用户视觉验收通过。

## 关键文件

- `server.py`：本地 API、KIE 上传/生成/轮询、最终合成入口
- `app/static/index.html`：前端表单
- `app/static/app.js`：上传、Key、生成和预览交互
- `skill/scripts/compose_poster.py`：自适应顶部联名条及底部商家名称合成
- `skill/scripts/validate_output.py`：尺寸和固定模板像素验证
- `skill/assets/fantuan-info-overlay-1080x1440.svg`：可编辑模板源文件
- `skill/assets/fantuan-info-overlay-1080x1440.png`：SVG 渲染后的运行时模板
- `skill/assets/fantuan-lockup-transparent.png`：饭团 Logo＋分隔线透明派生资源

## 最近的真实生成结果

- 任务：`data/jobs/20261021-151607-98604b67/`
- 原始最终图：`final.png`
- SVG 固定槽测试：`final-svg-template-test.png`
- 自适应顶部测试：`final-adaptive-header-test.png`

## 已知问题

- Sunburst 生成的主标题仍可能进入顶部 160 px 安全区，被联名条遮挡。
- 底部报名信息可能进入底部固定信息条区域。
- 产品名称曾直接带出 `.jpg` 文件扩展名。
- 当前“机械验证通过”只验证尺寸和固定像素，不等于视觉验收通过。
- 自适应布局的 Padding、间距、Logo 最大宽高仍需要继续视觉调校。
- 当前 Logo 规则仍允许小尺寸位图放大；如遇低清真实 Logo，需增加放大倍率上限或要求更高清源文件。

## 下一步建议

1. 先只调整顶部自适应联名条，不重新调用 KIE；使用已有底图做本地重合成。
2. 确认不同 Logo 类型的规则：方形、横版、竖版、带白底、透明边过大。
3. 确认最小/最大联名条宽度及窄 Logo 是否允许放大。
4. 用户确认顶部效果后，再处理 Sunburst 上下安全区和自动视觉拦截。
5. 任何重新调用 KIE 的操作前，先说明模型、数量和可能费用并等待确认。

## 运行状态

- 服务地址：`http://127.0.0.1:8788`
- 当前服务进程已经按自适应版本启动。
- 不要把技术验证描述为真实视觉验收。
