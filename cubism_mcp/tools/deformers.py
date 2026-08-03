"""变形器的添加与编辑操作（4 个工具）。

包含：AddWarpDeformer, AddRotationDeformer,
      EditWarpDeformer, EditRotationDeformer
"""

from ..server import mcp
from ..types import DeformerParentMode, LabelColorType
from ._helpers import _run_edit


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
