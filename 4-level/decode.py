#!/usr/bin/env python3
"""Evaluate four-level decoding accuracy against row-wise binary references."""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import matplotlib.pyplot as plt
import numpy as np

LOGGER = logging.getLogger("four_color_evaluator")

SYNC_BITS = (1, 0, 1, 0)
CALIBRATION_SYMBOLS = (0, 1, 2, 3, 0, 1, 2, 3)

BITS_PER_ROW = 48
BITS_PER_SYMBOL = 2
DATA_SYMBOLS_PER_ROW = BITS_PER_ROW // BITS_PER_SYMBOL

SYMBOL_TO_BITS = {
    0: (0, 0),
    1: (0, 1),
    2: (1, 0),
    3: (1, 1),
}


@dataclass(frozen=True)
class DecoderConfig:
    """Acquisition and row-decoding parameters."""

    initial_position: int
    cell: int = 2
    row_length: int = 148
    rows: int = 1080
    shift_candidates: tuple[int, ...] = (5, 6, 7)
    diagnostic_rows: int = 20

    @property
    def data_start(self) -> int:
        return len(SYNC_BITS) + len(CALIBRATION_SYMBOLS)


@dataclass(frozen=True)
class RowDecodeResult:
    """Decoded symbols and row-local calibration metadata."""

    start: int
    polarity: int
    thresholds: tuple[float, float, float]
    symbols: tuple[int, ...]


class ReferencePayload:
    """Load and expose row-aligned reference bits and symbols."""

    def __init__(self, rows: Sequence[str]) -> None:
        self.rows = tuple(rows)
        self.symbol_rows = tuple(self._bits_to_symbols(row) for row in self.rows)
        self.bit_rows = tuple(tuple(int(bit) for bit in row) for row in self.rows)

    @classmethod
    def from_file(cls, path: Path, expected_rows: int) -> "ReferencePayload":
        rows = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]

        if len(rows) != expected_rows:
            raise ValueError(
                f"The reference file must contain exactly {expected_rows} lines; "
                f"received {len(rows)}."
            )

        for line_number, row in enumerate(rows, start=1):
            if len(row) != BITS_PER_ROW:
                raise ValueError(
                    f"Reference line {line_number} must contain exactly "
                    f"{BITS_PER_ROW} bits; received {len(row)}."
                )
            if any(bit not in "01" for bit in row):
                raise ValueError(
                    f"Reference line {line_number} contains non-binary characters."
                )

        return cls(rows)

    @staticmethod
    def _bits_to_symbols(bit_string: str) -> tuple[int, ...]:
        return tuple(
            int(bit_string[index : index + BITS_PER_SYMBOL], 2)
            for index in range(0, len(bit_string), BITS_PER_SYMBOL)
        )


class IQSignal:
    """Interleaved float32 IQ data with derived magnitude and phase-difference arrays."""

    def __init__(self, iq_path: Path) -> None:
        raw = np.fromfile(iq_path, np.float32)
        i_values, q_values = raw[0::2], raw[1::2]

        self.magnitude_values = np.hypot(i_values, q_values)
        self.phase_difference = np.abs(
            np.diff(np.unwrap(np.arctan2(q_values, i_values)))
        )

    def magnitude(self, index: int) -> float:
        if 0 <= index < len(self.magnitude_values):
            return float(self.magnitude_values[index])
        return 0.0

    def peak_near(self, position: int, window: int = 1) -> int:
        values = self.phase_difference
        lower = max(1, position - window)
        upper = min(len(values) - 2, position + window)
        scores = [
            (values[index - 1] - values[index])
            + (values[index + 1] - values[index])
            for index in range(lower, upper + 1)
        ]
        return lower + int(np.argmax(scores))


