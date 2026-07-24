"""
Cubism Editor External API MCP Server
将 Live2D Cubism Editor 的外部应用集成 API 封装为 MCP 工具，
供 Workbuddy 等 AI Agent 直接调用。

依赖见 pyproject.toml（pip install . 或 uvx 运行时自动安装）

使用前:
  1. 启动 Cubism Editor 并打开模型
  2. 菜单「文件」→「外部应用程序集成的设置」→ 确保「使用」开关已开启
  3. 当 MCP 首次连接时，Editor 会弹出「外部应用程序集成」对话框，
     看到 "cubism-mcp" 后，依次勾选 Allow 和 Edit 权限并点 OK。
     如果没看到弹窗，检查 Editor 右下角是否有闪烁的外部应用图标。
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from typing import Literal

import websockets

from mcp.server.fastmcp import FastMCP

# MCP 使用 stdio 协议，日志必须输出到 stderr，绝不能污染 stdout
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="[cubism-mcp] %(levelname)s %(message)s")
logger = logging.getLogger("cubism-mcp")

# Editor「外部应用程序集成的设置」中可修改端口，可用环境变量 CUBISM_PORT 覆盖默认值
DEFAULT_PORT = int(os.environ.get("CUBISM_PORT", "22033"))
URL = "localhost"
# token 存到用户目录而非包安装目录：uvx 缓存清理或版本更新后安装目录会变化，导致 token 丢失需重新授权
TOKEN_FILENAME = os.path.join(os.path.expanduser("~"), ".cubism-mcp", "token.txt")

# 支持的编辑 API 列表，用于 inputSchema 的 enum 约束，让客户端在发送前拦截无效 action
EDIT_ACTIONS = [
    "AddParameter", "EditParameter", "DeleteParameter",
    "AddParameterGroup", "EditParameterGroup",
    "AddPart", "EditPart",
    "AddWarpDeformer", "AddRotationDeformer", "EditWarpDeformer",
    "EditArtMesh", "EditGlue",
    "MoveParameter", "MoveParameterGroup",
    "AddParameterKey", "DeleteParameterKey", "MoveParameterKey",
    "DeleteObject", "MoveObjectOnPartsPalette",
]

# 用 Literal 类型让 FastMCP 自动生成 enum 约束的 inputSchema
EditAction = Literal[
    "AddParameter", "EditParameter", "DeleteParameter",
    "AddParameterGroup", "EditParameterGroup",
    "AddPart", "EditPart",
    "AddWarpDeformer", "AddRotationDeformer", "EditWarpDeformer",
    "EditArtMesh", "EditGlue",
    "MoveParameter", "MoveParameterGroup",
    "AddParameterKey", "DeleteParameterKey", "MoveParameterKey",
    "DeleteObject", "MoveObjectOnPartsPalette",
]


class CEPluginClient:
    """Cubism Editor WebSocket 客户端（基于官方 ceplugin.py 改写）"""

    def __init__(self):
        self.websocket = None
        self.TOKEN = ""
        if os.path.isfile(TOKEN_FILENAME):
            with open(TOKEN_FILENAME, "r") as f:
                self.TOKEN = f.read().strip()
        self.appName = "cubism-mcp"
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
                    await self.on_receive(await self.websocket.recv())
                except websockets.ConnectionClosed:
                    logger.info("与 Cubism Editor 的连接断开，准备重连")
                    self.websocket = None
                    self.isRegistered = False
                    self._ensure_reconnect()
                except Exception:
                    logger.exception("处理 Editor 消息时出错")
                    await asyncio.sleep(0.5)

    async def connect(self, port: int = DEFAULT_PORT):
        if self.websocket is not None:
            await self.websocket.close()
        try:
            self.websocket = await websockets.connect(self.uri(port))
            await self.registerPlugin()
        except Exception as e:
            logger.warning(f"连接 Cubism Editor 失败: {e}")
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

    def _ensure_reconnect(self):
        """确保同一时间只有一个重连任务在运行，避免并发重连互相关闭对方的连接。
        已有健康连接时直接返回：否则每次工具调用都会触发一次完整重连，
        而 Editor 的授权绑定在连接上，重连会丢失授权状态。"""
        if self.websocket is not None and self.isRegistered:
            return
        if self._connect_task is None or self._connect_task.done():
            self._connect_task = asyncio.ensure_future(self.connectWithRetry())

    def start(self):
        """启动监听与连接任务（幂等）"""
        if self._listen_task is None:
            self._listen_task = asyncio.ensure_future(self.startListen())
        self._ensure_reconnect()

    async def sendRaw(self, data: dict):
        if self.websocket is None:
            raise ConnectionError("未连接到 Cubism Editor")
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
        guid = uuid.uuid4().hex
        fut = asyncio.get_running_loop().create_future()

        async def onReceive(responseData):
            if not fut.done():
                fut.set_result(responseData)

        async def onError(errorData):
            if not fut.done():
                fut.set_result({"Error": errorData})

        self.responseHandlers[guid] = onReceive
        self.errorHandlers[guid] = onError
        try:
            await self.sendRaw({
                "Version": "1.1.0",
                "RequestId": guid,
                "Type": "Request",
                "Method": method,
                "Data": data
            })
            if timeout > 0:
                return await asyncio.wait_for(fut, timeout)
            return await fut
        except asyncio.TimeoutError:
            return {"Error": {"ErrorType": "Timeout", "Message": f"{method} timed out"}}
        except ConnectionError as e:
            return {"Error": {"ErrorType": "NotConnected", "Message": str(e)}}
        finally:
            # 无论响应、超时还是异常，都清理 handler，避免泄漏和迟到响应误触发
            self.responseHandlers.pop(guid, None)
            self.errorHandlers.pop(guid, None)

    async def registerPlugin(self):
        async def onReceive(data):
            newToken = data.get("Token", "")
            if newToken and newToken != self.TOKEN:
                self.TOKEN = newToken
                os.makedirs(os.path.dirname(TOKEN_FILENAME), exist_ok=True)
                with open(TOKEN_FILENAME, "w") as f:
                    f.write(newToken)
            self.isRegistered = True
            logger.info("已注册到 Cubism Editor")

        await self.send("RegisterPlugin", {
            "Token": self.TOKEN,
            "Name": self.appName
        }, responseHandler=onReceive)

    async def on_receive(self, message: str):
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
            return {"Error": {
                "ErrorType": "NotRegistered",
                "Message": "未连接到 Cubism Editor。",
                "Steps": [
                    "1. 确保已启动 Cubism Editor 并打开了一个模型",
                    "2. 点击菜单「文件」→「外部应用程序集成的设置」",
                    "3. 确认「使用」开关已开启（端口默认 22033）",
                    "4. 如果已开启但仍无法连接，请尝试关闭后重新开启"
                ]
            }}
        isAuth = await self.sendAndWait("GetIsApproval", {})
        if not isAuth.get("Result", False):
            return {"Error": {
                "ErrorType": "NotApproved",
                "Message": "MCP 已连接到 Editor，但需要在 Editor 中授权。",
                "Steps": [
                    "1. 切换到 Cubism Editor 窗口，应该能看到「外部应用程序集成」弹窗",
                    "2. 找到「cubism-mcp」，勾选 Allow 权限",
                    "3. 点击 OK 确认",
                    "4. 如果没看到弹窗，检查 Editor 右下角任务栏是否有闪烁的外部应用图标，点击打开"
                ]
            }}
        return None

    async def ensureEditReady(self):
        err = await self.ensureReady()
        if err:
            return err
        isEdit = await self.sendAndWait("GetIsEditApproval", {})
        if not isEdit.get("Result", False):
            return {"Error": {
                "ErrorType": "EditNotApproved",
                "Message": "Allow 权限已授权，但缺少 Edit 修改权限。",
                "Steps": [
                    "1. 切换到 Cubism Editor 窗口的「外部应用程序集成」对话框",
                    "2. 找到「cubism-mcp」，额外勾选 Edit 权限",
                    "3. 点击 OK 确认"
                ]
            }}
        return None


client = CEPluginClient()

mcp = FastMCP("cubism-mcp")


def _start_client():
    """确保 WebSocket 客户端已启动（幂等）"""
    client.start()


def _json(data, indent=None):
    return json.dumps(data, ensure_ascii=False, indent=indent)


@mcp.tool()
async def cubism_status() -> str:
    """检查与 Cubism Editor 的连接及授权状态。未连接或未授权时会返回具体指引。"""
    _start_client()
    if client.websocket is None or not client.isRegistered:
        return _json({
            "connected": client.websocket is not None,
            "registered": client.isRegistered,
            "approved": False,
            "edit_approved": False,
            "port": DEFAULT_PORT,
            "hint": "未连接到 Cubism Editor。请启动 Editor → 打开模型 → 「文件」→「外部应用程序集成的设置」→ 开启开关。连接成功后需在弹窗中勾选 Allow 和 Edit 权限。"
        }, indent=2)
    isAuth = await client.sendAndWait("GetIsApproval", {})
    isEdit = await client.sendAndWait("GetIsEditApproval", {})
    return _json({
        "connected": client.websocket is not None,
        "registered": client.isRegistered,
        "approved": isAuth.get("Result", False),
        "edit_approved": isEdit.get("Result", False),
        "port": DEFAULT_PORT,
        "hint": "已连接。如需编辑模型，请确保对话框中 Allow 和 Edit 都已勾选。"
    }, indent=2)


@mcp.tool()
async def cubism_get_model_uid() -> str:
    """获取当前在 Cubism Editor 中打开的模型 UID"""
    _start_client()
    err = await client.ensureReady()
    if err:
        return _json(err)
    resp = await client.sendAndWait("GetCurrentModelUID", {})
    return _json(resp, indent=2)


@mcp.tool()
async def cubism_get_parameter_structure(model_uid: str) -> str:
    """获取模型的完整参数结构树（参数组 + 参数，含 Min/Default/Max/KeyValues）

    Args:
        model_uid: 模型 UID（可通过 cubism_get_model_uid 获取）
    """
    _start_client()
    err = await client.ensureReady()
    if err:
        return _json(err)
    resp = await client.sendAndWait("GetParameterStructure", {"ModelUID": model_uid})
    return _json(resp, indent=2)


@mcp.tool()
async def cubism_get_part_structure(model_uid: str) -> str:
    """获取模型的部件结构树（含 ArtMesh/WarpDeformer/RotationDeformer/Part/ArtPath/Glue 类型）

    Args:
        model_uid: 模型 UID
    """
    _start_client()
    err = await client.ensureReady()
    if err:
        return _json(err)
    resp = await client.sendAndWait("GetPartStructure", {"ModelUID": model_uid})
    return _json(resp, indent=2)


@mcp.tool()
async def cubism_get_deformer_structure(model_uid: str) -> str:
    """获取模型的变形器结构树

    Args:
        model_uid: 模型 UID
    """
    _start_client()
    err = await client.ensureReady()
    if err:
        return _json(err)
    resp = await client.sendAndWait("GetDeformerStructure", {"ModelUID": model_uid})
    return _json(resp, indent=2)


@mcp.tool()
async def cubism_get_object(model_uid: str, id: str) -> str:
    """获取指定对象的信息（按 Type 返回不同数据结构：ArtMesh/Part/WarpDeformer/RotationDeformer/Glue）

    Args:
        model_uid: 模型 UID
        id: 对象 ID
    """
    _start_client()
    err = await client.ensureReady()
    if err:
        return _json(err)
    resp = await client.sendAndWait("GetObject", {"ModelUID": model_uid, "Id": id})
    return _json(resp, indent=2)


@mcp.tool()
async def cubism_edit(action: EditAction, params: dict) -> str:
    """执行编辑操作。会自动处理 EditBegin/EditEnd。

    Args:
        action: 编辑 API 名称，如 AddParameter / EditPart / AddWarpDeformer
        params: 编辑 API 的参数对象（无需 ModelUID，自动填充）
    """
    _start_client()
    err = await client.ensureEditReady()
    if err:
        return _json(err)
    modelUID_resp = await client.sendAndWait("GetCurrentModelUID", {})
    modelUID = modelUID_resp.get("ModelUID", "")
    params = dict(params)
    params["ModelUID"] = modelUID

    beginResp = await client.sendAndWait("EditBegin", {"Silent": False})
    if "Error" in beginResp:
        return _json(beginResp)

    resp = None
    try:
        resp = await client.sendAndWait(action, params)
    except Exception as e:
        resp = {"Error": {"ErrorType": "Exception", "Message": str(e)}}
    finally:
        # 无论编辑成功、失败还是异常，都必须关闭事务，否则 Editor 会停留在编辑模式
        endResp = await client.sendAndWait("EditEnd", {"Cancel": resp is None or "Error" in resp})
    return _json({
        "action": action,
        "result": resp,
        "edit_end": endResp
    }, indent=2)


@mcp.tool()
async def cubism_edit_batch(actions: list[dict]) -> str:
    """批量执行多个编辑操作，在同一个 EditBegin/EditEnd 事务内完成。

    Args:
        actions: [{action, params}] 数组，action 是编辑 API 名称，params 是该 API 的参数对象
    """
    _start_client()
    err = await client.ensureEditReady()
    if err:
        return _json(err)
    modelUID_resp = await client.sendAndWait("GetCurrentModelUID", {})
    modelUID = modelUID_resp.get("ModelUID", "")

    beginResp = await client.sendAndWait("EditBegin", {"Silent": False})
    if "Error" in beginResp:
        return _json(beginResp)

    results = []
    hasError = False
    exception = None
    try:
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
    except Exception as e:
        hasError = True
        exception = str(e)
    finally:
        # 无论成功、失败还是异常，都必须关闭事务，否则 Editor 会停留在编辑模式
        endResp = await client.sendAndWait("EditEnd", {"Cancel": hasError})
    output = {
        "total": len(actions),
        "completed": len(results),
        "cancelled": hasError,
        "results": results,
        "edit_end": endResp
    }
    if exception:
        output["exception"] = exception
    return _json(output, indent=2)


@mcp.tool()
async def cubism_get_selected(model_uid: str) -> str:
    """获取当前在 Editor 中选中的对象 ID 列表

    Args:
        model_uid: 模型 UID
    """
    _start_client()
    err = await client.ensureReady()
    if err:
        return _json(err)
    resp = await client.sendAndWait("GetSelectedObjects", {"ModelUID": model_uid})
    return _json(resp, indent=2)


def cli():
    """Entry point for uvx / pip install"""
    mcp.run()


if __name__ == "__main__":
    cli()
