"""Extract stills from an air-side waybeam recording (MPEG-TS) to compare with Quest stills (quality_shots.sh).

Usage: python3 air_frame.py <rec.ts> <out_prefix> [n=3]
Saves n evenly spaced decodable frames as <out_prefix>-<i>.jpg (longest side <= 1600 px) and prints
"<frame index> <file>" per still. The air recording is the exact bitstream the encoder sent, so any artifact seen on the
Quest but not here comes from the link or the decoder, not the encoder.

Getting the recording (waybeam refuses a directory with < 50 MiB free, star6e_recorder.h:14 @ f8742fe; /tmp on the
air has ~45 MB), runtime only:
  mkdir -p /tmp/rec && mount -t tmpfs -o size=64m tmpfs /tmp/rec
  wget -qO- 'http://127.0.0.1/api/v1/record/start?dir=/tmp/rec'; sleep 2; wget -qO- 'http://127.0.0.1/api/v1/record/stop'
  scp the .ts, then: rm /tmp/rec/*.ts; umount /tmp/rec
"""
import sys

import cv2


def decodable_frames(path):
    cap = cv2.VideoCapture(path)
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    return frames


def save_scaled(frame, out, longest=1600):
    h, w = frame.shape[:2]
    scale = min(1.0, longest / max(h, w))
    if scale < 1.0:
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    cv2.imwrite(out, frame, [cv2.IMWRITE_JPEG_QUALITY, 88])


def main():
    path, prefix = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    frames = decodable_frames(path)
    if not frames:
        sys.exit(f"no decodable frame in {path}")
    print(f"{len(frames)} frames, {frames[0].shape[1]}x{frames[0].shape[0]}")
    picks = [int(i * (len(frames) - 1) / max(1, n - 1)) for i in range(n)]
    for i, idx in enumerate(picks, 1):
        out = f"{prefix}-{i}.jpg"
        save_scaled(frames[idx], out)
        print(idx, out)


if __name__ == "__main__":
    main()
