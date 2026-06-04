"""
Google Coral TPU / TFLite object detector for freeNVR.

Priority chain:
  1. pycoral + Edge TPU delegate  (Coral USB/PCIe)
  2. ai-edge-litert with libedgetpu delegate  (Coral, Python 3.11+)
  3. tflite-runtime CPU
  4. No detection (logs warning on first use)

Frame input comes from a 1-fps FFmpeg subprocess pipe to avoid OpenCV RTSP
reliability issues.
"""
from __future__ import annotations

import asyncio
import io
import logging
import struct
from pathlib import Path
from typing import Optional

import aiosqlite
from datetime import datetime, UTC

from app.config import settings

logger = logging.getLogger(__name__)

# ─── Backend detection ────────────────────────────────────────────────────────

_backend: str = "none"
_make_interpreter_fn = None


def _init_backend():
    global _backend, _make_interpreter_fn

    # 1) pycoral (Python ≤ 3.9, official)
    try:
        from pycoral.utils.edgetpu import make_interpreter, list_edge_tpus
        devices = list_edge_tpus()
        if devices:
            logger.info("Coral TPU found via pycoral: %s", devices)
            _make_interpreter_fn = lambda path: make_interpreter(path)
            _backend = "pycoral"
            return
        logger.info("pycoral available but no Coral device found, using CPU")
        _make_interpreter_fn = lambda path: make_interpreter(path.replace("_edgetpu.tflite", ".tflite"))
        _backend = "pycoral_cpu"
        return
    except ImportError:
        pass

    # 2) ai-edge-litert with edgetpu delegate (Python 3.11+)
    try:
        import ai_edge_litert.interpreter as tflite

        def _make_edgetpu(path):
            try:
                delegate = tflite.load_delegate("libedgetpu.so.1")
                interp = tflite.Interpreter(model_path=path, experimental_delegates=[delegate])
                logger.info("Coral TPU loaded via ai-edge-litert + libedgetpu")
                return interp
            except Exception:
                # Fall back to CPU model (drop _edgetpu suffix)
                cpu_path = path.replace("_edgetpu.tflite", ".tflite")
                return tflite.Interpreter(model_path=cpu_path if Path(cpu_path).exists() else path)

        _make_interpreter_fn = _make_edgetpu
        _backend = "ai_edge_litert"
        return
    except ImportError:
        pass

    # 3) tflite-runtime CPU
    try:
        import tflite_runtime.interpreter as tflite

        def _make_tflite(path):
            cpu_path = path.replace("_edgetpu.tflite", ".tflite")
            return tflite.Interpreter(model_path=cpu_path if Path(cpu_path).exists() else path)

        _make_interpreter_fn = _make_tflite
        _backend = "tflite_cpu"
        return
    except ImportError:
        pass

    logger.warning(
        "No AI inference backend found. Install ai-edge-litert (pip install ai-edge-litert) "
        "or pycoral for Coral TPU support. Detection mode 'coral' will be inactive."
    )
    _backend = "none"


_init_backend()


def backend_info() -> dict:
    return {"backend": _backend, "available": _backend != "none"}


# ─── COCO labels ─────────────────────────────────────────────────────────────

_COCO_LABELS: dict[int, str] = {}

def _load_labels() -> dict[int, str]:
    global _COCO_LABELS
    if _COCO_LABELS:
        return _COCO_LABELS
    path = Path(settings.CORAL_LABELS_PATH)
    if path.exists():
        with open(path) as f:
            for line in f:
                parts = line.strip().split(None, 1)
                if len(parts) == 2 and parts[0].isdigit():
                    _COCO_LABELS[int(parts[0])] = parts[1]
    else:
        # Minimal inline COCO labels (subset)
        _COCO_LABELS = {
            0: "person", 1: "bicycle", 2: "car", 3: "motorcycle",
            4: "airplane", 5: "bus", 6: "train", 7: "truck", 8: "boat",
            14: "bird", 15: "cat", 16: "dog", 17: "horse",
            18: "sheep", 19: "cow", 20: "elephant", 21: "bear",
        }
    return _COCO_LABELS


# ─── CoralDetector ────────────────────────────────────────────────────────────

