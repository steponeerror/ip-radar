# honyport 日 CSV 组件接入交付报告(issue #265,truth-v2 增量单)

- 分支:truth-v2-hp(基线 truth-v2 @ 921e2259,开工已验 `git merge-base --is-ancestor truth-v2 HEAD`)
- 工单:GitHub issue #265(truth-v2 增量:honyport 日 CSV 组件接入+月轮 rsync 面)
- 依据:ADR 0017 §2(构成=小机快照+honyport CSV)/§4(组件闸 1,000)/§7(永不入池);spec docs/research/2026-11-01-truth-layer-v2-spec.md
- 真数据样例:仅 ssh 只读实测(2026-11-01),未拷入 git

## 1. 改了什么 / 为什么

### 1.1 解析方式论证:表头格式探测(弃显式组件类型参数)

工单给的两个选项中选**表头探测**,理由:

1. 表头是数据自带的声明:快照 `ip,attempts` vs honyport 六列表头,精确字符串匹配,零模糊;未知表头直接 ValueError fail-loud,与 `parse_snapshot_csv`「坏快照不许静默缩水」同哲学。
2. 显式组件类型参数会引入「声明与数据不符」的新错误面(调用方声明 honyport 但目录里是快照);校验这个一致性的手段恰恰就是表头探测——等于两套机制做一件事。
3. `--truth-v2-component NAME=DIR` 调用面不变(ADR 0017 §2 预留接口原样),组件名纯属运营命名,不进解析器。

### 1.2 backend/ipdb/_eval/truth_v2.py

- 新增 `parse_honyport_csv(path)`:表头逐字 `ip,service,protocol,events,first_seen,last_seen`(2026-11-01 服务器实测);采集日取文件名 `-YYYY-MM-DD` 段(表头无 captured_at;`_HP_NAME_RE`);`csv.reader` 分列(service 含逗号时 exporter 引号包裹,split(",") 会错拆);protocol 可空(实测样例);同 IP 多 service 行 events 累加(成员判定只看 IP 集合,行为计数如实);first_seen/last_seen 做格式校验拦半截行但不入证据。fail-loud 族:坏文件名/坏表头/列数错/非 v4/非整数 events/坏时间戳全 ValueError。
- `load_snapshots` 改为逐文件表头探测(`_parse_component_csv`):快照/honyport 同目录混存合法,未知表头 ValueError。
- 窗归属/清洗链/组件闸**零改**:`_clean_component` 按 `day` 过滤,格式无关;组件闸仍按组件各算(honyport 起步个位数 IP=恒哨兵,合法态,ADR 0017 §4)。
- 模块 docstring 与 provenance notes 措辞更新(honyport 从「接口预留」→「表头探测同位并入」)。

### 1.3 scripts/monthly_eval.sh

