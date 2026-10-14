"""Dedicated TLS/TCP service, independent of SSH and HTTP."""
from __future__ import annotations

import argparse
import hmac
import signal
import socketserver
import ssl
import sys
import threading

from common.config import load_config
from server.service import ManagementService
from shared.protocol import receive, send
from storage.encrypted import read_secret


class TLSServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 32

    def __init__(self, address, service, context, token):
        self.service, self.context, self.token = service, context, token
        self.slots = threading.BoundedSemaphore(32)
        super().__init__(address, Handler)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


def readable_job(job):
    return job.get("kind") in {"connections", "monitoring", "ci_inventory"} or (job.get("kind") == "accounts" and job.get("options", {}).get("action") == "list")


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(20)
        try:
            with self.server.context.wrap_socket(self.request, server_side=True) as connection:
                request = receive(connection)
                supplied = request.get("token", "")
                from server.auth import authenticate, role_for, authorize
                token_ok = isinstance(supplied, str) and hmac.compare_digest(supplied.encode(), self.server.token)
                try:
                    with self.server.service.lock:
                        login_ok = not token_ok and authenticate(self.server.service.data, request.get("username", ""), request.get("password", ""))
                except Exception:
                    login_ok = False
                if not token_ok and not login_ok:
                    send(connection, {"ok": False, "error": "Authentication failed"})
                    return
                try:
                    with self.server.service.lock:
                        role = "admin" if token_ok else role_for(self.server.service.data, request.get("username", ""))
                        authorize(role, request["method"], request.get("params", {}))
                        if role != "admin" and request["method"] in {"job.get", "job.result"}:
                            job = self.server.service.jobs.get(request.get("params", {}).get("id"), {})
                            if not readable_job(job): raise ValueError("Permission denied: this job is restricted")
                    if request["method"] == "session.info":
                        result = {"username": request.get("username", ""), "role": role}
                    else:
                        result = self.server.service.dispatch(request["method"], request.get("params", {}))
                    if role != "admin" and request["method"] == "job.list":
                        result = [row for row in result if readable_job(row)]
                    response = {"ok": True, "result": result}
                except (ValueError, KeyError, TypeError, RuntimeError) as exc:
                    response = {"ok": False, "error": str(exc)}
                except Exception:
                    response = {"ok": False, "error": "Server operation failed; check server configuration and storage"}
                send(connection, response)
        except (OSError, ValueError):
            pass


def main():
    parser = argparse.ArgumentParser(description="SM Automation Linux main server")
    parser.add_argument("--config")
    args = parser.parse_args()
    if not sys.platform.startswith("linux"):
        parser.error("The main server must run on Linux. Use desktop/main.py on Windows.")
    config = load_config(args.config)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    read_secret(config.tls_key)
    context.load_cert_chain(config.tls_cert, config.tls_key)
    token = read_secret(config.token_file)
    if len(token) < 32:
        raise ValueError("API token must contain at least 32 bytes")
    service = ManagementService(config)
    with TLSServer((config.listen_host, config.listen_port), service, context, token) as server:
        def stop(*_):
            threading.Thread(target=server.shutdown, daemon=True).start()
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        print(f"SM Automation TLS service listening on {config.listen_host}:{config.listen_port}", flush=True)
        try:
            server.serve_forever()
        finally:
            service.close()


if __name__ == "__main__":
    main()
