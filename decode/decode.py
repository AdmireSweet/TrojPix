
# ---

# `decode_frames.py`

# ```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EM Covert Channel Decoder (Frame-Based)

This script decodes frame-indexed payloads from interleaved float32 IQ samples.
It reproduces the original pipeline with:
- English-only console/file output
- CLI arguments for all key hyperparameters
- Logging, type hints, error handling
- Optional plotting

Author: (your name)
License: MIT
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import matplotlib.pyplot as plt


# --------------------------- Configuration ---------------------------

@dataclass
class Config:
    iq_file: Path
    txt_folder: Path
    img_dir: Path
    result_dir: Path
    cell: int = 2
    rowlen: int = 148
    sync4: Tuple[int, int, int, int] = (1, 0, 1, 0)
    data_bits_per_row: int = 60
    num_images: int = 130
    num_rows_per_img: int = 1080
    img_jump: int = 166_667
    frame_id_len: int = 11  # 11-bit ID in the frame head (binary encoded 1..n)
    phy0: int = 26_067_229
    ph_off: int = 15  # kept for compatibility; not used by the current pipeline
    save_plots: bool = True
    plot_limit: int = 50  # rows to plot for image 2 (debug parity with original)


# --------------------------- IO & Helpers ---------------------------

def load_iq_float32_interleaved(path: Path) -> Tuple[np.ndarray, np.ndarray]:
    """Load interleaved float32 IQ -> (I, Q)."""
    raw = np.fromfile(str(path), dtype=np.float32)
    if raw.size % 2 != 0:
        logging.warning("IQ file length is odd; last sample will be ignored.")
        raw = raw[:-1]
    I, Q = raw[0::2], raw[1::2]
    return I, Q


