export { cn } from "cn";

// 自托管常走 http://LAN-IP(非 secure context),navigator.clipboard 为 undefined——
// 降级 legacy execCommand;两条路都挂则返回 false(调用方不假装已复制)。
// U10 自 VersionBanner 收编为共享 helper:密钥复制(KeysSection,仅展示一次,
// 失败代价最高)与更新命令复制(VersionBanner)同源。
export function copyText(text: string): Promise<boolean> {
  if (navigator.clipboard?.writeText) {
    return navigator.clipboard.writeText(text).then(() => true, () => false);
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return Promise.resolve(ok);
  } catch {
    return Promise.resolve(false);
  }
}
