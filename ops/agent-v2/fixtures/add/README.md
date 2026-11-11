# add 域 faux 夹具(票 #332 P1)

加源轮(`ops/agent-v2/tasks/add-round.mjs`)faux 面的罐装世界;零网络零花费,
与发现轮夹具(`ops/agent/fixtures/pipeline/`)同律:faux 面的**数据读数**罐装,
工具执行面真实(write_file/run_pytest 在沙箱真写真跑)。

- `turns.json` — fauxProvider 罐装回合序列(整轮一会话顺序消费):
  第 1 回合=DOSSIER 相位产出交接单 JSON;第 2-5 回合=IMPLEMENT 相位 TDD 硬序
  (write_file 测试 → run_pytest 亲眼看红 → write_file 源 → run_pytest 转绿,
  工具真执行,红面=ModuleNotFoundError 正确理由);第 6 回合=实现摘要 JSON。
  bench 形态(DOSSIER 跳过)测试自备副本去掉首回合,本目录不动。
- `verify.json` — VERIFY 相位罐装读数:roster(与 `python -m ipdb._registry
  --roster` 行形一致,真实面才跑子进程)+ liveness 鲜活度证据(last_modified
  内时间戳 age_days=2;真实面=4 组合探活)。
- `gate.json` — GATE 相位罐装命令清单(真实面=逐源测试+source_infra+目录源
  审计三连;faux 沙箱最小树只跑逐源测试)。

卡世界(queue.md 的 PROPOSE/APPROVE 行)由测试自种,不在本目录——行形冻结于
`backend/ipdb/_ops_store.py` QUEUE_HEADER。
