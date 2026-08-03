"""MCP Server 装配层 + 读取/查询类工具。

本模块创建 FastMCP 实例和全局 client 单例，并注册所有非编辑类工具：
- 诊断：cubism_status
- 读写操作：get/set/clear parameter values, get parameters/groups
- 结构查询：parameter/part/deformer structure, get object, get selected, parameter keys
- 通用编辑入口：cubism_edit / cubism_edit_batch（向后兼容）

编辑类工具分布在 cubism_mcp.tools 子包中，通过 tools/__init__.py 导入触发注册。
"""

from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from .client import CEPluginClient
from .config import DEFAULT_PORT, _json
from .types import EditAction

# 全局客户端单例
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


# ── 诊断 ──


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


# ── 读写操作 ──


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


# ── 结构查询 ──


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


# ── 通用编辑入口（向后兼容 + 批量） ──
# 导入编辑工具的辅助函数和子模块，触发 @mcp.tool() 注册
from . import tools  # noqa: F401  导入 tools 包以注册所有编辑工具
from .tools._helpers import _get_current_model_uid, _run_edit, _run_step


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
        actions: [{action, params}] 数组，action 是编辑 API 名称，params 是该 API 的参数对象

    Returns:
        JSON {"total": int, "completed": int, "cancelled": bool, "results": [{action, result}], "edit_end": {EditEnd响应}}
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


# ── 选择操作（需要 Edit 权限，归在此处因为不属于特定对象域） ──


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


# ── Prompts（提示词模板） ──
# prompts 与 tools 并列，是 MCP 的第三种能力。
# tools 让模型去"执行动作"，prompts 则是给用户准备的"话术模板/快捷指令"，
# 由用户主动选择、填入参数后生成一段提示文本交给模型使用，本身不直接执行副作用。
# 以下示例把常见的 Cubism 操作组合固化成模板，方便用户在客户端一键套用。


@mcp.prompt()
def cubism_prompt_reset_angles(model_uid: str) -> str:
    """生成一段提示，引导模型把指定模型的所有角度类参数（ParamAngleX/Y/Z 等）归零。

    Args:
        model_uid: 模型 UID（可通过 cubism_get_model_uid 获取）

    Returns:
        渲染后的提示文本（供模型消费）
    """
    return (
        f"请对模型 {model_uid} 执行以下操作：\n"
        "1. 调用 cubism_get_parameters 获取全部参数，筛选出所有以 'ParamAngle' 开头的参数 ID。\n"
        "2. 对每个筛选出的参数，调用 cubism_set_parameter_values 将其 Value 设置为 0。\n"
        "3. 完成后调用 cubism_clear_parameter_values 清理临时缓存。\n"
        "请逐步执行并在最后汇报被归零的参数列表。"
    )


@mcp.prompt()
def cubism_prompt_add_warp_workflow(object_name: str) -> str:
    """生成一段提示，引导模型按标准流程为指定对象新增一个 WarpDeformer。

    Args:
        object_name: 目标对象名称（如某个 ArtMesh 的名称）

    Returns:
        渲染后的提示文本（供模型消费）
    """
    return (
        f"请为对象 '{object_name}' 按标准流程新增 WarpDeformer：\n"
        "1. 调用 cubism_get_model_uid 获取当前模型 UID。\n"
        "2. 调用 cubism_get_part_structure 确认该对象所在部件路径。\n"
        "3. 调用 cubism_add_warp_deformer 在其父部件下新增 WarpDeformer（使用合理行列数）。\n"
        "4. 调用 cubism_get_deformer_structure 校验新增结果。\n"
        "如任意步骤返回 Error，请停止并报告错误。"
    )


def cli():
    """Entry point for uvx / pip install"""
    mcp.run()
