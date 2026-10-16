#!/usr/bin/env python3
"""
Arducam IMX519 Quad-Camera Kit (CamArray HAT) on NVIDIA Jetson
Single-channel mode: one camera at a time, each at full sensor resolution.

For each camera (channel) the script:
  1. switches the CamArray HAT to single-channel mode for that camera,
  2. starts the Argus stream (the lens only answers on I2C while streaming),
  3. sets a rough lens focus (default 275, the middle of 250-300),
  4. waits for focus/exposure to settle and saves one JPEG.
Afterwards the HAT is put back into its default four-in-one mode.

Everything runs on I2C bus 10 by default (override with --bus).

Requirements:  sudo apt install v4l-utils i2c-tools
Run with sudo:
    sudo python3 imx519_capture_all.py
    sudo python3 imx519_capture_all.py --mode 3 --channels 0,1
    sudo python3 imx519_capture_all.py --focus 400

Sources
  * Lens control: the register sequence is taken from Arducam's Focuser.py
    (Jetson_IMX519_Focus_Example, MIT licence, Copyright (c) 2019-4 Arducam):
    lens address 0x0C; init = write 0x00 to reg 0x02; focus 0-1000 is scaled to
    12 bits, shifted left 4, high byte -> reg 0x00, low byte -> reg 0x01.
  * Channel switching (bus 10, HAT address 0x24, register 0x24):
        0x02 = single channel 0   0x12 = single channel 1   0x00 = four-in-one
    comes from an Arducam support post. The codes for channels 2 and 3 are NOT
    in that post; 0x22 and 0x32 are an extrapolation of the pattern. Check that
    each picture shows a different camera, or override with --channel-codes.
  * That the lens write reaches the *selected* camera in single-channel mode is
    an assumption; judge it by the sharpness of the pictures.
"""

import argparse
import glob
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime

DEFAULT_BUS = 10
HAT_ADDR = 0x24
HAT_REG = 0x24
FOUR_IN_ONE = 0x00
DEFAULT_CHANNEL_CODES = {0: 0x02, 1: 0x12, 2: 0x22, 3: 0x32}  # 2 and 3 are inferred
UNVERIFIED_CHANNELS = {2, 3}

LENS_ADDR = 0x0C
FOCUS_MIN, FOCUS_MAX = 0, 1000     # Arducam's focus units

SWITCH_SETTLE_S = 0.5       # let the HAT re-route the camera
STREAM_START_S = 1.0        # wait for Argus to start streaming (lens only answers then)
FOCUS_SETTLE_S = 0.5        # let the lens stop moving
EXPOSURE_SETTLE_S = 1.5     # let auto-exposure settle on the focused image
FOCUS_RETRIES = 12          # focus attempts (0.5 s apart) while the stream warms up
SENSOR_ID = 0               # the HAT presents one camera to Argus in single-channel mode

# Used only if v4l2-ctl can't report modes. Verify with:
#   v4l2-ctl -d /dev/video0 --list-formats-ext
FALLBACK_MODES = [(1920, 1080, 60), (3840, 2160, 18), (4656, 3496, 9)]


# -------------------------------------------------------------------- I2C ---
def i2cset(bus, addr, *values):
    cmd = ["i2cset", "-y", str(bus), f"0x{addr:02x}"] + [f"0x{v:02x}" for v in values]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0, r.stderr.strip()


def set_channel(bus, code):
    return i2cset(bus, HAT_ADDR, HAT_REG, code)


class Lens:
    """Lens (voice-coil) control, following Arducam's Focuser.py."""

    def __init__(self, bus):
        self.bus = bus
        self.initialised = False

    def init(self):
        ok, err = i2cset(self.bus, LENS_ADDR, 0x02, 0x00)
        self.initialised = ok
        return ok, err

    def set_focus(self, value):
        value = max(FOCUS_MIN, min(FOCUS_MAX, int(value)))
        raw = int(value / 1000.0 * 4095) << 4
        ok, err = i2cset(self.bus, LENS_ADDR, 0x00, raw >> 8)
        if ok:
            ok, err = i2cset(self.bus, LENS_ADDR, 0x01, raw & 0xFF)
        return ok, err

    def apply(self, value):
        """Init once (while streaming), then set focus."""
        if not self.initialised:
            ok, err = self.init()
            if not ok:
                return False, err
        return self.set_focus(value)


