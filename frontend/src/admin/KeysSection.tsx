import { useEffect, useState } from "react";
import { Modal } from "../components/Modal";
import { useI18n } from "../i18n";
import {
  createAdminKey,
  deleteAdminKey,
  getSources,
  listAdminKeys,
  revokeAdminKey,
  setAdminKeySources,
  type ApiKeyMetaInfo,
  type SourceInfo,
} from "../api";

const fmtDate = (iso: string | null): string =>
  iso ? new Date(iso).toLocaleString() : "";

// 与 SourcesPage 同序的源目录分组展示顺序
const CATEGORY_ORDER = ["geo_asn", "threat", "asset", "other"];

// 源集合选择体:创建弹窗与行内编辑共用(Task 6)。“全部源”开关默认开
// (= 提交 sources: null);关掉才懒加载 /api/sources 目录(admin 页带
// cookie 可调),按 category 分组渲染 checkbox 多选。onChange 每次变更
// 上报当前值(开关开时恒 null)。
function SourcePickerBody({ initial, onChange }: {
  initial: string[] | null;
  onChange: (sources: string[] | null) => void;
}) {
  const { t } = useI18n();
  const [all, setAll] = useState(initial === null);
  const [picked, setPicked] = useState<string[]>(initial ?? []);
  const [catalog, setCatalog] = useState<SourceInfo[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (all || catalog !== null || loadError) return;
    let alive = true;
    getSources()
      .then((ss) => { if (alive) setCatalog(ss); })
      .catch((e) => {
        if (alive) setLoadError(e instanceof Error ? e.message : t("sources.loadFailed"));
      });
    return () => { alive = false; };
  }, [all, catalog, loadError, t]);

  const toggleAll = (next: boolean) => {
    setAll(next);
    onChange(next ? null : picked);
  };

  const toggleSource = (name: string, on: boolean) => {
    const next = on ? [...picked, name] : picked.filter((n) => n !== name);
    setPicked(next);
    onChange(next);
  };

  const grouped = CATEGORY_ORDER
    .map((cat) => ({ cat, items: (catalog ?? []).filter((s) => s.category === cat) }))
    .filter((g) => g.items.length > 0);

  return (
    <div>
      <label className="flex items-center gap-2 text-sm text-zinc-300">
        <input
          type="checkbox"
          role="switch"
          checked={all}
          onChange={(e) => toggleAll(e.target.checked)}
          className="h-4 w-4 accent-emerald-500"
        />
        {t("admin.keys.allSources")}
      </label>
      {!all && (
        <div className="mt-3">
          <p className="text-xs text-zinc-500">{t("admin.keys.pickSources")}</p>
          {picked.length === 0 && (
            <p className="mt-1 text-xs text-amber-400">{t("admin.keys.sourcesEmptyHint")}</p>
          )}
          {loadError ? (
            <p className="mt-2 text-xs text-red-400">{loadError}</p>
          ) : catalog === null ? (
            <p className="mt-2 text-xs text-zinc-600">…</p>
          ) : (
            grouped.map(({ cat, items }) => (
              <div key={cat} className="mt-3">
                <p className="text-xs font-semibold uppercase tracking-wider text-zinc-600">
                  {t(`sources.cat.${cat}`)}
                </p>
                <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1">
                  {items.map((s) => (
                    <label key={s.name} className="flex items-center gap-2 text-sm text-zinc-300">
                      <input
                        type="checkbox"
                        checked={picked.includes(s.name)}
                        onChange={(e) => toggleSource(s.name, e.target.checked)}
                        className="h-4 w-4 accent-emerald-500"
                      />
                      <span className="font-mono text-xs">{s.name}</span>
                    </label>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// 行内“源集合”编辑弹窗:初始集合预填,保存走 setAdminKeySources。
function SourcePickerModal({ editing, busy, onSave, onClose }: {
  editing: { sub: string; sources: string[] | null };
  busy: boolean;
  onSave: (sources: string[] | null) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [pending, setPending] = useState<string[] | null>(editing.sources);
  return (
    <Modal open title={t("admin.keys.editSources")} onClose={onClose}>
      <SourcePickerBody initial={editing.sources} onChange={setPending} />
      <button
        type="button"
        onClick={() => onSave(pending)}
        disabled={busy || (pending !== null && pending.length === 0)}
        className="mt-4 rounded-lg bg-emerald-500 px-5 py-2 text-sm font-semibold text-zinc-950 transition-transform hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50"
      >
        {t("admin.keys.saveSources")}
      </button>
    </Modal>
  );
}

// /admin 密钥区(Task 5 契约 + Task 6 源集合):列表(元数据,绝不回 key)+
// 创建弹窗(完整 key 仅此一次展示 + 复制 + 源集合选择)+ 吊销 + 两击确认
// 删除 + 行内源集合编辑;web 种子行(demoweb)同享编辑/吊销(钦定 demo
// 集合 + fail-closed kill switch),仅删除隐藏(backend 403)。
export default function KeysSection({ onUnauthorized }: { onUnauthorized?: () => void } = {}) {
  const { t } = useI18n();
  const [keys, setKeys] = useState<ApiKeyMetaInfo[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [expiresDays, setExpiresDays] = useState("");
  // 创建表单里的源集合(null = 全部源,默认)
  const [createSources, setCreateSources] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  // 创建成功后的完整 key(仅此一次);非 null 即在弹窗内展示
  const [created, setCreated] = useState<{ key: string; meta: ApiKeyMetaInfo } | null>(null);
  const [copied, setCopied] = useState(false);
  const [confirmDeleteSub, setConfirmDeleteSub] = useState<string | null>(null);
  // 行内源集合编辑目标;非 null 即弹 SourcePickerModal
  const [editing, setEditing] = useState<{ sub: string; sources: string[] | null } | null>(null);
  const [savingSources, setSavingSources] = useState(false);

  // 会话中 401(cookie 过期/服务端重启)→ 踢回登录页(spec §9);
  // 其余错误仍走错误横幅。
  const handleErr = (e: unknown) => {
    if ((e as { status?: number }).status === 401) { onUnauthorized?.(); return; }
    setError(e instanceof Error ? e.message : t("admin.keys.loadFailed"));
  };

  useEffect(() => {
    let alive = true;
    listAdminKeys()
      .then((ks) => { if (alive) setKeys(ks); })
      .catch((e) => { if (alive) handleErr(e); })
      .finally(() => { if (alive) setLoaded(true); });
    return () => { alive = false; };
  }, [t]);

  const patchRow = (meta: ApiKeyMetaInfo) =>
    setKeys((prev) => prev.map((k) => (k.sub === meta.sub ? meta : k)));

  const openCreate = () => {
    setName("");
    setExpiresDays("");
    setCreateSources(null);
    setCreated(null);
    setCopied(false);
    setError(null);
    setCreateOpen(true);
  };

  const submitCreate = async () => {
    if (busy || !name.trim()) return;
    setBusy(true);
    try {
      const r = await createAdminKey(
        name.trim(),
        expiresDays ? Number(expiresDays) : undefined,
        createSources,
      );
      setCreated(r);
      setKeys((prev) => [r.meta, ...prev]); // 列表 desc,新键插最前
    } catch (e) {
      handleErr(e);
    } finally {
      setBusy(false);
    }
  };

  const copyKey = async () => {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.key);
      setCopied(true);
    } catch { /* 剪贴板被拒:用户仍可手动选中复制 */ }
  };

  const handleRevoke = async (k: ApiKeyMetaInfo) => {
    try {
      patchRow(await revokeAdminKey(k.sub));
    } catch (e) {
      handleErr(e);
    }
  };

  const handleDelete = async (sub: string) => {
    if (confirmDeleteSub !== sub) { setConfirmDeleteSub(sub); return; } // 第一击仅换确认文案
    setConfirmDeleteSub(null);
    try {
      await deleteAdminKey(sub);
      setKeys((prev) => prev.filter((k) => k.sub !== sub));
    } catch (e) {
      handleErr(e);
    }
  };

  const handleSaveSources = async (sub: string, sources: string[] | null) => {
    setSavingSources(true);
    try {
      patchRow(await setAdminKeySources(sub, sources));
      setEditing(null);
    } catch (e) {
      handleErr(e);
    } finally {
      setSavingSources(false);
    }
  };

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <p className="text-xs text-zinc-500">{t("admin.section.keys")}</p>
        <button
          type="button"
          onClick={openCreate}
          className="rounded-lg bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-zinc-950 transition-transform hover:scale-[1.02] active:scale-[0.98]"
        >
          {t("admin.keys.create")}
        </button>
      </div>

      {error && (
        <div className="mb-3 rounded-lg border border-red-400/30 bg-red-400/10 px-4 py-2 text-sm text-red-400">
          {error}
        </div>
      )}

      {loaded && keys.length === 0 ? (
        <p className="py-6 text-center text-sm text-zinc-600">{t("admin.keys.empty")}</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-xs uppercase tracking-wider text-zinc-600">
                <th className="px-4 py-2 font-semibold">{t("admin.keys.name")}</th>
                <th className="px-4 py-2 font-semibold">{t("admin.keys.created")}</th>
                <th className="px-4 py-2 font-semibold">{t("admin.keys.lastUsed")}</th>
                <th className="px-4 py-2 font-semibold">{t("admin.keys.status")}</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-900">
              {keys.map((k) => (
                <tr key={k.sub} className="text-zinc-300">
                  <td className="px-4 py-2 font-mono text-sm">
                    {k.name}
                    {k.web && (
                      <span className="ml-2 rounded-md border border-sky-400/30 bg-sky-400/10 px-2 py-0.5 text-xs text-sky-400">
                        {t("admin.keys.webBadge")}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-xs text-zinc-500">{fmtDate(k.created_at)}</td>
                  <td className="px-4 py-2 text-xs text-zinc-500">
                    {k.last_used_at ? fmtDate(k.last_used_at) : t("admin.keys.neverUsed")}
                  </td>
                  <td className="px-4 py-2">
                    {k.disabled ? (
                      <span className="rounded-md border border-zinc-700 bg-zinc-800/50 px-2 py-0.5 text-center text-xs text-zinc-500">
                        {t("admin.keys.disabled")}
                      </span>
                    ) : (
                      <span className="rounded-md border border-emerald-500/20 bg-emerald-500/5 px-2 py-0.5 text-center text-xs text-emerald-400">
                        {t("admin.keys.active")}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2">
                    {/* web 种子行(demoweb):可编辑源集合(PATCH sources 钦定 demo 集合)*/}
                    {/* + 可吊销(PATCH disabled,fail-closed kill switch);仅删除隐藏(backend 403) */}
                    <div className="flex justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => setEditing({ sub: k.sub, sources: k.sources })}
                        className="rounded-md border border-zinc-700 px-2.5 py-1 text-xs text-zinc-200 transition-colors hover:bg-zinc-800"
                      >
                        {t("admin.keys.editSources")}
                      </button>
                      {!k.disabled && (
                      <button
                        type="button"
                        onClick={() => handleRevoke(k)}
                        className="rounded-md border border-zinc-700 px-2.5 py-1 text-xs text-zinc-200 transition-colors hover:bg-zinc-800"
                      >
                        {t("admin.keys.revoke")}
                      </button>
                    )}
                    {!k.web && (
                      <button
                        type="button"
                        onClick={() => handleDelete(k.sub)}
                        className={`rounded-md border px-2.5 py-1 text-xs transition-colors ${
                          confirmDeleteSub === k.sub
                            ? "border-red-400/50 bg-red-400/10 text-red-400"
                            : "border-zinc-700 text-zinc-200 hover:bg-zinc-800"
                        }`}
                      >
                        {confirmDeleteSub === k.sub
                          ? t("admin.keys.deleteConfirm")
                          : t("admin.keys.delete")}
                      </button>
                    )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal
        open={createOpen}
        title={t("admin.keys.create")}
        onClose={() => { setCreateOpen(false); setCreated(null); }}
      >
        {created ? (
          <div>
            <p className="text-xs text-amber-400">{t("admin.keys.onceWarning")}</p>
            <code data-testid="created-key" className="mt-2 block break-all rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 font-mono text-xs text-emerald-300">
              {created.key}
            </code>
            <button
              type="button"
              onClick={copyKey}
              className="mt-2 rounded-md border border-zinc-700 px-3 py-1.5 text-xs text-zinc-200 transition-colors hover:bg-zinc-800"
            >
              {copied ? t("admin.keys.copied") : t("admin.keys.copy")}
            </button>
          </div>
        ) : (
          <div>
            <label className="block text-xs text-zinc-500" htmlFor="key-name">
              {t("admin.keys.name")}
            </label>
            <input
              id="key-name"
              value={name}
              onChange={(e) => { setName(e.target.value); setError(null); }}
              className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 focus:border-emerald-600 focus:outline-none"
            />
            <label className="mt-4 block text-xs text-zinc-500" htmlFor="key-expires">
              {t("admin.keys.expiresDays")}
            </label>
            <input
              id="key-expires"
              type="number"
              min={1}
              value={expiresDays}
              onChange={(e) => setExpiresDays(e.target.value)}
              className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 focus:border-emerald-600 focus:outline-none"
            />
            {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
            <div className="mt-4">
              <SourcePickerBody initial={null} onChange={setCreateSources} />
            </div>
            <button
              type="button"
              onClick={submitCreate}
              disabled={busy || !name.trim()
                || (createSources !== null && createSources.length === 0)}
              className="mt-3 rounded-lg bg-emerald-500 px-5 py-2 text-sm font-semibold text-zinc-950 transition-transform hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50"
            >
              {t("admin.keys.confirm")}
            </button>
          </div>
        )}
      </Modal>

      {editing && (
        <SourcePickerModal
          key={editing.sub}
          editing={editing}
          busy={savingSources}
          onSave={(sources) => handleSaveSources(editing.sub, sources)}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}
