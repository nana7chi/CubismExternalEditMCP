"""参数与参数组的增删改查、移动操作（8 个工具）。

包含：AddParameter, EditParameter, DeleteParameter,
      AddParameterGroup, EditParameterGroup, DeleteParameterGroup,
      MoveParameter, MoveParameterGroup
"""

from ..server import mcp
from ..types import LabelColorType
from ._helpers import _run_edit


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
