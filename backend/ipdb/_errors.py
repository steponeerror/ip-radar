"""统一错误信封(spec 2026-08-28 §5.3)。

所有 HTTP 错误响应统一为 {"error":{code,message,detail?,retry_after?}};
status code 全部透传不变。两层码:
- 语义码 ErrorCode(9 值):路由显式 raise ApiError 时使用,精确语义;
- 通用兜底码:普通 HTTPException 按状态映射(not_found/conflict/...),
  require_ready 的 X-IPRadar-Reason 头映射 warming/no_sources。
"""
from enum import Enum

# warming 503 的建议重试间隔(秒)
RETRY_AFTER_WARMING = 30


class ErrorCode(str, Enum):
    warming = "warming"
    no_sources = "no_sources"
    not_ready = "not_ready"
    invalid_ip = "invalid_ip"
    source_not_found = "source_not_found"
    eval_busy = "eval_busy"
    task_not_found = "task_not_found"
    bad_request = "bad_request"
    internal = "internal"


# 语义码 → HTTP 状态(ApiError.status 的唯一真相)
_STATUS: dict = {
    ErrorCode.warming: 503,
    ErrorCode.no_sources: 503,
    ErrorCode.not_ready: 503,
    ErrorCode.invalid_ip: 400,
    ErrorCode.bad_request: 400,
    ErrorCode.source_not_found: 404,
    ErrorCode.task_not_found: 404,
    ErrorCode.eval_busy: 409,
    ErrorCode.internal: 500,
}


class ApiError(Exception):
    """路由可 raise 的语义错误;handler 收敛为信封 + 映射状态码。"""

    def __init__(self, code, message, detail=None, retry_after=None):
        self.code = code if isinstance(code, ErrorCode) else ErrorCode(code)
        self.message = message
        self.detail = detail
        self.retry_after = retry_after

    @property
    def status(self) -> int:
        return _STATUS[self.code]

    def envelope(self) -> dict:
        err = {"code": self.code.value, "message": self.message}
        if self.detail is not None:
            err["detail"] = self.detail
        if self.retry_after is not None:
            err["retry_after"] = self.retry_after
        return {"error": err}


def envelope(code: str, message: str, detail=None, retry_after=None) -> dict:
    """构造信封 dict(可选字段缺省即不出现)。"""
    err = {"code": code, "message": message}
    if detail is not None:
        err["detail"] = detail
    if retry_after is not None:
        err["retry_after"] = retry_after
    return {"error": err}
