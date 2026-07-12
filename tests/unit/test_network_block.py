"""Self-test for the SC-001 network-blocking fixture (T004)."""

import socket

import pytest

from tests.conftest import NetworkBlockedError


def test_non_loopback_connect_is_blocked(block_non_loopback_network):
    with pytest.raises(NetworkBlockedError):
        socket.create_connection(("8.8.8.8", 53), timeout=1)


def test_non_loopback_dns_is_blocked(block_non_loopback_network):
    with pytest.raises(NetworkBlockedError):
        socket.getaddrinfo("example.com", 80)


def test_loopback_is_permitted(block_non_loopback_network):
    # Resolving/handling loopback must NOT raise the block; a refused connection
    # (nothing listening) is fine — it proves the fixture let the attempt through.
    socket.getaddrinfo("127.0.0.1", 80)
    with pytest.raises(OSError) as exc:
        socket.create_connection(("127.0.0.1", 1), timeout=1)
    assert not isinstance(exc.value, NetworkBlockedError)


def test_block_is_removed_after_fixture():
    # Outside the fixture, DNS works normally again (restoration).
    socket.getaddrinfo("127.0.0.1", 80)
