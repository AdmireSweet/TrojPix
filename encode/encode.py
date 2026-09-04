#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bit Embedding Pipeline (1920×1080, 60-bit rows)

This script implements a simple bit-to-image embedding scheme intended for
reproducible experiments and artifact evaluation.

High-level steps:
1) Read a UTF-8 text file and write its raw bytes to a .bin file.
2) Convert these bytes to a bitstream.
3) Chunk the bitstream into blocks of size:
       BITS_PER_LINE * (NUM_LINES - 1)
   so that each block fits into one image (rows 1..NUM_LINES-1).
4) For each block, create a 1920×1080 RGB PNG frame using a template image:
   - Row 0 carries a header:
       FIRST_ROW_PREFIX (14 bits) + 11-bit image index,
     padded with zeros to BITS_PER_LINE bits.
   - Rows 1..NUM_LINES-1 carry data:
       SYNC_BITS + BITS_PER_LINE data bits per row.
   - A logical '1' is encoded by setting the two least significant bits
     (LSBs) of the blue channel to 1 in the corresponding column group.
     A logical '0' leaves the template pixels unchanged.
5) For each image N, also write N.txt where each line contains exactly
   BITS_PER_LINE bits (zero-padded on the right if necessary).

Author: htz
License: MIT
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import List, Tuple

import numpy as np
from PIL import Image


# -------------------- Helper functions --------------------


def ensure_dir(p: Path) -> None:
    """
    Create the directory `p` (and parents) if it does not already exist.
    This is a convenience wrapper around pathlib.Path.mkdir().
    """
    p.mkdir(parents=True, exist_ok=True)


def bytes_to_bits(b: bytes) -> List[int]:
    """
    Convert a byte string into a list of integer bits (0/1).

    Each byte is expanded into its 8-bit binary representation, using a
    most-significant-bit-first convention.

    Example:
        b'\x03' -> [0, 0, 0, 0, 0, 0, 1, 1]
    """
    return [int(bit) for byte in b for bit in f"{byte:08b}"]


def calc_groups(width: int, ideal: float = 29.7) -> List[Tuple[int, int]]:
    """
    Partition the horizontal pixel range [0, width) into approximately
    equal contiguous integer column groups.

    A floating-point cursor is advanced by `ideal` each step and rounded
    to the nearest integer to form group boundaries.

    Each returned tuple (start, end) is a half-open interval [start, end)
    representing one "bit cell" in the horizontal direction.
    """
    pos_f = 0.0
    prev_i = 0
    groups: List[Tuple[int, int]] = []

    while prev_i < width:
        pos_f += ideal
        nxt_i = int(round(pos_f))
        if nxt_i > width:
            nxt_i = width
        groups.append((prev_i, nxt_i))
        prev_i = nxt_i

    return groups


def set_blue_lsb_two_bits(out: np.ndarray, row: int, c0: int, c1: int) -> None:
    """
    Encode a logical '1' into the specified column range at the given row
    by setting the two least significant bits (LSBs) of the blue channel
    (channel index 2) to 1.

    The red and green channels are left unchanged, and locations intended
    to encode a logical '0' should not be modified at all.

    Parameters
    ----------
    out : np.ndarray
        The output RGB image array of shape (H, W, 3), dtype uint8.
    row : int
        Row index at which the bit cell is encoded.
    c0, c1 : int
        Column range [c0, c1) defining the horizontal bit cell.
    """
    # Extract the blue channel slice in the given row and column range.
    blue_slice = out[row, c0:c1, 2]
    # Set the two least significant bits to 1 (bitwise OR with 0b00000011).
    out[row, c0:c1, 2] = blue_slice | 0b00000011


