"""Serialize official GPU inference while independent CPU trials can overlap.

Only local Unix-socket clients are accepted. Sequence names are isolated per
connection; no estimate or tracked state can leak from one trial into another.
"""

import argparse
import json
import os
from pathlib import Path
import signal
import socketserver
import subprocess
import threading

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "MA6216_REPLY "


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--socket", required=True, type=Path)
    p.add_argument("--python", required=True, type=Path)
    p.add_argument("--repository", type=Path, default=ROOT / "third_party/FoundationPose")
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    if args.socket.exists():
        raise FileExistsError(args.socket)
    log = (args.output / "worker.log").open("w")
    process = subprocess.Popen(
        [
            str(args.python),
            "-u",
            str(ROOT / "scripts/serve_model_free_pose.py"),
            "--repository",
            str(args.repository),
            "--debug-dir",
            str(args.output / "debug"),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=log,
        text=True,
        bufsize=1,
    )
    lock = threading.Lock()
    counter = 0
    connection = 0

    def read_reply():
        for line in process.stdout:
            if line.startswith(PREFIX):
                return json.loads(line[len(PREFIX) :])
            log.write(line)
        raise RuntimeError("Shared GPU worker exited; inspect worker.log")

    if not read_reply().get("ready"):
        raise RuntimeError("GPU worker startup failed")

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            nonlocal counter, connection
            with lock:
                connection += 1
                client = connection
            self.wfile.write((PREFIX + '{"ready":true}\n').encode())
            for line in self.rfile:
                request = json.loads(line)
                if request.get("operation") == "shutdown":
                    break
                original_id = request["id"]
                with lock:
                    counter += 1
                    request["id"] = counter
                    request["sequence"] = f"client_{client}/" + request.get("sequence", "default")
                    process.stdin.write(json.dumps(request) + "\n")
                    process.stdin.flush()
                    result = read_reply()
                result["id"] = original_id
                result["shared_gpu_worker"] = True
                self.wfile.write((PREFIX + json.dumps(result) + "\n").encode())

    class Server(socketserver.ThreadingUnixStreamServer):
        daemon_threads = True

    server = Server(str(args.socket), Handler)
    os.chmod(args.socket, 0o600)

    def stop(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        print(json.dumps({"ready": True, "socket": str(args.socket)}), flush=True)
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        args.socket.unlink(missing_ok=True)
        if process.poll() is None:
            process.stdin.write('{"operation":"shutdown"}\n')
            process.stdin.flush()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=10)
        log.close()


if __name__ == "__main__":
    main()
