"""统一错误信封(spec 2026-08-28 §5.3)。

所有 HTTP 错误响应统一为 {"error":{code,message,detail?,retry_after?}};
status code 全部透传不变。两层码:
- 语义码 ErrorCode(raise 用):仅收 ApiError 显式 raise 的码;
- 通用兜底码:普通 HTTPException / require_ready 头按字符串映射
  (warming/no_sources/bad_request 等),不经枚举直入 envelope。
"""
from enum import Enum

# warming 503 的建议重试间隔(秒)
RETRY_AFTER_WARMING = 30


class ErrorCode(str, Enum):
    invalid_ip = "invalid_ip"
    source_not_found = "source_not_found"
    eval_busy = "eval_busy"
    internal = "internal"


# 语义码 → HTTP 状态(ApiError.status 的唯一真相)
_STATUS: dict = {
    ErrorCode.invalid_ip: 400,
    ErrorCode.source_not_found: 404,
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
        return envelope(self.code.value, self.message,
                        self.detail, self.retry_after)


def envelope(code: str, message: str, detail=None, retry_after=None) -> dict:
    """构造信封 dict(可选字段缺省即不出现)。"""
    err = {"code": code, "message": message}
    if detail is not None:
        err["detail"] = detail
    if retry_after is not None:
        err["retry_after"] = retry_after
    return {"error": err}