def embed_block(
    frame: np.ndarray,
    bits: List[int],
    img_idx: int,
    *,
    width: int,
    height: int,
    bits_per_line: int,
    num_lines: int,
    sync_bits: Tuple[int, ...],
    first_row_prefix: str,
    on_value: int,  # kept for CLI compatibility; not used in LSB-based embedding
) -> np.ndarray:
    """
    Embed one logical data block into a copy of the given template frame.

    The embedding scheme is line-based and uses bit cells spanning groups
    of columns. The image is conceptually divided into rows and groups:

    - Row 0:
        FIRST_ROW_PREFIX (14 bits) + 11-bit image index (MSB-first),
        right-padded with zeros to `bits_per_line` bits total.

    - Rows 1..num_lines-1:
        Each row begins with SYNC_BITS (len(sync_bits) bits), followed by
        `bits_per_line` data bits.

    Bit encoding:
        A logical '1' is encoded by setting the two least significant bits
        of the blue channel (channel index 2) to 1 in the corresponding
        column group of the specified row. A logical '0' leaves the
        template pixel values unchanged.

    Parameters
    ----------
    frame : np.ndarray
        Template RGB image array of shape (height, width, 3), dtype uint8.
    bits : List[int]
        The data bits (0/1) to be embedded into this frame (one block).
    img_idx : int
        1-based index of the image, used in the Row 0 header.
    width, height : int
        Expected dimensions of the image.
    bits_per_line : int
        Number of payload bits per data row (excluding sync bits).
    num_lines : int
        Total number of rows considered per image (typically == height).
    sync_bits : Tuple[int, ...]
        Synchronization bits prefixed to each data row.
    first_row_prefix : str
        Binary string used as the fixed prefix in row 0.
    on_value : int
        Retained for backward compatibility. It is not used in this LSB-based
        embedding implementation.

    Returns
    -------
    np.ndarray
        A copy of the template frame with encoded bits in the blue channel.
    """
    assert frame.shape[:2] == (height, width), "Template frame size mismatch"
    out = frame.copy()

    # Compute column groups for mapping logical bit positions to horizontal cells.
    groups = calc_groups(width)

    # We need at least len(sync_bits) + bits_per_line groups for data rows.
    required_groups = len(sync_bits) + bits_per_line
    if len(groups) < required_groups:
        raise ValueError(
            f"Not enough column groups ({len(groups)}) for sync_bits "
            f"({len(sync_bits)}) + bits_per_line ({bits_per_line})."
        )

    # ----- Row 0: header bits -----
    # 11-bit image index, binary, MSB-first (1..N images).
    img_bin = format(img_idx, "011b")
    header = (first_row_prefix + img_bin).ljust(bits_per_line, "0")
    header_bits = [int(ch) for ch in header]

    # Only the first `bits_per_line` groups are used in row 0.
    for g_idx in range(bits_per_line):
        c0, c1 = groups[g_idx]
        if header_bits[g_idx] == 1:
            # Encode a logical '1' by modifying only the blue channel LSBs.
            set_blue_lsb_two_bits(out, 0, c0, c1)
        # Logical '0' is represented by leaving the template pixels unchanged.

    # ----- Rows 1..num_lines-1: sync + data bits -----
    data_idx = 0
    g_sync = len(sync_bits)

    for row in range(1, num_lines):
        # Each row may use the first (g_sync + bits_per_line) groups.
        for g_idx in range(g_sync + bits_per_line):
            c0, c1 = groups[g_idx]

            # Determine which logical bit to embed at this (row, group).
            if g_idx < g_sync:
                # Sync region at the beginning of the row.
                b = sync_bits[g_idx]
            else:
                # Data region: consume from the block bitstream.
                if data_idx < len(bits):
                    b = bits[data_idx]
                    data_idx += 1
                else:
                    # If the block is shorter than the maximum capacity,
                    # remaining cells are treated as logical '0'.
                    b = 0

            if b == 1:
                # Encode a logical '1' via blue-channel LSB modification.
                set_blue_lsb_two_bits(out, row, c0, c1)
            # If b == 0, do nothing and keep the template pixel values.

    return out


def write_block_txt(block_bits: List[int], out_path: Path, bits_per_line: int) -> None:
    """
    Write the bits of a single block to a text file, one line per row.

    Each line contains exactly `bits_per_line` characters ('0' or '1'),
    right-padded with '0' if the final line is not complete. This is
    intended as a human-readable and machine-parseable ground truth
    representation of the embedded bits.
    """
    with out_path.open("w", encoding="utf-8") as f:
        for i in range(0, len(block_bits), bits_per_line):
            line = block_bits[i:i + bits_per_line]
            if not line:
                break
            f.write("".join(str(b) for b in line).ljust(bits_per_line, "0") + "\n")


# -------------------- Main pipeline --------------------


