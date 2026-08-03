"""关键帧的添加、删除、移动操作（3 个工具）。

包含：AddParameterKey, DeleteParameterKey, MoveParameterKey
"""

from ..server import mcp
from ._helpers import _run_edit


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
