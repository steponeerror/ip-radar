import { describe, it, expect } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithI18n } from "../../test/i18nTestUtils";
import { ensureOpenCC } from "../../i18n/opencc";
import { translate } from "../../i18n/translate";
import { SourceDetailRow } from "../SourceDetailRow";
import type { ClassificationDetail } from "../../api";

const base: ClassificationDetail = { source: "otx", verdict: "malicious", reliability: 0.9 };

describe("SourceDetailRow", () => {
  it("always renders source and reliability", () => {
    renderWithI18n(<SourceDetailRow detail={base} />);
    expect(screen.getByText(/otx/)).toBeInTheDocument();
    expect(screen.getByText(/rel 0\.9/)).toBeInTheDocument();
  });

  it("renders the per-source verdict chip with localized label and tooltip", () => {
    renderWithI18n(<SourceDetailRow detail={{ ...base, verdict: "informational" }} />);
    const chip = screen.getByText("Informational");
    expect(chip).toBeInTheDocument();
    expect(chip.getAttribute("title")).toBe("This source's verdict stamp for the record");
  });

  it("styles unknown verdict codes with the informational fallback", () => {
    renderWithI18n(<SourceDetailRow detail={{ ...base, verdict: "weird" }} />);
    // missing label key → raw key text; style falls back to informational ring
    const chip = screen.getByText("verdict.weird");
    expect(chip.className).toContain("bg-zinc-500/15");
    expect(chip.className).toContain("ring-zinc-500/25");
  });

  it("renders all optional fields when present", () => {
    const d: ClassificationDetail = {
      ...base,
      malware_name: "remcos",
      comment: "sinkholed by abuse.ch",
      tags: ["c2", "botnet"],
      reporter_count: 4,
      native_confidence: 85,
      first_seen: "2026-07-01T00:00:00+00:00",
      last_seen: "2026-08-15T00:00:00+00:00",
      native_categories: ["PUB"],
    };
    renderWithI18n(<SourceDetailRow detail={d} />);
    expect(screen.getByText(/malware: remcos/)).toBeInTheDocument();
    expect(screen.getByText(/reporters: 4/)).toBeInTheDocument();
    expect(screen.getByText(/\[c2\]/)).toBeInTheDocument();
    expect(screen.getByText(/\[PUB\]/)).toBeInTheDocument();
    expect(screen.getByText(/native 85/)).toBeInTheDocument();
    expect(screen.getByText(/first 2026-07-01/)).toBeInTheDocument();
    expect(screen.getByText(/last 2026-08-15/)).toBeInTheDocument();
  });

  it("omits optional lines and the extra toggle when absent", () => {
    renderWithI18n(<SourceDetailRow detail={base} />);
    expect(screen.queryByText(/malware:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/reporters:/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("truncates long comments and exposes the full text via title", () => {
    const long = "x".repeat(60);
    const d: ClassificationDetail = { ...base, comment: long };
    renderWithI18n(<SourceDetailRow detail={d} />);
    const node = screen.getByText(/comment:/);
    expect(node.getAttribute("title")).toBe(long);
    expect(node.textContent).toContain("…");
  });

  it("toggles the extra key/value block", () => {
    const d: ClassificationDetail = {
      ...base,
      extra: { foo: "bar", n: 1, b: true },
    };
    renderWithI18n(<SourceDetailRow detail={d} />);
    const toggle = screen.getByRole("button", { name: /extra 3 keys/i });
    const rowText = () => document.body.textContent ?? "";
    fireEvent.click(toggle);
    expect(rowText()).toContain("foo: ");
    expect(rowText()).toContain('"bar"');
  });

  it("renders native_categories as chips", () => {
    const d: ClassificationDetail = { ...base, native_categories: ["15", "16"] };
    renderWithI18n(<SourceDetailRow detail={d} />);
    expect(screen.getByText(/\[15\]/)).toBeInTheDocument();
    expect(screen.getByText(/\[16\]/)).toBeInTheDocument();
  });

  it("renders the full scanner self-declared-range label chip (SR-T3 #214)", async () => {
    // spec §5:scanner 证人行 native 标签「研究扫描 · <厂商/机构>(自报段)」
    // 全文出 chip(通用 native_categories 渲染,零新 UI 机制;钉法照上例)。
    // 2026-10-26 i18n 裁定:展示面跟 locale 走(zh-CN 必须与后端原字面量逐字一致,
    // zh-TW 由 OpenCC 派生,en 英文;非自报段形状仍原样透传)。
    await ensureOpenCC();  // 转换器同步就绪再渲染(生产路径 = Provider 异步武装后重渲染)
    const d: ClassificationDetail = {
      source: "scanner_ranges",
      verdict: "malicious",
      reliability: 0.9,
      native_categories: ["研究扫描 · Stretchoid(自报段)"],
    };
    const cases = [
      ["en", "[Research scanning · Stretchoid (self-declared range)]"],
      ["zh-CN", "[研究扫描 · Stretchoid(自报段)]"],
      ["zh-TW", "[研究掃描 · Stretchoid(自報段)]"],
    ] as const;
    for (const [locale, expected] of cases) {
      const { unmount } = renderWithI18n(<SourceDetailRow detail={d} />, { locale });
      expect(screen.getByText(expected)).toBeInTheDocument();
      unmount();
    }
  });

  it("ignores retired extra.native_type (fallback removed)", () => {
    const d: ClassificationDetail = { ...base, extra: { native_type: "PUB" } };
    renderWithI18n(<SourceDetailRow detail={d} />);
    expect(screen.queryByText(/\[PUB\]/)).not.toBeInTheDocument();  // fallback gone
  });

  it("sbl_id and urls render as links, others plain", () => {
    const d: ClassificationDetail = {
      ...base,
      extra: { sbl_id: "SBL123456", tweet_url: "https://x.com/p/1", port: 80 },
    };
    renderWithI18n(<SourceDetailRow detail={d} />);
    fireEvent.click(screen.getByRole("button", { name: /extra 3 keys/i }));
    const sbl = screen.getByRole("link", { name: "SBL123456" }) as HTMLAnchorElement;
    expect(sbl.href).toBe("https://check.spamhaus.org/sbl/query/SBL123456");
    expect(sbl.target).toBe("_blank");
    const tweet = screen.getByRole("link", { name: "https://x.com/p/1" }) as HTMLAnchorElement;
    expect(tweet.href).toBe("https://x.com/p/1");
    // non-link values render as bare JSON text (no quotes stripped)
    expect(screen.getByText((c, el) => c === "80" && el?.className.includes("break-all") === false)).toBeTruthy();
  });

  // honyport 自建蜜罐观测可读行(#273;spec 2026-11-02 §1 证据语义:只报
  // 事实「30 天内观测到攻击,共 X 次」+ 服务列表 + 最后观测,不评
  // severity)。字段契约 = backend HonyportSource.parse_row(#272,
  // tests/sources/test_honyport.py::test_query_evidence_shape):服务 →
  // native_categories 列表、last_seen ISO 串、计数 → extra.total_events。
  const honyportDetail = (over: Partial<ClassificationDetail> = {}): ClassificationDetail => ({
    source: "honyport",
    verdict: "malicious",
    reliability: 0.85,
    native_categories: ["mssql", "ssh"],
    last_seen: "2026-11-01T17:53:43Z",
    extra: { total_events: 11663 },
    ...over,
  });

  it("honyport: observed line renders count + service list + last seen (#273)", () => {
    renderWithI18n(<SourceDetailRow detail={honyportDetail()} />);
    const text = document.body.textContent ?? "";
    expect(text).toContain("Observed attacks in the last 30 days: 11663 total");
    expect(text).toContain("services: mssql, ssh");
    expect(text).toContain("last seen 2026-11-01");
  });

  it("honyport: zh-CN verbatim copy 「30 天内观测到攻击,共 X 次」(#273)", () => {
    expect(translate("zh-CN", "sourceDetail.honeypotObserved", { n: 962 }))
      .toBe("30 天内观测到攻击,共 962 次");
    expect(translate("zh-CN", "sourceDetail.honeypotServices")).toBe("服务");
    expect(translate("zh-CN", "sourceDetail.honeypotLastSeen")).toBe("最后观测");
  });

  it("honyport without extra.total_events renders generic row only", () => {
    renderWithI18n(<SourceDetailRow detail={honyportDetail({ extra: undefined })} />);
    const text = document.body.textContent ?? "";
    expect(text).not.toContain("30 days");
    expect(text).not.toContain("last seen");   // 通用行只有「last <date>」
    expect(text).toContain("last 2026-11-01"); // 通用槽照常
  });

  it("non-honyport source carrying total_events extra gets no observed line", () => {
    renderWithI18n(<SourceDetailRow detail={honyportDetail({ source: "feodo" })} />);
    expect(document.body.textContent ?? "").not.toContain("30 days");
  });

  // honyport 二期手法明细(#283;spec 2026-11-03 §4):消费 extra.techniques
  // 八字段(契约 = backend HonyportSource._TECHNIQUES_FIELDS,票 A 冻结)。
  // 主渲染 commands(前 3 + 共 N 条截断计数)、CVE 纯文本徽标(不链接
  // 外站,纯本地红线精神)、user_agents 直列;protocols/statuses/
  // actions/stages/paths 进折叠;空字段一律不渲染;文案沿用一期「30 天内
  // 观测到」只报事实口径。
  const fullTechniques = {
    commands: [
      "/bin/./uname -s -v -n -r -m",
      "lspci | grep x | cut -f5- -d ' '",
      "nvidia-smi",
      "curl http://x/1",
      "wget http://x/2",
    ],
    cves: ["CVE-2026-109618", "CVE-2026-109619"],   // 真样例锚(spec §1,109.105.210.2)
    user_agents: ["python-requests/2.31.0"],          // 真样例锚(spec §1)
    protocols: ["tcp"],
    statuses: ["401"],
    actions: ["brute-force"],
    stages: ["exploit"],
    paths: ["/phpmyadmin/"],
  };
  const techniquesDetail = (techniques: unknown): ClassificationDetail =>
    honyportDetail({ extra: { total_events: 11663, techniques } });

  it("honyport techniques: commands truncated to first 3 + total count (#283)", () => {
    renderWithI18n(<SourceDetailRow detail={techniquesDetail(fullTechniques)} />);
    const text = document.body.textContent ?? "";
    expect(text).toContain("commands: /bin/./uname -s -v -n -r -m");
    expect(text).toContain("nvidia-smi");
    expect(text).not.toContain("curl http://x/1");   // 第 4 条起截断
    expect(text).not.toContain("wget http://x/2");
    expect(text).toContain("5 total");               // 共 N 条计数(en 口径对齐一期 {n} total)
  });

  it("honyport techniques: CVE badges are plain text, never links (#283)", () => {
    renderWithI18n(<SourceDetailRow detail={techniquesDetail(fullTechniques)} />);
    const badge = screen.getByText("CVE-2026-109618");
    expect(badge.tagName).toBe("SPAN");              // 纯文本徽标,非 <a>
    expect(screen.queryByRole("link")).toBeNull();   // 不链接外站(纯本地红线)
    expect(screen.getByText("CVE-2026-109619")).toBeInTheDocument();
  });

  it("honyport techniques: user_agents listed directly (#283)", () => {
    renderWithI18n(<SourceDetailRow detail={techniquesDetail(fullTechniques)} />);
    expect(document.body.textContent ?? "").toContain(
      "user agents: python-requests/2.31.0");
  });

  it("honyport techniques: five minor fields behind fold toggle (#283)", () => {
    renderWithI18n(<SourceDetailRow detail={techniquesDetail(fullTechniques)} />);
    expect(document.body.textContent ?? "").not.toContain("protocols: tcp");
    fireEvent.click(screen.getByRole("button", { name: /techniques detail/i }));
    const text = document.body.textContent ?? "";
    expect(text).toContain("protocols: tcp");
    expect(text).toContain("statuses: 401");
    expect(text).toContain("actions: brute-force");
    expect(text).toContain("stages: exploit");
    expect(text).toContain("paths: /phpmyadmin/");
  });

  it("honyport techniques: empty fields render nothing (#283)", () => {
    renderWithI18n(
      <SourceDetailRow
        detail={techniquesDetail({
          commands: ["/bin/sh"], cves: [], user_agents: [],
          protocols: [], statuses: [], actions: [], stages: [], paths: [],
        })}
      />,
    );
    const text = document.body.textContent ?? "";
    expect(text).toContain("commands: /bin/sh");
    expect(text).not.toContain("CVE:");
    expect(text).not.toContain("user agents:");
    expect(screen.queryByRole("button", { name: /techniques detail/i })).toBeNull();
    expect(text.match(/ total/g) ?? []).toHaveLength(1);  // 仅观测行计数,无截断计数
  });

  it("honyport techniques: fold renders when main trio all empty (#283)", () => {
    renderWithI18n(
      <SourceDetailRow
        detail={techniquesDetail({
          commands: [], cves: [], user_agents: [],
          protocols: ["tcp"], statuses: [], actions: [], stages: [], paths: [],
        })}
      />,
    );
    expect(document.body.textContent ?? "").not.toContain("commands:");
    fireEvent.click(screen.getByRole("button", { name: /techniques detail/i }));
    expect(document.body.textContent ?? "").toContain("protocols: tcp");
  });

  it("honyport techniques key excluded from generic extra fold (#283)", () => {
    renderWithI18n(<SourceDetailRow detail={techniquesDetail(fullTechniques)} />);
    const toggle = screen.getByRole("button", { name: /extra 1 keys/i });  // techniques 不计入
    fireEvent.click(toggle);
    const text = document.body.textContent ?? "";
    expect(text).toContain("total_events: 11663");
    expect(text).not.toContain('"techniques"');   // 可读渲染替代原始 JSON,同一事实不双列
  });

  it("honyport without techniques keeps phase-1 shape (#283)", () => {
    renderWithI18n(<SourceDetailRow detail={honyportDetail()} />);
    const text = document.body.textContent ?? "";
    expect(text).not.toContain("commands:");
    expect(screen.queryByRole("button", { name: /techniques detail/i })).toBeNull();
    expect(screen.getByRole("button", { name: /extra 1 keys/i })).toBeInTheDocument();
  });

  it("non-honyport extra.techniques gets no techniques UI (#283)", () => {
    renderWithI18n(
      <SourceDetailRow detail={{ ...techniquesDetail(fullTechniques), source: "feodo" }} />,
    );
    const text = document.body.textContent ?? "";
    expect(text).not.toContain("commands: ");
    expect(text).not.toContain("user agents:");
    expect(screen.queryByRole("button", { name: /techniques detail/i })).toBeNull();
  });

  it("honyport techniques: zh-CN verbatim copy (#283)", () => {
    expect(translate("zh-CN", "sourceDetail.honeypotCommands")).toBe("命令");
    expect(translate("zh-CN", "sourceDetail.honeypotCves")).toBe("CVE");
    expect(translate("zh-CN", "sourceDetail.honeypotUserAgents")).toBe("浏览器标识");
    expect(translate("zh-CN", "sourceDetail.honeypotTotal", { n: 6 })).toBe("共 6 条");
    expect(translate("zh-CN", "sourceDetail.honeypotTechniques")).toBe("手法明细");
    expect(translate("zh-CN", "sourceDetail.honeypotProtocols")).toBe("协议");
    expect(translate("zh-CN", "sourceDetail.honeypotStatuses")).toBe("状态");
    expect(translate("zh-CN", "sourceDetail.honeypotActions")).toBe("动作");
    expect(translate("zh-CN", "sourceDetail.honeypotStages")).toBe("阶段");
    expect(translate("zh-CN", "sourceDetail.honeypotPaths")).toBe("路径");
  });
});
