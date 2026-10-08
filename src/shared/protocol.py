"""Length-prefixed JSON over a certificate-verified TLS connection."""
from __future__ import annotations

import json
import struct

MAX_FRAME = 16 * 1024 * 1024


def _read_exact(connection, size):
    chunks = bytearray()
    while len(chunks) < size:
        chunk = connection.recv(size - len(chunks))
        if not chunk:
            raise ConnectionError("Connection closed before the message was complete")
        chunks.extend(chunk)
    return bytes(chunks)


def receive(connection):
    size = struct.unpack("!I", _read_exact(connection, 4))[0]
    if size == 0 or size > MAX_FRAME:
        raise ValueError("Message size exceeds the protocol limit")
    message = json.loads(_read_exact(connection, size).decode("utf-8"))
    if not isinstance(message, dict):
        raise ValueError("Message must be an object")
    return message


def send(connection, message):
    payload = json.dumps(message, ensure_ascii=False).encode("utf-8")
    if len(payload) > MAX_FRAME:
        raise ValueError("Response is too large; request a smaller page")
    connection.sendall(struct.pack("!I", len(payload)) + payload)
