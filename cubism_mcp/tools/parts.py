"""部件与对象的增删改、移动操作（4 个工具）。

包含：AddPart, EditPart, DeleteObject, MoveObjectOnPartsPalette
"""

from ..server import mcp
from ..types import AlphaBlendMode, ColorBlendMode, LabelColorType
from ._helpers import _run_edit


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
