"""Desktop requests to the Linux server over a dedicated TLS port."""
from __future__ import annotations

import socket
import ssl
import threading
from dataclasses import dataclass

from shared.protocol import receive, send


@dataclass(frozen=True)
class ConnectionSettings:
    host: str
    port: int
    ca_file: str
    token: str
    username: str = ""
    password: str = ""


class ServerClient:
    def __init__(self, settings: ConnectionSettings):
        self.settings = settings
        self._context = None
        self._context_lock = threading.Lock()

    def tls_context(self):
        with self._context_lock:
            if self._context is None:
                self._context = self.build_tls_context()
            return self._context

    def build_tls_context(self):
        settings = self.settings
        context = ssl.create_default_context(cafile=settings.ca_file or None)
        if not settings.ca_file:
            # Automatically trust this local WSL lab through the local OS boundary.
            import subprocess
            try:
                addresses = subprocess.check_output(["wsl", "-d", "Ubuntu", "-u", "root", "--", "hostname", "-I"], text=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).split()
                if settings.host in {*addresses, "localhost", "127.0.0.1", "::1"}:
                    ca = subprocess.check_output(["wsl", "-d", "Ubuntu", "-u", "root", "--", "cat", "/root/.config/sm-automation/ca.crt"], timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).decode()
                    context.load_verify_locations(cadata=ca)
            except (OSError, subprocess.SubprocessError):
                pass
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        return context

    def call(self, method: str, **params):
        settings = self.settings
        context = self.tls_context()
        with socket.create_connection((settings.host, settings.port), timeout=15) as sock:
            with context.wrap_socket(sock, server_hostname=settings.host) as connection:
                connection.settimeout(30)
                send(connection, {"method": method, "params": params, "token": settings.token, "username": settings.username, "password": settings.password})
                response = receive(connection)
        if not response.get("ok"):
            raise RuntimeError(response.get("error", "Server rejected the request"))
        return response["result"]

    def results(self, job_id, hosts=None):
        rows, offset = [], 0
        while True:
            params={"id":job_id,"offset":offset,"page_size":50}
            if hosts is not None:params["hosts"]=hosts
            page = self.call("job.result", **params)
            rows.extend(page["items"])
            offset += len(page["items"])
            if offset >= page["total"] or not page["items"]:
                return rows
