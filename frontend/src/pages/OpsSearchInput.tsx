import type { KeyboardEvent } from "react";
import { useI18n } from "../i18n";

// OpsSearchInput.tsx — 运营面搜索输入统一件(视觉门 2026-10-21 阻断1 及其
// 同根因补收口)。根因:type="search" 的原生 ::-webkit-search-cancel-button
// 在 Chromium 位于 UA shadow,对作者 CSS 完全免疫(实测 display:none /
// -webkit-appearance 连 !important 内联注入均触达不了,默认蓝 #3F71B7 系
// 图标仍在)——出 accent 纪律(硬规⑤:accent 只绿 + 语义色)。故运营面全部
// 搜索输入弃 type=search,统一 type="text" + role="searchbox"(保 a11y 语义
// 与 getByRole("searchbox") 测试选择器),清除面走本件中性灰自定义钮
// (text-zinc-500 hover:text-zinc-300,空输入不渲染不占位)。
// 调用面(三处,同款不漂移):设置密钥搜索(OpsPage ConfigSection)/驾驶舱
// 发现轮输入(OpsCockpit)/档案判例检索(OpsPage PrecedentsSection)。
// 尺寸分工:输入恒通栏 w-full;行内弹性(flex-1/min-w-*)与外距由调用面经
// wrapperClass 施加到容器(容器即 flex item / 尺寸承担者)。
export function OpsSearchInput({ label, placeholder, value, onChange, onKeyDown, wrapperClass = "" }: {
  label: string;
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
  onKeyDown?: (e: KeyboardEvent<HTMLInputElement>) => void; // 透传(判例检索 Enter 即查)
  wrapperClass?: string;
}) {
  const { t } = useI18n();
  return (
    <div className={`relative ${wrapperClass}`}>
      <input
        type="text"
        role="searchbox"
        aria-label={label}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        className="w-full rounded-md border border-zinc-700 bg-zinc-950 py-1.5 pl-3 pr-8 text-xs text-zinc-200 focus:border-emerald-600 focus:outline-none"
      />
      {value && (
        <button
          type="button"
          aria-label={t("ops.searchClear")}
          onClick={() => onChange("")}
          className="absolute inset-y-0 right-2 flex items-center py-0.5 text-sm leading-none text-zinc-500 transition-colors hover:text-zinc-300"
        >
          ×
        </button>
      )}
    </div>
  );
}
