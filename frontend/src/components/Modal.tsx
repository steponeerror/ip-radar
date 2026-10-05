import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { useI18n } from "../i18n";
import { Dialog, DialogClose, DialogOverlay, DialogPortal, DialogTitle } from "./ui/dialog";

interface ModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  closeLabel?: string;
}

// Escape/焦点陷阱/滚动锁/焦点恢复/外点关闭全部交给 Base UI(modal 默认 true)。
// 不走 ui DialogContent:其内置 overlay 硬编码 bg-black/10+blur 且不透传 className,
// 视觉契约要求 bg-black/60 无模糊,而 ui/dialog.tsx 是 registry-verbatim 不可改——
// 故直接组装 Overlay + Popup,并保留旧面板的 zinc 硬编码类(视觉零漂移)。
export function Modal({ open, title, onClose, children, closeLabel }: ModalProps) {
  const { t } = useI18n();

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogPortal>
        <DialogOverlay className="bg-black/60 supports-backdrop-filter:backdrop-blur-none" />
        <DialogPrimitive.Popup className="fade-in fixed top-1/2 left-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border border-zinc-800 bg-zinc-900 p-6 outline-none">
          <DialogTitle className="mb-2 text-base font-semibold leading-normal text-zinc-100">
            {title}
          </DialogTitle>
          <div className="mb-4 text-sm text-zinc-400">{children}</div>
          <DialogClose
            type="button"
            className="rounded-lg bg-emerald-500 px-5 py-2 text-sm font-semibold text-zinc-950 transition-transform hover:scale-[1.02] active:scale-[0.98]"
          >
            {closeLabel ?? t("modal.close")}
          </DialogClose>
        </DialogPrimitive.Popup>
      </DialogPortal>
    </Dialog>
  );
}
