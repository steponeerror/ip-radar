import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import App from "../App";
import { renderWithI18n } from "../test/i18nTestUtils";

// Admin split + 公开数据源页退役:公开壳 = 纯 lookup(admin 走独立文档
// /admin,数据源管理只在管理台内)。此文件钉住拆分后的路由契约。
vi.mock("../api", async () => {
  const real = await vi.importActual<any>("../api");
  return {
    ...real,
    // 挂载期网络面哑化:Layout(warmup 轮询/version)
    getDbStatus: vi.fn().mockResolvedValue({ warming_up: false, total_records: 0 }),
    getVersion: vi.fn().mockResolvedValue({ self_update_enabled: false }),
  };
});

beforeEach(() => {
  location.hash = "";
});

describe("App routing after admin split + public sources retirement", () => {
  it("renders the lookup view by default, nav has no admin or sources buttons", () => {
    renderWithI18n(<App />);
    expect(screen.getByRole("button", { name: "Query" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Admin" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Sources" })).toBeNull();
  });

  it("#/sources no longer routes to a public sources page — falls back to lookup", () => {
    location.hash = "#/sources";
    renderWithI18n(<App />);
    expect(screen.getByRole("button", { name: "Query" })).toBeInTheDocument();
  });

  it("#/admin no longer routes to the admin console — falls back to lookup", () => {
    location.hash = "#/admin";
    renderWithI18n(<App />);
    expect(screen.getByRole("button", { name: "Query" })).toBeInTheDocument();
  });
});
