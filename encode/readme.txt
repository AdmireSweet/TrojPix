This repository provides a reproducible end-to-end pipeline for converting a UTF-8 text file into bit-embedded 1080p PNG images, packaging them into a lossless FFV1/MKV video, and playing the resulting video deterministically. The toolkit is designed for Artifact Evaluation (AE), reproducible EM-based experiments, and general research on low-visibility pixel modulation.

The toolkit contains three standalone Python scripts:

(1) encode.py Text → bitstream → embedded PNG frames

(2) video_from_images.py PNG sequence → lossless FFV1/MKV video

(3) video_player.py Deterministic video playback (OpenCV)

All components are deterministic, transparent, and easy to verify during AE.

1. Requirements

Python 3.8 or newer

Install required packages:
pip install numpy pillow opencv-python

2. Pipeline Overview

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


Summary of script functions:

encode.py
Converts a UTF-8 text file into 1920x1080 PNG frames containing embedded bits using blue-channel LSB encoding.
Also outputs a .bin copy of the raw bytes and per-frame bit-dump files (N.txt), each line containing exactly 60 bits.

video_from_images.py
Converts PNG frames into a lossless FFV1/MKV video.
Ensures natural filename ordering (2.png before 10.png) and pixel-accurate preservation.

video_player.py
Plays the MKV file frame-by-frame using OpenCV.
Supports fullscreen and deterministic timing based on FPS.

3. encode.py — Text to Embedded PNG Frames

Purpose:
Embed bits into a 1920×1080 image grid using blue-channel LSB encoding.
Each image stores a block of bits defined by:
BITS_PER_LINE × (NUM_LINES − 1)

Embedding logic:
Row 0:
14-bit prefix + 11-bit image index
Rows 1..(NUM_LINES−1):
SYNC_BITS followed by BITS_PER_LINE data bits
Logical 1:
Set the lowest two bits of the blue channel (LSB2) to 1
Logical 0:
Leave template pixels unchanged

Outputs per image N:
N.png (encoded frame)
N.txt (ground-truth bits; each line padded to 60 bits)

Also outputs:
message.bin (raw bytes of the input text)

Usage:
python encode.py
--txt_input message.txt
--bin_output message.bin
--txt_output_dir out/txt
--img_template template_1920x1080.png
--img_output_dir out/img
--width 1920 --height 1080
--bits_per_line 60
--num_lines 1080
--sync_bits 1 0 1 0
--first_row_prefix 10101010000000

Example: python encode.py --txt_input dataset/text8_1MB.txt --bin_output 1MB/output.bin --txt_output_dir 1MB/txt --img_template black.png --img_output_dir 1MB/img

Key parameters:
--txt_input UTF-8 text file to encode
--bin_output Raw output .bin file
--img_template PNG template image (e.g., 1920×1080)
--img_output_dir Directory for output encoded PNGs
--txt_output_dir Directory for per-frame bit text files
--bits_per_line Bits stored per row (default 60)
--sync_bits Synchronization bits for each data row
--first_row_prefix 14-bit header prefix
--on_value Legacy parameter (unused in LSB encoding)
--loglevel DEBUG / INFO / WARNING / ERROR

4. video_from_images.py — PNG Frames to FFV1/MKV

Purpose:
Produce a pixel-perfect, lossless video suitable for EM measurements and AE reproduction.

Features:
Natural filename ordering
Automatic resizing to target resolution
Lossless FFV1 codec in MKV container
Deterministic frame order

Usage:
python video_from_images.py
--image_dir out/img
--output out/1M.mkv
--fps 60
--width 1920
--height 1080
--repeat 1

Example: 
python video_from_images.py --image_dir 1MB/img --output 1MB.mkv --fps 60 --width 1920 --height 1080 --repeat 1

Parameters:
--image_dir Directory of PNG images
--output Output MKV path
--fps Frames per second
--width, --height Output resolution
--repeat Repeat each frame N times
--pattern Default: *.png
--loglevel Logging verbosity

5. video_player.py — Deterministic Playback

Purpose:
Provide reproducible playback behavior for demonstrations and AE.

Features:
Reads FPS from video header (fallback: 60 FPS)
Optional fullscreen
ESC key to exit
Logs frame counts and exit reason

Usage:
python video_player.py
--video out/1MB.mkv
--fullscreen
--window_name TrojPixPlayer

Example:
python video_player.py --video 1MB.mkv --fullscreen --window_name TrojPixPlayer

Parameters:
--video Input MKV/MP4/video file
--fullscreen Enable fullscreen mode
--window_name Playback window title
--loglevel Logging verbosity

6. Example End-to-End Workflow

Step 1: Prepare inputs
- A UTF-8 text file (message.txt)
- A template PNG image (template_1920x1080.png)

Step 2: Encode the text into PNG frames
python encode.py
--txt_input message.txt
--bin_output message.bin
--txt_output_dir out/txt
--img_template template_1920x1080.png
--img_output_dir out/img

Step 3: Convert PNG frames into a lossless FFV1 video
python video_from_images.py
--image_dir out/img
--output out/1M.mkv

Step 4: Play the video deterministically
python video_player.py
--video out/1M.mkv

7. Reproducibility Notes

No randomness is used anywhere; outputs are fully deterministic.

FFV1 ensures exact pixel preservation of LSB encodings.

Each frame has an explicit bit-dump file for verification.

Only the blue channel’s lowest two bits are modified, keeping images visually clean.

8. License

This project is released under the MIT License.
You may use, modify, and redistribute the code with appropriate attribution.