"""
Cubism Editor External API MCP Server
将 Live2D Cubism Editor 的外部应用集成 API 封装为 MCP 工具，
供 Claude Code / Codex CLI 等 AI Agent 直接调用。

依赖: pip install mcp websockets pydantic nest_asyncio

配置 Claude Code:
  在 ~/.claude/mcp.json 添加:
  {
    "mcpServers": {
      "cubism-editor": {
        "command": "python",
        "args": ["C:/path/to/cubism_mcp_server.py"]
      }
    }
  }

使用前:
  1. 启动 Cubism Editor 5.4 alpha 并打开模型
  2. 文件菜单 → 外部应用集成设置 → 端口 22033 → 开启开关
  3. 连接后在对话框勾选 Allow + Edit 权限
"""

import asyncio
import json
import os
import time
import uuid
from typing import Any, Optional

import websockets
from pydantic import BaseModel
import nest_asyncio

from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.lowlevel.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

nest_asyncio.apply()

DEFAULT_PORT = 22033
URL = "localhost"
TOKEN_FILENAME = os.path.join(os.path.dirname(__file__), "token.txt")


class CEPluginClient:
    """Cubism Editor WebSocket 客户端（基于官方 ceplugin.py 改写）"""

    def __init__(self):
        self.websocket = None
        self.TOKEN = ""
        if os.path.isfile(TOKEN_FILENAME):
            with open(TOKEN_FILENAME, "r") as f:
                self.TOKEN = f.read()
        self.appName = "MCP-CubismAgent"
        self.responseHandlers = {}
        self.eventHandlers = {}
        self.errorHandlers = {}
        self.isRegistered = False
        self._listen_task = None
        self._connect_task = None

    def uri(self, port: int) -> str:
        return f"ws://{URL}:{port}"

    async def startListen(self):
        while True:
            if self.websocket is None:
                await asyncio.sleep(0.2)
            else:
                try:
                    await self.on_receieve(await self.websocket.recv())
                except websockets.ConnectionClosed:
                    self.websocket = None
                    self.isRegistered = False
                    asyncio.ensure_future(self.connectWithRetry())
                except Exception:
                    await asyncio.sleep(0.5)

    async def connect(self, port: int = DEFAULT_PORT):
        if self.websocket is not None:
            await self.websocket.close()
        try:
            self.websocket = await websockets.connect(self.uri(port))
            await self.registerPlugin()
        except Exception as e:
            self.websocket = None
            return False
        return True

    async def connectWithRetry(self, port: int = DEFAULT_PORT, retryInterval: int = 3):
        self.isRegistered = False
        while True:
            ok = await self.connect(port)
            if ok:
                break
            await asyncio.sleep(retryInterval)

    async def sendRaw(self, data: dict):
        await self.websocket.send(json.dumps(data))

    async def send(self, method: str, data: dict,
                   responseHandler=None, eventHandler=None, errorHandler=None):
        guid = uuid.uuid4().hex
        if responseHandler:
            self.responseHandlers[guid] = responseHandler
        if eventHandler:
            self.eventHandlers[method] = eventHandler
        if errorHandler:
            self.errorHandlers[guid] = errorHandler
        await self.sendRaw({
            "Version": "1.1.0",
            "RequestId": guid,
            "Type": "Request",
            "Method": method,
            "Data": data
        })

    async def sendAndWait(self, method: str, data: dict, timeout: float = 15) -> dict:
        response = None
        isReceived = False

        async def onReceieve(responseData):
            nonlocal response, isReceived
            response = responseData
            isReceived = True

        async def onError(errorData):
            nonlocal response, isReceived
            response = {"Error": errorData}
            isReceived = True

        await self.send(method, data, responseHandler=onReceieve, errorHandler=onError)
        startTime = time.monotonic()
        while not isReceived:
            await asyncio.sleep(0.05)
            if timeout > 0 and time.monotonic() - startTime > timeout:
                return {"Error": {"ErrorType": "Timeout", "Message": f"{method} timed out"}}
        return response

    async def registerPlugin(self):
        async def onReceieve(data):
            newToken = data.get("Token", "")
            if newToken and newToken != self.TOKEN:
                self.TOKEN = newToken
                with open(TOKEN_FILENAME, "w") as f:
                    f.write(newToken)
            self.isRegistered = True

        await self.send("RegisterPlugin", {
            "Token": self.TOKEN,
            "Name": self.appName
        }, responseHandler=onReceieve)

    async def on_receieve(self, message: str):
        jsonData = json.loads(message)
        requestType = jsonData.get("Type")
        method = jsonData.get("Method")
        if requestType in ("Response", "Error"):
            requestID = jsonData.get("RequestId")
            if requestType == "Error":
                if task := self.errorHandlers.get(requestID):
                    asyncio.ensure_future(task(jsonData.get("Data", {})))
                self.errorHandlers.pop(requestID, None)
                self.responseHandlers.pop(requestID, None)
            else:
                if task := self.responseHandlers.get(requestID):
                    asyncio.ensure_future(task(jsonData.get("Data", {})))
                self.responseHandlers.pop(requestID, None)
                self.errorHandlers.pop(requestID, None)
        elif requestType == "Event":
            if task := self.eventHandlers.get(method):
                asyncio.ensure_future(task(jsonData.get("Data", {})))

    async def ensureReady(self):
        if not self.isRegistered:
            return {"Error": {"ErrorType": "NotRegistered", "Message": "未连接到 Editor，请先启动 Editor 并开启外部应用集成"}}
        isAuth = await self.sendAndWait("GetIsApproval", {})
        if not isAuth.get("Result", False):
            return {"Error": {"ErrorType": "NotApproved", "Message": "请在 Editor 外部应用集成对话框勾选 Allow"}}
        return None

    async def ensureEditReady(self):
        err = await self.ensureReady()
        if err:
            return err
        isEdit = await self.sendAndWait("GetIsEditApproval", {})
        if not isEdit.get("Result", False):
            return {"Error": {"ErrorType": "EditNotApproved", "Message": "请在 Editor 对话框勾选 Edit 权限"}}
        return None


