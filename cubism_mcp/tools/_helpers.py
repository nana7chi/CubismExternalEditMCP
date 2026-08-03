"""编辑事务辅助函数。

供所有编辑类工具共用，统一处理：
- 校验 model_uid 与 Editor 当前模型一致（不一致则报错）
- 自动包裹 EditBegin/EditEnd 事务
- 异常时自动 Cancel 回滚
"""

from ..config import _json
from ..server import _start_client, client


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
