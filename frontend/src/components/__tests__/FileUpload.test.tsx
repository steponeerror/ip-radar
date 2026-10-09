import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { fireEvent } from "@testing-library/react";
import { FileUpload } from "../FileUpload";
import { renderWithI18n } from "../../test/i18nTestUtils";

// U2:拖放并发守卫 —— loading(查询进行中)与 disabled(warming)统一收口为
// blocked 谓词,拖放与点选同拦。本批唯一行为变更点,守卫语义钉死在此:
//   - loading 态:drop 被拦 + busy 弹窗(zh/en 双语);change 被拦(handler 层)
//   - disabled 态:drop 被拦且静默(提示归 WarmupBanner)
//   - 空闲态:两条路径放行,守卫不误伤

let alertSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
});
afterEach(() => {
  alertSpy.mockRestore();
});

const txtFile = () => new File(["1.2.3.4\n"], "ips.txt", { type: "text/plain" });
// onDrop 挂在最外层拖放区 div 上
const dropZone = (container: HTMLElement) => container.firstElementChild as HTMLElement;
// label+input 常驻 DOM(loading 时整体 hidden),handler 层守卫真实可达
const fileInput = (container: HTMLElement) =>
  container.querySelector('input[type="file"]') as HTMLInputElement;

describe("FileUpload U2 concurrent guard", () => {
  it("loading 态拖放被拦:不触发 onUpload,zh-CN 弹「查询进行中，请稍候」", () => {
    const onUpload = vi.fn();
    const { container } = renderWithI18n(
      <FileUpload onUpload={onUpload} loading progress={null} />,
      { locale: "zh-CN" },
    );
    fireEvent.drop(dropZone(container), { dataTransfer: { files: [txtFile()] } });
    expect(onUpload).not.toHaveBeenCalled();
    expect(alertSpy).toHaveBeenCalledWith("查询进行中，请稍候");
  });

  it("loading 态拖放被拦:en 同键对称「A lookup is in progress, please wait」", () => {
    const onUpload = vi.fn();
    const { container } = renderWithI18n(
      <FileUpload onUpload={onUpload} loading progress={{ done: 1, total: 3 }} />,
    );
    fireEvent.drop(dropZone(container), { dataTransfer: { files: [txtFile()] } });
    expect(onUpload).not.toHaveBeenCalled();
    expect(alertSpy).toHaveBeenCalledWith("A lookup is in progress, please wait");
  });

  it("loading 态点选被拦:input 常驻且 disabled,change 带文件也不上抛", () => {
    const onUpload = vi.fn();
    const { container } = renderWithI18n(
      <FileUpload onUpload={onUpload} loading progress={null} />,
    );
    const input = fileInput(container);
    expect(input).not.toBeNull();
    expect(input).toBeDisabled(); // input disabled 与 handler 守卫吃同一 blocked 谓词
    fireEvent.change(input, { target: { files: [txtFile()] } });
    expect(onUpload).not.toHaveBeenCalled();
    expect(alertSpy).not.toHaveBeenCalled();
  });

  it("disabled(warming)拖放被拦且静默:busy 弹窗仅 loading,提示归 WarmupBanner", () => {
    const onUpload = vi.fn();
    const { container } = renderWithI18n(
      <FileUpload onUpload={onUpload} loading={false} disabled progress={null} />,
    );
    fireEvent.drop(dropZone(container), { dataTransfer: { files: [txtFile()] } });
    expect(onUpload).not.toHaveBeenCalled();
    expect(alertSpy).not.toHaveBeenCalled();
  });

  it("disabled 态点选同拦:change 带文件不上抛", () => {
    const onUpload = vi.fn();
    const { container } = renderWithI18n(
      <FileUpload onUpload={onUpload} loading={false} disabled progress={null} />,
    );
    fireEvent.change(fileInput(container), { target: { files: [txtFile()] } });
    expect(onUpload).not.toHaveBeenCalled();
  });

  it("空闲态拖放放行:守卫不误伤正常路径", () => {
    const onUpload = vi.fn();
    const { container } = renderWithI18n(
      <FileUpload onUpload={onUpload} loading={false} progress={null} />,
    );
    fireEvent.drop(dropZone(container), { dataTransfer: { files: [txtFile()] } });
    expect(onUpload).toHaveBeenCalledTimes(1);
  });

  it("空闲态点选放行", () => {
    const onUpload = vi.fn();
    const { container } = renderWithI18n(
      <FileUpload onUpload={onUpload} loading={false} progress={null} />,
    );
    fireEvent.change(fileInput(container), { target: { files: [txtFile()] } });
    expect(onUpload).toHaveBeenCalledTimes(1);
  });
});
