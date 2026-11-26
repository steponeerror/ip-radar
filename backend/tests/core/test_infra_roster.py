"""_infra_roster 名单单真源钉子(#466,架构评审第四轮卡 15)。

名单文本只准住一个文件:谁把名单抄第二份(旧 infra_services._DATA 形态
回流,或新源内嵌一份「公共解析器清单」),这里翻红。针地址取
132.163.97.1(NIST NTP)——名单里仅此一处提及、backend/ipdb 其余代码与
注释均不引用(2026-11-26 master 02006a69 全包 rg 核过),故命中面收窄
到「名单文本本体」。
"""
from pathlib import Path

from ipdb._infra_roster import ROSTER_CSV


def test_roster_text_lives_in_exactly_one_file():
    """名单原文在 backend/ipdb 下只命中 _infra_roster.py 一个文件。"""
    assert "132.163.97.1" in ROSTER_CSV          # 针地址确在名单里
    ipdb_root = Path(__file__).resolve().parents[2] / "ipdb"
    needle = b"132.163.97.1"                     # 字节搜,免解码歧义
    hits = {p for p in ipdb_root.rglob("*.py") if needle in p.read_bytes()}
    assert hits == {ipdb_root / "_infra_roster.py"}, hits
