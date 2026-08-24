import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { VersionBanner } from "../VersionBanner";
import { renderWithI18n } from "../../test/i18nTestUtils";
import * as api from "../../api";

const base: api.VersionInfo = {
  current: "v1.1.0", latest: "v1.2.0", update_available: true,
  summary: "new features", release_url: "https://x", self_update_enabled: false, public_demo: false,
};

// renderWithI18n 默认 en locale;沿用 WarmupBanner.test 的 importActual mock 风格
vi.mock("../../api", async () => {
  const real = await vi.importActual<any>("../../api");
  return { ...real, getVersion: vi.fn() };
});

function render(props?: Partial<{ selfUpdateEnabled: boolean }>) {
  return renderWithI18n(
    <VersionBanner selfUpdateEnabled={props?.selfUpdateEnabled ?? false} onStartUpdate={vi.fn()} />,
  );
}

describe("VersionBanner", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(api.getVersion).mockReset();
    vi.mocked(api.getVersion).mockResolvedValue(base);
  });

  it("renders when update available", async () => {
    render();
    await waitFor(() => expect(screen.getByText(/v1\.2\.0/)).toBeTruthy());
  });

  it("hidden when no update", async () => {
    vi.mocked(api.getVersion).mockResolvedValue({ ...base, update_available: false });
    render();
    await waitFor(() => expect(api.getVersion).toHaveBeenCalled());
    expect(screen.queryByText(/v1\.2\.0/)).toBeNull();
  });

  it("dismiss persists per version", async () => {
    render();
    const dismiss = await screen.findByRole("button", { name: /Dismiss this version/i });
    fireEvent.click(dismiss);
    expect(localStorage.getItem("dismissed_version")).toBe("v1.2.0");
  });

  it("check button forces refresh", async () => {
    render();
    fireEvent.click(await screen.findByRole("button", { name: /Check for updates/i }));
    await waitFor(() => expect(api.getVersion).toHaveBeenCalledWith(true));
  });

  it("L2 shows update-now button and calls onStartUpdate", async () => {
    const onStartUpdate = vi.fn();
    renderWithI18n(<VersionBanner selfUpdateEnabled={true} onStartUpdate={onStartUpdate} />);
    fireEvent.click(await screen.findByRole("button", { name: /Update now/i }));
    expect(onStartUpdate).toHaveBeenCalled();
  });
});
