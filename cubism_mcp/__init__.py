"""Cubism Editor External API MCP Server。

将 Live2D Cubism Editor 的外部应用集成 API 封装为 MCP 工具，
供 Workbuddy 等 AI Agent 直接调用。

使用前:
  1. 启动 Cubism Editor 并打开模型
  2. 菜单「文件」→「外部应用程序集成的设置」→ 确保「使用」开关已开启
  3. 当 MCP 首次连接时，Editor 会弹出「外部应用程序集成」对话框，
     看到 "cubism-mcp" 后，依次勾选 Allow 和 Edit 权限并点 OK。
     如果没看到弹窗，检查 Editor 右下角是否有闪烁的外部应用图标。

包结构:
  config.py   — 配置常量与日志
  types.py    — 编辑 Action 与枚举 Literal 类型
  client.py   — CEPluginClient（WebSocket 通信层）
  server.py   — FastMCP 装配 + 读取/查询工具 + 通用编辑入口
  tools/      — 编辑工具按域分模块
"""

# 导入 server 触发所有 @mcp.tool() 注册（server.py 内部会导入 tools 子包）
from .server import cli, mcp

__all__ = ["cli", "mcp"]
