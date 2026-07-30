# CLAUDE.md

> AI 助手项目指南 — 在修改此项目的任何代码前，请先阅读本文件。

## 构建 / 运行 / 测试

```bash
# 安装开发依赖（在项目根目录）
python3 -m venv .venv
.venv/bin/pip install -e .

# 语法检查
.venv/bin/python3 -c "import py_compile; py_compile.compile('cubism_mcp.py', doraise=True)"

# 导入检查
.venv/bin/python3 -c "import cubism_mcp"

# Lint 检查（CI 同等）
.venv/bin/pip install ruff
.venv/bin/ruff check cubism_mcp.py --ignore E501,BLE001,ASYNC230

# 本地开发时 MCP 配置（直接跑脚本，不用 uvx）
# command: /Users/linjiashen/CubismExternalEditMCP/.venv/bin/python3
# args: ["/Users/linjiashen/CubismExternalEditMCP/cubism_mcp.py"]
# 注意：修改工具列表后需"先禁用 → 再启用"连接器才能强制重连
```

## 项目架构

**单文件 Python 项目**，将 Live2D Cubism Editor（5.4 Alpha）的外部应用集成 API 封装为 MCP 服务器。

```
AI Agent (WorkBuddy/Claude) ←→ stdio/MCP ←→ cubism_mcp.py ←→ WebSocket ←→ Cubism Editor (ws://localhost:22033)
```

### 核心文件

| 文件 | 用途 |
|------|------|
| `cubism_mcp.py` | **唯一源码文件**（~1400 行）。包含 42 个 MCP 工具 + WebSocket 客户端 |
| `pyproject.toml` | 项目元数据，依赖 `mcp>=1.0.0` + `websockets>=12.0` |
| `README.md` | 中文主文档 |
| `i18n/README_{EN,JA,KO}.md` | 英/日/韩翻译文档 |

### 核心类：`CEPluginClient`

WebSocket 连接管理，负责：
- 与 Editor 建立/重连 WebSocket（端口 22033，可通过 `CUBISM_PORT` 环境变量覆盖）
- `RegisterPlugin` 注册 + token 持久化到 `~/.cubism-mcp/token.txt`
- 请求/响应匹配（`asyncio.Future` 机制，超时 15 秒）
- 权限分级：`ensureReady()`（Allow 权限）/ `ensureEditReady()`（Allow + Edit 权限）

### 编辑工具架构

所有 21 个编辑 Action 均有独立 Tool（`cubism_add_parameter` 等），带完整类型签名和 JSON Schema。
内部通过 `_run_edit(action, params, silent, model_uid)` 辅助函数统一处理：
- 校验 `model_uid` 与 Editor 当前模型一致（不一致则报错）
- 自动包裹 `EditBegin/EditEnd` 事务
- 异常时自动 `Cancel` 回滚

`cubism_edit` 和 `cubism_edit_batch` 保留用于向后兼容和批量操作。

### 权限模型

| 权限 | 说明 | 适用操作 |
|------|------|---------|
| Allow | 只读 | Get/Set/ClearParameterValues、GetDocuments、结构查询 |
| Edit | 可写 | EditBegin/EditEnd 事务内所有编辑 API |

`cubism_edit` 和 `cubism_edit_batch` 自动管理 `EditBegin/EditEnd` 事务，异常时自动 `Cancel` 回滚。

## 代码规范

### README 维护规则（强制执行）

1. **修改 `README.md` 时，必须同步更新** `i18n/README_EN.md`、`i18n/README_JA.md`、`i18n/README_KO.md`
2. **专业术语必须与 Live2D 官方文档一致**：
   - 英文：External API Integration、Allow、Edit、ModelingDocuments、PhysicsDocuments、AnimationDocuments
   - 日文：外部連携 API、許可、編集
   - 韩文：외부 연동 API、허용
3. **5.4 Alpha 专属接口**在章节标题标注"5.4 Alpha 新增"，不在每行加标记

### 编辑 Action 添加规则

当官方文档有新增编辑 API 时，需要在**两个地方**同步添加：
1. `EDIT_ACTIONS` 列表（第 41-50 行）— 运行时 enum 校验
2. `EditAction` Literal 类型（第 53-62 行）— MCP inputSchema 生成

当前支持的 action 列表见 `EDIT_ACTIONS` 常量。

