#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Image Sequence → Lossless Video (FFV1 / MKV)

This script converts all PNG images in a directory into a lossless
FFV1-encoded MKV video. Images are sorted in natural order so that
files like "2.png" come before "10.png".

Designed for Artifact Evaluation (AE):
- Deterministic behavior.
- Uses FFV1 (lossless) for pixel-accurate preservation.
- Simple CLI interface.
- Configurable FPS, resolution, and per-frame repetition.

Example:
    python video_from_images.py \
        --image_dir ./1MB/img \
        --output ./1M.mkv \
        --fps 60 \
        --width 1920 \
        --height 1080 \
        --repeat 1

Author: (your name)
License: MIT
"""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path
from typing import List, Tuple

import cv2
import glob


# -------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------

def natural_key(path: Path) -> Tuple:
    """
    Natural sort key for filenames.

    It splits the filename into alternating digit and non-digit parts,
    and tags each part so that comparisons never mix integers and strings.

    Example:
        "frame_10.png" -> [("t","frame_"), ("n",10), ("t",".png")]

    This avoids TypeError when sorting keys from heterogeneous filenames.
    """
    name = path.name
    parts = re.findall(r"\d+|\D+", name)
    key: List[Tuple[str, object]] = []
    for part in parts:
        if part.isdigit():
            # "n" = numeric part, value is int
            key.append(("n", int(part)))
        else:
            # "t" = text part, value is lowercased string
            key.append(("t", part.lower()))
    return tuple(key)


def list_png_images(image_dir: Path, pattern: str = "*.png") -> List[Path]:
    """
    List all PNG images in the given directory matching the specified pattern,
    sorted in natural order.

    Parameters
    ----------
    image_dir : Path
        Directory containing PNG images.
    pattern : str
        Glob pattern for images (default: '*.png').

    Returns
    -------
    List[Path]
        A list of image paths sorted in natural (human-friendly) order.
    """
    candidates = [Path(p) for p in glob.glob(str(image_dir / pattern))]
    # Keep only .png files (case-insensitive)
    candidates = [p for p in candidates if p.suffix.lower() == ".png"]
    candidates.sort(key=natural_key)
    return candidates


def image_is_readable(path: Path) -> bool:
    """
    Check whether an image exists and can be read by OpenCV.

    Returns
    -------
    bool
        True if readable, False otherwise.
    """
    if not path.exists():
        logging.warning("Image does not exist: %s", path)
        return False
    test = cv2.imread(str(path))
    if test is None:
        logging.warning("Failed to read image: %s", path)
        return False
    return True


# -------------------------------------------------------------
# Main Conversion Logic
# -------------------------------------------------------------

def run(cfg) -> None:
    """
    Convert all PNG images in a directory into an FFV1 MKV video.

    Images are:
        - Discovered via a glob pattern (default: '*.png').
        - Sorted in natural order (e.g., 0.png, 1.png, 2.png, 10.png, ...).
        - Resized to the target resolution if needed.
        - Written to the output video, each repeated N times.
    """
    logging.info("Input directory: %s", cfg.image_dir)
    logging.info("Output video: %s", cfg.output)
    logging.info(
        "FPS=%d | Size=%dx%d | Repeat=%d | Pattern=%s",
        cfg.fps,
        cfg.width,
        cfg.height,
        cfg.repeat,
        cfg.pattern,
    )

    frame_size = (cfg.width, cfg.height)

    # Collect and sort PNG images
    image_paths = list_png_images(cfg.image_dir, pattern=cfg.pattern)
    if not image_paths:
        raise RuntimeError(f"No PNG images found in directory: {cfg.image_dir}")

    logging.info("Found %d PNG images.", len(image_paths))

    # Filter unreadable images
    readable_paths = [p for p in image_paths if image_is_readable(p)]
    if not readable_paths:
        raise RuntimeError("No readable PNG images found — aborting.")

    if len(readable_paths) != len(image_paths):
        logging.warning(
            "Some images are not readable and will be skipped "
            "(readable=%d / total=%d).",
            len(readable_paths),
            len(image_paths),
        )

    # Initialize FFV1 writer (lossless)
    fourcc = cv2.VideoWriter_fourcc(*"FFV1")
    writer = cv2.VideoWriter(str(cfg.output), fourcc, float(cfg.fps), frame_size)
    if not writer.isOpened():
        raise RuntimeError(
            "Failed to initialize FFV1 video writer. "
            "Please check codec/container support in your OpenCV build."
        )

    frames_written = 0
    skipped = 0

    for img_path in image_paths:
        img = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
        if img is None:
            logging.warning("Skipping unreadable image: %s", img_path)
            skipped += 1
            continue

        # Resize to target resolution if needed
        h, w = img.shape[:2]
        if (w, h) != frame_size:
            img = cv2.resize(img, frame_size, interpolation=cv2.INTER_NEAREST)

        # Write repeated frames
        repeat_count = max(1, cfg.repeat)
        for _ in range(repeat_count):
            writer.write(img)
            frames_written += 1

    writer.release()

    logging.info("Video generation completed.")
    logging.info("Frames written: %d", frames_written)
    logging.info("Images skipped: %d", skipped)
    logging.info("Saved to: %s", cfg.output)


# -------------------------------------------------------------
# CLI
# -------------------------------------------------------------

def parse_args():
    """
    Parse command-line arguments and configure logging.
    """
    parser = argparse.ArgumentParser(
        description="Convert all PNG images in a directory into a lossless FFV1 MKV video."
    )

    parser.add_argument(
        "--image_dir",
        type=Path,
        required=True,
        help="Directory containing PNG images (e.g., 0.png, 1.png, 2.png, ...).",
    )

    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output MKV file path (e.g., ./output.mkv).",
    )

    parser.add_argument(
        "--pattern",
        type=str,
        default="*.png",
        help="Glob pattern for images (default: '*.png').",
    )

    parser.add_argument(
        "--fps",
        type=int,
        default=60,
        help="Video frame rate (default: 60).",
    )

    parser.add_argument(
        "--width",
        type=int,
        default=1920,
        help="Output video width in pixels (default: 1920).",
    )

    parser.add_argument(
        "--height",
        type=int,
        default=1080,
        help="Output video height in pixels (default: 1080).",
    )

    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Repeat each input frame N times (default: 1).",
    )

    parser.add_argument(
        "--loglevel",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO).",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.loglevel.upper()),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    return args


# -------------------------------------------------------------
# Entry Point
# -------------------------------------------------------------

if __name__ == "__main__":
    cfg = parse_args()
    run(cfg)
