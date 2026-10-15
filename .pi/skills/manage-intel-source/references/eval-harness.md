# Eval Harness 用法

## download 前置(eval 保持纯)

`load_db()` 只 load 已有数据文件,**不 download**。新源第一次必须显式 download,否则候选采样为空 → INSUFFICIENT-SAMPLE(假象)。

```python
from ipdb._registry import _sources
s = next(x for x in _sources if x.name == "<source>")
s.download()        # 显式前置
s.rebuild()         # LMDB 唯一写入口(load 此时无 env 只会返回 0)
print(s.health())   # 确认 record_count > 0、is_stale=False
```

大源(数百万 CIDR)rebuild 前留意 RSS:单证据 geo/asset 源已走 `single_evidence` 流式;若新增累积型大源,在 WSL 内单进程 rebuild 仍可能吃数百 MB。

然后 eval:`python -m ipdb._eval <source>`(从 `backend/` cwd)。

**为什么不放进 eval 自动 download**:eval 的设计基石是 reproducible seeded sampling(确定性)。混入网络 side-effect 会:(a) 首次慢、(b) 下载失败时 eval 挂而非给 verdict、(c) CI/批量评估抖动。download 是"准备数据",eval 是"评估",职责分离。

## metrics 解读

| metric | 含义 | 高= |
|---|---|---|
| MC | 去掉该源丢多少 (ip,type) | 贡献大 |
| CG | 独立源佐证数 | 可信(VERIFIED 门槛) |
| OC | 与其他源重叠率 | 高=冗余 |
| fp | benign IP 误伤率 | 高=误报(MIXED 的 cost lever) |
| other | 分类映射到 `other` 的比例 | 高=分类膨胀(收紧 `_MAP`) |
| dead_slot_fill | 填补的空分类槽 | 该源独占某分类 |
| confidence_uplift | 带来的置信度提升 | 贡献 |

## INSUFFICIENT-SAMPLE 别误判

多为 corpus 偏向(geo/asn 源 IP 不在威胁 corpus),不是源差。例:cn_isp/iptoasn/ipinfo_lite(geo)、ip2proxy/stopforumspam(数据少或 IP 不在样本)。处理:补样本 / 换 corpus / 接受(geo 源本就不靠威胁 corpus 评估)。

## gate 接入关语义(spec 2026-10-12-eval-loop-hardening-design.md §3.1/§3.2)

新源收录收尾强制跑接入关(`cd backend && IP_RADAR_EVAL_ENV=gate IP_RADAR_DATA_DIR=<repo>/.eval-gate-mirror python -m ipdb._eval --gate <source>`;物化前序 `scripts/materialize_source.sh` 见 add-intel-source skill Phase 4),**gate 报告必附 PR**。

**双口径并报(Q4)**:「candidate-stratum 自域判别力」(消融 + verdict 8 态——候选自己行不行)与「四层舰队净影响」(ON/OFF delta——加进舰队搬动了什么)是两个问题,各答各节、可拆着下结论(演示 B 判例)。ON/OFF 两臂同一套四层语料资产 + 同一 run_seed——delta 是配对读数,不是两独立样本的差(Q14)。

**共识层装配两场景**:gate=装配后排除候选键集(与他源重叠的候选 IP 一并剔,在场性证据不可拆分,宁少算);月轮=全舰队(固有循环语义,月报注记承载)。**同批多候选串行纳入**——后放行者的舰队含先放行者。

**强制人裁触发集(只升旗不自动动作,声明 r:测量建言,人裁终局)**:R2 基础三态(NEGATIVE/MIXED/NO-DATA)+ S1 抄尺(候选键集对 truth 资产成员包含度>0.5 且非蜜罐声明)+ S2 好得可疑(独有命中×低 OC,或真值层 delta 显著正且 OC 低)+ S3 OC≥0.9 未声明派生(0.7-0.9 敏感带 report-only,报告不触发)+ S4 任一层 delta 显著恶化(bootstrap p<0.05)而 verdict 非 NEGATIVE/MIXED(NO-DATA 不豁免:死源四层 delta 仍可恶化)。旗标行 = PR 人裁清单项,逐项处置留痕;零旗标也留哨兵行(未触发≠未评估)。

**镜像 epoch 对齐契约(S7,fail-closed)**:gate 每次跑前 rsync 生产 volume → `.eval-gate-mirror/`(常驻增量镜像,已 gitignore)+ ssh 逐源比对 epoch,失配即拒跑(rc=3,绝不降级为警告)——测量基线必须是生产实况,不因想跑而放行。实跑协议:测量数据目录须设 `IP_RADAR_DATA_DIR=<repo>/.eval-gate-mirror`(不设则读本地 dev 数据,CLI 会在镜像对齐后再校验 registry 数据目录与镜像 epoch 逐源一致——candidate 自身豁免,其新 ptr 只存在于物化侧——失配同样 rc=3 拒跑;monthly_eval.sh run_step 同款接线);候选物化落镜像工作副本(`IP_RADAR_DATA_DIR=<repo>/.eval-gate-mirror bash scripts/materialize_source.sh <name>`);`--gate` 的前置 sync 自动保留候选文件(`--exclude=<name>` / `<name>.*`,与候选豁免同口径;仅覆盖 filename==name house style 源,filename≠源名的老源会被 gate 以 rc=3 拒绝,不支持镜像流);镜像内**其他**本地改动(非生产、非候选)仍会被 `--delete-after` 清除。
