#!/usr/bin/env python3
"""Generate four-color stripe images from row-wise binary payloads."""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image

LOGGER = logging.getLogger("four_color_encoder")

BITS_PER_ROW = 48
BITS_PER_SYMBOL = 2
SYNC_PATTERN = "1010"
SYNC_BITS = tuple(int(bit) for bit in SYNC_PATTERN)
CALIBRATION_SYMBOLS = (0, 1, 2, 3, 0, 1, 2, 3)

SAMPLES_PER_SYMBOL = 2
SAMPLE_RATE = 10e6
PIXEL_CLOCK = 148236488
IDEAL_PIXELS_PER_SYMBOL = SAMPLES_PER_SYMBOL * PIXEL_CLOCK / SAMPLE_RATE
MAX_SYMBOLS_AFTER_SYNC = 52

EXPECTED_WIDTH = 1920
EXPECTED_HEIGHT = 1080
DEFAULT_OUTPUT_SUFFIX = "-10M.png"


@dataclass(frozen=True)
class EncoderConfig:
    """Static parameters used by the four-color stripe encoder."""

    bits_per_row: int = BITS_PER_ROW
    bits_per_symbol: int = BITS_PER_SYMBOL
    ideal_pixels_per_symbol: float = IDEAL_PIXELS_PER_SYMBOL
    max_symbols_after_sync: int = MAX_SYMBOLS_AFTER_SYNC
    expected_width: int = EXPECTED_WIDTH
    expected_height: int = EXPECTED_HEIGHT

    @property
    def data_symbols_per_row(self) -> int:
        return self.bits_per_row // self.bits_per_symbol


class PayloadCodec:
    """Validation and binary-to-four-level conversion utilities."""

    @staticmethod
    def load_rows(path: Path, bits_per_row: int) -> list[str]:
        rows = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]

        if not rows:
            raise ValueError("The payload file is empty.")

        for line_number, row in enumerate(rows, start=1):
            if len(row) != bits_per_row:
                raise ValueError(
                    f"Payload line {line_number} must contain exactly "
                    f"{bits_per_row} bits; received {len(row)}."
                )
            if any(bit not in "01" for bit in row):
                raise ValueError(
                    f"Payload line {line_number} contains non-binary characters."
                )

        return rows

    @staticmethod
    def bits_to_symbols(bit_string: str, bits_per_symbol: int = BITS_PER_SYMBOL) -> list[int]:
        if len(bit_string) % bits_per_symbol != 0:
            raise ValueError("The bit-string length must be divisible by the symbol width.")

        return [
            int(bit_string[index : index + bits_per_symbol], 2)
            for index in range(0, len(bit_string), bits_per_symbol)
        ]


class FourColorStripeEncoder:
    """Embed synchronization, calibration, and payload symbols into image rows."""

    def __init__(self, config: EncoderConfig | None = None) -> None:
        self.config = config or EncoderConfig()

    def _calculate_groups(self, width: int) -> list[tuple[int, int]]:
        position = 0.0
        previous = 0
        groups: list[tuple[int, int]] = []

        while previous < width:
            position += self.config.ideal_pixels_per_symbol
            current = min(int(round(position)), width)
            groups.append((previous, current))
            previous = current

        return groups

    @staticmethod
    def _apply_symbol(
        frame: np.ndarray,
        row: int,
        col_start: int,
        col_end: int,
        symbol: int,
    ) -> None:
        if symbol == 1:
            frame[row, col_start:col_end, 2] = 1
        elif symbol == 2:
            frame[row, col_start:col_end, 0] = 1
            frame[row, col_start:col_end, 1] = 1
        elif symbol == 3:
            frame[row, col_start:col_end, 0] = 1

    def encode(self, frame: np.ndarray, payload_rows: Sequence[str]) -> np.ndarray:
        height, width, _ = frame.shape
        assert height % 2 == 0, "Image height must be even."

        if len(payload_rows) != height:
            raise ValueError(
                f"The payload must contain exactly one line per image row: "
                f"expected {height}, received {len(payload_rows)}."
            )

        groups = self._calculate_groups(width)
        sync_count = len(SYNC_BITS)
        calibration_count = len(CALIBRATION_SYMBOLS)
        data_count = self.config.data_symbols_per_row
        symbols_after_sync = calibration_count + data_count

        if symbols_after_sync > self.config.max_symbols_after_sync:
            raise ValueError(
                f"Calibration and payload require {symbols_after_sync} symbols after sync, "
                f"exceeding the configured limit of {self.config.max_symbols_after_sync}."
            )

        required_groups = sync_count + symbols_after_sync
        if required_groups > len(groups):
            raise ValueError(
                f"The image width provides {len(groups)} symbol groups, "
                f"but {required_groups} are required."
            )

        calibration_end = sync_count + calibration_count
        data_end = calibration_end + data_count
        output = frame.copy()

        for row in range(height):
            data_symbols = PayloadCodec.bits_to_symbols(
                payload_rows[row],
                self.config.bits_per_symbol,
            )

            for group_index, (col_start, col_end) in enumerate(groups):
                if group_index < sync_count:
                    if SYNC_BITS[group_index] == 1:
                        output[row, col_start:col_end, 0] = 1
                    continue

                if group_index < calibration_end:
                    symbol = CALIBRATION_SYMBOLS[group_index - sync_count]
                elif group_index < data_end:
                    symbol = data_symbols[group_index - calibration_end]
                else:
                    continue

                self._apply_symbol(output, row, col_start, col_end, symbol)

        return output

    def process_directory(
        self,
        input_dir: Path,
        output_dir: Path,
        payload_rows: Sequence[str],
        output_suffix: str,
    ) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)

        processed = 0
        for source_path in sorted(input_dir.glob("*.png")):
            image = Image.open(source_path).convert("RGB")
            frame = np.asarray(image, dtype=np.uint8)

            if frame.shape[:2] != (
                self.config.expected_height,
                self.config.expected_width,
            ):
                LOGGER.warning(
                    "Skipping %s: expected %dx%d image.",
                    source_path.name,
                    self.config.expected_width,
                    self.config.expected_height,
                )
                continue

            encoded = self.encode(frame, payload_rows)
            output_path = output_dir / f"{source_path.stem}{output_suffix}"
            Image.fromarray(encoded, mode="RGB").save(output_path, compress_level=0)
            LOGGER.info("Saved %s", output_path.name)
            processed += 1

        LOGGER.info("Processing complete: %d image(s) generated.", processed)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Embed one 48-bit payload line into each row of every PNG image in a directory."
        )
    )
    parser.add_argument(
        "--payload",
        type=Path,
        required=True,
        help="Text file containing one 48-bit binary payload per line.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="Directory containing source PNG images.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory in which encoded PNG images will be written.",
    )
    parser.add_argument(
        "--output-suffix",
        default=DEFAULT_OUTPUT_SUFFIX,
        help=f"Suffix appended to generated image names (default: {DEFAULT_OUTPUT_SUFFIX}).",
    )
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    args = build_argument_parser().parse_args()

    config = EncoderConfig()
    payload_rows = PayloadCodec.load_rows(args.payload, config.bits_per_row)
    encoder = FourColorStripeEncoder(config)
    encoder.process_directory(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        payload_rows=payload_rows,
        output_suffix=args.output_suffix,
    )


if __name__ == "__main__":
    main()
