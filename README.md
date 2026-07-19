# Cubism External Edit MCP

[![Python](https://img.shields.io/badge/python-%3C%3D3.13-blue)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-1.0-8A2BE2)](https://modelcontextprotocol.io/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

将 Live2D Cubism Editor 的外部应用集成 API 封装为 **MCP (Model Context Protocol)** 工具，让 AI Agent（如 CodeBuddy、Claude Code）通过自然语言操控 Cubism Editor 进行建模操作。

## 架构

```
AI Agent (CodeBuddy / Claude Code)
    │
    │ stdio (MCP Protocol)
    │
┌───▼──────────────────────┐
│  cubism_mcp_server.py    │  ← 本项目
│  (MCP Server, 9 Tools)   │
└───┬──────────────────────┘
    │
    │ WebSocket (ws://localhost:22033)
    │
┌───▼──────────────────────┐
│  Cubism Editor 5.4 Alpha │
│  (外部应用集成 API)        │
└──────────────────────────┘
```

## 功能特性

- **完整模型查询** — 参数结构、部件结构、变形器结构、单个对象详情
- **编辑操作** — 增删改查参数/部件/变形器/ArtMesh/Glue，自动事务包裹
- **批量编辑** — 同一事务内执行多个操作，任一失败自动回滚
- **权限分级** — 查询需 Allow 授权，编辑需 Edit 授权
- **自动重连** — Editor 重启后自动重连，3 秒间隔
- **Token 持久化** — 认证令牌缓存到 `token.txt`，避免重复授权

## 环境要求

| 组件 | 版本 |
|------|------|
| Python | ≤ 3.13 |
| Cubism Editor | 5.4 Alpha（有效期至 2026-09-14） |
|操作系统 | Windows / macOS |

## 安装

```bash
git clone https://github.com/nana7chi/CubismExternalEditMCP.git
cd CubismExternalEditMCP
pip install -r requirements.txt
```

## 配置 MCP 客户端

### CodeBuddy

设置 → MCP → 添加，粘贴以下 JSON（修改 `cwd` 为实际路径）：

```json
{
  "mcpServers": {
    "cubism-editor": {
      "type": "stdio",
      "command": "python",
      "args": ["cubism_mcp_server.py"],
      "cwd": "J:/CubismExternalEditMCP",
      "description": "Cubism Editor 建模工具"
    }
  }
}
```

### Claude Code

在 `~/.claude/mcp.json` 添加：

```json
{
  "mcpServers": {
    "cubism-editor": {
      "command": "python",
      "args": ["cubism_mcp_server.py"],
      "cwd": "/path/to/CubismExternalEditMCP"
    }
  }
}
```

## 使用流程

1. 启动 Cubism Editor，加载模型
2. **文件 → 外部应用集成设置** → 端口 `22033` → 开启
3. 弹出对话框**勾选 Allow + Edit**，确认
4. 在 AI Agent 中通过自然语言操控 Editor

## 可用工具

### 诊断

| 工具 | 说明 |
|------|------|
| `cubism_status` | 检查连接状态、注册状态、授权状态、编辑授权 |

### 查询

| 工具 | 参数 | 说明 |
|------|------|------|
| `cubism_get_model_uid` | — | 获取当前打开模型的 UID |
| `cubism_get_parameter_structure` | `model_uid` | 参数结构树（组+参数，含 Min/Default/Max） |
| `cubism_get_part_structure` | `model_uid` | 部件结构树（ArtMesh/Deformer/Part/Glue） |
| `cubism_get_deformer_structure` | `model_uid` | 变形器结构树 |
| `cubism_get_object` | `model_uid`, `id` | 获取指定对象详情（按类型返回不同结构） |
| `cubism_get_selected` | `model_uid` | 获取 Editor 中当前选中的对象列表 |

### 编辑

| 工具 | 参数 | 说明 |
|------|------|------|
| `cubism_edit` | `action`, `params` | 执行单个编辑操作（自动 Begin/End） |
| `cubism_edit_batch` | `actions[]` | 批量编辑（同一事务，失败自动回滚） |

#### 支持的编辑 Action

`AddParameter`, `EditParameter`, `DeleteParameter`, `AddParameterGroup`, `EditParameterGroup`, `AddPart`, `EditPart`, `AddWarpDeformer`, `AddRotationDeformer`, `EditWarpDeformer`, `EditArtMesh`, `EditGlue`, `MoveParameter`, `MoveParameterGroup`, `AddParameterKey`, `DeleteParameterKey`, `MoveParameterKey`, `DeleteObject`, `MoveObjectOnPartsPalette`

## 使用示例

```
"列出当前模型的参数结构"
"查看部件层级"
"把 Core 部件的标签设为蓝色"
"新建参数 ParamsTest，ID 为 ParamTest，范围 0-1，默认 0.5"
"批量添加 3 个关键帧到 ParamAngleX"
"选中整体XY 变形器，移动到位置 (3000, 4000)"
```

## 常见问题

| 症状 | 原因 | 解决 |
|------|------|------|
| MCP 状态红色 | Python 路径/依赖/`cwd` 错误 | 检查 Python 版本 ≤ 3.13，确认依赖安装、`cwd` 路径正确 |
| 未连接到 Editor | Editor 未启动或外部集成未开启 | 启动 Editor → 加载模型 → 文件菜单开启外部集成 |
| 未授权 | 弹窗未勾选 Allow | 在外部集成对话框中勾选 Allow |
| 编辑报错 | 弹窗未勾选 Edit | 在外部集成对话框中勾选 Edit |
| 重启后失效 | Editor 重启需重新授权 | 重新开启外部集成并勾选权限 |
| 操作报错 | 参数/ID 不正确 | 先用 `cubism_get_*_structure` 查询结构再操作 |

## 开发

```bash
# 直接运行测试
python cubism_mcp_server.py

# 依赖
pip install -r requirements.txt
```

### 依赖

| 包 | 用途 |
|----|------|
| `mcp` | MCP 服务端框架（stdio 通信） |
| `websockets` | WebSocket 客户端，连接 Editor API |
| `pydantic` | 数据模型验证 |
| `nest_asyncio` | 嵌套事件循环支持 |

## 注意事项

- **Alpha 版本限制**：Cubism Editor 5.4 Alpha 有效期至 2026-09-14，到期后需升级
- **重启授权**：每次重启 Editor 都需要重新开启外部应用集成并勾选权限
- **单模型**：MCP 服务同时只能操作一个打开的模型
- **事务安全**：编辑操作自动包裹 `EditBegin/EditEnd`，批量操作失败自动 `Cancel` 回滚

## License

MIT
