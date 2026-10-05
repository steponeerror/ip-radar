import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { useState } from "react";
import userEvent from "@testing-library/user-event";
import { renderWithI18n } from "../../test/i18nTestUtils";
import { Modal } from "../Modal";

describe("Modal", () => {
  it("renders title and children when open", () => {
    // Base UI 1.8 不再输出 aria-modal:模态性改由外层元素 aria-hidden+inert 表达,断言该等价语义
    const { container } = renderWithI18n(
      <Modal open={true} title="Done" onClose={() => {}}>
        <p>body text</p>
      </Modal>,
    );
    expect(container).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Done")).toBeInTheDocument();
    expect(screen.getByText("body text")).toBeInTheDocument();
    // 标题关联成立: DialogTitle 经 aria-labelledby 成为 dialog 的可访问名
    expect(screen.getByRole("dialog", { name: "Done" })).toBeInTheDocument();
  });

  it("renders nothing when closed", () => {
    renderWithI18n(
      <Modal open={false} title="Done" onClose={() => {}}>
        <p>body</p>
      </Modal>,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("calls onClose when Esc is pressed", () => {
    const onClose = vi.fn();
    renderWithI18n(
      <Modal open={true} title="Done" onClose={onClose}>
        <p>body</p>
      </Modal>,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when the backdrop is clicked", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderWithI18n(
      <Modal open={true} title="Done" onClose={onClose}>
        <p>body</p>
      </Modal>,
    );
    // portal 渲染后遮罩与面板同级挂在 body 下;点击遮罩(data-slot=dialog-overlay)即外点关闭
    const overlay = document.querySelector('[data-slot="dialog-overlay"]');
    expect(overlay).not.toBeNull();
    await user.click(overlay!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does NOT call onClose when the panel is clicked", () => {
    const onClose = vi.fn();
    renderWithI18n(
      <Modal open={true} title="Done" onClose={onClose}>
        <p>body</p>
      </Modal>,
    );
    fireEvent.click(screen.getByRole("dialog"));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("calls onClose when the close button is clicked", () => {
    const onClose = vi.fn();
    renderWithI18n(
      <Modal open={true} title="Done" onClose={onClose}>
        <p>body</p>
      </Modal>,
    );
    fireEvent.click(screen.getByRole("button", { name: "OK" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("restores focus to the trigger element on close", async () => {
    const user = userEvent.setup();

    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)}>open modal</button>
          <Modal open={open} title="Test" onClose={() => setOpen(false)}>
            <p>body</p>
          </Modal>
        </>
      );
    }
    renderWithI18n(<Harness />);

    const trigger = screen.getByRole("button", { name: "open modal" });
    // focus the trigger, THEN open — so the Modal's effect captures it as triggerRef
    trigger.focus();
    expect(document.activeElement).toBe(trigger);

    await user.click(trigger); // opens modal; effect runs, captures trigger
    // focus has moved into the dialog (async, Base UI defers to after mount)
    await waitFor(() => expect(document.activeElement).not.toBe(trigger));

    await user.keyboard("{Escape}"); // closes modal; cleanup runs, restores focus
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });

  it("wraps Tab focus within the dialog", async () => {
    const user = userEvent.setup();

    renderWithI18n(
      <Modal open={true} title="Done" onClose={() => {}}>
        <button type="button">First button</button>
        <button type="button">Last button</button>
      </Modal>,
    );

    const buttons = screen.getAllByRole("button");
    // DOM order: child buttons first, then close button
    // buttons[0] = first child button, buttons[1] = last child button, buttons[2] = close button
    const firstChildButton = buttons[0];
    const lastChildButton = buttons[1];
    const closeButton = buttons[2];

    // Base UI opens by focusing the first tabbable element (async, after mount)
    await waitFor(() => expect(document.activeElement).toBe(firstChildButton));

    // Tab forward: first child button → last child button
    await user.tab();
    expect(document.activeElement).toBe(lastChildButton);

    // Tab forward: last child button → close button
    await user.tab();
    expect(document.activeElement).toBe(closeButton);

    // Tab forward: at last focusable (close button), trap wraps to first
    // (Base UI 经焦点守卫重定向,是异步的,用 waitFor 等待落点)
    await user.tab();
    await waitFor(() => expect(document.activeElement).toBe(firstChildButton));

    // Tab backward (Shift+Tab): at first focusable, trap wraps to last
    await user.tab({ shift: true });
    await waitFor(() => expect(document.activeElement).toBe(closeButton));
  });
});
