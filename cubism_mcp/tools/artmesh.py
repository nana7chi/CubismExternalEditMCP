"""ArtMesh 和 Glue 的编辑操作（2 个工具）。

包含：EditArtMesh, EditGlue
"""

from ..server import mcp
from ..types import AlphaBlendMode, ColorBlendMode, LabelColorType
from ._helpers import _run_edit


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
    if intensity is not None: params["Intensity"] = intensity
    if label_color_type is not None: params["LabelColorType"] = label_color_type
    if label_custom_color is not None: params["LabelCustomColor"] = label_custom_color
    return await _run_edit("EditGlue", params, model_uid=model_uid)