- 新增 /opt/honyport/out rsync 面(快照面之后):先 `ssh test -d /opt/honyport/out` 探测——rc=255(ssh 自身连接/认证失败)照 fail-loud,**不与目录缺席混淆**(网络断不得伪装成哨兵态静默跳过);目录在场→rsync,容忍规则抄快照面先例(rc=24 源侧活文件消失良性,其余非零拒绝);目录缺席→不传 honyport 组件参数、truth-v2 腿只跑 smallbox(缺目录=哨兵不持死,#265 验收线)。
- truth-v2 腿同位并接 `"${HP_COMPONENT_ARG[@]}"`(bash 5.2 空数组 set -u 展开已验);dry-run 分支打印探测说明。
- 目录在场但空(0 个 CSV)→ python 侧 `load_snapshots` ValueError → 构建腿 rc=2 → 工件缺席=报告族缺员即死:采集健康事故须人见,与快照面断供同律。

### 1.4 测试

- backend/tests/eval/test_eval_truth_v2.py:+8 测(第 10 节),全离线合成 fixture:
  1. `test_parse_honyport_day_from_filename_events_accumulate`(文件名取日+多 service 行累加,IP 集照实测样例)
  2. `test_parse_honyport_quoted_service_field_survives`(引号 service 字段 csv.reader 分列)
  3. `test_parse_honyport_fail_loud_family`(tamper-red 六负例:无日期文件名/坏表头/5 列/非整数 events/非 v4/坏时间戳)
  4. `test_load_snapshots_sniffs_both_formats_rejects_unknown`(混目录合法+未知表头炸;文件名序非采集日序)
  5. `test_honyport_window_boundary_day_files`(窗归属边界:文件名日=窗起点当日 2026-08-04 计入/前一日属上一版;断言落组件级 provenance 计数——个位组件必不过闸,与组件闸正交)
  6. `test_two_components_end_to_end_union`(smallbox 快照 1,000 + honyport 日 CSV 1,000 双过闸→并集 2,000 员端到端)
  7. `test_honyport_tiny_component_sentinel_union_with_smallbox`(个位哨兵与 smallbox 并存:出版成员零漏入)
  8. `test_tamper_honyport_input_changes_pins`(换证留痕:输入 sha256 pin 变;出版指纹不变是正确的——哨兵组件不入出版面)
- backend/tests/eval/test_monthly_eval_cascade.py:ssh 桩升级两调用形(`test -d` 探测=缺席 rc 1 不 touch 心跳;心跳推送调用照旧)——探测调用在族校验前发生,旧桩无条件 touch 会假推心跳。
- CHANGELOG.md:Unreleased/新增 Added 双语条目。

## 2. 怎么验证(TDD 时序)

- **红证**:实现前 `python -m pytest tests/eval/test_eval_truth_v2.py -q` → `8 failed, 21 passed`(`parse_honyport_csv` 未存在,ImportError 全红;既有 21 全绿)。
- 中途真红 2 枚被我自己的断言错误触发(混目录排序期望反了;窗边界断言落在出版成员而个位组件必不过闸)——修正测试设计而非实现,`_clean_component` 层窗归属经独立 debug 脚本证正确。
- cascade 桩修前 2 红(`缺员即死不推心跳`被探测调用假推)→ 桩升级后 14 全绿。
- 终态:`tests/eval` 588 passed / 0 failed;`tests/core` 741 passed / 8 skipped / **1 failed=test_no_retired_terms_in_living_docs,基线既有红**(NEEDS.md 拒用词「舰队」「语料」来自基线提交 921e2259 的 NEEDS 注记,`git show truth-v2:NEEDS.md` 可证,与本单改动零交集,本单未碰 NEEDS.md;处置待裁,见 §4)。
- `bash -n scripts/monthly_eval.sh` 语法通过;`--dry-run` 回显 12 腿 + honyport 面探测说明行 + truth-v2 腿命令行正确。
- 真数据核对:`ssh root@203.88.124.85 head -4 /opt/honyport/out/honeypot_attackers-2026-11-01.csv` 只读确认表头/时间戳/protocol 空值三事实,与解析器逐字对齐;CSV 未拷入仓库。

## 3. 纪律自查

- codegraph MCP 不在本实现工会话工具面 → 按后备规则用 read/grep 读码,已注明。
- 扫描器剔除只在 ip-radar 侧(scanner_ranges 面既有机制),源侧零重复(工单让渡已裁)。
- 互斥红线:产物只在 eval 语料目录,永不写 private_sources/池(改动未触碰输出布局)。
- 真数据不入 git;测试全离线合成。
- 只在 truth-v2-hp 分支 commit,未 push、未动 master。

## 4. 待裁(上报 supervisor)

- tests/core 的 NEEDS.md 拒用词失败是 **truth-v2 基线自带**(921e2259 注记写入了「舰队」「语料」两个退役词)。修法=改 NEEDS.md 措辞(如「蜜罐机群」「真值数据」),一行事,但 NEEDS.md 是用户三态并轨裁决件,我不擅自改;建议随本单或单独微批处理,否则 PR #264 若挂 CI 会红在这。

## 5. 复核命令

```bash
cd backend
env -u IP_RADAR_EVAL_ENV python -m pytest tests/eval/test_eval_truth_v2.py -q        # 29 passed(21 既有+8 新)
env -u IP_RADAR_EVAL_ENV python -m pytest tests/eval/test_monthly_eval_cascade.py -q # 14 passed
env -u IP_RADAR_EVAL_ENV python -m pytest tests/eval -q                              # 588 passed
env -u IP_RADAR_EVAL_ENV python -m pytest tests/core -q                              # 741 passed 8 skipped 1 failed(基线 NEEDS 拒用词,非本单)
cd ..
bash -n scripts/monthly_eval.sh                                                      # 语法
bash scripts/monthly_eval.sh --dry-run                                               # 12 腿回显+honyport 面说明
ssh root@203.88.124.85 "head -4 /opt/honyport/out/honeypot_attackers-$(date +%F).csv"  # 只读对照表头
```
