"""FR-17: a name that resolves to a local address is refused, whatever it looks like."""

import socket
from typing import Any

import pytest

from cvforge.web.fetch import FetchError, check_url, resolve_host


def _addresses(*addresses: str) -> Any:
    def getaddrinfo(host: str, port: object, **kwargs: Any) -> list[Any]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, 0)) for a in addresses]

    return getaddrinfo


@pytest.mark.parametrize("numeric", ["http://2130706433/", "http://0x7f.1/", "http://127.1/"])
def test_numeric_spellings_of_loopback_are_refused_by_the_real_resolver(numeric: str) -> None:
    with pytest.raises(FetchError, match="local address"):
        check_url(numeric)


def test_a_name_resolving_to_a_private_address_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _addresses("10.0.0.7"))
    with pytest.raises(FetchError, match="resolves to a local address"):
        check_url("https://intranet.example.test/job")


def test_one_private_address_among_public_ones_is_enough_to_refuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _addresses("93.184.216.34", "169.254.169.254"))
    with pytest.raises(FetchError, match="resolves to a local address"):
        check_url("https://mixed.example.test/job")


def test_a_scoped_ipv6_address_is_judged_without_its_zone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _addresses("fe80::1%eth0"))
    with pytest.raises(FetchError, match="resolves to a local address"):
        check_url("https://v6.example.test/job")


def test_a_public_resolution_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _addresses("93.184.216.34"))
    check_url("https://jobs.example.test/job")


def test_allow_local_skips_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("resolved a host although local targets are allowed")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    check_url("http://10.0.0.7/job", allow_local=True)


def test_an_unresolvable_name_is_a_handled_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise socket.gaierror("no such host")

    monkeypatch.setattr(socket, "getaddrinfo", fail)
    with pytest.raises(FetchError, match="could not resolve"):
        resolve_host("nowhere.example.test")
