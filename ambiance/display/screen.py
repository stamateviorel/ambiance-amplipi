#!/usr/bin/env python3
"""ambiance front screen — ILI9341 320x240 TFT.

Runs as its own process (ambiance-display.service) polling the ambiance API, so a
screen/SPI crash never touches audio. Shows: station header + playing dot, now-playing +
live album art (from /api/cover), a 6-zone strip (effective-silent zones dimmed), a clock,
and a red SIRENE banner while the alarm is active.

Panel wiring is the AmpliPi-VERIFIED one (amplipi/display/tftdisplay.py, non-test-board):
  SECONDARY SPI (SCLK_2/MOSI_2/MISO_2), cs=D44, dc=D39, backlight PWM on D12, rst=None,
  baud 16 MHz, rotation 270 (-> 320x240 landscape). The push path is only exercised at
  cutover (amplipi-display owns the panel until then); RADIO_DISPLAY_OUT=/x.png renders a
  frame to a PNG for content verification without the panel.
"""
import io
import json
import os
import sys
import time
import urllib.request

from PIL import Image, ImageDraw, ImageFont

W, H = 320, 240
API = os.environ.get("AMBIANCE_API", "http://127.0.0.1:8080")
OUT = os.environ.get("RADIO_DISPLAY_OUT", "")
TEST = os.environ.get("RADIO_TEST", "0") == "1"
FONTDIR = "/usr/share/fonts/truetype/dejavu/"


def font(sz, bold=True):
    try:
        return ImageFont.truetype(FONTDIR + ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"), sz)
    except Exception:
        return ImageFont.load_default()


def get_state():
    if TEST:
        return {"station": "VRT Studio Brussel", "playing": True, "title": "Coldplay - Yellow",
                "siren": False,
                "zones": [{"id": 0, "name": "Office", "vol": 70, "mute": False, "power": True},
                          {"id": 1, "name": "Wc up", "vol": 59, "mute": True, "power": True},
                          {"id": 2, "name": "Main area", "vol": 80, "mute": False, "power": True},
                          {"id": 3, "name": "Kitchen", "vol": 70, "mute": False, "power": True},
                          {"id": 4, "name": "Wc down", "vol": 60, "mute": False, "power": False},
                          {"id": 5, "name": "Showroom", "vol": 39, "mute": False, "power": True}]}
    try:
        d = json.loads(urllib.request.urlopen(API + "/api/status", timeout=4).read())
        r = d.get("radio", {})
        return {"station": r.get("station"), "playing": r.get("playing"), "title": r.get("title", ""),
                "siren": d.get("siren", False), "zones": d.get("zones", [])}
    except Exception:
        return {"station": None, "playing": False, "title": "", "siren": False, "zones": []}


def fetch_cover():
    try:
        with urllib.request.urlopen(API + "/api/cover", timeout=6) as r:
            if r.status == 200:
                return Image.open(io.BytesIO(r.read())).convert("RGB").resize((116, 116))
    except Exception:
        pass
    return None


def _wrap(draw, text, fnt, maxw, maxlines):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=fnt) <= maxw:
            cur = t
        else:
            lines.append(cur); cur = w
            if len(lines) >= maxlines:
                break
    if cur and len(lines) < maxlines:
        lines.append(cur)
    return lines[:maxlines]


def render(st, art):
    img = Image.new("RGB", (W, H), (12, 12, 16))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 30], fill=(20, 26, 40))
    d.text((10, 5), (st.get("station") or "— geen zender —")[:24], font=font(19), fill=(150, 200, 255))
    d.ellipse([W - 22, 11, W - 12, 21], fill=(60, 210, 90) if st.get("playing") else (90, 90, 90))
    if art:
        img.paste(art, (W - 128, 40))
        d.rectangle([W - 129, 39, W - 12, 157], outline=(60, 60, 70))
    title = st.get("title") or ""
    d.text((10, 42), "NU SPEELT", font=font(11), fill=(120, 130, 150))
    tw = (W - 140) if art else (W - 20)
    y = 60
    for ln in _wrap(d, title or "—", font(17), tw, 4):
        d.text((10, y), ln, font=font(17), fill=(235, 235, 235)); y += 22
    d.line([0, 166, W, 166], fill=(40, 40, 50))
    for i, z in enumerate(st.get("zones", [])[:6]):
        col, row = i % 3, i // 3
        x, yy = 8 + col * 104, 172 + row * 30
        silent = z.get("mute") or (not z.get("power", True))     # effective silence
        d.text((x, yy), z["name"][:9], font=font(11), fill=(110, 110, 120) if silent else (200, 200, 210))
        d.rectangle([x, yy + 15, x + 94, yy + 21], outline=(50, 50, 60))
        fillw = int(94 * z.get("vol", 0) / 100)
        d.rectangle([x, yy + 15, x + fillw, yy + 21], fill=(70, 70, 80) if silent else (70, 150, 220))
    d.text((10, H - 22), time.strftime("%H:%M"), font=font(18), fill=(220, 220, 220))
    d.text((70, H - 20), time.strftime("%a %d/%m"), font=font(13, False), fill=(130, 130, 140))
    if st.get("siren"):
        for w in range(7):
            d.rectangle([w, w, W - 1 - w, H - 1 - w], outline=(230, 30, 30))
        d.rectangle([40, 95, W - 40, 145], fill=(200, 20, 20))
        d.text((W // 2 - 62, 104), "! SIRENE !", font=font(30), fill=(255, 255, 255))
    return img


_panel = None


def push(img):
    # VERIFIED AmpliPi wiring — secondary SPI, cs=D44 dc=D39, backlight PWM D12, rst=None, rot 270.
    global _panel
    if _panel is None:
        import board, busio, digitalio, pwmio
        from adafruit_rgb_display import ili9341
        spi = busio.SPI(clock=board.SCLK_2, MOSI=board.MOSI_2, MISO=board.MISO_2)
        disp = ili9341.ILI9341(spi, cs=digitalio.DigitalInOut(board.D44),
                               dc=digitalio.DigitalInOut(board.D39), rst=None,
                               baudrate=16000000, rotation=270)
        led = pwmio.PWMOut(board.D12, frequency=5000, duty_cycle=0)
        led.duty_cycle = 65535          # backlight on (there's no RST; blank until first image)
        _panel = disp
    _panel.image(img)


def main():
    if OUT:
        render(get_state(), fetch_cover() if not TEST else None).save(OUT)
        print("rendered -> %s" % OUT, file=sys.stderr, flush=True)
        return
    print("ambiance display: pushing to ILI9341", file=sys.stderr, flush=True)
    last_title = None
    art = None
    while True:
        try:
            st = get_state()
            if st.get("title") != last_title:
                last_title = st.get("title")
                art = fetch_cover()
            push(render(st, art))
        except Exception as e:
            print("display error: %s" % e, file=sys.stderr, flush=True)
        time.sleep(1)


if __name__ == "__main__":
    main()