def compute_features(I: np.ndarray, Q: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return magnitude, high-pass magnitude (identity here), and |diff(unwrapped phase)|."""
    mag = np.hypot(I, Q)
    mag_hp = mag  # placeholder for possible filtering
    dphi = np.abs(np.diff(np.unwrap(np.arctan2(Q, I))))
    return mag, mag_hp, dphi


# Safe accessor for magnitude
def mag_at(mag_hp: np.ndarray, idx: int) -> float:
    return float(mag_hp[idx]) if 0 <= idx < len(mag_hp) else 0.0


def frame_head_align(mag_hp: np.ndarray, base_pos: int, cell: int) -> Tuple[int, int]:
    """
    Try small shifts to maximize alternating high/low pattern contrast.
    Returns (best_shift, flag) where flag in {0,1} encodes initial polarity.
    """
    best_score = None
    best_shift = 0
    for sh in range(-3, 5):
        score = abs(
            mag_at(mag_hp, base_pos + sh) - mag_at(mag_hp, base_pos + sh + cell)
            + mag_at(mag_hp, base_pos + sh + 2 * cell) - mag_at(mag_hp, base_pos + sh + 3 * cell)
            + mag_at(mag_hp, base_pos + sh + 4 * cell) - mag_at(mag_hp, base_pos + sh + 5 * cell)
            + mag_at(mag_hp, base_pos + sh + 6 * cell) - mag_at(mag_hp, base_pos + sh + 7 * cell)
        )
        if best_score is None or score > best_score:
            best_score = score
            best_shift = sh
    flag = 1 if mag_at(mag_hp, base_pos + best_shift) > mag_at(mag_hp, base_pos + best_shift + cell) else 0
    return best_shift, flag


def find_valid_frame(
    mag_hp: np.ndarray,
    start_pos: int,
    img_idx: int,
    cell: int,
    frame_id_len: int,
    img_jump: int
) -> Optional[int]:
    """
    Frame layout:
      [8 ALIGN] [6 GAP] [11-bit ID]
    Sampling:
      Each bit spans 'cell' samples; we read the center/representative point at multiples of 'cell'.
    """
    ALIGN_LEN = 8
    GAP_LEN = 6
    ID_LEN = frame_id_len
    START_OFF = ALIGN_LEN + GAP_LEN  # 14

    pos = int(start_pos)
    n = len(mag_hp)
    max_needed = (START_OFF + ID_LEN) * cell  # farthest index needed (half-open)

    while pos + max_needed <= n:
        shift, flag_high = frame_head_align(mag_hp, pos, cell)
        base = pos + shift
        if base < 0 or base + max_needed > n:
            pos += img_jump
            continue

        # Threshold from the first 8 alignment cells
        T = float(np.mean([mag_at(mag_hp, base + i * cell) for i in range(ALIGN_LEN)]))

        # Read ID bits with polarity adaptation
        val = 0
        for fi in range(ID_LEN):
            idx = base + (START_OFF + fi) * cell
            bit_is_high = (mag_at(mag_hp, idx) > T)
            b = 1 if (bit_is_high == (flag_high == 1)) else 0
            val = (val << 1) | b

        if val == img_idx:
            return base

        pos += img_jump

    return None


def read_reference_rows(txt_file: Path) -> List[List[int]]:
    """
    Load reference bit-lines (one line per row) as lists of 0/1.
    """
    lines: List[List[int]] = []
    with txt_file.open("r", encoding="utf-8") as f:
        for raw in f:
            s = raw.strip()
            if s:
                lines.append([int(x) for x in s])
    return lines


def ensure_dirs(*paths: Path) -> None:
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)


# --------------------------- Plotting ---------------------------

def plot_frame_head(mag_hp: np.ndarray, frame_start: int, cell: int, out_path: Path, title: str) -> None:
    xs = np.arange(64 * cell)
    vals = [mag_at(mag_hp, frame_start + i) for i in xs]
    plt.figure(figsize=(12, 4))
    plt.plot(xs, vals, lw=1, label='Frame Head Magnitude')
    plt.scatter(np.arange(64) * cell,
                [mag_at(mag_hp, frame_start + i * cell) for i in range(64)],
                s=16, label='Head Samples')
    plt.title(title)
    plt.legend()
    plt.grid(alpha=.3, ls='--')
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def plot_row_segment(mag_hp: np.ndarray, start: int, cell: int, out_path: Path, title: str) -> None:
    xs = np.arange(cell * 64)
    plt.figure(figsize=(12, 4))
    plt.plot(xs, [mag_at(mag_hp, start + i) for i in xs], lw=1, label='Magnitude')
    plt.scatter(np.arange(64) * cell, [mag_at(mag_hp, start + i * cell) for i in range(64)], s=16)
    plt.title(title)
    plt.grid(alpha=.3, ls='--')
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


# --------------------------- Core Decoding ---------------------------

def decode_images(cfg: Config) -> None:
    logging.info("Loading IQ: %s", cfg.iq_file)
    I, Q = load_iq_float32_interleaved(cfg.iq_file)
    mag, mag_hp, dphi = compute_features(I, Q)  # noqa: F841 (dphi kept for parity / future use)

    ensure_dirs(cfg.img_dir, cfg.result_dir)

    total_ok = 0
    total_bits = 0
    img_success: List[float] = []
    all_img_result_lines: List[str] = []
    frame_starts: List[Tuple[int, int]] = []

    float_pos = cfg.phy0

    for img_idx in range(1, cfg.num_images + 1):
        txt_file = cfg.txt_folder / f"{img_idx}.txt"
        if not txt_file.exists():
            logging.warning("Missing reference file for image %d: %s (skipping)", img_idx, txt_file)
            continue

        ref_lines = read_reference_rows(txt_file)
        if not ref_lines:
            logging.warning("Empty reference file for image %d: %s (skipping)", img_idx, txt_file)
            continue

        rows_to_process = min(cfg.num_rows_per_img - 1, len(ref_lines))
        if len(ref_lines) != cfg.num_rows_per_img:
            logging.info("Reference rows for %s: actual=%d, will process=%d (cap %d).",
                         txt_file.name, len(ref_lines), rows_to_process, cfg.num_rows_per_img - 1)
        if rows_to_process <= 0:
            logging.warning("No usable rows in %s, skipping image %d.", txt_file, img_idx)
            continue

        # Find frame head
        frame_start = find_valid_frame(
            mag_hp=mag_hp,
            start_pos=float_pos,
            img_idx=img_idx,
            cell=cfig.cell if (cfig := cfg) else cfg.cell,  # small trick to avoid shadowing
            frame_id_len=cfg.frame_id_len,
            img_jump=cfg.img_jump,
        )
        if frame_start is None:
            logging.error("Image %d: frame head not found near pos=%d. Skipping.", img_idx, float_pos)
            # Advance search window to avoid stalling
            float_pos += cfg.img_jump
            continue

        logging.info("Image %d: frame sync OK at %d", img_idx, frame_start)
        frame_starts.append((img_idx, frame_start))

        if cfg.save_plots:
            plot_frame_head(
                mag_hp, frame_start, cfg.cell,
                cfg.result_dir / f"img{img_idx}_framehead.png",
                title=f"Image {img_idx} — Frame Head @ {frame_start}"
            )

        img_total_ok, img_total_bits = 0, 0
        img_result_lines: List[str] = []

        last_row_index = rows_to_process - 1
        for row_idx in range(rows_to_process):
            ref_bits = ref_lines[row_idx]

            # Determine row start
            if row_idx == 0:
                pe = frame_start + cfg.rowlen - 5
            else:
                pe = float_pos

            # Small discrete search for the best local shift
            SHIFT_CAND = [5, 6]
            best_score, shift_result = None, 4
            for sh in SHIFT_CAND:
                score = abs(
                    mag_at(mag_hp, pe + sh) - mag_at(mag_hp, pe + sh + cfg.cell)
                    + mag_at(mag_hp, pe + sh + 2 * cfg.cell) - mag_at(mag_hp, pe + sh + 3 * cfg.cell)
                )
                if best_score is None or score > best_score:
                    best_score = score
                    shift_result = sh

            start = pe + shift_result

            # Polarity + threshold from a small 4-sample window
            v0, v1 = mag_at(mag_hp, start), mag_at(mag_hp, start + cfg.cell)
            flag = 1 if v0 > v1 else -1
            vals = [mag_at(mag_hp, start + i * cfg.cell) for i in range(4)]
            T = (max(vals) + min(vals)) / 2.0

            # Decode 60 data bits
            bits: List[int] = []
            for i in range(4, 4 + cfg.data_bits_per_row):
                v = mag_at(mag_hp, start + i * cfg.cell)
                bit = 1 if flag * (v - T) > 0 else 0
                bits.append(bit)

            # Compare against reference
            ok = sum(int(a == b) for a, b in zip(bits, ref_bits))
            img_total_ok += ok
            img_total_bits += cfg.data_bits_per_row

            # Store per-row result (with leading SYNC4 for parity with prior logs)
            row_line = f"{row_idx:04d}, {''.join(map(str, cfg.sync4 + tuple(bits)))}, {ok}/{cfg.data_bits_per_row}"
            img_result_lines.append(row_line)

            # Optional debug plots (parity with original: image 2, first N rows)
            if cfg.save_plots and img_idx == 2 and row_idx < cfg.plot_limit:
                plot_row_segment(
                    mag_hp, start, cfg.cell,
                    cfg.img_dir / f"img{img_idx}_row_{row_idx:03d}.png",
                    title=f"Image {img_idx} — Row {row_idx:03d} start={start}"
                )

            # Advance pointer to next row or next image
            if row_idx != last_row_index:
                float_pos = start + cfg.rowlen - 5
            else:
                float_pos = frame_start + cfg.img_jump

        # Save per-image results
        result_txt = cfg.result_dir / f"img{img_idx}_result.txt"
        with result_txt.open('w', encoding='utf-8') as f:
            f.write('\n'.join(img_result_lines))

        img_rate = (img_total_ok / img_total_bits) if img_total_bits else 0.0
        img_success.append(img_rate)
        all_img_result_lines.append(
            f"Image {img_idx}: success = {img_total_ok}/{img_total_bits} = {img_rate:.4%}"
        )
        total_ok += img_total_ok
        total_bits += img_total_bits

        logging.info("Image %d: success = %.4f  (%d/%d)",
                     img_idx, img_rate, img_total_ok, img_total_bits)

    # Save global summary
    summary_path = cfg.result_dir / "summary.txt"
    with summary_path.open('w', encoding='utf-8') as f:
        f.write("Frame start positions:\n")
        for idx, pos in frame_starts:
            f.write(f"Image {idx}: {pos}\n")
        f.write("\n")
        for line in all_img_result_lines:
            f.write(line + '\n')
        f.write("\nPer-image success rates: " + str([f"{r:.4f}" for r in img_success]) + "\n")
        if total_bits > 0:
            f.write(f"Overall success: {total_ok/total_bits:.4%}  ({total_ok}/{total_bits})\n")
        else:
            f.write("Overall success: N/A (no bits processed)\n")

    # Console summary
    logging.info("Per-image success rates: %s", [f"{r:.4f}" for r in img_success])
    if total_bits > 0:
        logging.info("Overall success: %.4f  (%d/%d)", total_ok / total_bits, total_ok, total_bits)
    logging.info("Detailed results written to: %s", cfg.result_dir)


# --------------------------- CLI ---------------------------

def parse_args() -> Config:
    p = argparse.ArgumentParser(
        description="Decode frame-indexed payloads from IQ samples."
    )
    p.add_argument("--iq_file", type=Path, required=True, help="Path to interleaved float32 IQ file.")
    p.add_argument("--txt_folder", type=Path, required=True, help="Folder with reference rows as N.txt.")
    p.add_argument("--img_dir", type=Path, required=True, help="Directory to save row plots (if enabled).")
    p.add_argument("--result_dir", type=Path, required=True, help="Directory to save decoding results.")
    p.add_argument("--cell", type=int, default=2, help="Samples per bit-cell.")
    p.add_argument("--rowlen", type=int, default=148, help="Row length in samples.")
    p.add_argument("--num_images", type=int, default=130, help="Number of images to decode.")
    p.add_argument("--num_rows_per_img", type=int, default=1080, help="Rows per image.")
    p.add_argument("--img_jump", type=int, default=166_667, help="Inter-frame stride in samples.")
    p.add_argument("--frame_id_len", type=int, default=11, help="Frame ID bit length.")
    p.add_argument("--phy0", type=int, default=26_067_229, help="Initial search position.")
    p.add_argument("--ph_off", type=int, default=15, help="Phase offset placeholder (unused).")
    p.add_argument("--data_bits_per_row", type=int, default=60, help="Number of data bits per row.")
    p.add_argument("--save_plots", action="store_true", help="Save plotting artifacts (frame heads / rows).")
    p.add_argument("--plot_limit", type=int, default=50, help="Rows to plot for image 2 (debug).")
    p.add_argument("--loglevel", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = p.parse_args()

    logging.basicConfig(level=getattr(logging, args.loglevel.upper()),
                        format="%(asctime)s [%(levelname)s] %(message)s")

    return Config(
        iq_file=args.iq_file,
        txt_folder=args.txt_folder,
        img_dir=args.img_dir,
        result_dir=args.result_dir,
        cell=args.cell,
        rowlen=args.rowlen,
        num_images=args.num_images,
        num_rows_per_img=args.num_rows_per_img,
        img_jump=args.img_jump,
        frame_id_len=args.frame_id_len,
        phy0=args.phy0,
        ph_off=args.ph_off,
        data_bits_per_row=args.data_bits_per_row,
        save_plots=args.save_plots,
        plot_limit=args.plot_limit,
    )


def main() -> None:
    cfg = parse_args()
    decode_images(cfg)


if __name__ == "__main__":
    main()