class FourLevelDecoder:
    """Decode one row using synchronization offset selection and four-level calibration."""

    def __init__(self, signal: IQSignal, config: DecoderConfig) -> None:
        self.signal = signal
        self.config = config

    def _select_start(self, position: int) -> int:
        # Keep the original fixed-position behavior. To enable local peak search,
        # replace the next line with:
        # peak = self.signal.peak_near(int(round(position)))
        peak = position

        best_score: float | None = None
        selected_shift: int | None = None

        for shift in self.config.shift_candidates:
            score = abs(
                self.signal.magnitude(peak + shift)
                - self.signal.magnitude(peak + shift + self.config.cell)
                + self.signal.magnitude(peak + shift + 2 * self.config.cell)
                - self.signal.magnitude(peak + shift + 3 * self.config.cell)
            )
            if best_score is None or score > best_score:
                best_score = score
                selected_shift = shift

        if selected_shift is None:
            raise RuntimeError("No synchronization shift candidate is available.")

        return peak + selected_shift

    def _estimate_levels(
        self,
        start: int,
        polarity: int,
    ) -> tuple[np.ndarray, tuple[float, float, float]]:
        training_values = [
            polarity * self.signal.magnitude(start + index * self.config.cell)
            for index in range(len(SYNC_BITS), self.config.data_start)
        ]

        levels = np.array(
            [
                np.mean([training_values[0], training_values[4]]),
                np.mean([training_values[1], training_values[5]]),
                np.mean([training_values[2], training_values[6]]),
                np.mean([training_values[3], training_values[7]]),
            ],
            dtype=float,
        )

        order = np.argsort(levels)
        sorted_levels = levels[order]
        thresholds = (
            (sorted_levels[0] + sorted_levels[1]) / 2.0,
            (sorted_levels[1] + sorted_levels[2]) / 2.0,
            (sorted_levels[2] + sorted_levels[3]) / 2.0,
        )

        inverse_map = np.empty(4, dtype=int)
        inverse_map[0] = int(order[0])
        inverse_map[1] = int(order[1])
        inverse_map[2] = int(order[2])
        inverse_map[3] = int(order[3])

        return inverse_map, thresholds

    def decode_row(self, position: int) -> RowDecodeResult:
        start = self._select_start(position)

        value0 = self.signal.magnitude(start)
        value1 = self.signal.magnitude(start + self.config.cell)
        polarity = 1 if value0 > value1 else -1

        inverse_map, thresholds = self._estimate_levels(start, polarity)
        decoded_symbols: list[int] = []

        for index in range(
            self.config.data_start,
            self.config.data_start + DATA_SYMBOLS_PER_ROW,
        ):
            normalized_value = polarity * self.signal.magnitude(
                start + index * self.config.cell
            )
            level_index = int(np.digitize(normalized_value, bins=thresholds))
            decoded_symbols.append(int(inverse_map[level_index]))

        return RowDecodeResult(
            start=start,
            polarity=polarity,
            thresholds=thresholds,
            symbols=tuple(decoded_symbols),
        )


