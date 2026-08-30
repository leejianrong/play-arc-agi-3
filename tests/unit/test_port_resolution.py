import socket

from main import resolve_port

HOST = "127.0.0.1"


def test_resolve_port_returns_preferred_port_when_free():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((HOST, 0))
        free_port = probe.getsockname()[1]

    assert resolve_port(free_port, HOST) == free_port


def test_resolve_port_falls_back_when_preferred_port_is_taken():
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    holder.bind((HOST, 0))
    holder.listen(1)
    occupied_port = holder.getsockname()[1]

    try:
        resolved = resolve_port(occupied_port, HOST)
        assert resolved != occupied_port
        assert 0 < resolved < 65536
    finally:
        holder.close()
