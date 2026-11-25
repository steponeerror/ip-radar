# syntax=docker/dockerfile:1

FROM node:22-alpine AS frontend
WORKDIR /build
ARG NPM_REGISTRY=""
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci ${NPM_REGISTRY:+--registry $NPM_REGISTRY}
COPY frontend/ ./
RUN npm run build

# ── P5(票 #137):运营 agent 生产依赖层 ──────────────────────────
# bookworm-slim(glibc)而非 alpine:最终镜像(python:3.12-slim = trixie)直接
# 复用本层 node 二进制——trixie glibc/libstdc++ 向上兼容 bookworm 链接产物,零
# musl 移植问题。engines node>=22.19(ops/package.json,#412 单包):node:22 浮动 tag
# 自 2025-10 起恒 ≥22.19 且持续吃补丁;下方显式断言钉下界,基镜像漂移到 <22.19
# 构建即红(不靠 npm engines 软警告)。
# #412(ADR 0012 切流收尾)单包层:ops/agent + ops/agent-v2 两包合并为 ops/ 单包,
# 一份 package.json/lock/node_modules(pipeline-core=共享管线引擎+legacy 宿主,
# agent-v2=Pi Durable 宿主);旧双依赖层(opsagent/opsagent-v2 双 node_modules 拷贝)退役。
FROM node:22-bookworm-slim AS opsagent
WORKDIR /opsagent
ARG NPM_REGISTRY=""
COPY ops/package.json ops/package-lock.json ./
RUN node -e 'const [maj,min]=process.versions.node.split(".").map(Number);if(maj!==22||min<19){console.error("node >=22.19 required (ops/engines), got "+process.versions.node);process.exit(1)}' \
    && npm ci ${NPM_REGISTRY:+--registry $NPM_REGISTRY}

FROM python:3.12-slim
# IP_RADAR_EVAL_DIR(#453):评估报告根定到数据卷(缺省会落在容器自身的
# /app/backend/data/eval,重建即丢)—— 页面上手动跑的评估落卷上 dev/,
# 读侧 _eval_reader 同根并看 monthly/dev,月轮推送面(月轮脚本)也写卷上
# eval/monthly/。_paths.eval_dir 缺省字面量只兜 checkout,不承担生产语义。
ENV PYTHONUNBUFFERED=1 IP_RADAR_DATA_DIR=/app/data IP_RADAR_EVAL_DIR=/app/data/eval
WORKDIR /app
ARG PIP_INDEX_URL=""
# L2 self-update toolchain + F4: docker CLI 不在 Debian 源,加官方源(python:3.12-slim = trixie)
# P5: ripgrep = 判例检索词法面(lib.sh inject_precedents / backend _ops_read rg 检索)
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates curl ripgrep \
    && install -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian trixie stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*
