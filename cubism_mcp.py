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
from contextlib import asynccontextmanager
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
    "AddParameterGroup", "EditParameterGroup", "DeleteParameterGroup",
    "AddPart", "EditPart",
    "AddWarpDeformer", "AddRotationDeformer",
    "EditWarpDeformer", "EditRotationDeformer",
    "EditArtMesh", "EditGlue",
    "MoveParameter", "MoveParameterGroup",
    "AddParameterKey", "DeleteParameterKey", "MoveParameterKey",
    "DeleteObject", "MoveObjectOnPartsPalette",
]

# 用 Literal 类型让 FastMCP 自动生成 enum 约束的 inputSchema
EditAction = Literal[
    "AddParameter", "EditParameter", "DeleteParameter",
    "AddParameterGroup", "EditParameterGroup", "DeleteParameterGroup",
    "AddPart", "EditPart",
    "AddWarpDeformer", "AddRotationDeformer",
    "EditWarpDeformer", "EditRotationDeformer",
    "EditArtMesh", "EditGlue",
    "MoveParameter", "MoveParameterGroup",
    "AddParameterKey", "DeleteParameterKey", "MoveParameterKey",
    "DeleteObject", "MoveObjectOnPartsPalette",
]
# 参数枚举类型（通过 Editor API 实测验证，非推断）
# 测试方法：cubism_edit_artmesh 传入无效值，Editor 返回完整的 Allowed values 列表
ColorBlendMode = Literal[
    "normal", "add", "addglow", "darken", "multiply",
    "colorburn", "linearburn", "lighten", "screen",
    "colordodge", "overlay", "softlight", "hardlight",
    "linearlight", "hue", "color",
    "add_5.2", "multiply_5.2",
]
AlphaBlendMode = Literal[
    "over", "atop", "out", "conjoint", "disjoint",
]
LabelColorType = Literal[
    "undefined", "custom",
    "red", "orange", "yellow", "green", "blue", "purple", "gray",
]
DeformerParentMode = Literal["AsParent", "AsChild"]


class CEPluginClient:
    """Cubism Editor WebSocket 客户端（基于官方 ceplugin.py 改写）"""

    def __init__(self):
        self.websocket = None
        self.TOKEN = ""
        if os.path.isfile(TOKEN_FILENAME):
            with open(TOKEN_FILENAME, "r") as f:
                self.TOKEN = f.read().strip()
        self.appName = "cubism-mcp"
        self.icon = None   # 可选：Base64 PNG 图标（32×32~256×256，≤0.5MB）
        self.path = None   # 可选：应用程序路径信息
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
            if "proxy" in str(e).lower() or "socks" in str(e).lower():
                logger.info('检测到代理拦截 localhost 连接，请在 MCP 配置中添加 "env": { "NO_PROXY": "localhost,127.0.0.1" }')
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

    async def waitForRegistration(self, timeout: float = 10) -> bool:
        """等待注册完成。已注册时立即返回 True，超时返回 False。

        连接任务在后台异步建立，工具调用时用它兜底：
        即使 lifespan 预热来不及（Editor 刚启动、首次授权弹窗等），
        也会等待注册完成而非因竞态立即误报未连接。"""
        if self.isRegistered:
            return True
        self._ensure_reconnect()
        deadline = asyncio.get_running_loop().time() + timeout
        while not self.isRegistered:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return False
            await asyncio.sleep(min(0.2, remaining))
        return True

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

        payload = {
            "Token": self.TOKEN,
            "Name": self.appName
        }
        # 可选：Base64 PNG 图标（32×32~256×256，正方形，≤0.5MB）
        if self.icon:
            payload["Icon"] = self.icon
        # 可选：应用程序路径信息
        if self.path:
            payload["Path"] = self.path
        await self.send("RegisterPlugin", payload, responseHandler=onReceive)

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
        if not await self.waitForRegistration(10):
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


@asynccontextmanager
async def lifespan(app):
    # 在 MCP 握手前就启动 WebSocket 连接，让连接建立与 stdio 初始化并行。
    # 这样首次工具调用时注册大概率已完成，避免竞态导致的误报未连接。
    client.start()
    yield


mcp = FastMCP("cubism-mcp", lifespan=lifespan)


def _start_client():
    """确保 WebSocket 客户端已启动（幂等）"""
    client.start()


def _json(data, indent=None):
    return json.dumps(data, ensure_ascii=False, indent=indent)


