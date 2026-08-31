from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from urllib.parse import urlsplit

AddressResolver = Callable[..., Iterable[tuple[object, ...]]]

_BLOCKED_METADATA_HOSTS = frozenset(
    {
        "instance-data",
        "metadata",
        "metadata.google.internal",
        "metadata.tencentyun.com",
    }
)
_BLOCKED_METADATA_ADDRESSES = frozenset(
    {
        ipaddress.ip_address("100.100.100.200"),
        ipaddress.ip_address("fd00:ec2::254"),
    }
)


class UnsafeProviderEndpointError(ValueError):
    """Raised when a custom provider URL targets a protected network address."""


def _is_blocked_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return (
        address in _BLOCKED_METADATA_ADDRESSES
        or address.is_link_local
        or address.is_unspecified
        or address.is_multicast
        or address.is_reserved
    )


def _validate_address(address: str) -> None:
    parsed = ipaddress.ip_address(address.partition("%")[0])
    if _is_blocked_address(parsed):
        raise UnsafeProviderEndpointError(
            "api_base targets a protected network address"
        )


def validate_provider_endpoint(
    url: str,
    *,
    resolve: bool = True,
    resolver: AddressResolver = socket.getaddrinfo,
) -> None:
    """Reject metadata, link-local, and non-routable custom provider targets.

    Loopback and RFC1918 addresses remain available for explicitly configured
    local providers such as Ollama. Hostnames are resolved immediately before
    outbound requests so a public-looking name cannot simply point at a cloud
    metadata address.
    """

    parsed = urlsplit(url)
    hostname = parsed.hostname
    if hostname is None:
        raise UnsafeProviderEndpointError("api_base hostname is missing")

    normalized_host = hostname.rstrip(".").lower()
    if normalized_host in _BLOCKED_METADATA_HOSTS:
        raise UnsafeProviderEndpointError(
            "api_base targets a protected metadata service"
        )

    try:
        literal_address = ipaddress.ip_address(normalized_host.partition("%")[0])
    except ValueError:
        literal_address = None
    if literal_address is not None:
        if _is_blocked_address(literal_address):
            raise UnsafeProviderEndpointError(
                "api_base targets a protected network address"
            )
        return

    if not resolve:
        return

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        records = resolver(
            normalized_host,
            port,
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise UnsafeProviderEndpointError(
            "api_base hostname could not be resolved"
        ) from exc

    addresses = {
        str(record[4][0])
        for record in records
        if len(record) > 4 and isinstance(record[4], tuple) and record[4]
    }
    if not addresses:
        raise UnsafeProviderEndpointError(
            "api_base hostname did not resolve to an IP address"
        )
    for address in addresses:
        _validate_address(address)