def sensor_bound(bus):
    return os.path.exists(f"/sys/bus/i2c/devices/{bus}-001a/driver")


# ------------------------------------------------------------------ modes ---
def list_modes(video_dev):
    """Return [(width, height, fps), ...] reported by the driver."""
    try:
        out = subprocess.run(
            ["v4l2-ctl", "-d", video_dev, "--list-formats-ext"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    modes, current = {}, None
    for line in out.splitlines():
        size = re.search(r"Size: Discrete (\d+)x(\d+)", line)
        if size:
            current = (int(size.group(1)), int(size.group(2)))
            modes.setdefault(current, 0)
            continue
        fps = re.search(r"\(([\d.]+) fps\)", line)
        if fps and current:
            modes[current] = max(modes[current], int(round(float(fps.group(1)))))
    return sorted(((w, h, f) for (w, h), f in modes.items() if f > 0),
                  key=lambda m: m[0] * m[1])


def choose_mode(modes, preselected=None):
    print("\nAvailable resolutions:")
    for i, (w, h, fps) in enumerate(modes, 1):
        print(f"  {i}) {w}x{h} @ {fps} fps")
    if preselected is not None:
        if not 1 <= preselected <= len(modes):
            sys.exit(f"--mode must be between 1 and {len(modes)}")
        return modes[preselected - 1]
    while True:
        c = input(f"Select a resolution [1-{len(modes)}]: ").strip()
        if c.isdigit() and 1 <= int(c) <= len(modes):
            return modes[int(c) - 1]
        print("Invalid choice, try again.")


def give_to_invoking_user(path):
    """When run with sudo, hand the file/folder to the user who ran sudo (not root)."""
    uid, gid = os.environ.get("SUDO_UID"), os.environ.get("SUDO_GID")
    if uid is None or gid is None:
        return
    try:
        os.chown(path, int(uid), int(gid))
    except OSError:
        pass


# ---------------------------------------------------------------- capture ---
def capture_with_focus(width, height, fps, out_path, bus, focus):
    """
    Start the Argus stream, set the lens focus WHILE it is running, wait for the
    image to settle, then stop the stream and keep the last frame as a JPEG.
    Returns (captured, focus_ok, last_focus_error).
    """
    tmp = tempfile.mkdtemp(prefix="imx519_")
    pattern = os.path.join(tmp, "f_%05d.jpg")
    log_path = os.path.join(tmp, "gst.log")
    cmd = [
        "gst-launch-1.0", "-e",
        "nvarguscamerasrc", f"sensor-id={SENSOR_ID}",
        "!", f"video/x-raw(memory:NVMM),width={width},height={height},framerate={fps}/1",
        "!", "nvvidconv",
        "!", "video/x-raw(memory:NVMM),format=I420",
        "!", "nvjpegenc",
        "!", "multifilesink", f"location={pattern}", "max-files=1",
    ]
    lens = Lens(bus)
    focus_ok, err = False, "stream never started"
    try:
        with open(log_path, "w") as log:
            proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
            try:
                time.sleep(STREAM_START_S)
                for _ in range(FOCUS_RETRIES):
                    if proc.poll() is not None:
                        break
                    focus_ok, err = lens.apply(focus)
                    if focus_ok:
                        break
                    time.sleep(0.5)
                if focus_ok:
                    time.sleep(FOCUS_SETTLE_S)
                time.sleep(EXPOSURE_SETTLE_S)
                if proc.poll() is None:
                    proc.send_signal(signal.SIGINT)   # -e makes gst-launch finish cleanly
                try:
                    proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            except BaseException:
                proc.kill()
                raise

        frames = sorted(glob.glob(os.path.join(tmp, "f_*.jpg")))
        if not frames:
            print("    ! No frames captured. GStreamer output:")
            with open(log_path) as f:
                for line in f.read().strip().splitlines()[-6:]:
                    print(f"      {line}")
            return False, focus_ok, err
        shutil.move(frames[-1], out_path)
        return True, focus_ok, err
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------- main ---
def parse_codes(text):
    codes = dict(DEFAULT_CHANNEL_CODES)
    if text:
        for item in text.split(","):
            ch, code = item.split("=")
            codes[int(ch)] = int(code, 0)
    return codes


def main():
    p = argparse.ArgumentParser(description="Single-channel capture for the IMX519 quad kit")
    p.add_argument("--bus", type=int, default=DEFAULT_BUS, help="I2C bus (default 10)")
    p.add_argument("--channels", default="0,1,2,3", help="cameras to capture (default 0,1,2,3)")
    p.add_argument("--channel-codes", help='override HAT codes, e.g. "2=0x22,3=0x32"')
    p.add_argument("--mode", type=int, help="resolution number from the menu (skips the prompt)")
    p.add_argument("--focus", type=int, help="exact focus value 0-1000 (overrides the 250-300 range)")
    p.add_argument("--focus-min", type=int, default=250)
    p.add_argument("--focus-max", type=int, default=300)
    p.add_argument("--out", default="captures", help="output folder (default ./captures)")
    p.add_argument("--video-dev", default="/dev/video0", help="node used to list modes")
    p.add_argument("--no-restore", action="store_true",
                   help="leave the HAT in single-channel mode when finished")
    args = p.parse_args()

    for tool in ("gst-launch-1.0", "i2cset"):
        if shutil.which(tool) is None:
            sys.exit(f"Missing '{tool}'. Install with: sudo apt install i2c-tools")
    if not os.path.exists(f"/dev/i2c-{args.bus}"):
        sys.exit(f"I2C bus {args.bus} not found (/dev/i2c-{args.bus}). Check with: sudo i2cdetect -l")
    if not sensor_bound(args.bus):
        print(f"Warning: no bound imx519 driver at {args.bus}-001a "
              f"(check: dmesg | grep -i imx519). Continuing anyway.")

    codes = parse_codes(args.channel_codes)
    channels = [int(c) for c in args.channels.split(",")]
    for ch in channels:
        if ch not in codes:
            sys.exit(f"No HAT code known for channel {ch}; supply one with --channel-codes")
        if ch in UNVERIFIED_CHANNELS and not args.channel_codes:
            print(f"Note: the code for channel {ch} (0x{codes[ch]:02x}) is inferred, not confirmed "
                  f"by Arducam. Check that its picture shows a different camera.")

    focus = args.focus if args.focus is not None else (args.focus_min + args.focus_max) // 2
    saved = []

    try:
        # Switch to single-channel first so the driver reports full-resolution modes.
        ok, err = set_channel(args.bus, codes[channels[0]])
        if not ok:
            sys.exit(f"Could not talk to the CamArray HAT on bus {args.bus}: {err}\n"
                     f"Check wiring and run: sudo i2cdetect -y -r {args.bus}  (expect 0x24)")
        time.sleep(SWITCH_SETTLE_S)

        modes = list_modes(args.video_dev)
        if not modes:
            print("\nCould not read modes from v4l2-ctl; using fallback list (unverified).")
            modes = FALLBACK_MODES
        width, height, fps = choose_mode(modes, args.mode)
        print(f"\nUsing {width}x{height} @ {fps} fps, focus {focus}, I2C bus {args.bus}")

        existed = os.path.isdir(args.out)
        os.makedirs(args.out, exist_ok=True)
        if not existed:
            give_to_invoking_user(args.out)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for ch in channels:
            print(f"\nCamera {ch}:")
            ok, err = set_channel(args.bus, codes[ch])
            if not ok:
                print(f"  ! Channel switch failed: {err}")
                continue
            time.sleep(SWITCH_SETTLE_S)

            path = os.path.join(args.out, f"cam{ch}_{width}x{height}_{stamp}.jpg")
            print(f"  streaming, focusing ({focus}) and capturing -> {path}")
            got, focus_ok, err = capture_with_focus(width, height, fps, path, args.bus, focus)
            print(f"  focus {focus}: {'ok' if focus_ok else 'FAILED - ' + err}")
            if got:
                give_to_invoking_user(path)
                saved.append(path)
    finally:
        if not args.no_restore:
            set_channel(args.bus, FOUR_IN_ONE)
            print("\nHAT restored to four-in-one mode.")

    print(f"Done: {len(saved)}/{len(channels)} pictures saved in '{args.out}'.")
    if len(saved) != len(channels):
        sys.exit(1)


if __name__ == "__main__":
    main()