class CoralDetector:
    """
    Per-camera detector that grabs frames at CORAL_INFERENCE_FPS via FFmpeg
    and runs object detection inference.
    """

    def __init__(self, camera: dict, on_detection):
        self.camera = camera
        self.on_detection = on_detection  # async callable(camera_id, detections)
        self._task: asyncio.Task | None = None
        self.running = False
        self._interpreter = None

    def _load_interpreter(self):
        if _backend == "none":
            return None
        model_path = settings.CORAL_MODEL_PATH
        if not Path(model_path).exists():
            logger.warning("Coral model not found at %s — download with scripts/download_model.py", model_path)
            return None
        try:
            interp = _make_interpreter_fn(model_path)
            interp.allocate_tensors()
            return interp
        except Exception as e:
            logger.error("Failed to load model: %s", e)
            return None

    def _rtsp_url(self) -> str:
        url = self.camera.get("rtsp_url", "")
        user = self.camera.get("username")
        pwd = self.camera.get("password")
        if user and pwd and "://" in url:
            scheme, rest = url.split("://", 1)
            if "@" not in rest:
                return f"{scheme}://{user}:{pwd}@{rest}"
        return url

    def _ffmpeg_cmd(self) -> list[str]:
        fps = settings.CORAL_INFERENCE_FPS
        return [
            settings.FFMPEG_BIN,
            "-rtsp_transport", "tcp",
            "-i", self._rtsp_url(),
            "-vf", f"fps={fps},scale=300:300",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "pipe:1",
        ]

    def _run_inference(self, raw_frame: bytes) -> list[dict]:
        """Run SSD MobileNet inference; return detections above threshold."""
        interp = self._interpreter
        if interp is None:
            return []

        input_details = interp.get_input_details()
        output_details = interp.get_output_details()

        import numpy as np
        frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape(300, 300, 3)
        frame = np.expand_dims(frame, axis=0)

        interp.set_tensor(input_details[0]["index"], frame)
        interp.invoke()

        # SSD MobileNet V2 COCO outputs: boxes, classes, scores, count
        boxes = interp.get_tensor(output_details[0]["index"])[0]
        classes = interp.get_tensor(output_details[1]["index"])[0]
        scores = interp.get_tensor(output_details[2]["index"])[0]

        labels = _load_labels()
        threshold = settings.CORAL_SCORE_THRESHOLD
        detect_classes = settings.CORAL_DETECT_CLASSES

        results = []
        for i in range(int(interp.get_tensor(output_details[3]["index"])[0])):
            score = float(scores[i])
            if score < threshold:
                continue
            cls_id = int(classes[i])
            label = labels.get(cls_id, str(cls_id))
            if detect_classes and label not in detect_classes:
                continue
            ymin, xmin, ymax, xmax = boxes[i]
            results.append({
                "class_id": cls_id,
                "label": label,
                "score": round(score, 3),
                "bbox": [round(float(xmin), 3), round(float(ymin), 3),
                         round(float(xmax), 3), round(float(ymax), 3)],
            })
        return results

    async def _run(self):
        self._interpreter = self._load_interpreter()
        if self._interpreter is None:
            logger.warning("Coral detector inactive for camera %d (no backend)", self.camera["id"])
            return

        frame_size = 300 * 300 * 3
        cam_id = self.camera["id"]
        logger.info("Coral detector starting for camera %d (backend=%s)", cam_id, _backend)

        while self.running:
            cmd = self._ffmpeg_cmd()
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                while self.running:
                    raw = await proc.stdout.readexactly(frame_size)
                    if not raw:
                        break
                    loop = asyncio.get_event_loop()
                    detections = await loop.run_in_executor(None, self._run_inference, raw)
                    if detections:
                        await self.on_detection(cam_id, detections)
            except asyncio.IncompleteReadError:
                pass
            except Exception as e:
                logger.debug("Coral frame error cam %d: %s", cam_id, e)
            if self.running:
                await asyncio.sleep(3)

    def start(self):
        self.running = True
        self._task = asyncio.create_task(self._run(), name=f"coral-{self.camera['id']}")

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
