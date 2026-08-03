"""编辑工具子包。

导入此包会触发所有编辑工具模块的加载，从而通过 @mcp.tool() 装饰器完成注册。
按域划分：
- parameters: 参数/参数组的 add/edit/delete/move
- keyframes:  关键帧 add/delete/move
- parts:      部件 add/edit + 对象 delete/move
- artmesh:    ArtMesh/Glue 编辑
- deformers:  变形器 add/edit
"""

from . import (  # noqa: F401  导入即注册
    artmesh,
    deformers,
    keyframes,
    parameters,
    parts,
)
