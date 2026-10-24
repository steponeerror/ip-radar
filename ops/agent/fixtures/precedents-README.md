# fixtures/precedents — 判例库真实快照(golden 字节等价 + JS↔Python 契约对拍 fixture)

PR #177「ops 工具通道修复」随建:2026-10-24 一次性拷贝嵌套 docs 仓
`docs/ops/precedents/*.md` 全量(23 件,含 `_INDEX.md`/`_schema.md` —— `_` 前缀
件必须在场,rg `-g '!_*'` 排除面才有真实对象)。

用途与纪律:

- `golden/inject-block.*.golden.txt` 的字节基准 = 本快照上的 lib.sh
  `inject_precedents` 现行输出(改造前钉死);tools.mjs `searchPrecedentsCore`
  的 JS 重实现必须与该快照逐字节等价(含隐藏细节:YAML 折叠字段 `>` 拍平后
  「context:  」双空格、字段块内空行即终止等,以现行为准不顺手修正)。
- JS↔Python 契约对拍(selftest-t4 契约对拍例)用同一目录:JS 核心与
  `backend/ipdb/_ops_store.py rg_search_precedents`(argv 逐字对齐的参考实现)
  命中集必须相等。

再生(判例库语义演进、golden 需重钉时;禁止无声再生——须同 PR 显式重钉并说明):

```sh
cp /path/to/docs/ops/precedents/*.md ops/agent/fixtures/precedents/
PRECEDENTS_DIR=ops/agent/fixtures/precedents bash -c \
  '. ops/agent/lib.sh; inject_precedents 排他率 聚合器 许可 体量 冻结 sunset' \
  > ops/agent/golden/inject-block.discover-kws.golden.txt
PRECEDENTS_DIR=ops/agent/fixtures/precedents bash -c \
  '. ops/agent/lib.sh; inject_precedents 不存在的词xyz' \
  > ops/agent/golden/inject-block.zerohit.golden.txt
```

注意:本快照是测试 fixture 不是判例真源——判例追加只进 docs 仓,此处仅在
golden 基准漂移(输出格式变更等)时整批重拷重钉。