# PR #177 工具通道修复:gh CLI(gh_search 通道;判例 docs/ops/precedents/
# 2026-10-24-discover-dual-channel-dead = 容器无 gh 双通道全灭的正身)。官方 tar.gz
# pin 版本而非 apt(选型理由:gh 不在 Debian 源,cli.github.com apt 源版本随上游浮动;
# 镜像面依赖钉版本——node>=22.19 断言同旨,升版本 = 显式改 ARG 逃不过评审)。amd64
# 钉死(生产小机 x86_64;迁 arm 需扩 --build-arg,防无声错架构)。本地/其他运行环境
# 无 gh = 运行时 channel_missing 分类信封可诊断降级(tools.mjs classifyChannelError),不硬依赖。
# 独立最小层(与 apt 层分缓存);构建时断言版本号防上游 tar 偷换。
ARG GH_VERSION=2.103.2
RUN curl -fsSL --max-time 120 -o /tmp/gh.tgz \
      https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_amd64.tar.gz \
    && tar -xzf /tmp/gh.tgz -C /tmp gh_${GH_VERSION}_linux_amd64/bin/gh \
    && install -m 0755 /tmp/gh_${GH_VERSION}_linux_amd64/bin/gh /usr/local/bin/gh \
    && rm -rf /tmp/gh.tgz /tmp/gh_${GH_VERSION}_linux_amd64 \
    && gh --version | head -1 | grep -q "gh version ${GH_VERSION}"
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt ${PIP_INDEX_URL:+-i $PIP_INDEX_URL}
COPY backend/ ./backend/
# P5:运营 agent 源树 + 生产依赖(pi-agent-core/pi-ai/typebox/undici + pi-web-access
# 0.44.0 树,#412 单包 lockfile 实测 309 包全 JS 无 native 二进制;包数变更大,改锁文件时同步本注
# ——审后修 P2 2026-10-24:旧注「89 包」已陈旧)。node_modules 不进构建上下文
# (.dockerignore 排除,本地也无需装),
# 由 opsagent 层 npm ci 注入;node 二进制经 PATH 供 P2 桥 spawn(node --max-old-
# space-size=256 ops/pipeline-core/pipeline.mjs|agent.mjs 按轮型选入口,#412;cwd=/app)。
COPY ops/ ./ops/
COPY --from=opsagent /opsagent/node_modules ./ops/node_modules
COPY --from=opsagent /usr/local/bin/node /usr/local/bin/node
COPY .gitignore ./.gitignore
# 版本自描述:构建上下文含 .git(.dockerignore 已放行)
COPY .git /app/.git
# 版本串不带 --dirty:构建树天生不完整(frontend/ 源码在最后阶段不拷入镜像、backend/tests/
# 被 .dockerignore 挡在构建上下文外,其余零散受管文件同理;2026-11-25 线上实测 /app 缺
# 495 个受管文件),git 把缺失文件看成被删,脏检查恒为真——线上曾恒显 -dirty 而服务器
# 检出的受管文件零改动。生产部署恒为干净检出。版本串在下方 .git 被重建成单提交仓
# 之前固化,不受那段影响。
RUN git describe --tags --always > /app/BUILD_VERSION 2>/dev/null || echo dev > /app/BUILD_VERSION
# P5 沙箱锚:.git 重建为镜像运行时快照仓。ops/pipeline-core/lib.sh sandbox_assert 每轮跑
# `git status --porcelain -- backend/ frontend/`(红线:agent 零改数据面),而原样
# COPY 进来的 .git 在镜像内必然两条路皆败:①CI 全量 checkout 的 .git 索引含
# frontend/ 源码与 backend/tests,它们不进镜像 → status 报删除;②worktree 本地构建
# 时 .git 是断链指针文件(gitdir: 指向仓外主仓)→ git status 直接失败。BUILD_VERSION
# 已固化构建出处,.git 的唯一存活理由是 sandbox 比对基准——换成与镜像文件树对齐的
# 单提交仓(backend/ 入索引;frontend/dist、__pycache__ 等经根 .gitignore 静音,
# 故 COPY .gitignore):运行时 agent 改 backend/ 即脏即败、未改即净即过,红线语义
# 不变,出处走 BUILD_VERSION。lib.sh 冻结面零触碰(ROOT 落位推导,不可环境覆盖)。
RUN rm -rf /app/.git && git init -q -b main \
    && git -c user.email=ipradar-image@localhost -c user.name=ipradar-image add backend/ \
    && git -c user.email=ipradar-image@localhost -c user.name=ipradar-image \
       commit -qm "runtime snapshot: sandbox_assert baseline (P5)" \
    && test -z "$(git status --porcelain -- backend/ frontend/)"
COPY --from=frontend /build/dist ./frontend/dist
COPY docker/entrypoint.sh /entrypoint.sh
# P5 验收锚:node(桥 spawn 面)/rg(检索面)在此层真跑一次,缺库缺二进制构建即红;
# PR #177 增 gh(gh_search 面;同旨)。v2 依赖冒烟:registry.mjs 全链(单包
# node:sqlite 内建面,node_modules 单根 ops/)在此层真载入
# 一次——加载期即验依赖树完整与 node 版本面,registry 只定义不实例化,零 DB/网络副作用。
RUN chmod +x /entrypoint.sh \
    && node --version \
    && rg --version | head -1 \
    && gh --version | head -1 \
    && node -e 'import("./ops/agent-v2/registry.mjs").then(()=>console.log("v2 registry import ok"))'
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
