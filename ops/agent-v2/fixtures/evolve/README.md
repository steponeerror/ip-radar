# fixtures/evolve — 自演化轮驱动器罐装提案者回合(#356 端到端冒烟面)

`turns.json` = faux 提案者罐装回合(fauxProvider 重放,驱动真工具,零网络零花费):
①write_file 在开放面路径落一个文件(验证 worktree 沙箱遏制与候选面可见性);
②run_bash 配 git 身份并提交(候选面=HEAD 提交,trial 沙箱基);
③终答文本=提案者报告(驱动器落 proposer-report.md)。

消费面:tests/evolve-e2e.test.mjs 经 runEvolveRound({fixturesDir: 本目录})装载
(fauxAddBundle 同构:faux-add-round 模型 id + turns 重放)。真实提案者面见
bench/evolution/run-round.mjs 头注「提案者机制取舍」。
