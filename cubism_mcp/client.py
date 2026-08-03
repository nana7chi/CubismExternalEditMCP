"""Cubism Editor WebSocket 客户端（基于官方 ceplugin.py 改写）。

负责：
- 与 Editor 建立/重连 WebSocket（端口 22033，可通过 CUBISM_PORT 环境变量覆盖）
- RegisterPlugin 注册 + token 持久化到 ~/.cubism-mcp/token.txt
- 请求/响应匹配（asyncio.Future 机制，超时 15 秒）
- 权限分级：ensureReady()（Allow 权限）/ ensureEditReady()（Allow + Edit 权限）
"""

import asyncio
import json
import os
import uuid

import websockets

from .config import DEFAULT_PORT, TOKEN_FILENAME, URL, logger


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
