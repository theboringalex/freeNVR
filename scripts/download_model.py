#!/usr/bin/env python3
"""
Download the SSD MobileNet V2 COCO model for Google Coral TPU + CPU fallback.

Usage:
    python scripts/download_model.py
"""
import urllib.request
import zipfile
import os
from pathlib import Path

MODELS_DIR = Path("models")
MODELS_DIR.mkdir(exist_ok=True)

# Coral Edge TPU model (compiled for Edge TPU)
EDGETPU_MODEL_URL = (
    "https://github.com/google-coral/test_data/raw/master/"
    "ssd_mobilenet_v2_coco_quant_postprocess_edgetpu.tflite"
)
# CPU fallback model
CPU_MODEL_URL = (
    "https://github.com/google-coral/test_data/raw/master/"
    "ssd_mobilenet_v2_coco_quant_postprocess.tflite"
)
# COCO labels
LABELS_URL = (
    "https://raw.githubusercontent.com/google-coral/test_data/master/coco_labels.txt"
)

DOWNLOADS = [
    (EDGETPU_MODEL_URL, MODELS_DIR / "ssd_mobilenet_v2_coco_quant_postprocess_edgetpu.tflite"),
    (CPU_MODEL_URL, MODELS_DIR / "ssd_mobilenet_v2_coco_quant_postprocess.tflite"),
    (LABELS_URL, MODELS_DIR / "coco_labels.txt"),
]


def download(url: str, dest: Path):
    if dest.exists():
        print(f"  Already exists: {dest}")
        return
    print(f"  Downloading {dest.name}...")
    urllib.request.urlretrieve(url, dest)
    print(f"  Saved to {dest} ({dest.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    print("Downloading Coral / TFLite models...")
    for url, dest in DOWNLOADS:
        download(url, dest)
    print("\nDone! Models are in the 'models/' directory.")
    print("Start freeNVR and set CORAL_MODEL_PATH=models/ssd_mobilenet_v2_coco_quant_postprocess_edgetpu.tflite")
