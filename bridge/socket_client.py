"""
Python socket client (Lab 2): sends one line per message to the Java server.

Lab 2 pattern: socket.create_connection(...) + sendall(text + "\\n").
Additions for a kiosk: a queue + background thread (Lab 2 "Threads"), so callers
never block, and automatic reconnect, so the bridge can start before the Java app.
"""
import queue
import socket
import threading
import time


class SocketClient(threading.Thread):
    def __init__(self, host="127.0.0.1", port=5000, retry_seconds=2.0):
        super().__init__(daemon=True)
        self.host, self.port = host, port
        self.retry_seconds = retry_seconds
        self.outbox = queue.Queue()       # every message from every source goes through here
        self.running = True

    def send(self, line):
        """Thread-safe. Called by the marker thread, the gesture source and the console."""
        self.outbox.put(line)

    def stop(self):
        self.running = False

    def run(self):
        conn = None
        pending = None                    # message that failed to send, retried after reconnect
        while self.running:
            if conn is None:
                conn = self._connect()
                if conn is None:
                    continue
            if pending is None:
                try:
                    pending = self.outbox.get(timeout=0.5)
                except queue.Empty:
                    continue
            try:
                conn.sendall((pending + "\n").encode("utf-8"))
                print(f"[SOCKET] sent: {pending}")
                pending = None
            except OSError:
                print("[SOCKET] Java app disconnected, reconnecting...")
                conn.close()
                conn = None
        if conn:
            conn.close()

    def _connect(self):
        try:
            conn = socket.create_connection((self.host, self.port), timeout=3)
            conn.settimeout(None)
            print(f"[SOCKET] connected to Java server {self.host}:{self.port}")
            return conn
        except OSError:
            print(f"[SOCKET] Java server not reachable on {self.host}:{self.port}, retrying...")
            time.sleep(self.retry_seconds)
            return None
