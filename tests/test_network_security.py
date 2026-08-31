import socket

import pytest

from backend.network_security import (
    UnsafeProviderEndpointError,
    validate_provider_endpoint,
)


def resolver_for(*addresses: str):
    def resolve(_host: str, port: int, **_kwargs: object):
        return [
            (
                socket.AF_INET6 if ":" in address else socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                (address, port),
            )
            for address in addresses
        ]

    return resolve


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data",
        "http://169.254.170.2/v2/credentials",
        "http://100.100.100.200/latest/meta-data",
        "http://[fe80::1]/v1",
        "http://[fd00:ec2::254]/latest",
        "http://metadata.google.internal/computeMetadata/v1",
    ],
)
def test_provider_endpoint_rejects_metadata_and_link_local_targets(
    url: str,
) -> None:
    with pytest.raises(UnsafeProviderEndpointError):
        validate_provider_endpoint(url, resolve=False)


def test_provider_endpoint_rejects_hostname_resolving_to_link_local() -> None:
    with pytest.raises(UnsafeProviderEndpointError):
        validate_provider_endpoint(
            "https://provider.example/v1",
            resolver=resolver_for("203.0.113.10", "169.254.169.254"),
        )


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.20.30.40", "203.0.113.10"],
)
def test_provider_endpoint_preserves_local_and_public_providers(
    address: str,
) -> None:
    validate_provider_endpoint(
        "http://provider.example:11434/v1",
        resolver=resolver_for(address),
    )
