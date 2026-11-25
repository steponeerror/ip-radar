"""路径类 IP_RADAR_* 环境变量解析 —— 全库唯一真源(#406)。

折并前现状:IP_RADAR_DATA_DIR 在 ≥5 处独立解析、3 种 fallback
(_app_dir/"data"、/app/data、<repo>/backend/data);_update 的
/app/data 字面量在 dev 检出上把 update_state.json 落到不可写路径,
本模块统一消除。

约定(fallback convention):
- env 恒优先;未设 → 回落 <backend>/data(本文件 _APP_DIR/"data")。
- 容器由 Dockerfile `ENV IP_RADAR_DATA_DIR=/app/data` 恒定有值,
  fallback 仅 checkout(开发/CI)跑时生效,不承担生产语义。
- 全部访问器惰性(调用时现算,不设导入期路径常量):测试 monkeypatch
  env 免 reload,进程内多次调用始终见最新值(_ops_store.ops_root 先例)。
- 空串语义沿用折并前各变量原样:真值型(eval_dir/honyport/heartbeat/
  static_dir/env_path_or_state_sibling)空串视同未设;键缺省型(data_dir/
  source_state_path/update_state_file/build_version_file)沿用
  os.environ.get(var, default) 键缺失才回落的字面语义。
- backend/.env(dotenv)加载收口于此:存在才生效、不覆盖已设值
  (load_dotenv 默认),与折并前 _registry/_ops_store 两处各自加载
  的语义相同。

不回落 data_dir 的两个例外:
- eval_dir 缺省钉 <backend>/data/eval(checkout 树),不随
  IP_RADAR_DATA_DIR 派生 —— 它有自己的 env(IP_RADAR_EVAL_DIR)与缺省
  字面量。#453 起写侧 ipdb._eval.__main__.report_dir 同取本函数
(读写单真源;旧注释里挂靠 ADR 0021 影子期的「两处缺省恰同值
  才同址」冻结理由,由 #453 裁决收口);容器里读写同根不靠缺省巧合,
  由镜像显式给值(Dockerfile ENV IP_RADAR_EVAL_DIR=/app/data/eval)保证,
  checkout 上缺省读写天然同根。
- build_version_file 缺省字面量 "/app/BUILD_VERSION" 原样保留
  (容器烤进镜像;checkout 恒 miss → 回落 IP_RADAR_VERSION/"dev")。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

_APP_DIR = Path(__file__).resolve().parent.parent   # <repo>/backend
# 行为声明(终审 P2-3):旧 _registry._app_dir 无 .resolve(),此处加了——与
# _ops_store.py 同一先例对齐;符号链接检出下默认 data_dir 的字符串可能
# 与旧实现不同(真路径),属有意变更,非「零变化」折并的例外项。

# backend/.env 加载(见模块头):折并前 _registry.py 与 _ops_store.py
# 两处重复,收口至此一处;两模块经 import 本模块获得同一加载时机。
load_dotenv(_APP_DIR / ".env")


def data_dir() -> Path:
    """$IP_RADAR_DATA_DIR;未设 → <backend>/data。"""
    return Path(os.environ.get("IP_RADAR_DATA_DIR", str(_APP_DIR / "data")))


def source_state_path() -> Path:
    """$SOURCE_STATE_PATH;未设 → <data_dir>/source_state.json。"""
    return Path(os.environ.get("SOURCE_STATE_PATH",
                               str(data_dir() / "source_state.json")))


def env_path_or_state_sibling(env_var: str, filename: str) -> Path:
    """env 覆写的 db 路径解析(#258 折并自 _alerts/_auth 同形五连;自
    _registry 搬入 #406):env_var 非空 → Path(env 值);否则落
    source_state.json 同目录下 filename(auth.db/alerts.db 同级)。
    空串 env 视同未设(真值语义,折并前后零变化)。"""
    env = os.environ.get(env_var)
    if env:
        return Path(env)
    return source_state_path().parent / filename


def update_state_path() -> Path:
    """$IP_RADAR_STATE_FILE;未设 → <data_dir>/update_state.json。

    折并前 _update 落 /app/data/update_state.json(容器字面量,dev
    检出不可写)= 全库唯一坏 fallback,#406 顺带修活归一到 data_dir。"""
    return Path(os.environ.get("IP_RADAR_STATE_FILE",
                               str(data_dir() / "update_state.json")))


def repo_dir() -> str:
    """$IP_RADAR_REPO_DIR(L2 自更新流);未设 → ""(M1:未配置不得
    退化到 CWD)。"""
    return os.environ.get("IP_RADAR_REPO_DIR", "")


def compose_file() -> str:
    """$IP_RADAR_COMPOSE_FILE;未设 → <repo_dir>/docker-compose.yml。"""
    return os.environ.get("IP_RADAR_COMPOSE_FILE",
                          os.path.join(repo_dir(), "docker-compose.yml"))


def eval_dir() -> Path:
    """$IP_RADAR_EVAL_DIR;未设 → <backend>/data/eval(不随 data_dir
    派生,理由见模块头「不回落 data_dir 的例外」)。"""
    return Path(os.environ.get("IP_RADAR_EVAL_DIR")
                or (_APP_DIR / "data" / "eval"))


def honyport_aggregate_dir() -> Path:
    """$IP_RADAR_HONYPORT_AGGREGATE_DIR;未设 → <data_dir>/honyport-aggregate
    (从 data_dir 派生;折并前 /app/data/honyport-aggregate 字面量清除,
    容器 DATA_DIR=/app/data 下取值不变,开发机回落 checkout 数据树)。"""
    return Path(os.environ.get("IP_RADAR_HONYPORT_AGGREGATE_DIR")
                or (data_dir() / "honyport-aggregate"))


def eval_heartbeat_path() -> Path | None:
    """$IP_RADAR_EVAL_HEARTBEAT(S6 月轮心跳);未设/空 → None = 不检查
    (新部署防误报)。"""
    env = os.environ.get("IP_RADAR_EVAL_HEARTBEAT", "")
    return Path(env) if env else None


def static_dir() -> Path | None:
    """$IP_RADAR_STATIC_DIR(SPA 挂载覆写);未设/空 → None(沿用
    frontend/dist 缺省)。main.py 仍在导入期取值,时机不变(#406 只换
    解析来源)。"""
    env = os.environ.get("IP_RADAR_STATIC_DIR", "")
    return Path(env) if env else None


def build_version_file() -> Path:
    """$IP_RADAR_BUILD_VERSION_FILE;缺省字面量 "/app/BUILD_VERSION"
    原样保留(容器烤进镜像,checkout 恒 miss)。"""
    return Path(os.environ.get("IP_RADAR_BUILD_VERSION_FILE",
                               "/app/BUILD_VERSION"))
