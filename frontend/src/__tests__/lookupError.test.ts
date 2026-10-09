import { describe, it, expect } from "vitest";
import { errorToBanner, outcomeToBanner } from "../lib/lookupError";
import type { ApiError } from "../api";

const apiErr = (partial: Partial<ApiError> & { message: string }) =>
  Object.assign(new Error(partial.message), partial) as ApiError;

describe("errorToBanner (U1 错误映射)", () => {
  it("429 rate_limited → i18n 键 + retry_after,信封 message 不作次要行", () => {
    const b = errorToBanner(
      apiErr({ message: "rate limit exceeded", status: 429, code: "rate_limited", retry_after: 30 }),
      "lookup.queryFailed",
    );
    expect(b).toEqual({ key: "lookup.error.rate_limited", retryAfter: 30 });
  });

  it("前端超时哨兵 code=timeout → timeout 键,无冗余 detail", () => {
    const b = errorToBanner(
      apiErr({ message: "Request timed out (120s idle)", status: 0, code: "timeout" }),
      "lookup.queryFailed",
    );
    expect(b).toEqual({ key: "lookup.error.timeout" });
  });

  it("422 validation_error → validation_error 键,无冗余 detail", () => {
    const b = errorToBanner(
      apiErr({ message: "request validation failed", status: 422, code: "validation_error" }),
      "lookup.queryFailed",
    );
    expect(b).toEqual({ key: "lookup.error.validation_error" });
  });

  it("400 bad_request → bad_request 键(HTTP phrase 与文案重复,无 detail)", () => {
    const b = errorToBanner(
      apiErr({ message: "Bad Request", status: 400, code: "bad_request" }),
      "lookup.queryFailed",
    );
    expect(b).toEqual({ key: "lookup.error.bad_request" });
  });

  it("400 invalid_ip → invalid_ip 键,保留含具体 IP 的 message 作次要行", () => {
    const b = errorToBanner(
      apiErr({ message: "not a valid IP: 999.1.1.1", status: 400, code: "invalid_ip" }),
      "lookup.queryFailed",
    );
    expect(b).toEqual({ key: "lookup.error.invalid_ip", detail: "not a valid IP: 999.1.1.1" });
  });

  it("未映射码(warming)与裸 Error → fallback 键 + message 次要行", () => {
    expect(
      errorToBanner(
        apiErr({ message: "database is warming up", status: 503, code: "warming" }),
        "lookup.queryFailed",
      ),
    ).toEqual({ key: "lookup.queryFailed", detail: "database is warming up" });
    expect(errorToBanner(new Error("boom"), "lookup.uploadFailed")).toEqual({
      key: "lookup.uploadFailed",
      detail: "boom",
    });
  });

  it("retry_after 缺省或非正数不产出 retryAfter", () => {
    expect(
      errorToBanner(
        apiErr({ message: "rate limit exceeded", status: 429, code: "rate_limited" }),
        "lookup.queryFailed",
      ).retryAfter,
    ).toBeUndefined();
    expect(
      errorToBanner(
        apiErr({ message: "rate limit exceeded", status: 429, code: "rate_limited", retry_after: 0 }),
        "lookup.queryFailed",
      ).retryAfter,
    ).toBeUndefined();
  });
});

describe("outcomeToBanner (流式 done.error 映射)", () => {
  it("EOF 截断哨兵 → stream_truncated 键,前端哨兵串不上屏", () => {
    expect(
      outcomeToBanner(
        { error: "stream ended before done", error_code: "stream_truncated" },
        "lookup.queryFailed",
      ),
    ).toEqual({ key: "lookup.error.stream_truncated" });
  });

  it("backend done.error(internal)→ fallback 键 + 错误串次要行", () => {
    expect(outcomeToBanner({ error: "boom", error_code: "internal" }, "lookup.queryFailed")).toEqual({
      key: "lookup.queryFailed",
      detail: "boom",
    });
  });

  it("error 为空 → null", () => {
    expect(outcomeToBanner({ error: null, error_code: null }, "lookup.queryFailed")).toBeNull();
  });
});
