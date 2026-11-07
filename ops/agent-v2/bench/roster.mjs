// roster.mjs — roster dump 行解析单源(终审 P2-2:leak-check 与 score 曾各持一份解析器,
// 失败语义分叉——旧 leak 版 3 列宽容/坏行静默跳,旧 score 版 ≥4 列/坏行 throw;同一
// --roster 输入格式漂移时打分器红、漏题闸静默少针)。统一 = score 旧语义 fail-closed:
// 坏行(列数<4)throw、零有效行 throw——两侧同红,不给「静默少针装绿」留门。
// 行形:`name | category | download_host | fields [| 子列表]`(registry --roster 固定
// 格式,子列表键并入 fields 供参考);download_host '-' 原样保留(= 无下载面,消费方
// 各自处理:leak-check 无域名针,score 无 URL 声明面)。
// 消费方:score.mjs(答案表)、leak-check.mjs(针生成,取前 3 列)。
export function parseRoster(text) {
  const rows = [];
  for (const line of String(text ?? "").split("\n")) {
    const t = line.trim();
    if (!t) continue;
    const parts = t.split("|").map((p) => p.trim());
    if (parts.length < 4) throw new Error(`roster 行列数不足(须 ≥4:name|category|host|fields):${t}`);
    const [name, category, host, ...rest] = parts;
    rows.push({ name, category, host, fields: rest.flatMap((c) => c.split(",")).filter(Boolean) });
  }
  if (!rows.length)
    throw new Error("roster 解析零条:名单取数面坏了(空文件/空输出),拒绝零针开闸/零答案打分");
  return rows;
}
