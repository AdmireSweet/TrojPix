# TrojPix – Artifact 

This repository contains the source code, datasets, and reproduction instructions for the paper **“Covert Channels via Electromagnetic Emissions from Digital Video Cables”**, submitted to **IEEE Transactions on Mobile Computing (TMC)**.

---

## Overview

This artifact demonstrates how carefully crafted video frames—when played in full screen on a display—induce controllable electromagnetic leakage from a video cable.

By encoding binary data into pixel-level LSB modulations, **TrojPix enables high-speed, stealthy electromagnetic communication** without system privileges or hardware modifications.

This package contains:

- Image encoding scripts  
- EM signal decoding scripts
- A four-level modulation implementation  
- Example pictures and datasets collected using USRP-based EM receivers  

The workflow reproduces the full TrojPix pipeline:

**text → bitstream → encoded images → video → EM leakage capture → decoding**

---

## Hardware Requirements

### Transmitter Side (Video Leakage Source)

- A computer connected to a monitor/projector via **HDMI cable**
- Display resolution: **1920×1080 @ 60 Hz** (fixed requirement)
- **Fullscreen playback** of the encoded video frames

### Receiver Side (EM Capture System)

- **USRP / SDR device** capable of capturing EM leakage at the clock rate and its harmonics  
  *(In our experiments: USRP X310 with a directional antenna)*
- Host PC for recording baseband IQ samples
- **Sampling rate ≥ 5 MS/s recommended**

---

## Repository Structure

```plaintext
/encode/        → Image & video encoding scripts
/decode/        → EM-sampled signal decoding scripts
/4-level/
/examples/      → Example pictures and sampling data
license.txt
readme.txt
```



# 1. Encoding Module

Located in `/encode/`.  **For more detailed instructions and explanations, please see the README files located in the corresponding subdirectories.**

These scripts generate pixel-encoded frames and convert them into a lossless video used in the covert channel attack.

---

## Files

### **encode.py**

Converts a UTF-8 text file into binary, embeds bits into **1920×1080 RGB frames** using the blue-channel LSB method, and outputs:

- Encoded PNG frames  
- Corresponding bit-dump TXT files  
- A `.bin` copy of raw input bytes  

---

### **video_from_images.py**

Converts PNG frames into a **MKV/AVI video** so that LSB-level modifications remain intact during playback.

---

### **video_player.py**

Deterministic OpenCV-based full screen playback with a fixed frame delay derived from the video’s FPS.

---

## Typical Workflow

```bash
python encode.py ...
python video_from_images.py ...
python video_player.py ...
```

# 2. Decoding Module

Located in `/decode/`. **For more detailed instructions and explanations, please see the README files located in the corresponding subdirectories.**

These scripts decode TrojPix-encoded data from electromagnetic (EM) leakage captured by a USRP device.

---

## Files

### **decode.py**

Given raw IQ samples (USRP recordings), performs the following steps:

- **Band-pass filtering**
- **Frame synchronization**
- **Bit extraction**
- **Reconstruction of the transmitted bitstream**
- **Reassembly into UTF-8 text**

---

### **requirements.txt**

Python dependencies required for decoding.

---

### **sampling_results/**

Example EM capture outputs recorded during experiments.

---

### **txt/**

Intermediate decoded bitstreams.

---

## Expected Inputs

- IQ samples stored as `.bin` or `.npy`
- Sampling rate metadata
- Known frame-encoding structure from the `/encode/` module

---

# 3. Four-Level Modulation Module

Located in `4-level/`.

This module provides an alternative four-level modulation scheme used by TrojPix. Instead of representing each transmitted symbol using two amplitude levels, the encoder maps every two payload bits to one of four pixel-induced signal levels.

The mapping is:

| Bits | Symbol |
|------|--------|
| `00` | 0 |
| `01` | 1 |
| `10` | 2 |
| `11` | 3 |

## Files

### `encode.py`

Reads binary payloads from a TXT file and embeds them into image rows using four-level pixel modulation.

Each line of the input TXT file contains a 48-bit binary sequence and corresponds to one image row.

### `decode.py`

Decodes the four-level symbols from captured IQ samples and compares the recovered payload of each row against the corresponding line in the reference TXT file.

The decoder reports both symbol-level and bit-level accuracy.

For implementation details, input formats, and command-line usage, see `4-level/README.md`.

# 4. Examples Module

Located in `/examples/`.

---

## Contents

### **/pictures/**

Example encoded frames used in demonstrations and debugging.

### **/data/**

Example raw EM captures collected using **USRP X310**.

These examples allow reviewers to test the decoding pipeline **without capturing their own EM signals**.

---

# EM Capture Workflow (USRP)

1. Configure USRP center frequency to match leakage band *(typical: 148.5MHz and its harmonic)*  
2. Set sampling rate *(5, 10, 15, 20 MS/s recommended)*  
3. Set bandwidth *(corresponding to sampling rate)*  
4. Record baseband IQ while the encoded video plays in full screen  
5. Pass IQ samples to `/decode/decode.py`

---



## Notes for Accurate Reproduction

- **Display must be set to 1920×1080 @ 60 Hz**  
  - Many monitors default to 59.94 Hz; explicitly set to 60.00 Hz
- **Video playback must be fullscreen**  
  - Windowed playback significantly alters leakage amplitude
- **Leakage intensity drift is common**  

---

## 4. Recommended USRP Configuration 

For reviewers who wish to reproduce EM capture without manual tuning, we recommend the following default USRP settings used in our experiments:

- **Center Frequency:** 148.5 MHz / 891MHz / 1039MHz / ...
- **Sampling Rate:** 10 M
- **Bandwidth:** 10 M
- **Gain:** 20-40 dB  
- **Antenna:** High-gain directional antenna  
- **Sample Format:** Complex IQ (`float32` or `int16`)  
- **Recording Duration:** Same as encoded video duration  
- **GNU Radio Version:** GNU Radio 3.8.5.0

### Example UHD Command (USRP X310)

```bash
uhd_rx_cfile --freq 148e6 --rate 10e6 --gain 35 --duration 10 --file usrp_samples.dat
```



These defaults match the datasets found in:

- `/examples/data/`
- `/decode/sampling_results/`

---

## License

This artifact is released under the **MIT License**.  
See `license` for details.

---

## Contact

For any questions, please contact:

**zhanghuiting@mail.sdu.edu.cn**