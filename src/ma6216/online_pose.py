"""Nonblocking RGB-D worker client and timestamped motion estimation.

This module knows no simulated object positions or CAD geometry. The simulator
can continue stepping while the separate CUDA process estimates a pose.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import threading
import time

import numpy as np

from .config import project_root
from .foundationpose import validate_rigid_transform


class PoseWorker:
    def __init__(self, python, repository, output):
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.log = (self.output / "worker.log").open("w")
        self.socket = None
        endpoint = os.environ.get("MA6216_POSE_SOCKET")
        if endpoint:
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.socket.connect(endpoint)
            self.process = None
            self.input = self.socket.makefile("w")
            self.stream = self.socket.makefile("r")
        else:
            self.process = subprocess.Popen(
            [str(Path(python).resolve()), "-u", str(project_root() / "scripts/serve_model_free_pose.py"),
             "--repository", str(Path(repository).resolve()), "--debug-dir", str(self.output / "debug")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, text=True, bufsize=1)
            self.input, self.stream = self.process.stdin, self.process.stdout
        self.queue = queue.Queue()
        self.results, self.pending = {}, {}
        self.count = 0
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        deadline = time.monotonic() + 60.
        while time.monotonic() < deadline:
            try:
                message = self.queue.get(timeout=.2)
            except queue.Empty:
                if not self.reader.is_alive():
                    raise RuntimeError("Pose worker exited during startup; see worker.log")
                continue
            if message.get("ready"):
                return
        self.close()
        raise TimeoutError("Pose worker did not initialize")

    def _read(self):
        for line in self.stream:
            if line.startswith("MA6216_REPLY "):
                try:
                    self.queue.put(json.loads(line[len("MA6216_REPLY "):]))
                except json.JSONDecodeError:
                    self.log.write(line)
            else:
                self.log.write(line)
        self.log.flush()

    def submit(self, *, model_bundle, sequence="default", frame=None, K=None,
               world_T_camera=None, capture_time_s=0., register=False, world_T_object_prior=None):
        self.count += 1
        request = {"id": self.count, "model_bundle": str(Path(model_bundle).resolve()),
                   "sequence": sequence, "register": register, "capture_time_s": float(capture_time_s)}
        if frame is None:
            request["operation"] = "load"
        else:
            request.update({key: str(Path(value).resolve()) for key, value in frame.items()})
            request["K"] = np.asarray(K).tolist()
            if world_T_object_prior is not None:
                request["camera_T_object_prior"] = (np.linalg.inv(world_T_camera) @ world_T_object_prior).tolist()
        self.pending[self.count] = (request, None if world_T_camera is None else
                                    validate_rigid_transform(world_T_camera).copy())
        self.input.write(json.dumps(request) + "\n")
        self.input.flush()
        return self.count

    def poll(self, request_id):
        while True:
            try:
                result = self.queue.get_nowait()
            except queue.Empty:
                break
            if "id" not in result:
                continue
            request, world_T_camera = self.pending.pop(result["id"])
            if result["success"] and "camera_T_object" in result and world_T_camera is not None:
                result["world_T_object"] = (world_T_camera @ np.asarray(result["camera_T_object"])).tolist()
            self.results[result["id"]] = result
            (self.output / f"request_{result['id']:05d}.json").write_text(
                json.dumps({"request": request, "result": result}, indent=2) + "\n")
        if request_id in self.results:
            return self.results.pop(request_id)
        if not self.reader.is_alive():
            raise RuntimeError("Pose worker exited before returning a result")
        return None

    def wait(self, request_id, *, on_wait=None, timeout=180.):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.poll(request_id)
            if result is not None:
                if not result["success"]:
                    raise RuntimeError(result["error"])
                return result
            if on_wait is None:
                time.sleep(.01)
            else:
                on_wait()
        raise TimeoutError(f"Pose request {request_id} timed out")

    def close(self):
        if self.socket is not None:
            try:
                self.input.write('{"operation":"shutdown"}\n')
                self.input.flush()
            except BrokenPipeError:
                pass
            self.socket.shutdown(socket.SHUT_RDWR)
            self.socket.close()
        elif self.process.poll() is None:
            try:
                self.process.stdin.write('{"operation":"shutdown"}\n')
                self.process.stdin.flush()
                self.process.wait(timeout=5)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
        self.reader.join(timeout=2.)
        self.input.close()
        self.stream.close()
        self.log.close()


class PoseHistory:
    """Bounded constant-velocity prediction from visual measurements only."""
    def __init__(self, max_samples=6):
        if max_samples < 2:
            raise ValueError("Motion estimation needs at least two retained samples")
        self.samples = []
        self.max_samples = max_samples

    def add(self, timestamp, pose):
        pose = validate_rigid_transform(pose).copy()
        if not np.isfinite(timestamp):
            raise ValueError("Visual capture timestamp must be finite")
        if self.samples and timestamp <= self.samples[-1][0]:
            raise ValueError("Visual capture timestamps must increase")
        self.samples.append((float(timestamp), pose))
        self.samples = self.samples[-self.max_samples:]

    @property
    def velocity(self):
        if len(self.samples) < 2:
            return np.zeros(3)
        times = np.array([s[0] for s in self.samples])
        xyz = np.array([s[1][:3, 3] for s in self.samples])
        times -= times.mean()
        speed = times @ (xyz - xyz.mean(axis=0)) / max(float(times @ times), 1e-9)
        if np.linalg.norm(speed) > .05:
            raise ValueError("Visual motion exceeds validated conveyor velocity range")
        return speed

    def predict(self, timestamp, max_horizon=12.):
        if not self.samples:
            raise ValueError("No visual measurement available")
        latest, pose = self.samples[-1]
        horizon = float(timestamp) - latest
        if not 0. <= horizon <= max_horizon:
            raise ValueError("Prediction request has an invalid time horizon")
        predicted = pose.copy()
        predicted[:3, 3] += self.velocity * horizon
        return predicted
