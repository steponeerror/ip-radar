"""Lazy CIDR / bare-IP expansion for the stream query path.

The expansion is lazy: ``total`` is computed by summing ``num_addresses``
(O(num_lines), never materialized), and iteration yields ``(idx, ip_str)``
pairs on demand. This keeps backend memory constant regardless of how large
a CIDR the user queries — a /14 (262,144 addresses) costs the same as a /24.

CIDR iteration uses ``for ip in network:`` (ALL num_addresses, including the
network and broadcast addresses), NOT ``.hosts()`` which silently drops them.
"""
import ipaddress
from typing import Iterator


class LazyExpansion:
    """Lazy view over expanded IP inputs.

    Attributes:
        total: total address count (sum of CIDR num_addresses + bare IPs).
        invalid: count of malformed lines (neither valid IPv4 nor IPv6).
        ipv6: 恒 0；保留为 SSE done 事件 `ipv6_unsupported` 字段的兼容来源
            （Q4，spec §4.1）——v6 行现已进展开计划。
    """

    __slots__ = ("total", "invalid", "ipv6", "_plan")

    def __init__(self, lines):
        self.total = 0
        self.invalid = 0
        self.ipv6 = 0
        self._plan = []  # list of ("ip", str) | ("cidr", IPv4Network | IPv6Network)
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            if ":" in line:  # IPv6 hint — parse v6 ip / cidr
                try:
                    if "/" in line:
                        net = ipaddress.IPv6Network(line, strict=False)
                        self.total += net.num_addresses
                        self._plan.append(("cidr", net))
                    else:
                        addr = ipaddress.IPv6Address(line)
                        self.total += 1
                        self._plan.append(("ip", str(addr)))
                except (ipaddress.AddressValueError,
                        ipaddress.NetmaskValueError, ValueError):
                    self.invalid += 1
                continue
            try:
                if "/" in line:
                    net = ipaddress.IPv4Network(line, strict=False)
                    self.total += net.num_addresses
                    self._plan.append(("cidr", net))
                else:
                    addr = ipaddress.IPv4Address(line)
                    self.total += 1
                    self._plan.append(("ip", str(addr)))
            except (ipaddress.AddressValueError,
                    ipaddress.NetmaskValueError, ValueError):
                self.invalid += 1

    def __iter__(self) -> Iterator[tuple[int, str]]:
        idx = 0
        for kind, val in self._plan:
            if kind == "ip":
                yield idx, val
                idx += 1
            else:  # cidr — iterate ALL addresses incl network + broadcast
                for ip in val:
                    yield idx, str(ip)
                    idx += 1


def expand_inputs(lines: list[str]) -> LazyExpansion:
    """Expand a list of raw input lines into a lazy IP stream."""
    return LazyExpansion(lines)