client = CEPluginClient()
server = Server("cubism-editor")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="cubism_status",
            description="检查与 Cubism Editor 的连接状态（是否连接、是否授权、是否编辑授权）",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="cubism_get_model_uid",
            description="获取当前在 Cubism Editor 中打开的模型 UID",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="cubism_get_parameter_structure",
            description="获取模型的完整参数结构树（参数组 + 参数，含 Min/Default/Max/KeyValues）",
            inputSchema={"type": "object", "properties": {
                "model_uid": {"type": "string", "description": "模型 UID（可通过 cubism_get_model_uid 获取）"}
            }, "required": ["model_uid"]}
        ),
        Tool(
            name="cubism_get_part_structure",
            description="获取模型的部件结构树（含 ArtMesh/WarpDeformer/RotationDeformer/Part/ArtPath/Glue 类型）",
            inputSchema={"type": "object", "properties": {
                "model_uid": {"type": "string"}
            }, "required": ["model_uid"]}
        ),
        Tool(
            name="cubism_get_deformer_structure",
            description="获取模型的变形器结构树",
            inputSchema={"type": "object", "properties": {
                "model_uid": {"type": "string"}
            }, "required": ["model_uid"]}
        ),
        Tool(
            name="cubism_get_object",
            description="获取指定对象的信息（按 Type 返回不同数据结构：ArtMesh/Part/WarpDeformer/RotationDeformer/Glue）",
            inputSchema={"type": "object", "properties": {
                "model_uid": {"type": "string"},
                "id": {"type": "string", "description": "对象 ID"}
            }, "required": ["model_uid", "id"]}
        ),
        Tool(
            name="cubism_edit",
            description="执行编辑操作。会自动处理 EditBegin/EditEnd。action 指定具体编辑 API，params 是该 API 的参数（不含 ModelUID，会自动填充）。常用 action: AddParameter, EditParameter, DeleteParameter, AddParameterGroup, EditParameterGroup, AddPart, EditPart, AddWarpDeformer, AddRotationDeformer, EditWarpDeformer, EditArtMesh, EditGlue, MoveParameter, MoveParameterGroup, AddParameterKey, DeleteParameterKey, MoveParameterKey, DeleteObject, MoveObjectOnPartsPalette",
            inputSchema={"type": "object", "properties": {
                "action": {"type": "string", "description": "编辑 API 名称，如 AddParameter / EditPart / AddWarpDeformer"},
                "params": {"type": "object", "description": "编辑 API 的参数对象（无需 ModelUID，自动填充）"}
            }, "required": ["action", "params"]}
        ),
        Tool(
            name="cubism_edit_batch",
            description="批量执行多个编辑操作，在同一个 EditBegin/EditEnd 事务内完成。actions 是 [{action, params}] 数组。任一操作失败会自动 Cancel 回滚。",
            inputSchema={"type": "object", "properties": {
                "actions": {"type": "array", "items": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string"},
                        "params": {"type": "object"}
                    },
                    "required": ["action", "params"]
                }}
            }, "required": ["actions"]}
        ),
        Tool(
            name="cubism_get_selected",
            description="获取当前在 Editor 中选中的对象 ID 列表",
            inputSchema={"type": "object", "properties": {
                "model_uid": {"type": "string"}
            }, "required": ["model_uid"]}
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    # 确保客户端在运行
    if client._listen_task is None:
        client._listen_task = asyncio.ensure_future(client.startListen())
        client._connect_task = asyncio.ensure_future(client.connectWithRetry())
        await asyncio.sleep(1)

    if name == "cubism_status":
        isEdit = await client.sendAndWait("GetIsEditApproval", {})
        isAuth = await client.sendAndWait("GetIsApproval", {})
        return [TextContent(type="text", text=json.dumps({
            "connected": client.websocket is not None,
            "registered": client.isRegistered,
            "approved": isAuth.get("Result", False),
            "edit_approved": isEdit.get("Result", False),
            "port": DEFAULT_PORT
        }, ensure_ascii=False, indent=2))]

    if name == "cubism_get_model_uid":
        err = await client.ensureReady()
        if err:
            return [TextContent(type="text", text=json.dumps(err, ensure_ascii=False))]
        resp = await client.sendAndWait("GetCurrentModelUID", {})
        return [TextContent(type="text", text=json.dumps(resp, ensure_ascii=False, indent=2))]

    if name == "cubism_get_parameter_structure":
        err = await client.ensureReady()
        if err:
            return [TextContent(type="text", text=json.dumps(err, ensure_ascii=False))]
        resp = await client.sendAndWait("GetParameterStructure", {"ModelUID": arguments["model_uid"]})
        return [TextContent(type="text", text=json.dumps(resp, ensure_ascii=False, indent=2))]

    if name == "cubism_get_part_structure":
        err = await client.ensureReady()
        if err:
            return [TextContent(type="text", text=json.dumps(err, ensure_ascii=False))]
        resp = await client.sendAndWait("GetPartStructure", {"ModelUID": arguments["model_uid"]})
        return [TextContent(type="text", text=json.dumps(resp, ensure_ascii=False, indent=2))]

    if name == "cubism_get_deformer_structure":
        err = await client.ensureReady()
        if err:
            return [TextContent(type="text", text=json.dumps(err, ensure_ascii=False))]
        resp = await client.sendAndWait("GetDeformerStructure", {"ModelUID": arguments["model_uid"]})
        return [TextContent(type="text", text=json.dumps(resp, ensure_ascii=False, indent=2))]

    if name == "cubism_get_object":
        err = await client.ensureReady()
        if err:
            return [TextContent(type="text", text=json.dumps(err, ensure_ascii=False))]
        resp = await client.sendAndWait("GetObject", {"ModelUID": arguments["model_uid"], "Id": arguments["id"]})
        return [TextContent(type="text", text=json.dumps(resp, ensure_ascii=False, indent=2))]

    if name == "cubism_get_selected":
        err = await client.ensureReady()
        if err:
            return [TextContent(type="text", text=json.dumps(err, ensure_ascii=False))]
        resp = await client.sendAndWait("GetSelectedObjects", {"ModelUID": arguments["model_uid"]})
        return [TextContent(type="text", text=json.dumps(resp, ensure_ascii=False, indent=2))]

    if name == "cubism_edit":
        err = await client.ensureEditReady()
        if err:
            return [TextContent(type="text", text=json.dumps(err, ensure_ascii=False))]
        modelUID_resp = await client.sendAndWait("GetCurrentModelUID", {})
        modelUID = modelUID_resp.get("ModelUID", "")
        params = dict(arguments.get("params", {}))
        params["ModelUID"] = modelUID

        beginResp = await client.sendAndWait("EditBegin", {"Silent": False})
        if "Error" in beginResp:
            return [TextContent(type="text", text=json.dumps(beginResp, ensure_ascii=False))]

        resp = await client.sendAndWait(arguments["action"], params)
        endResp = await client.sendAndWait("EditEnd", {"Cancel": "Error" in resp})
        return [TextContent(type="text", text=json.dumps({
            "action": arguments["action"],
            "result": resp,
            "edit_end": endResp
        }, ensure_ascii=False, indent=2))]

    if name == "cubism_edit_batch":
        err = await client.ensureEditReady()
        if err:
            return [TextContent(type="text", text=json.dumps(err, ensure_ascii=False))]
        modelUID_resp = await client.sendAndWait("GetCurrentModelUID", {})
        modelUID = modelUID_resp.get("ModelUID", "")
        actions = arguments["actions"]

        beginResp = await client.sendAndWait("EditBegin", {"Silent": False})
        if "Error" in beginResp:
            return [TextContent(type="text", text=json.dumps(beginResp, ensure_ascii=False))]

        results = []
        hasError = False
        for i, act in enumerate(actions):
            params = dict(act.get("params", {}))
            params["ModelUID"] = modelUID
            await client.sendAndWait("EditSendProgress", {"Value": (i + 1) / len(actions)})
            await client.sendAndWait("EditSendLog", {"Message": f"[{i+1}/{len(actions)}] {act['action']}"})
            resp = await client.sendAndWait(act["action"], params)
            results.append({"action": act["action"], "result": resp})
            if "Error" in resp:
                hasError = True
                break

        endResp = await client.sendAndWait("EditEnd", {"Cancel": hasError})
        return [TextContent(type="text", text=json.dumps({
            "total": len(actions),
            "completed": len(results),
            "cancelled": hasError,
            "results": results,
            "edit_end": endResp
        }, ensure_ascii=False, indent=2))]

    return [TextContent(type="text", text=f"未知工具: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="cubism-editor",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities=None
                )
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
