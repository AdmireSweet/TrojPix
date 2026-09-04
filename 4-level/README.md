# Four-Color Stripe Encoding and Decoding Evaluation

This repository provides a compact reference implementation for generating four-color stripe patterns from row-wise binary payloads and evaluating recovered IQ measurements against the original payload.

The code is intentionally data-agnostic: no experiment files, dataset paths, or captured measurements are included. Users provide all input and output locations through command-line arguments.

## Overview

The pipeline contains two stages:

1. **Stripe generation**: read one 48-bit binary payload per text line and embed the corresponding payload into one image row.
2. **Decoding evaluation**: recover four-level symbols from an interleaved float32 IQ capture and compare each decoded row with the matching line in the reference text file.

The synchronization, four-level calibration, thresholding, polarity handling, and row-advance logic are kept consistent between the encoder and evaluator.

## Repository layout

```text
generate_4color_stripes.py
evaluate_4color_decode.py
README.md
```

No payload file, source image, generated image, IQ capture, or evaluation output is distributed with the code.

## Requirements

Python 3.9 or newer is recommended.

```bash
pip install numpy pillow matplotlib
```

## Payload format

Prepare a plain-text file containing exactly one 48-bit binary string per line.

```text
<48 binary bits for row 0>
<48 binary bits for row 1>
<48 binary bits for row 2>
...
```

For the default 1920x1080 setup, the payload contains 1080 lines because each image row carries its own 48-bit value.

Each pair of bits is converted to one four-level symbol:

| Bits | Symbol |
| --- | ---: |
| `00` | 0 |
| `01` | 1 |
| `10` | 2 |
| `11` | 3 |

A 48-bit row therefore produces 24 data symbols.

## Encoded row structure

Each encoded image row follows:

```text
[SYNC][CALIBRATION][DATA]
```

where:

- `SYNC` is the four-bit pattern `1010`.
- `CALIBRATION` is the fixed four-level sequence `0, 1, 2, 3, 0, 1, 2, 3`.
- `DATA` contains 24 four-level symbols converted from the row's 48-bit payload.

The calibration sequence is separate from the payload because the decoder uses the eight known calibration symbols to estimate the four amplitude levels before classifying the data symbols.

## 1. Generate stripe images

Prepare:

- a payload text file in the format above;
- a directory containing the source PNG images;
- an empty or writable output directory.

Run:

```bash
python generate_4color_stripes.py \
  --payload <payload-file> \
  --input-dir <source-image-directory> \
  --output-dir <encoded-image-directory>
```

The generator preserves the original implementation's default 1920x1080 image requirement and produces one encoded PNG for each valid source PNG.

An alternative output-name suffix can be selected with:

```bash
--output-suffix <suffix>
```

## 2. Evaluate decoding accuracy

Prepare:

- the interleaved float32 IQ capture;
- the same row-wise 48-bit payload used during encoding;
- a destination for the text results;
- a directory for diagnostic plots;
- the initial sample position determined for the capture.

Run:

```bash
python evaluate_4color_decode.py \
  --iq-file <iq-capture> \
  --reference <payload-file> \
  --output <result-file> \
  --plot-dir <diagnostic-plot-directory> \
  --initial-position <sample-index>
```

For row `k`, the evaluator compares the recovered 48 bits with line `k` of the reference payload.

The evaluator reports:

- symbol accuracy over the 24 recovered four-level symbols per row;
- bit accuracy over the 48 recovered bits per row;
- mismatch information for imperfect rows;
- diagnostic plots for the first configured rows.

## Acquisition-specific parameters

The decoder exposes the main acquisition-dependent values as command-line options instead of embedding dataset-specific paths or file names in the source code.

```text
--initial-position   Initial sample position for synchronization
--cell               Samples per symbol cell
--row-length         Sample-domain row advance parameter
--rows               Number of rows to decode
--diagnostic-rows    Number of leading rows to visualize
```

Use `--help` to inspect all available arguments:

```bash
python generate_4color_stripes.py --help
python evaluate_4color_decode.py --help
```

## Notes

- The encoder and evaluator must use the same payload file.
- Each payload line must contain exactly 48 characters and may contain only `0` and `1`.
- The default image geometry is 1920x1080.
- The default evaluator processes 1080 rows.
- The fixed calibration prefix is required by the existing four-level amplitude estimation logic and should not be removed unless the decoder is redesigned accordingly.
- The repository contains implementation logic only; experimental data and capture files are intentionally excluded.