@mcp.tool()
async def cubism_status() -> str:
    """检查与 Cubism Editor 的连接及授权状态。未连接或未授权时会返回具体指引。"""
    _start_client()
    await client.waitForRegistration(10)
    if client.websocket is None or not client.isRegistered:
        return _json({
            "connected": client.websocket is not None,
            "registered": client.isRegistered,
            "approved": False,
            "edit_approved": False,
            "port": DEFAULT_PORT,
            "hint": "未连接到 Cubism Editor。请启动 Editor → 打开模型 → 「文件」→「外部应用程序集成的设置」→ 开启开关。连接成功后需在弹窗中勾选 Allow 和 Edit 权限。如日志提示 proxy/socks 错误，请在 MCP 配置中添加 \"env\": {\"NO_PROXY\": \"localhost,127.0.0.1\"}。"
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
async def cubism_get_current_edit_mode() -> str:
    """获取 Editor 当前的编辑模式。

    返回值: Physics/Modeling/Animation/ModelingMeshEdit/FormAnimation

    Returns:
        JSON {"EditMode": "Modeling"|"Physics"|"Animation"|"ModelingMeshEdit"|"FormAnimation"}
    """
    _start_client()
    err = await client.ensureReady()
    if err:
        return _json(err)
    resp = await client.sendAndWait("GetCurrentEditMode", {})
    return _json(resp, indent=2)


@mcp.tool()
async def cubism_get_documents() -> str:
    """列出 Editor 中当前打开的所有文档（工作区）。
    按类型分为 PhysicsDocuments（物理模拟）、ModelingDocuments（模型编辑）、
    AnimationDocuments（动画编辑），每种各为一个数组，无对应类型时为空数组。

    无需 model_uid 参数，返回的是 Editor 全局打开的文档列表。

    Returns:
        JSON {"PhysicsDocuments": [...], "ModelingDocuments": [...], "AnimationDocuments": [...]}
    """
    _start_client()
    err = await client.ensureReady()
    if err:
        return _json(err)
    resp = await client.sendAndWait("GetDocuments", {})
    return _json(resp, indent=2)


@mcp.tool()
async def cubism_get_document(document_uid: str) -> str:
    """通过 DocumentUID 获取单个文档的详细信息。

    Args:
        document_uid: 文档 UID（可通过 cubism_get_documents 获取）

    Returns:
        JSON {"ModelingDocuments": [{"DocumentFilePath": str, "Views": [{"ModelUID": str}]}],
              "PhysicsDocuments": [...], "AnimationDocuments": [...]}
    """
    _start_client()
    err = await client.ensureReady()
    if err:
        return _json(err)
    resp = await client.sendAndWait("GetDocument", {"DocumentUID": document_uid})
    return _json(resp, indent=2)


@mcp.tool()
async def cubism_get_parameter_values(model_uid: str, ids: list[str] | None = None) -> str:
    """获取模型当前的参数值。不指定 ids 则返回全部参数。

    这是轻量级读取操作，无需 EditBegin/EditEnd 事务。

    Args:
        model_uid: 模型 UID（可通过 cubism_get_model_uid 获取）
        ids: 可选，要查询的参数 ID 列表。省略则返回所有参数

    Returns:
        JSON {"Parameters": [{"Id": str, "Value": float}]}
    """
    _start_client()
    err = await client.ensureReady()
    if err:
        return _json(err)
    data = {"ModelUID": model_uid}
    if ids:
        data["Ids"] = ids
    resp = await client.sendAndWait("GetParameterValues", data)
    return _json(resp, indent=2)


@mcp.tool()
async def cubism_set_parameter_values(model_uid: str, parameters: list[dict]) -> str:
    """设置模型的参数值。轻量级写入，无需 EditBegin/EditEnd 事务。

    参数通过临时缓冲区生效，物理编辑器/动画模型中可能有延迟。
    使用 ClearParameterValues 可显式清除临时缓存。

    Args:
        model_uid: 模型 UID
        parameters: [{Id: 参数ID, Value: 数值}] 数组，例如 [{"Id":"ParamAngleX","Value":0.5}]

    Returns:
        JSON {"Result": bool}
    """
    _start_client()
    err = await client.ensureReady()
    if err:
        return _json(err)
    resp = await client.sendAndWait("SetParameterValues", {
        "ModelUID": model_uid,
        "Parameters": parameters
    })
    return _json(resp, indent=2)


@mcp.tool()
async def cubism_clear_parameter_values(model_uid: str) -> str:
    """清除发送到模型的临时参数值缓存。与 SetParameterValues 配套使用，
    可显式将模型恢复到参数写入前的状态。

    Args:
        model_uid: 模型 UID

    Returns:
        JSON {}
    """
    _start_client()
    err = await client.ensureReady()
    if err:
        return _json(err)
    resp = await client.sendAndWait("ClearParameterValues", {"ModelUID": model_uid})
    return _json(resp, indent=2)


@mcp.tool()
async def cubism_get_parameters(model_uid: str | None = None, document_uid: str | None = None) -> str:
    """获取模型参数的详细元信息（类型、范围、默认值、关键点、融合变形、循环等）。

    比 cubism_get_parameter_values 多返回参数名称、类型、范围、GroupUID 等结构信息。
    model_uid 和 document_uid 至少提供一个，均省略会返回错误。

    Args:
        model_uid: 模型 UID（可选，与 document_uid 二选一）
        document_uid: 文档 UID（可选，与 model_uid 二选一）

    Returns:
        JSON {"Parameters": [{"Id":str,"Name":str,"GroupUID":str,"Default":float,"Max":float,"Min":float,"Repeat":bool,"Type":int,"Keyform":[{"Value":float}]}]}
        Type: 0=正常, 1=融合变形
    """
    _start_client()
    err = await client.ensureReady()
    if err:
        return _json(err)
    data = {}
    if model_uid is not None:
        data["ModelUID"] = model_uid
    if document_uid is not None:
        data["DocumentUID"] = document_uid
    resp = await client.sendAndWait("GetParameters", data)
    return _json(resp, indent=2)


@mcp.tool()
async def cubism_get_parameter_groups(model_uid: str | None = None, document_uid: str | None = None) -> str:
    """获取模型的参数组列表（组 UID 和组名称）。

    model_uid 和 document_uid 至少提供一个，均省略会返回错误。

    Args:
        model_uid: 模型 UID（可选，与 document_uid 二选一）
        document_uid: 文档 UID（可选，与 model_uid 二选一）

    Returns:
        JSON {"Groups": [{"GroupUID": str, "GroupName": str}]}
    """
    _start_client()
    err = await client.ensureReady()
    if err:
        return _json(err)
    data = {}
    if model_uid is not None:
        data["ModelUID"] = model_uid
    if document_uid is not None:
        data["DocumentUID"] = document_uid
    resp = await client.sendAndWait("GetParameterGroups", data)
    return _json(resp, indent=2)


@mcp.tool()
async def cubism_get_parameter_structure(model_uid: str) -> str:
    """获取模型的完整参数结构树（参数组 + 参数，含 Min/Default/Max/KeyValues）

    Args:
        model_uid: 模型 UID（可通过 cubism_get_model_uid 获取）

    Returns:
        JSON {"ParameterStructure": {"Name":str,"Id":str,"Entries":[{...recursive}]}}
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

    Returns:
        JSON {"PartStructure": {"Name":str,"Id":str,"Type":str,"Entries":[{...recursive}]}}"""
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

    Returns:
        JSON {"DeformerStructure": {"Name":str,"Id":str,"Type":str,"Entries":[{...recursive}]}}
    """
    _start_client()
    err = await client.ensureReady()
    if err:
        return _json(err)
    resp = await client.sendAndWait("GetDeformerStructure", {"ModelUID": model_uid})
    return _json(resp, indent=2)


@mcp.tool()
async def cubism_get_object(model_uid: str, id: str, parameters: list[dict] | None = None) -> str:
    """获取指定对象的信息（按 Type 返回不同数据结构：ArtMesh/Part/WarpDeformer/RotationDeformer/Glue）。

    可选 parameters 参数可按特定参数值获取对象在该状态下的数据。

    Args:
        model_uid: 模型 UID
        id: 对象 ID
        parameters: 可选，关联参数 [{Id: "参数ID", Value: 数值}]，指定后返回该参数状态下的对象信息

    Returns:
        JSON {"Result": bool, "Type": str, "Data": {...}}
    """
    _start_client()
    err = await client.ensureReady()
    if err:
        return _json(err)
    data = {"ModelUID": model_uid, "Id": id}
    if parameters:
        data["Parameters"] = parameters
    resp = await client.sendAndWait("GetObject", data)
    return _json(resp, indent=2)


@mcp.tool()
async def cubism_edit(action: EditAction, params: dict) -> str:
    """执行编辑操作。会自动处理 EditBegin/EditEnd。
    所有 Action 均已拆分为独立 Tool（带完整类型签名），建议直接使用对应 Tool。
    cubism_edit 和 cubism_edit_batch 保留用于向后兼容和批量操作。
    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    示例: cubism_edit(action="AddParameterKey", params={"ObjectId":"ArtMesh","ParameterId":"ParamAngleX","KeyValue":0.5})

    提示：若不确定某个枚举参数的有效值（如 ColorBlend、LabelColorType），可故意传无效值
    （如 "INVALID"），Editor 会在错误信息中返回完整的 Allowed values 列表。
    """
    return await _run_edit(action, params)


@mcp.tool()
async def cubism_edit_batch(actions: list[dict]) -> str:
    """批量执行多个编辑操作，在同一个 EditBegin/EditEnd 事务内完成。

    各 Action 的参数格式参见 cubism_edit 工具的文档。

    Args:
    Returns:
        JSON {"total": int, "completed": int, "cancelled": bool, "results": [{action, result}], "edit_end": {EditEnd响应}}

    Args:
        actions: [{action, params}] 数组，action 是编辑 API 名称，params 是该 API 的参数对象

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    _start_client()
    err = await client.ensureEditReady()
    if err:
        return _json(err)
    modelUID = await _get_current_model_uid()
    if isinstance(modelUID, dict):
        return _json(modelUID)

    beginResp = await client.sendAndWait("EditBegin", {"Silent": False})
    if "Error" in beginResp:
        return _json(beginResp)

    results = []
    hasError = False
    exception = None
    try:
        for i, act in enumerate(actions):
            await client.sendAndWait("EditSendProgress", {"Value": (i + 1) / len(actions)})
            await client.sendAndWait("EditSendLog", {"Message": f"[{i+1}/{len(actions)}] {act['action']}"})
            resp = await _run_step(act["action"], act.get("params", {}), modelUID)
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

    Returns:
        JSON [str]
    """
    _start_client()
    err = await client.ensureReady()
    if err:
        return _json(err)
    resp = await client.sendAndWait("GetSelectedObjects", {"ModelUID": model_uid})
    return _json(resp, indent=2)


@mcp.tool()
async def cubism_get_parameter_keys(model_uid: str, object_id: str) -> str:
    """获取指定对象关联的参数关键帧值列表。

    返回每个参数 ID 及其绑定的关键帧值（KeyValues 数组）。

    Args:
        model_uid: 模型 UID
        object_id: 对象 ID（ArtMesh / Part / Deformer 等的 ID）

    Returns:
        JSON {"Parameters": [{"Id": str, "KeyValues": [float]}]}
    """
    _start_client()
    err = await client.ensureReady()
    if err:
        return _json(err)
    resp = await client.sendAndWait("GetParameterKeys", {
        "ModelUID": model_uid,
        "ObjectId": object_id
    })
    return _json(resp, indent=2)


@mcp.tool()
async def cubism_get_objects_by_parameter_keys(
    model_uid: str,
    parameter_id: str,
    key_value: float
) -> str:
    """按参数关键帧值反查关联的对象 ID 列表。

    给定一个参数 ID 和关键帧值，返回所有在该关键帧上有绑定的对象 ID。

    Args:
        model_uid: 模型 UID
        parameter_id: 参数 ID
        key_value: 关键帧值

    Returns:
        JSON {"Ids": [str]}
    """
    _start_client()
    err = await client.ensureReady()
    if err:
        return _json(err)
    resp = await client.sendAndWait("GetObjectsByParameterKeys", {
        "ModelUID": model_uid,
        "ParameterId": parameter_id,
        "KeyValue": key_value
    })
    return _json(resp, indent=2)


@mcp.tool()
async def cubism_add_selected_objects(model_uid: str, ids: list[str] | None = None) -> str:
    """将指定对象添加到 Editor 的当前选中状态（会保留已有选中项）。

    需要 Edit 权限，自动处理 EditBegin/EditEnd 事务。

    Args:
        model_uid: 模型 UID
        ids: 要添加到选中的对象 ID 列表。省略则不添加任何对象（可用于仅测试 EditBegin/EditEnd）

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    return await _run_edit("AddSelectedObjects", {"Ids": ids} if ids is not None else {}, silent=True, model_uid=model_uid)


@mcp.tool()
async def cubism_clear_selected_objects(model_uid: str) -> str:
    """清除 Editor 中所有对象的选中状态。

    需要 Edit 权限，自动处理 EditBegin/EditEnd 事务。

    Args:
        model_uid: 模型 UID

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    return await _run_edit("ClearSelectedObjects", {}, silent=True, model_uid=model_uid)


async def _get_current_model_uid(expected_uid: str | None = None) -> dict | str:
    """获取 Editor 当前模型 UID，可选校验是否与期望值一致。
    返回 model UID 字符串，或错误 dict。
    """
    resp = await client.sendAndWait("GetCurrentModelUID", {})
    uid = resp.get("ModelUID", "")
    if not uid:
        return {"Error": {
            "ErrorType": "NoModel",
            "Message": "未获取到当前模型 UID，请确保已在 Editor 中打开模型"
        }}
    if expected_uid and expected_uid != uid:
        return {"Error": {
            "ErrorType": "ModelUIDMismatch",
            "Message": f"指定的模型 UID ({expected_uid}) 与 Editor 当前打开的模型 ({uid}) 不一致"
        }}
    return uid


async def _run_step(action: str, params: dict, model_uid: str) -> dict:
    """执行单步编辑操作（假定事务已开启）。
    负责：注入 ModelUID、发送命令、捕获异常。不管理 EditBegin/EditEnd。

    Args:
        action: 编辑 API 名称
        params: 编辑 API 参数（不含 ModelUID）
        model_uid: 已校验通过的当前模型 UID（由 _get_current_model_uid 返回）
    Returns:
        响应 dict（含可能 Error）
    """
    data = dict(params)
    data["ModelUID"] = model_uid
    try:
        return await client.sendAndWait(action, data)
    except Exception as e:
        return {"Error": {"ErrorType": "Exception", "Message": str(e)}}


async def _run_edit(action: str, params: dict, silent: bool = False, model_uid: str | None = None) -> str:
    """内部辅助函数：带事务包裹的单次编辑操作。供独立 tool 和 cubism_edit 共用。

    Args:
        action: 编辑 API 名称
        params: 编辑 API 参数（不含 ModelUID）
        silent: 是否隐藏编辑对话框
        model_uid: 可选，调用者指定的模型 UID。传入后会校验是否与 Editor 当前模型一致
    """
    _start_client()
    err = await client.ensureEditReady()
    if err:
        return _json(err)
    uid = await _get_current_model_uid(model_uid)
    if isinstance(uid, dict):
        return _json(uid)

    beginResp = await client.sendAndWait("EditBegin", {"Silent": silent})
    if "Error" in beginResp:
        return _json(beginResp)

    resp = None
    try:
        resp = await _run_step(action, params, uid)
    finally:
        endResp = await client.sendAndWait("EditEnd", {"Cancel": resp is None or "Error" in resp})
    return _json({
        "action": action,
        "result": resp,
        "edit_end": endResp
    }, indent=2)


# ── 独立编辑 Tool（每个 action 有完整类型签名） ──


@mcp.tool()
async def cubism_add_parameter(
    model_uid: str,
    name: str | None = None,
    id: str | None = None,
    group_id: str | None = None,
    min: float | None = None,
    default: float | None = None,
    max: float | None = None,
    is_blend_shape: bool | None = None,
) -> str:
    """添加参数到模型。自动处理 EditBegin/EditEnd 事务。

    Args:
        model_uid: 模型 UID
        name: 参数名称
        id: 参数 ID（省略则自动生成）
        group_id: 所属参数组 ID。注意: GetParameterGroups 返回的是 GroupUID 格式，直接传入可能报错，建议省略此参数让参数添加到根级别
        min: 最小值
        default: 默认值
        max: 最大值
        is_blend_shape: 是否为融合变形参数

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    params = {}
    if name is not None: params["Name"] = name
    if id is not None: params["Id"] = id
    if group_id is not None: params["GroupId"] = group_id
    if min is not None: params["Min"] = min
    if default is not None: params["Default"] = default
    if max is not None: params["Max"] = max
    if is_blend_shape is not None: params["IsBlendShape"] = is_blend_shape
    return await _run_edit("AddParameter", params, model_uid=model_uid)


@mcp.tool()
async def cubism_edit_parameter(
    model_uid: str,
    id: str,
    new_id: str | None = None,
    name: str | None = None,
    min: float | None = None,
    default: float | None = None,
    max: float | None = None,
    is_repeat: bool | None = None,
) -> str:
    """编辑参数属性。自动处理 EditBegin/EditEnd 事务。

    Args:
        model_uid: 模型 UID
        id: 参数 ID（必填）
        new_id: 新参数 ID
        name: 新参数名称
        min: 最小值
        default: 默认值
        max: 最大值
        is_repeat: 是否可循环

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    params = {"Id": id}
    if new_id is not None: params["NewId"] = new_id
    if name is not None: params["Name"] = name
    if min is not None: params["Min"] = min
    if default is not None: params["Default"] = default
    if max is not None: params["Max"] = max
    if is_repeat is not None: params["IsRepeat"] = is_repeat
    return await _run_edit("EditParameter", params, model_uid=model_uid)


@mcp.tool()
async def cubism_delete_object(model_uid: str, id: str) -> str:
    """从部件面板删除对象（ArtMesh/Deformer/Part/Glue 等任意类型均可）。
    自动处理 EditBegin/EditEnd 事务。

    Args:
        model_uid: 模型 UID
        id: 要删除的对象 ID

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    return await _run_edit("DeleteObject", {"Id": id}, model_uid=model_uid)


@mcp.tool()
async def cubism_add_part(
    model_uid: str,
    name: str | None = None,
    id: str | None = None,
    draw_order: float | None = None,
    ids: list[str] | None = None,
    is_nested: bool | None = None,
) -> str:
    """添加部件。自动处理 EditBegin/EditEnd 事务。
    注: AddPart API 不支持指定父部件，部件会添加到根级别。

    Args:
        model_uid: 模型 UID
        name: 部件名称
        id: 部件 ID（省略则自动生成）
        draw_order: 绘制顺序 (0~1000)
        ids: 要包含的子对象 ID 列表
        is_nested: 是否将 ids 中的对象作为子元素嵌套

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    params = {}
    if name is not None: params["Name"] = name
    if id is not None: params["Id"] = id
    if draw_order is not None: params["DrawOrder"] = draw_order
    if ids is not None: params["Ids"] = ids
    if is_nested is not None: params["IsNested"] = is_nested
    return await _run_edit("AddPart", params, model_uid=model_uid)


@mcp.tool()
async def cubism_edit_part(
    model_uid: str,
    id: str,
    parameters: list[dict] | None = None,
    is_exact_match: bool | None = None,
    new_id: str | None = None,
    name: str | None = None,
    parent_id: str | None = None,
    is_grouped: bool | None = None,
    is_guid_image: bool | None = None,
    is_offscreen: bool | None = None,
    clipping_ids: list[str] | None = None,
    is_reverse_mask: bool | None = None,
    draw_order: float | None = None,
    opacity: float | None = None,
    multiply_color: str | None = None,
    screen_color: str | None = None,
    color_blend: ColorBlendMode | None = None,
    alpha_blend: AlphaBlendMode | None = None,
    label_color_type: LabelColorType | None = None,
    label_custom_color: str | None = None,
) -> str:
    """编辑部件属性。自动处理 EditBegin/EditEnd 事务。

    Args:
        model_uid: 模型 UID
        id: 部件 ID（必填）
        new_id: 新部件 ID
        name: 新部件名称
        parent_id: 父部件 ID
        is_grouped: 是否分组
        is_guid_image: 是否设为参考图像
        is_offscreen: 是否离屏绘制
        clipping_ids: 裁剪 ID 列表
        is_reverse_mask: 是否反转遮罩
        draw_order: 绘制顺序 (0~1000)
        opacity: 不透明度 (0~100)
        multiply_color: 正片叠底颜色 ("#000000"~"#FFFFFF")
        screen_color: 滤色颜色
        color_blend: 颜色混合模式
        alpha_blend: Alpha 混合模式
        label_color_type: 标签颜色类型
        label_custom_color: 自定义标签颜色 ("#RRGGBB")

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    params = {"Id": id}
    if parameters is not None: params["Parameters"] = parameters
    if is_exact_match is not None: params["IsExactMatch"] = is_exact_match
    if new_id is not None: params["NewId"] = new_id
    if name is not None: params["Name"] = name
    if parent_id is not None: params["ParentId"] = parent_id
    if is_grouped is not None: params["IsGrouped"] = is_grouped
    if is_guid_image is not None: params["IsGuidImage"] = is_guid_image
    if is_offscreen is not None: params["IsOffscreen"] = is_offscreen
    if clipping_ids is not None: params["ClippingIds"] = clipping_ids
    if is_reverse_mask is not None: params["IsReverseMask"] = is_reverse_mask
    if draw_order is not None: params["DrawOrder"] = draw_order
    if opacity is not None: params["Opacity"] = opacity
    if multiply_color is not None: params["MultiplyColor"] = multiply_color
    if screen_color is not None: params["ScreenColor"] = screen_color
    if color_blend is not None: params["ColorBlend"] = color_blend
    if alpha_blend is not None: params["AlphaBlend"] = alpha_blend
    if label_color_type is not None: params["LabelColorType"] = label_color_type
    if label_custom_color is not None: params["LabelCustomColor"] = label_custom_color
    return await _run_edit("EditPart", params, model_uid=model_uid)


@mcp.tool()
async def cubism_edit_artmesh(
    model_uid: str,
    id: str,
    parameters: list[dict] | None = None,
    is_exact_match: bool | None = None,
    new_id: str | None = None,
    name: str | None = None,
    parent_id: str | None = None,
    parent_deformer_id: str | None = None,
    clipping_ids: list[str] | None = None,
    is_reverse_mask: bool | None = None,
    draw_order: float | None = None,
    opacity: float | None = None,
    multiply_color: str | None = None,
    screen_color: str | None = None,
    color_blend: ColorBlendMode | None = None,
    alpha_blend: AlphaBlendMode | None = None,
    is_culling: bool | None = None,
    label_color_type: LabelColorType | None = None,
    label_custom_color: str | None = None,
) -> str:
    """编辑 ArtMesh 属性。自动处理 EditBegin/EditEnd 事务。

    Args:
        model_uid: 模型 UID
        id: ArtMesh ID（必填）
        new_id: 新 ArtMesh ID
        name: 新 ArtMesh 名称
        parent_id: 父部件 ID
        parent_deformer_id: 父变形器 ID
        clipping_ids: 裁剪 ID 列表
        is_reverse_mask: 是否反转遮罩
        draw_order: 绘制顺序 (0~1000)
        opacity: 不透明度 (0~100)
        multiply_color: 正片叠底颜色
        screen_color: 滤色颜色
        color_blend: 颜色混合模式
        alpha_blend: Alpha 混合模式
        is_culling: 是否裁剪
        label_color_type: 标签颜色类型
        label_custom_color: 自定义标签颜色

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    params = {"Id": id}
    if parameters is not None: params["Parameters"] = parameters
    if is_exact_match is not None: params["IsExactMatch"] = is_exact_match
    if new_id is not None: params["NewId"] = new_id
    if name is not None: params["Name"] = name
    if parent_id is not None: params["ParentId"] = parent_id
    if parent_deformer_id is not None: params["ParentDeformerId"] = parent_deformer_id
    if clipping_ids is not None: params["ClippingIds"] = clipping_ids
    if is_reverse_mask is not None: params["IsReverseMask"] = is_reverse_mask
    if draw_order is not None: params["DrawOrder"] = draw_order
    if opacity is not None: params["Opacity"] = opacity
    if multiply_color is not None: params["MultiplyColor"] = multiply_color
    if screen_color is not None: params["ScreenColor"] = screen_color
    if color_blend is not None: params["ColorBlend"] = color_blend
    if alpha_blend is not None: params["AlphaBlend"] = alpha_blend
    if is_culling is not None: params["IsCulling"] = is_culling
    if label_color_type is not None: params["LabelColorType"] = label_color_type
    if label_custom_color is not None: params["LabelCustomColor"] = label_custom_color
    return await _run_edit("EditArtMesh", params, model_uid=model_uid)


@mcp.tool()
async def cubism_edit_rotation_deformer(
    model_uid: str,
    id: str,
    parameters: list[dict] | None = None,
    is_exact_match: bool | None = None,
    new_id: str | None = None,
    name: str | None = None,
    parent_id: str | None = None,
    parent_deformer_id: str | None = None,
    angle: float | None = None,
    base_angle: float | None = None,
    scale: float | None = None,
    opacity: float | None = None,
    multiply_color: str | None = None,
    screen_color: str | None = None,
    label_color_type: LabelColorType | None = None,
    label_custom_color: str | None = None,
) -> str:
    """编辑旋转变形器属性。自动处理 EditBegin/EditEnd 事务。

    Args:
        model_uid: 模型 UID
        id: 旋转变形器 ID（必填）
        new_id: 新变形器 ID
        name: 新变形器名称
        parent_id: 父部件 ID
        parent_deformer_id: 父变形器 ID
        angle: 角度
        base_angle: 标准角度
        scale: 缩放
        opacity: 不透明度
        multiply_color: 正片叠底颜色
        screen_color: 滤色颜色
        label_color_type: 标签颜色类型
        label_custom_color: 自定义标签颜色

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    params = {"Id": id}
    if parameters is not None: params["Parameters"] = parameters
    if is_exact_match is not None: params["IsExactMatch"] = is_exact_match
    if new_id is not None: params["NewId"] = new_id
    if name is not None: params["Name"] = name
    if parent_id is not None: params["ParentId"] = parent_id
    if parent_deformer_id is not None: params["ParentDeformerId"] = parent_deformer_id
    if angle is not None: params["Angle"] = angle
    if base_angle is not None: params["BaseAngle"] = base_angle
    if scale is not None: params["Scale"] = scale
    if opacity is not None: params["Opacity"] = opacity
    if multiply_color is not None: params["MultiplyColor"] = multiply_color
    if screen_color is not None: params["ScreenColor"] = screen_color
    if label_color_type is not None: params["LabelColorType"] = label_color_type
    if label_custom_color is not None: params["LabelCustomColor"] = label_custom_color
    return await _run_edit("EditRotationDeformer", params, model_uid=model_uid)


@mcp.tool()
async def cubism_edit_warp_deformer(
    model_uid: str,
    id: str,
    parameters: list[dict] | None = None,
    is_exact_match: bool | None = None,
    new_id: str | None = None,
    name: str | None = None,
    parent_id: str | None = None,
    parent_deformer_id: str | None = None,
    opacity: float | None = None,
    multiply_color: str | None = None,
    screen_color: str | None = None,
    label_color_type: LabelColorType | None = None,
    label_custom_color: str | None = None,
) -> str:
    """编辑弯曲变形器属性。自动处理 EditBegin/EditEnd 事务。

    Args:
        model_uid: 模型 UID
        id: 弯曲变形器 ID（必填）
        new_id: 新变形器 ID
        name: 新变形器名称
        parent_id: 父部件 ID
        parent_deformer_id: 父变形器 ID
        opacity: 不透明度
        multiply_color: 正片叠底颜色
        screen_color: 滤色颜色
        label_color_type: 标签颜色类型
        label_custom_color: 自定义标签颜色

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    params = {"Id": id}
    if parameters is not None: params["Parameters"] = parameters
    if is_exact_match is not None: params["IsExactMatch"] = is_exact_match
    if new_id is not None: params["NewId"] = new_id
    if name is not None: params["Name"] = name
    if parent_id is not None: params["ParentId"] = parent_id
    if parent_deformer_id is not None: params["ParentDeformerId"] = parent_deformer_id
    if opacity is not None: params["Opacity"] = opacity
    if multiply_color is not None: params["MultiplyColor"] = multiply_color
    if screen_color is not None: params["ScreenColor"] = screen_color
    if label_color_type is not None: params["LabelColorType"] = label_color_type
    if label_custom_color is not None: params["LabelCustomColor"] = label_custom_color
    return await _run_edit("EditWarpDeformer", params, model_uid=model_uid)


@mcp.tool()
async def cubism_edit_glue(
    model_uid: str,
    id: str,
    parameters: list[dict] | None = None,
    is_exact_match: bool | None = None,
    new_id: str | None = None,
    name: str | None = None,
    parent_id: str | None = None,
    intensity: float | None = None,
    label_color_type: LabelColorType | None = None,
    label_custom_color: str | None = None,
) -> str:
    """编辑 Glue（胶水）属性。自动处理 EditBegin/EditEnd 事务。

    Args:
        model_uid: 模型 UID
        id: Glue ID（必填）
        new_id: 新 Glue ID
        name: 新 Glue 名称
        parent_id: 父部件 ID
        intensity: 兼容性 (0~100)
        label_color_type: 标签颜色类型
        label_custom_color: 自定义标���颜色

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    params = {"Id": id}
    if parameters is not None: params["Parameters"] = parameters
    if is_exact_match is not None: params["IsExactMatch"] = is_exact_match
    if new_id is not None: params["NewId"] = new_id
    if name is not None: params["Name"] = name
    if parent_id is not None: params["ParentId"] = parent_id
    if intensity is not None: params["Intensity"] = intensity
    if label_color_type is not None: params["LabelColorType"] = label_color_type
    if label_custom_color is not None: params["LabelCustomColor"] = label_custom_color
    return await _run_edit("EditGlue", params, model_uid=model_uid)


@mcp.tool()
async def cubism_delete_parameter(model_uid: str, id: str) -> str:
    """删除参数。自动处理 EditBegin/EditEnd 事务。

    Args:
        model_uid: 模型 UID
        id: 参数 ID

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    return await _run_edit("DeleteParameter", {"Id": id}, model_uid=model_uid)


@mcp.tool()
async def cubism_add_parameter_group(
    model_uid: str,
    name: str | None = None,
    id: str | None = None,
) -> str:
    """添加参数组。自动处理 EditBegin/EditEnd 事务。

    Args:
        model_uid: 模型 UID
        name: 参数组名称
        id: 参数组 ID（省略则自动生成）

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    params = {}
    if name is not None: params["Name"] = name
    if id is not None: params["Id"] = id
    return await _run_edit("AddParameterGroup", params, model_uid=model_uid)


@mcp.tool()
async def cubism_edit_parameter_group(
    model_uid: str,
    id: str,
    new_id: str | None = None,
    name: str | None = None,
    label_color_type: LabelColorType | None = None,
    label_custom_color: str | None = None,
) -> str:
    """编辑参数组属性。自动处理 EditBegin/EditEnd 事务。

    Args:
        model_uid: 模型 UID
        id: 参数组 ID（必填）
        new_id: 新参数组 ID
        name: 新参数组名称
        label_color_type: 标签颜色类型
        label_custom_color: 自定义标签颜色 ("#RRGGBB")

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    params = {"Id": id}
    if new_id is not None: params["NewId"] = new_id
    if name is not None: params["Name"] = name
    if label_color_type is not None: params["LabelColorType"] = label_color_type
    if label_custom_color is not None: params["LabelCustomColor"] = label_custom_color
    return await _run_edit("EditParameterGroup", params, model_uid=model_uid)


@mcp.tool()
async def cubism_delete_parameter_group(model_uid: str, id: str) -> str:
    """删除参数组。自动处理 EditBegin/EditEnd 事务。

    Args:
        model_uid: 模型 UID
        id: 参数组 ID

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    return await _run_edit("DeleteParameterGroup", {"Id": id}, model_uid=model_uid)


@mcp.tool()
async def cubism_move_parameter(
    model_uid: str,
    id: str,
    group_id: str,
    insert_index: float | None = None,
) -> str:
    """移动参数到指定参数组。自动处理 EditBegin/EditEnd 事务。

    Args:
        model_uid: 模型 UID
        id: 参数 ID
        group_id: 目标参数组 ID
        insert_index: 插入位置的索引

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    params = {"Id": id, "GroupId": group_id}
    if insert_index is not None: params["InsertIndex"] = insert_index
    return await _run_edit("MoveParameter", params, model_uid=model_uid)


@mcp.tool()
async def cubism_move_parameter_group(
    model_uid: str,
    id: str,
    insert_index: float,
) -> str:
    """调整参数组顺序。自动处理 EditBegin/EditEnd 事务。

    Args:
        model_uid: 模型 UID
        id: 参数组 ID
        insert_index: 目标索引

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    return await _run_edit("MoveParameterGroup", {"Id": id, "InsertIndex": insert_index}, model_uid=model_uid)


@mcp.tool()
async def cubism_add_parameter_key(
    model_uid: str,
    object_id: str,
    parameter_id: str,
    key_value: float,
) -> str:
    """为参数添加关键帧。自动处理 EditBegin/EditEnd 事务。

    Args:
        model_uid: 模型 UID
        object_id: 对象 ID
        parameter_id: 参数 ID
        key_value: 关键帧值

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    return await _run_edit("AddParameterKey", {
        "ObjectId": object_id, "ParameterId": parameter_id, "KeyValue": key_value
    }, model_uid=model_uid)


@mcp.tool()
async def cubism_delete_parameter_key(
    model_uid: str,
    object_id: str | None = None,
    parameter_id: str | None = None,
    key_value: float | None = None,
    strict: bool | None = None,
) -> str:
    """删除参数关键帧。自动处理 EditBegin/EditEnd 事务。

    Args:
        model_uid: 模型 UID
        object_id: 对象 ID（省略则匹配所有对象）
        parameter_id: 参数 ID（省略则匹配所有参数）
        key_value: 关键帧值
        strict: 是否严格匹配（默认 True）

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    params = {}
    if object_id is not None: params["ObjectId"] = object_id
    if parameter_id is not None: params["ParameterId"] = parameter_id
    if key_value is not None: params["KeyValue"] = key_value
    if strict is not None: params["Strict"] = strict
    return await _run_edit("DeleteParameterKey", params, model_uid=model_uid)


@mcp.tool()
async def cubism_move_parameter_key(
    model_uid: str,
    from_value: float,
    to_value: float,
    object_id: str | None = None,
    parameter_id: str | None = None,
    strict: bool | None = None,
    force_overwrite: bool | None = None,
) -> str:
    """移动参数关键帧位置。自动处理 EditBegin/EditEnd 事务。

    Args:
        model_uid: 模型 UID
        from_value: 源关键帧值
        to_value: 目标关键帧值
        object_id: 对象 ID
        parameter_id: 参数 ID
        strict: 是否严格匹配（默认 True）
        force_overwrite: 是否强制覆盖目标位置的关键帧（默认 False）

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    params = {"FromValue": from_value, "ToValue": to_value}
    if object_id is not None: params["ObjectId"] = object_id
    if parameter_id is not None: params["ParameterId"] = parameter_id
    if strict is not None: params["Strict"] = strict
    if force_overwrite is not None: params["ForceOverwrite"] = force_overwrite
    return await _run_edit("MoveParameterKey", params, model_uid=model_uid)


@mcp.tool()
async def cubism_add_warp_deformer(
    model_uid: str,
    name: str | None = None,
    id: str | None = None,
    parent_id: str | None = None,
    target_object_ids: list[str] | None = None,
    mode: DeformerParentMode | None = None,
    warp_div_h: float | None = None,
    warp_div_v: float | None = None,
    bezier_div_h: float | None = None,
    bezier_div_v: float | None = None,
    consider_child_keyforms: bool | None = None,
    snap_center: bool | None = None,
) -> str:
    """添加弯曲变形器。自动处理 EditBegin/EditEnd 事务。

    Args:
        model_uid: 模型 UID
        name: 变形器名称
        id: 变形器 ID（省略则自动生成）
        parent_id: 父部件 ID
        target_object_ids: 目标对象 ID 列表
        mode: 父级关系模式 ("AsParent" 或 "AsChild")
        warp_div_h: 水平转换分割数 (2~100)
        warp_div_v: 垂直转换分割数 (2~100)
        bezier_div_h: 水平贝塞尔分割数 (1~100)
        bezier_div_v: 垂直贝塞尔分割数 (1~100)
        consider_child_keyforms: 是否考虑子元素关键帧
        snap_center: 是否居中

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    params = {}
    if name is not None: params["Name"] = name
    if id is not None: params["Id"] = id
    if parent_id is not None: params["ParentId"] = parent_id
    if target_object_ids is not None: params["TargetObjectIds"] = target_object_ids
    if mode is not None: params["Mode"] = mode
    if warp_div_h is not None: params["WarpDivH"] = warp_div_h
    if warp_div_v is not None: params["WarpDivV"] = warp_div_v
    if bezier_div_h is not None: params["BezierDivH"] = bezier_div_h
    if bezier_div_v is not None: params["BezierDivV"] = bezier_div_v
    if consider_child_keyforms is not None: params["ConsiderChildKeyforms"] = consider_child_keyforms
    if snap_center is not None: params["SnapCenter"] = snap_center
    return await _run_edit("AddWarpDeformer", params, model_uid=model_uid)


@mcp.tool()
async def cubism_add_rotation_deformer(
    model_uid: str,
    name: str | None = None,
    id: str | None = None,
    parent_id: str | None = None,
    target_object_ids: list[str] | None = None,
    mode: DeformerParentMode | None = None,
) -> str:
    """添加旋转变形器。自动处理 EditBegin/EditEnd 事务。

    Args:
        model_uid: 模型 UID
        name: 变形器名称
        id: 变形器 ID（省略则自动生成）
        parent_id: 父部件 ID
        target_object_ids: 目标对象 ID 列表
        mode: 父级关系模式 ("AsParent" 或 "AsChild")

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    params = {}
    if name is not None: params["Name"] = name
    if id is not None: params["Id"] = id
    if parent_id is not None: params["ParentId"] = parent_id
    if target_object_ids is not None: params["TargetObjectIds"] = target_object_ids
    if mode is not None: params["Mode"] = mode
    return await _run_edit("AddRotationDeformer", params, model_uid=model_uid)


@mcp.tool()
async def cubism_move_object_on_parts_palette(
    model_uid: str,
    id: str,
    parent_id: str | None = None,
    insert_id: str | None = None,
    insert_index: float | None = None,
) -> str:
    """在部件面板中移动对象位置。自动处理 EditBegin/EditEnd 事务。

    Args:
        model_uid: 模型 UID
        id: 对象 ID
        parent_id: 父级 ID
        insert_id: 插入目标 ID
        insert_index: 插入索引

    Returns:
        JSON {"action": "API名", "result": {API原始响应}, "edit_end": {EditEnd响应}}
    """
    params = {"Id": id}
    if parent_id is not None: params["ParentId"] = parent_id
    if insert_id is not None: params["InsertId"] = insert_id
    if insert_index is not None: params["InsertIndex"] = insert_index
    return await _run_edit("MoveObjectOnPartsPalette", params, model_uid=model_uid)


def cli():
    """Entry point for uvx / pip install"""
    mcp.run()


if __name__ == "__main__":
    cli()