def run(cfg) -> None:
    """
    Execute the end-to-end bit embedding pipeline according to the
    configuration parsed from command-line arguments.
    """
    logging.info("Reading text: %s", cfg.txt_input)
    txt_bytes = Path(cfg.txt_input).read_text(encoding="utf-8").encode("utf-8")

    # Write raw bytes as .bin (artifact for reproducibility and verification).
    ensure_dir(Path(cfg.bin_output).parent)
    Path(cfg.bin_output).write_bytes(txt_bytes)
    logging.info("Wrote bin: %s  (%d bytes)", cfg.bin_output, len(txt_bytes))

    # Convert raw bytes to a bitstream.
    all_bits = bytes_to_bits(txt_bytes)
    logging.info("Bitstream length: %d bits", len(all_bits))

    # Calculate per-image payload capacity (rows 1..num_lines-1).
    max_bits_per_img = cfg.bits_per_line * (cfg.num_lines - 1)
    logging.info(
        "Bits per image: %d (bits_per_line=%d × data_rows=%d)",
        max_bits_per_img,
        cfg.bits_per_line,
        cfg.num_lines - 1,
    )

    # Split the bitstream into blocks, one block per image.
    blocks: List[List[int]] = []
    remaining = all_bits[:]
    while remaining:
        block = remaining[:max_bits_per_img]
        remaining = remaining[max_bits_per_img:]
        blocks.append(block)
    logging.info("Total blocks/images: %d", len(blocks))

    # Load the template image (single file) and validate its size.
    tmpl_path = Path(cfg.img_template)
    if not tmpl_path.exists():
        raise FileNotFoundError(f"Template image not found: {tmpl_path}")
    tmpl = Image.open(tmpl_path).convert("RGB")
    arr = np.asarray(tmpl, dtype=np.uint8)
    if arr.shape[:2] != (cfg.height, cfg.width):
        raise ValueError(
            f"Template size must be {cfg.width}×{cfg.height}, got {arr.shape[:2]}"
        )

    # Prepare output directories for PNG frames and TXT bit dumps.
    ensure_dir(Path(cfg.img_output_dir))
    ensure_dir(Path(cfg.txt_output_dir))

    # Embed each block into a separate image and write both PNG and TXT.
    for idx, block in enumerate(blocks, start=1):
        mod = embed_block(
            arr,
            block,
            img_idx=idx,
            width=cfg.width,
            height=cfg.height,
            bits_per_line=cfg.bits_per_line,
            num_lines=cfg.num_lines,
            sync_bits=tuple(cfg.sync_bits),
            first_row_prefix=cfg.first_row_prefix,
            on_value=cfg.on_value,
        )

        out_img = Path(cfg.img_output_dir) / f"{idx}.png"
        Image.fromarray(mod, mode="RGB").save(out_img, compress_level=0)

        out_txt = Path(cfg.txt_output_dir) / f"{idx}.txt"
        write_block_txt(block, out_txt, cfg.bits_per_line)

        logging.info("Wrote %s and %s", out_img, out_txt)

    logging.info("All image embedding completed.")


# -------------------- Command-line interface --------------------


def parse_args():
    """
    Parse and validate command-line arguments, and configure logging.

    Returns
    -------
    argparse.Namespace
        An object containing all parsed configuration options.
    """
    p = argparse.ArgumentParser(
        description="Embed a UTF-8 text file into 1920×1080 PNG frames "
                    "with 60-bit rows using blue-channel LSB encoding."
    )
    # I/O configuration
    p.add_argument(
        "--txt_input",
        type=Path,
        required=True,
        help="Input UTF-8 text file to be embedded.",
    )
    p.add_argument(
        "--bin_output",
        type=Path,
        required=True,
        help="Path to write raw bytes (.bin) corresponding to txt_input.",
    )
    p.add_argument(
        "--txt_output_dir",
        type=Path,
        required=True,
        help="Directory for per-image 60-bit TXT files.",
    )
    p.add_argument(
        "--img_template",
        type=Path,
        required=True,
        help="Template PNG (RGB, width×height) used as the base frame.",
    )
    p.add_argument(
        "--img_output_dir",
        type=Path,
        required=True,
        help="Directory for output PNG frames with embedded bits.",
    )

    # Geometry & mapping parameters
    p.add_argument(
        "--width",
        type=int,
        default=1920,
        help="Image width in pixels (default: 1920).",
    )
    p.add_argument(
        "--height",
        type=int,
        default=1080,
        help="Image height in pixels (default: 1080).",
    )
    p.add_argument(
        "--bits_per_line",
        type=int,
        default=60,
        help="Number of payload bits per data row (default: 60).",
    )
    p.add_argument(
        "--num_lines",
        type=int,
        default=1080,
        help="Total number of rows per image (default: 1080).",
    )

    # Coding parameters
    p.add_argument(
        "--sync_bits",
        type=int,
        nargs="+",
        default=[1, 0, 1, 0],
        help="Sync bits placed before each data row (e.g., 1 0 1 0).",
    )
    p.add_argument(
        "--first_row_prefix",
        type=str,
        default="10101010000000",
        help="14-bit prefix for row 0 header (string of 0/1 characters).",
    )
    p.add_argument(
        "--on_value",
        type=int,
        default=255,
        help=(
            "Retained for backward compatibility with earlier versions that "
            "used full-intensity blocks for '1' bits. It is not used in the "
            "current blue-channel LSB embedding scheme. Must be in [0, 255]."
        ),
    )

    # Miscellaneous options
    p.add_argument(
        "--loglevel",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO).",
    )

    args = p.parse_args()

    # Basic validation of arguments.
    if not set(args.first_row_prefix).issubset({"0", "1"}):
        raise ValueError("first_row_prefix must be a binary string containing only '0' and '1'.")
    if len(args.first_row_prefix) != 14:
        logging.warning(
            "first_row_prefix length is %d (expected 14).",
            len(args.first_row_prefix),
        )
    if not (0 <= args.on_value <= 255):
        raise ValueError("on_value must be an integer in the range [0, 255].")

    logging.basicConfig(
        level=getattr(logging, args.loglevel.upper()),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    return args


def main():
    """
    Entry point for command-line usage.
    """
    cfg = parse_args()
    run(cfg)


if __name__ == "__main__":
    main()
