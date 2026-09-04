# TrojPix Encoding & Playback Toolkit

This repository provides a reproducible end-to-end pipeline for converting a UTF-8 text file into bit-embedded 1080p PNG images, packaging them into a lossless FFV1/MKV video, and playing the resulting video deterministically. The toolkit is designed for **Artifact Evaluation (AE)**, reproducible EM-based experiments, and general research on low-visibility pixel modulation.

The toolkit contains three standalone Python scripts:

1. **encode.py** — Text → bitstream → embedded PNG frames  
2. **video_from_images.py** — PNG sequence → lossless FFV1/MKV video  
3. **video_player.py** — Deterministic video playback (OpenCV)

All components are deterministic, transparent, and easy to verify during AE.

---

# 1. Requirements

- Python 3.8 or newer

Install required packages:

```bash
pip install numpy pillow opencv-python
```

# 2. Pipeline Overview

The complete workflow is:

UTF-8 Text
 ↓
 Bitstream
 ↓
 Embedded PNG Frames
 ↓
 FFV1/MKV Video
 ↓
 Deterministic Playback

```
---

## Summary of Script Functions

### **encode.py**
Converts a UTF-8 text file into **1920×1080 PNG frames** containing embedded bits using **blue-channel LSB encoding**.

Produces:
- `N.png` — encoded image frames  
- `N.txt` — per-frame bit-dump files (each line padded to 60 bits)  
- `message.bin` — raw bytes of the input text  

---

### **video_from_images.py**
- Converts PNG frames into a **lossless FFV1/MKV** video.  
- Ensures natural filename ordering (`2.png` before `10.png`).  
- Guarantees pixel-accurate preservation.

---

### **video_player.py**
- Plays the MKV file frame-by-frame using OpenCV.  
- Supports fullscreen mode.  
- Provides deterministic timing based on FPS.

---

# 3. `encode.py` — Text to Embedded PNG Frames

## **Purpose**
Embed bits into a **1920×1080** image grid using blue-channel LSB encoding.

Each image stores:
```

BITS_PER_LINE × (NUM_LINES − 1) bits

```
---

## **Embedding Logic**

### **Row 0**
- 14-bit prefix  
- 11-bit image index  

### **Rows 1 .. (NUM_LINES−1)**
- `SYNC_BITS`  
- `BITS_PER_LINE` data bits  

### **Bit Encoding Rule**
- **Logical 1** → set lowest two bits of blue channel (**LSB2 = 1**)  
- **Logical 0** → leave template pixels unchanged  

---

## Outputs Per Image N
- `N.png` — encoded frame  
- `N.txt` — ground-truth bits (each row padded to 60 bits)

## Additional Output
- `message.bin` — raw bytes of the input text  

---

## **Usage**

```bash
python encode.py \
    --txt_input message.txt \
    --bin_output message.bin \
    --txt_output_dir out/txt \
    --img_template template_1920x1080.png \
    --img_output_dir out/img \
    --width 1920 \
    --height 1080 \
    --bits_per_line 60 \
    --num_lines 1080 \
    --sync_bits 1 0 1 0 \
    --first_row_prefix 10101010000000
```

------

## **Example**

```
python encode.py \
    --txt_input dataset/text8_1MB.txt \
    --bin_output 1MB/output.bin \
    --txt_output_dir 1MB/txt \
    --img_template black.png \
    --img_output_dir 1MB/img
```

------

## **Key Parameters**

| Parameter            | Description                                   |
| -------------------- | --------------------------------------------- |
| `--txt_input`        | UTF-8 text file to encode                     |
| `--bin_output`       | Raw output `.bin` file                        |
| `--img_template`     | PNG template image (e.g., 1920×1080)          |
| `--img_output_dir`   | Directory for encoded PNGs                    |
| `--txt_output_dir`   | Directory for bit-dump files                  |
| `--bits_per_line`    | Bits stored per row (default: 60)             |
| `--sync_bits`        | Synchronization bits per row                  |
| `--first_row_prefix` | 14-bit frame header prefix                    |
| `--on_value`         | Legacy parameter (unused)                     |
| `--loglevel`         | Logging level: DEBUG / INFO / WARNING / ERROR |

------

# 4. `video_from_images.py` — PNG Frames to FFV1/MKV

## **Purpose**

Produce a **pixel-perfect, lossless video** suitable for EM measurements and AE reproduction.

------

## **Features**

- Natural filename ordering
- Automatic resizing to target resolution
- Lossless FFV1 codec in MKV container
- Deterministic frame ordering

------

## **Usage**

```
python video_from_images.py \
    --image_dir out/img \
    --output out/1M.mkv \
    --fps 60 \
    --width 1920 \
    --height 1080 \
    --repeat 1
```

------

## **Example**

```
python video_from_images.py \
    --image_dir 1MB/img \
    --output 1MB.mkv \
    --fps 60 \
    --width 1920 \
    --height 1080 \
    --repeat 1
```

------

## **Parameters**

| Parameter             | Description                         |
| --------------------- | ----------------------------------- |
| `--image_dir`         | Directory containing PNG frames     |
| `--output`            | Output MKV path                     |
| `--fps`               | Frames per second                   |
| `--width`, `--height` | Output resolution                   |
| `--repeat`            | Repeat each frame N times           |
| `--pattern`           | Filename pattern (default: `*.png`) |
| `--loglevel`          | Logging verbosity                   |

------

# 5. `video_player.py` — Deterministic Playback

## **Purpose**

Provide reproducible playback behavior for demonstrations and AE.

------

## **Features**

- Reads FPS from video header (fallback: 60 FPS)
- Optional fullscreen mode
- ESC key to exit
- Logs frame counts and exit reason

------

## **Usage**

```
python video_player.py \
    --video out/1M.mkv \
    --fullscreen \
    --window_name TrojPixPlayer
```

------

## **Example**

```
python video_player.py \
    --video 1MB.mkv \
    --fullscreen \
    --window_name TrojPixPlayer
```

------

## **Parameters**

| Parameter       | Description                |
| --------------- | -------------------------- |
| `--video`       | Input MKV / MP4 file       |
| `--fullscreen`  | Enable fullscreen playback |
| `--window_name` | Playback window title      |
| `--loglevel`    | Logging verbosity          |

------

# 6. Example End-to-End Workflow

### **Step 1 — Prepare Inputs**

- `message.txt` — UTF-8 text file
- `template_1920x1080.png` — template PNG image

------

### **Step 2 — Encode Text into PNG Frames**

```
python encode.py \
    --txt_input message.txt \
    --bin_output message.bin \
    --txt_output_dir out/txt \
    --img_template template_1920x1080.png \
    --img_output_dir out/img
```

------

### **Step 3 — Convert PNG Frames into FFV1 Video**

```
python video_from_images.py \
    --image_dir out/img \
    --output out/1M.mkv
```

------

### **Step 4 — Deterministic Playback**

```
python video_player.py \
    --video out/1M.mkv
```

------

# 7. Reproducibility Notes

- No randomness is used anywhere; **all outputs are deterministic**.
- FFV1 ensures **exact pixel preservation** for LSB encodings.
- Each frame includes a matching bit-dump file (`N.txt`).
- Only the **blue channel’s lowest two bits** are modified, keeping images visually clean.

------

# 8. License

This project is released under the **MIT License**.
 You may use, modify, and redistribute the code with appropriate attribution.