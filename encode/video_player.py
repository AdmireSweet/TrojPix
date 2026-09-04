#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lossless Video Player (FFV1 / MKV / Any OpenCV-supported format)

This script provides a simple and deterministic video playback tool
designed for reproducibility in Artifact Evaluation (AE). It plays a
specified video file using OpenCV and supports optional fullscreen mode,
fixed frame delay, and user-configurable window naming.

Usage example:
    python video_player.py \
        --video ./1M.mkv \
        --fullscreen \
        --window_name TrojPixPlayer

Press ESC to exit playback.

Author: (your name)
License: MIT
"""

from __future__ import annotations

import argparse
import logging
import time
import cv2
from pathlib import Path


# -------------------------------------------------------------
# Main Player
# -------------------------------------------------------------

def run(cfg) -> None:
    """
    Play a video file frame-by-frame using OpenCV.

    Parameters
    ----------
    cfg : argparse.Namespace
        Parsed command-line configuration.
    """

    video_path = cfg.video
    window_name = cfg.window_name

    logging.info("Opening video: %s", video_path)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video file: {video_path}")

    # Read FPS from video file
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        logging.warning("Video FPS could not be determined. Falling back to 60 FPS.")
        fps = 60.0

    delay_sec = 1.0 / fps
    delay_ms = int(delay_sec * 1000)

    logging.info("Video FPS: %.3f | Frame delay: %.6f sec (≈ %d ms)", fps, delay_sec, delay_ms)

    # Create playback window
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    if cfg.fullscreen:
        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    # Playback loop
    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            logging.info("Reached end of video. Total frames: %d", frame_count)
            break

        cv2.imshow(window_name, frame)
        frame_count += 1

        # ESC to exit
        if cv2.waitKey(delay_ms) == 27:
            logging.info("Playback interrupted by user.")
            break

    cap.release()
    cv2.destroyAllWindows()
    logging.info("Video playback finished.")


# -------------------------------------------------------------
# CLI
# -------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Lossless video player for Artifact Evaluation (AE)."
    )

    parser.add_argument(
        "--video",
        type=Path,
        required=True,
        help="Path to the video file to play (e.g., ./1M.mkv)."
    )

    parser.add_argument(
        "--window_name",
        type=str,
        default="VideoPlayer",
        help="Window title for playback (default: VideoPlayer)."
    )

    parser.add_argument(
        "--fullscreen",
        action="store_true",
        help="Play video in fullscreen mode (default: off)."
    )

    parser.add_argument(
        "--loglevel",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity level."
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.loglevel.upper()),
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    return args


# -------------------------------------------------------------
# Entry Point
# -------------------------------------------------------------

if __name__ == "__main__":
    cfg = parse_args()
    run(cfg)
