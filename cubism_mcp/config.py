"""配置常量与日志。

集中管理所有可配置项，避免散落在各模块中。
"""

import json
import logging
import os
import sys

# MCP 使用 stdio 协议，日志必须输出到 stderr，绝不能污染 stdout
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="[cubism-mcp] %(levelname)s %(message)s",
)
logger = logging.getLogger("cubism-mcp")

# Editor「外部应用程序集成的设置」中可修改端口，可用环境变量 CUBISM_PORT 覆盖默认值
DEFAULT_PORT = int(os.environ.get("CUBISM_PORT", "22033"))
URL = "localhost"

# token 存到用户目录而非包安装目录：uvx 缓存清理或版本更新后安装目录会变化，导致 token 丢失需重新授权
TOKEN_FILENAME = os.path.join(os.path.expanduser("~"), ".cubism-mcp", "token.txt")


def _json(data, indent=None) -> str:
    """统一 JSON 序列化：ensure_ascii=False，可选缩进。"""
    return json.dumps(data, ensure_ascii=False, indent=indent)