class AccuracyEvaluator:
    """Run row-wise decoding, compare with the reference, and emit diagnostics."""

    def __init__(
        self,
        signal: IQSignal,
        reference: ReferencePayload,
        config: DecoderConfig,
    ) -> None:
        self.signal = signal
        self.reference = reference
        self.config = config
        self.decoder = FourLevelDecoder(signal, config)

    @staticmethod
    def symbols_to_bits(symbols: Sequence[int]) -> list[int]:
        bits: list[int] = []
        for symbol in symbols:
            bit0, bit1 = SYMBOL_TO_BITS[int(symbol)]
            bits.extend((bit0, bit1))
        return bits

    def _save_diagnostic_plot(
        self,
        row_index: int,
        result: RowDecodeResult,
        symbol_matches: int,
        bit_matches: int,
        plot_dir: Path,
    ) -> None:
        sample_indices = np.arange(self.config.cell * 60)
        plt.figure(figsize=(12, 4))
        plt.plot(
            sample_indices,
            [self.signal.magnitude(result.start + index) for index in sample_indices],
            c="royalblue",
            lw=1,
            label="Mag",
        )

        symbol_x = np.arange(60) * self.config.cell
        symbol_y = [
            self.signal.magnitude(result.start + index * self.config.cell)
            for index in range(60)
        ]
        plt.scatter(symbol_x, symbol_y, c="red", s=16)

        epsilon = 1e-12
        for threshold in result.thresholds:
            plt.axhline(
                y=threshold / (result.polarity + epsilon),
                ls="--",
                lw=1,
                alpha=0.5,
            )

        plt.title(
            f"Row {row_index:03d} start={result.start} "
            f"sym_ok={symbol_matches}/{DATA_SYMBOLS_PER_ROW} "
            f"bit_ok={bit_matches}/{BITS_PER_ROW}"
        )
        plt.grid(alpha=0.3, ls="--")
        plt.tight_layout()
        plt.savefig(plot_dir / f"row_{row_index:03d}.png")
        plt.close()

    def evaluate(self, output_file: Path, plot_dir: Path) -> None:
        plot_dir.mkdir(parents=True, exist_ok=True)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        position = self.config.initial_position
        output_rows: list[str] = []
        total_symbol_matches = 0
        total_bit_matches = 0

        for row_index in range(self.config.rows):
            result = self.decoder.decode_row(position)
            expected_symbols = self.reference.symbol_rows[row_index]

            symbol_matches = sum(
                int(decoded == expected)
                for decoded, expected in zip(result.symbols, expected_symbols)
            )
            if symbol_matches != DATA_SYMBOLS_PER_ROW:
                LOGGER.info("Row %d: %d symbols matched.", row_index, symbol_matches)
            total_symbol_matches += symbol_matches

            decoded_bits = self.symbols_to_bits(result.symbols)
            expected_bits = self.reference.bit_rows[row_index]
            bit_matches = sum(
                int(decoded == expected)
                for decoded, expected in zip(decoded_bits, expected_bits)
            )
            total_bit_matches += bit_matches

            if row_index < self.config.diagnostic_rows:
                self._save_diagnostic_plot(
                    row_index,
                    result,
                    symbol_matches,
                    bit_matches,
                    plot_dir,
                )

            decoded_bit_string = "".join(map(str, decoded_bits))
            output_rows.append(
                f"{row_index:04d}, "
                f"{''.join(map(str, SYNC_BITS))}{decoded_bit_string}, "
                f"sym:{symbol_matches}/{DATA_SYMBOLS_PER_ROW}, "
                f"bit:{bit_matches}/{BITS_PER_ROW}"
            )

            position = result.start + self.config.row_length - 6

        output_file.write_text("\n".join(output_rows), encoding="utf-8")

        total_symbols = self.config.rows * DATA_SYMBOLS_PER_ROW
        total_bits = self.config.rows * BITS_PER_ROW
        symbol_accuracy = total_symbol_matches / total_symbols
        bit_accuracy = total_bit_matches / total_bits

        LOGGER.info(
            "Symbol accuracy: %.4f%% (%d/%d)",
            symbol_accuracy * 100.0,
            total_symbol_matches,
            total_symbols,
        )
        LOGGER.info(
            "Bit accuracy: %.4f%% (%d/%d)",
            bit_accuracy * 100.0,
            total_bit_matches,
            total_bits,
        )
        LOGGER.info(
            "Evaluation complete: result file and %d diagnostic plot(s) generated.",
            min(self.config.diagnostic_rows, self.config.rows),
        )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Decode four-level IQ measurements and compare each recovered row "
            "with the corresponding 48-bit reference line."
        )
    )
    parser.add_argument(
        "--iq-file",
        type=Path,
        required=True,
        help="Interleaved float32 IQ sample file.",
    )
    parser.add_argument(
        "--reference",
        type=Path,
        required=True,
        help="Text file containing one 48-bit binary reference per row.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Text file to receive row-wise decoding results.",
    )
    parser.add_argument(
        "--plot-dir",
        type=Path,
        required=True,
        help="Directory to receive diagnostic plots.",
    )
    parser.add_argument(
        "--initial-position",
        type=int,
        required=True,
        help="Initial sample position used by the row synchronization logic.",
    )
    parser.add_argument("--cell", type=int, default=2, help="Samples per symbol cell.")
    parser.add_argument(
        "--row-length",
        type=int,
        default=148,
        help="Sample-domain row advance parameter.",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=1080,
        help="Number of rows to decode and compare.",
    )
    parser.add_argument(
        "--diagnostic-rows",
        type=int,
        default=20,
        help="Number of leading rows for which diagnostic plots are generated.",
    )
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    args = build_argument_parser().parse_args()

    config = DecoderConfig(
        initial_position=args.initial_position,
        cell=args.cell,
        row_length=args.row_length,
        rows=args.rows,
        diagnostic_rows=args.diagnostic_rows,
    )
    reference = ReferencePayload.from_file(args.reference, config.rows)
    signal = IQSignal(args.iq_file)
    evaluator = AccuracyEvaluator(signal, reference, config)
    evaluator.evaluate(args.output, args.plot_dir)


if __name__ == "__main__":
    main()