### API 版本兼容

- **第二类（外部集成 API）**：Editor 4.x+ 通用，协议版本 v0.9.x
  - v0.9.0：RegisterPlugin、Get/SetParameterValues、GetCurrentModelUID、GetDocuments
  - v0.9.1：ClearParameterValues、动画文档支持
  - v0.9.2：GetPhysicsInfo
  - v0.9.3：GetDocument、SendCubismLog
  - v1.0.1：GetParameters 支持 Keyform
- **第三类（编辑 API）**：仅 5.4 Alpha，协议版本 v1.1.0
  - EditBegin/EditEnd 事务 + 参数/部件/变形器/ArtMesh/Glue CRUD + 结构查询
  - 仅在建模模式（Modeling）下有效

### 日志与输出

- 所有 `logging` 输出到 `stderr`，严禁污染 `stdout`（MCP 使用 stdio 协议）
- `_json()` 辅助函数：统一 `ensure_ascii=False` + `indent=2`

## Git 工作流

| 分支 | 用途 |
|------|------|
| `master` | 稳定发布，合并通过 PR |
| `dev` | 日常开发，所有本地修改在此进行 |

### 推送规则

- **禁止 AI 助手未经用户明确同意执行 `git push`**
- 本机 `git push` 走 HTTP 代理可能不通（502），可用 `gh api` 替代

### CI（`.github/workflows/ci.yml`）

push/PR 到 `dev`/`master` 自动运行：语法检查 + 导入检查 + ruff lint
覆盖 Python 3.10 / 3.12

## 枚举参数值获取

官方 alpha1 文档中 `ColorBlend` / `AlphaBlend` / `LabelColorType` 等枚举参数的有效值藏在锚点内，WebFetch 可能抓不到。**可靠验证方法**：直接向 Editor API 传无效值（如 `"INVALID"`），Editor 会在错误信息中返回完整的 `Allowed values` 列表。

实测结果（已验证）：
- `ColorBlend`: `"normal"` `"add"` `"addglow"` `"darken"` `"multiply"` `"colorburn"` `"linearburn"` `"lighten"` `"screen"` `"colordodge"` `"overlay"` `"softlight"` `"hardlight"` `"linearlight"` `"hue"` `"color"` `"add_5.2"` `"multiply_5.2"`
- `AlphaBlend`: `"over"` `"atop"` `"out"` `"conjoint"` `"disjoint"`
- `LabelColorType`: `"undefined"` `"custom"` `"red"` `"orange"` `"yellow"` `"green"` `"blue"` `"purple"` `"gray"`
- `Mode`（变形器）: `"AsParent"` `"AsChild"`
- 注：Editor 存储归一化为小写，但输入大小写不敏感

## 官方文档参考

### 旧版外部集成 API（Editor 4.x+，协议 v0.9.x）

- 外部集成 API 总览（中文）：https://docs.live2d.com/zh-CHS/cubism-editor-manual/external-application-integration-api/
- 总览（英文）：https://docs.live2d.com/en/cubism-editor-manual/external-application-integration-api/
- 总览（日文）：https://docs.live2d.com/ja/cubism-editor-manual/external-application-integration-api/
- 命令列表（中文）：https://docs.live2d.com/zh-CHS/cubism-editor-manual/external-application-integration-api-list/
- 命令列表（英文）：https://docs.live2d.com/en/cubism-editor-manual/external-application-integration-api-list/
- 命令列表（日文）：https://docs.live2d.com/ja/cubism-editor-manual/external-application-integration-api-list/

### 5.4 Alpha 编辑 API（协议 v1.1.0，仅 5.4 Alpha）

- 开发者手册（中文）：https://cubism.live2d.com/link/manual5_4_alpha_external-api-intergration_zh
- 开发者手册（英语）：https://cubism.live2d.com/editor-alpha/doc/manual/alpha1/en/external-api-intergration/index.html
- 开发者手册（日语）：https://cubism.live2d.com/editor-alpha/doc/manual/alpha1/ja/external-api-intergration/index.html

> 注：中英文版可能存在机翻导致的歧义，API 名称和参数以日语原版为准。

### SDK 底层

- Cubism Core API（C++ SDK，非 Editor）：https://docs.live2d.com/en/cubism-sdk-manual/cubism-core-api-reference/
