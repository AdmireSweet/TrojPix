# EM Covert Channel Decoder 

This module provides a **reference implementation** for decoding TrojPix frame-indexed payloads from complex IQ samples recorded by a USRP/SDR device.  
The decoding pipeline mirrors the evaluation methodology in the paper, and all default parameters match the experimental setup used for Artifact Evaluation (AE).

---

# 1. Decoding Pipeline Overview

The decoding process consists of the following stages:

1. **Load IQ Samples**  
   Read interleaved complex IQ data (`float32` by default) from a binary file.

2. **Compute Features**  
   Extract magnitude and wrapped phase-difference features, which provide stable EM indicators for row-level modulation.

3. **Frame-Head Alignment & Image-ID Verification**  
   Detect frame headers, synchronize to row boundaries, and validate the embedded image index.

4. **Row-Wise Bit Extraction**  
   Perform polarity detection and adaptive thresholding to recover the 60-bit payload per row.

5. **Result Output & Visualization (Optional)**  
   Save per-row decoded results, summary statistics, and optional plots for debugging/verification.

> **Note:** All parameter defaults replicate the exact settings used in our paper’s experiments.  
> For AE reproducibility, no randomness is introduced at any stage.

---

# 2. Installation

Install dependencies:

```bash
pip install -r requirements.txt
```

The decoder has been tested on Python 3.8+.

------

# 3. Basic Usage

The simplest invocation of the decoder is:

```
python decode.py \
    --iq_file ./data \
    --txt_folder ./txt \
    --img_dir ./img_result \
    --result_dir ./result
```

### Input Arguments

| Argument       | Description                                        |
| -------------- | -------------------------------------------------- |
| `--iq_file`    | Path to the IQ recording (`.bin` or directory)     |
| `--txt_folder` | Directory to store per-frame bit-dump TXT files    |
| `--img_dir`    | Directory for optional visualization outputs       |
| `--result_dir` | Directory for final decoding results (logs, stats) |

### Notes

- IQ data must be **interleaved float32 (I0, Q0, I1, Q1, …)** unless otherwise specified.
- The decoder automatically performs frame synchronization and row-level extraction.
- The output format is designed to match the encoding pipeline’s `N.txt` representation for bit-accurate comparison.

------

# 4. Output Files

The decoder produces:

- **Per-row bit-dump TXT files** (one per recovered frame)
- **Frame-level summaries** including:
  - detected frame index
  - confidence metrics
  - synchronization offsets
- **Optional plots** (magnitude traces, phase-diff signatures)
- **Aggregate statistics** summarizing:
  - recovered frame count
  - bit accuracy metrics
  - row-level confidence distributions

All outputs are deterministic and reproducible.

------

# 5. Reproducibility Notes

- The decoder operates without randomness.
- All thresholding and polarity decisions are **deterministically computed**.
- Output rows align exactly with the 60-bit-per-line format used in the encoder.
- Useful for validating EM captures or verifying encoding correctness.

------

# 6. License

This module is released under the **MIT License** and may be reused or modified with attribution.