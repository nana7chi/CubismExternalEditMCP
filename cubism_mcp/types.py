"""类型定义：编辑 Action 枚举与各种 Literal 约束。

通过 typing.get_args(EditAction) 自动派生 EDIT_ACTIONS 列表，
消除原来「列表 + Literal 双处同步」的维护负担。
"""

from typing import Literal, get_args

# 用 Literal 类型让 FastMCP 自动生成 enum 约束的 inputSchema
# 支持的编辑 API 列表，用于 inputSchema 的 enum 约束，让客户端在发送前拦截无效 action
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
    "AddSelectedObjects", "ClearSelectedObjects",
]

# 从 Literal 自动生成列表，避免双处维护
EDIT_ACTIONS = list(get_args(EditAction))

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
