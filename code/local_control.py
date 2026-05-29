import socket
import threading
from typing import Callable, Optional


class LocalControlServer:
    """Tiny localhost TCP command server for status/stop control."""

    def __init__(
        self,
        name: str,
        port: int,
        on_stop: Optional[Callable[[], str]] = None,
        on_status: Optional[Callable[[], str]] = None,
        on_start: Optional[Callable[[], str]] = None,
        logger: Optional[Callable[[str], None]] = None,
    ):
        self.name = name
        self.port = int(port or 0)
        self.on_stop = on_stop
        self.on_status = on_status
        self.on_start = on_start
        self.logger = logger or (lambda _msg: None)
        self._thread = None
        self._stop_event = threading.Event()
        self._server_socket = None

    def start(self):
        if self.port <= 0:
            return False
        if self._thread is not None:
            return True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop_event.set()
        server = self._server_socket
        if server is not None:
            try:
                server.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    @staticmethod
    def send_command(port: int, command: str, timeout: float = 0.1) -> Optional[str]:
        """Send a command to a control server and return the response."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect(("127.0.0.1", port))
            sock.sendall(command.encode("utf-8"))
            data = sock.recv(4096)
            sock.close()
            return data.decode("utf-8", errors="ignore").strip()
        except (OSError, ConnectionError, socket.timeout):
            return None

    @staticmethod
    def is_peer_listening(port: int) -> bool:
        """Check if a control server is listening on the given port."""
        resp = LocalControlServer.send_command(port, "ping")
        return resp is not None and resp.startswith("pong")

    def _handle_command(self, command: str) -> str:
        cmd = (command or "").strip().lower()
        if cmd in ("", "help"):
            return "commands: ping, status, stop, start"
        if cmd == "ping":
            return f"pong {self.name}"
        if cmd == "status":
            if self.on_status is None:
                return "ok"
            try:
                return str(self.on_status())
            except Exception as exc:
                return f"status_error: {exc}"
        if cmd == "stop":
            if self.on_stop is None:
                return "stop not supported"
            try:
                return str(self.on_stop())
            except Exception as exc:
                return f"stop_error: {exc}"
        if cmd == "start":
            if self.on_start is None:
                return "start not supported"
            try:
                return str(self.on_start())
            except Exception as exc:
                return f"start_error: {exc}"
        return f"unknown command: {command}"

    def _run(self):
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket = server
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("127.0.0.1", self.port))
            server.listen(5)
            server.settimeout(0.5)
            self.logger(
                f"Local control server for {self.name} listening on 127.0.0.1:{self.port}"
            )
        except OSError as exc:
            self.logger(
                f"Local control server for {self.name} failed on port {self.port}: {exc}"
            )
            return

        while not self._stop_event.is_set():
            try:
                conn, _addr = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            with conn:
                conn.settimeout(1.0)
                try:
                    payload = conn.recv(1024)
                except OSError:
                    continue
                command = payload.decode("utf-8", errors="ignore").strip()
                response = self._handle_command(command)
                try:
                    conn.sendall((response + "\n").encode("utf-8"))
                except OSError:
                    pass

        try:
            server.close()
        except OSError:
            pass
