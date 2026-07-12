"""Shared test fixtures for feature 002 (local AI assistance).

`block_non_loopback_network` is the mechanical proof behind SC-001/FR-002: while
active, any attempt to open a socket to a non-loopback address raises
`NetworkBlockedError`. Loopback (127.0.0.0/8, ::1, localhost) and AF_UNIX are
permitted, because a local model runtime (Ollama) legitimately serves over
loopback HTTP — the guarantee is "no data leaves the machine", not "no sockets".
"""

from __future__ import annotations

import contextlib
import ipaddress
import socket

import pytest


class NetworkBlockedError(AssertionError):
    """Raised when code under test attempts a non-loopback network connection."""


def _is_loopback_host(host) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    if host in ("localhost", "localhost.localdomain", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False  # a real hostname needing DNS — treat as non-local


@contextlib.contextmanager
def block_non_loopback():
    """Install the block for the duration of the `with` body."""
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_create_connection = socket.create_connection
    real_getaddrinfo = socket.getaddrinfo

    def _check_address(address) -> None:
        # AF_UNIX addresses are str/bytes paths, not (host, port) tuples.
        if not isinstance(address, tuple):
            return
        host = address[0]
        if not _is_loopback_host(host):
            raise NetworkBlockedError(
                f"non-loopback network access blocked in local mode: {host!r}"
            )

    def guarded_connect(self, address):
        _check_address(address)
        return real_connect(self, address)

    def guarded_connect_ex(self, address):
        _check_address(address)
        return real_connect_ex(self, address)

    def guarded_create_connection(address, *args, **kwargs):
        _check_address(address)
        return real_create_connection(address, *args, **kwargs)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if not _is_loopback_host(host):
            raise NetworkBlockedError(
                f"non-loopback DNS resolution blocked in local mode: {host!r}"
            )
        return real_getaddrinfo(host, *args, **kwargs)

    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    socket.create_connection = guarded_create_connection
    socket.getaddrinfo = guarded_getaddrinfo
    try:
        yield
    finally:
        socket.socket.connect = real_connect
        socket.socket.connect_ex = real_connect_ex
        socket.create_connection = real_create_connection
        socket.getaddrinfo = real_getaddrinfo


@pytest.fixture
def block_non_loopback_network():
    """Fixture form of `block_non_loopback` — request it to prove offline behaviour."""
    with block_non_loopback():
        yield
