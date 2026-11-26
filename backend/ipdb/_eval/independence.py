# backend/ipdb/_eval/independence.py
"""Advisory overlap-suspicion check for the eval harness.

Effective vote counting now imports production semantics directly
(ipdb._logodds.dedup_lineage — see metrics.cg), replacing the retired static
INDEPENDENCE_GROUPS counter. This module keeps only the advisory alarm:
source pairs DECLARED independent whose measured (ip,ctype) overlap is high,
fed by the all-source pairwise OC table (pairwise.py, D4/B4).
"""
from . import config
from .events import same_republish_chain


def oc_suspicion_pairs(pair_oc) -> list[tuple[tuple[str, str], float]]:
    """Declared-independent source pairs whose overlap exceeds the suspicion
    threshold. Keys may be tuples or frozensets (pairwise.py emits frozensets);
    returned pairs are normalized to sorted tuples. Pairs inside one declared
    LINEAGE_CLUSTERS cluster (firehol x ipsum) share upstream by declaration
    and are NOT suspicious. Same for pairs on one republish chain (same
    transitive closure over the declared republishes links, #464 card-2
    first half): the echo is expected, not a discovery. Advisory: high OC can
    also mean two independent feeds tracking the same popular botnet, so we
    FLAG rather than auto-downgrade."""
    out = []
    for pair, oc_val in pair_oc.items():
        a, b = sorted(pair)
        if config.LINEAGE_CLUSTERS.get(a, a) == config.LINEAGE_CLUSTERS.get(b, b):
            continue
        if same_republish_chain(a, b):
            # 同一转载链(#464):声明转载关系本身解释了高 OC,不算发现
            continue
        if oc_val > config.OC_SUSPICION:
            out.append(((a, b), oc_val))
    return out
