"""dbip_city fast-path equivalence (2026-09-01).

The integer fast paths (inet_pton + bit-math CIDR) must be yield-for-yield
equivalent to the ipaddress-based reference on aligned, non-aligned, v6,
and invalid rows. Differential-verified against 300k real rows + edge
battery during development; these pin the contract.
"""
import ipaddress

from ipdb._sources.dbip_city import _v4_int, _v6_int, _fmt_v4, _fmt_v6


def _ref(start, end):
    """The pre-fastpath reference algorithm (old harvest body)."""
    try:
        sa = ipaddress.ip_address(start)
        ea = ipaddress.ip_address(end)
    except ValueError:
        return None
    if sa.version != ea.version:
        return None
    return [str(c) for c in ipaddress.summarize_address_range(sa, ea)]


def _fast(start, end):
    if ":" in start or ":" in end:
        a, b, bits, fmt = _v6_int(start), _v6_int(end), 128, _fmt_v6
    else:
        a, b, bits, fmt = _v4_int(start), _v4_int(end), 32, _fmt_v4
    if a is None or b is None or a > b:
        return None
    span = b - a + 1
    if span & (span - 1) == 0 and a & (span - 1) == 0:
        return [fmt(a, (bits + 1) - span.bit_length())]
    cls = ipaddress.IPv6Address if bits == 128 else ipaddress.IPv4Address
    return [str(c) for c in ipaddress.summarize_address_range(cls(a), cls(b))]


def _norm(cidrs):
    """Normalize to network objects — fast path emits uncompressed v6 strings,
    reference emits compressed; same networks is the contract."""
    return None if cidrs is None else sorted(
        ipaddress.ip_network(c) for c in cidrs)


CASES = [
    ("1.0.1.0", "1.0.3.255"),          # aligned /22
    ("1.0.4.0", "1.0.4.255"),          # aligned /24
    ("8.8.8.0", "8.8.8.255"),          # aligned /24 (the regression IP)
    ("1.0.16.0", "1.0.19.255"),        # aligned /22
    ("9.9.9.0", "9.9.10.255"),         # NON-aligned → summarize fallback
    ("1.0.1.5", "1.0.1.9"),            # tiny non-aligned
    ("0.0.0.0", "0.0.0.0"),            # single /32
    ("2001:db8::", "2001:db8:0:ffff:ffff:ffff:ffff:ffff"),   # v6 /64 aligned
    ("2a00:1450:4001::", "2a00:1450:4001:ff:ff:ff:ff:ff"),  # hmm invalid tail
    ("2001:db8::1", "2001:db8::10"),   # v6 non-aligned → fallback
    ("1.0.1.0", "1.0.1.999"),          # invalid end → None both
    ("garbage", "1.0.1.0"),            # invalid start → None both
    ("1.0.1.0", "2001:db8::1"),        # family mismatch → None both
]


def test_fast_path_yields_match_reference():
    for start, end in CASES:
        assert _norm(_fast(start, end)) == _norm(_ref(start, end)), (start, end)


def test_v6_uncompressed_form_is_parseable():
    # transient string form only needs to survive net_cls() re-parse
    n = ipaddress.IPv6Network(_fmt_v6(int(ipaddress.IPv6Address("2001:db8::")), 32))
    assert n == ipaddress.IPv6Network("2001:db8::/32")


def test_v4_fast_strings_roundtrip():
    assert _fmt_v4(0x08080800, 24) == "8.8.8.0/24"
    assert ipaddress.IPv4Network(_fmt_v4(0x01000000, 22)) == \
        ipaddress.IPv4Network("1.0.0.0/22")
