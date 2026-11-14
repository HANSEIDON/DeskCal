# -*- coding: utf-8 -*-
"""바탕화면에 상시 떠 있는 달력 + 시간표 위젯."""
import calendar
import ctypes
import datetime as dt
import glob
import hashlib
import hmac
import html
import json
import math
import os
import queue
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk
import tkinter.font as tkfont
import urllib.parse
import urllib.request
import winreg
import zipfile
import zlib
from tkinter import filedialog

__version__ = "1.3.1"
HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN = getattr(sys, "frozen", False) or "__compiled__" in globals()   # exe(Nuitka/PyInstaller)
RES_DIR = getattr(sys, "_MEIPASS", HERE)        # 함께 묶인 파일(글꼴·seeds)이 있는 곳


def default_data_dir():
    """스크립트로 실행하면 스크립트 옆 data 폴더. exe 는 %LOCALAPPDATA%\\DeskCal 에 둔다
    (exe 폴더는 Program Files 처럼 쓰기 금지일 수 있고, 새 버전으로 폴더를 통째로
    바꿔도 데이터가 남아야 한다)."""
    if FROZEN:
        return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                            "DeskCal")
    return os.path.join(HERE, "data")


APP_DIR = os.environ.get("DESKCAL_DIR") or default_data_dir()
DATA_FILE = os.path.join(APP_DIR, "events.json")
TT_FILE = os.path.join(APP_DIR, "timetable.json")
COURSE_FILE = os.path.join(APP_DIR, "courses.json")
CONF_FILE = os.path.join(APP_DIR, "config.json")
LOG_FILE = os.path.join(APP_DIR, "error.log")
FONT_DIR = os.path.join(RES_DIR, "fonts")

N_DAYS = 5                  # 시간표: 월~금
PERIODS = 12
WEEK_KEYS = ["all", "odd", "even"]
EXAM_KEYS = ["mid", "fin", "asg"]   # 期中考试 / 期末考试 / 최종과제

# ---------- 색 테마 ----------
# BASE 는 흐린 바탕화면 위에 덮는 색이다. 나머지 색(카드·입력칸·선·흐린 글자…)은
# 실제로 깔린 배경의 평균색에서 계산한다(derive_colors). 그래야 바탕화면이 밝든
# 어둡든 글자 대비가 유지된다. 그리는 코드는 모두 이 전역 이름들을 그대로 읽는다.
THEMES = {
    "dark": dict(BASE="#14161c", FG="#eceef4", ACCENT="#8fb3ff", ACCENT_INK="#0f1420",
                 SUN="#f0a3a3", SAT="#9cc2f2", OK="#8fd6a3", INK="#15171c"),
    "light": dict(BASE="#f3f4f7", FG="#1d2027", ACCENT="#3f6fd1", ACCENT_INK="#ffffff",
                  SUN="#c95454", SAT="#3567c4", OK="#2d8a4e", INK="#1d2027"),
}
THEME = "dark"
BASE = FG = ACCENT = ACCENT_INK = SUN = SAT = OK = INK = ""
BG = CARD = SUNK = LINE = MUTED = DIM = SEL_BG = SEL_BD = TODAY = HOVER = GRID = ""

# 유리 효과: 흐린 바탕화면 위에 BASE 를 얼마나 진하게 덮을지 (높을수록 덜 비침)
GLASS = {"off": None, "soft": 0.76, "clear": 0.62}



def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def hexc(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in c)


def mix(a, b, t):
    """a 와 b 를 섞는다. t=0 이면 a, t=1 이면 b."""
    a = rgb(a) if isinstance(a, str) else a
    b = rgb(b) if isinstance(b, str) else b
    return hexc([x + (y - x) * t for x, y in zip(a, b)])


def luminance(c):
    def ch(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb(c) if isinstance(c, str) else c
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def toward(c, target, need, against, step=0.12):
    """c 를 target 쪽으로 조금씩 옮겨 against 와의 대비가 need 이상이 되게 한다."""
    for _ in range(20):
        if contrast(c, against) >= need:
            break
        c = mix(c, target, step)
    return c


def derive_colors(avg_all=None, avg_panel=None):
    """배경 평균색에서 나머지 색을 계산한다. 유리 효과가 꺼져 있으면 BASE 기준.
    섞는 비율을 고정하면 바탕화면이 밝을 때 글자 대비가 모자라므로, 대비 기준
    (본문 9:1, 흐린 글자 4.8:1 — WCAG AA 4.5:1 위)을 채울 때까지 조정한다."""
    g = globals()
    base = hexc(avg_all) if avg_all else BASE
    panel = hexc(avg_panel) if avg_panel else base
    dark = THEME == "dark"
    if dark:
        card = toward(mix(panel, FG, 0.07), BASE, 9.0, FG)
    else:
        card = toward(mix(panel, "#ffffff", 0.55), "#ffffff", 12.0, FG)
    muted = FG
    for t in (0.42, 0.38, 0.34, 0.30, 0.26, 0.22, 0.18):
        muted = mix(FG, card, t)
        if contrast(muted, card) >= 4.8:
            break
    dim = FG
    for t in (0.62, 0.58, 0.54, 0.50, 0.46, 0.42):
        dim = mix(FG, card, t)
        if contrast(dim, card) >= 2.8:
            break
    if dark:
        g.update(SUNK=mix(card, FG, 0.08), SEL_BG=mix(base, ACCENT, 0.32),
                 TODAY=mix(base, FG, 0.12), HOVER=mix(card, FG, 0.05), GRID=mix(base, FG, 0.13))
    else:
        g.update(SUNK=mix(card, FG, 0.05), SEL_BG=mix(mix(base, "#ffffff", 0.4), ACCENT, 0.22),
                 TODAY=mix(base, "#ffffff", 0.45), HOVER=mix(card, FG, 0.04),
                 GRID=mix(base, FG, 0.12))
    g.update(BG=base, CARD=card, LINE=mix(card, FG, 0.14 if dark else 0.12),
             MUTED=muted, DIM=dim, SEL_BD=ACCENT)


def apply_theme(name):
    global THEME
    THEME = name if name in THEMES else "dark"
    globals().update(THEMES[THEME])
    derive_colors()


apply_theme("dark")
# 일정·수업 색 (채도를 낮춘 색)
PALETTE = ["#e8949b", "#eba77a", "#e3c66f", "#86c796", "#84b5e6", "#ac97e2", "#9ea4b3"]
URGENT, SOON = PALETTE[0], PALETTE[1]


def pc(c):
    return c or PALETTE[0]


# ---------- 교시 ----------
# 학교 시간표 (校本部·医学部). config.json 의 "periods" 로 바꿀 수 있다.
PERIOD_TIMES = ["08:00-08:50", "09:00-09:50", "10:10-11:00", "11:10-12:00",
                "13:00-13:50", "14:00-14:50", "15:10-16:00", "16:10-17:00",
                "17:10-18:00", "18:40-19:30", "19:40-20:30", "20:40-21:30"]
IDLE_RETURN = 120          # 이만큼(초) 손대지 않으면 달력을 오늘로 되돌린다

# ---------- 유리 배경 (직접 만든 Mica) ----------
# 바탕화면을 그려 받아 위젯 뒤 영역만 잘라, 아주 작게 줄였다가 부드럽게 키워
# 흐리게 만들고 BASE 색을 덮는다. Windows 의 흐림 효과는 Tk 의 반투명 창과 같이
# 쓰면 적용되지 않아서 직접 만든다. 글자는 불투명하게 그려지니 선명하다.
_gdi_ready = False


def _glass_init():
    global _gdi_ready, _gp
    if _gdi_ready:
        return
    H = ctypes.c_void_p
    u, g, ms = ctypes.windll.user32, ctypes.windll.gdi32, ctypes.windll.msimg32
    _gp = ctypes.windll.gdiplus
    u.GetDC.restype = H; u.GetDC.argtypes = [H]
    u.ReleaseDC.argtypes = [H, H]
    u.PrintWindow.argtypes = [H, H, ctypes.c_uint]
    g.CreateCompatibleDC.restype = H; g.CreateCompatibleDC.argtypes = [H]
    g.CreateCompatibleBitmap.restype = H
    g.CreateCompatibleBitmap.argtypes = [H, ctypes.c_int, ctypes.c_int]
    g.SelectObject.restype = H; g.SelectObject.argtypes = [H, H]
    g.SetStretchBltMode.argtypes = [H, ctypes.c_int]
    g.SetBrushOrgEx.argtypes = [H, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    g.StretchBlt.argtypes = [H] + [ctypes.c_int] * 4 + [H] + [ctypes.c_int] * 4 + [ctypes.c_uint]
    g.GetDIBits.argtypes = [H, H, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p,
                            ctypes.c_void_p, ctypes.c_uint]
    g.DeleteObject.argtypes = [H]; g.DeleteDC.argtypes = [H]
    g.CreateSolidBrush.restype = H; g.CreateSolidBrush.argtypes = [ctypes.c_uint]
    g.PatBlt.argtypes = [H] + [ctypes.c_int] * 4 + [ctypes.c_uint]
    ms.AlphaBlend.argtypes = [H] + [ctypes.c_int] * 4 + [H] + [ctypes.c_int] * 4 + [ctypes.c_uint32]

    class GPI(ctypes.Structure):
        _fields_ = [("ver", ctypes.c_uint32), ("cb", ctypes.c_void_p),
                    ("noThread", ctypes.c_bool), ("noCodecs", ctypes.c_bool)]
    tok = ctypes.c_size_t()
    _gp.GdiplusStartup(ctypes.byref(tok), ctypes.byref(GPI(1, None, False, False)), None)
    _gp.GdipCreateBitmapFromScan0.argtypes = [ctypes.c_int] * 4 + [ctypes.c_void_p, ctypes.c_void_p]
    _gp.GdipCreateFromHDC.argtypes = [H, ctypes.c_void_p]
    _gp.GdipSetInterpolationMode.argtypes = [H, ctypes.c_int]
    _gp.GdipSetPixelOffsetMode.argtypes = [H, ctypes.c_int]
    _gp.GdipCreateImageAttributes.argtypes = [ctypes.c_void_p]
    _gp.GdipSetImageAttributesWrapMode.argtypes = [H, ctypes.c_int, ctypes.c_uint, ctypes.c_bool]
    _gp.GdipDrawImageRectRectI.argtypes = [H, H] + [ctypes.c_int] * 9 + [H, H, H]
    _gp.GdipDisposeImageAttributes.argtypes = [H]
    _gp.GdipDeleteGraphics.argtypes = [H]
    _gp.GdipDisposeImage.argtypes = [H]
    _gdi_ready = True


def make_glass(x, y, w, h, tint, alpha, shrink=72):
    """화면 좌표 (x,y,w,h) 뒤의 바탕화면을 흐리게 해 BGRA 바이트로 돌려준다. 실패하면 None."""
    try:
        _glass_init()
    except Exception:
        log("유리 배경 준비 실패:\n" + traceback.format_exc())
        return None
    H = ctypes.c_void_p
    u, g, ms = ctypes.windll.user32, ctypes.windll.gdi32, ctypes.windll.msimg32
    desk = user32.FindWindowW("Progman", None)
    if not desk:
        return None
    rc = RECT()
    user32.GetWindowRect(desk, ctypes.byref(rc))
    dw, dh = rc.right - rc.left, rc.bottom - rc.top
    sw, sh = max(2, w // shrink), max(2, h // shrink)
    scr = u.GetDC(None)
    made = []
    try:
        ddc = g.CreateCompatibleDC(scr); dbmp = g.CreateCompatibleBitmap(scr, dw, dh)
        sdc = g.CreateCompatibleDC(scr); sbmp = g.CreateCompatibleBitmap(scr, sw, sh)
        odc = g.CreateCompatibleDC(scr); obmp = g.CreateCompatibleBitmap(scr, w, h)
        tdc = g.CreateCompatibleDC(scr); tbmp = g.CreateCompatibleBitmap(scr, 1, 1)
        made = [(ddc, dbmp), (sdc, sbmp), (odc, obmp), (tdc, tbmp)]
        for dc, bm in made:
            g.SelectObject(dc, bm)
        if not u.PrintWindow(desk, ddc, 2):
            return None
        g.SetStretchBltMode(sdc, 4)                        # HALFTONE: 평균내며 줄인다
        g.SetBrushOrgEx(sdc, 0, 0, None)
        # 창이 화면 밖으로 일부 나가 있으면 영역이 바탕화면 그림을 벗어난다.
        # StretchBlt 는 범위 밖을 못 읽으니 안쪽까지 자른다.
        sx, sy = x - rc.left, y - rc.top
        sws, shs = w, h
        if sx < 0:
            sws += sx; sx = 0
        if sy < 0:
            shs += sy; sy = 0
        sws = min(sws, dw - sx)
        shs = min(shs, dh - sy)
        if sws < 2 or shs < 2:
            return None
        g.StretchBlt(sdc, 0, 0, sw, sh, ddc, sx, sy, sws, shs, 0x00CC0020)
        small = ctypes.create_string_buffer(sw * sh * 4)
        hdr = ctypes.create_string_buffer(
            struct.pack("<IiiHHIIiiII", 40, sw, -sh, 1, 32, 0, 0, 0, 0, 0, 0), 44)
        g.GetDIBits(sdc, sbmp, 0, sh, small, hdr, 0)
        # GDI 는 키울 때 깍둑깍둑해진다. GDI+ 고품질 보간으로 부드럽게 키운다.
        bmp, gr, attr = H(), H(), H()
        _gp.GdipCreateBitmapFromScan0(sw, sh, sw * 4, 0x00022009, small, ctypes.byref(bmp))
        _gp.GdipCreateFromHDC(odc, ctypes.byref(gr))
        _gp.GdipSetInterpolationMode(gr, 7)
        _gp.GdipSetPixelOffsetMode(gr, 4)
        _gp.GdipCreateImageAttributes(ctypes.byref(attr))
        _gp.GdipSetImageAttributesWrapMode(attr, 3, 0, False)   # 가장자리 어두워짐 방지
        _gp.GdipDrawImageRectRectI(gr, bmp, 0, 0, w, h, 0, 0, sw, sh, 2, attr, None, None)
        _gp.GdipDisposeImageAttributes(attr)
        _gp.GdipDeleteGraphics(gr)
        _gp.GdipDisposeImage(bmp)
        r, gg, b = rgb(tint)
        brush = g.CreateSolidBrush(r | (gg << 8) | (b << 16))
        g.SelectObject(tdc, brush)
        g.PatBlt(tdc, 0, 0, 1, 1, 0x00F00021)
        ms.AlphaBlend(odc, 0, 0, w, h, tdc, 0, 0, 1, 1, int(255 * alpha) << 16)
        g.DeleteObject(brush)
        out = ctypes.create_string_buffer(w * h * 4)
        hdr = ctypes.create_string_buffer(
            struct.pack("<IiiHHIIiiII", 40, w, -h, 1, 32, 0, 0, 0, 0, 0, 0), 44)
        if not g.GetDIBits(odc, obmp, 0, h, out, hdr, 0):
            return None
        return out.raw
    except Exception:
        log("유리 배경 만들기 실패:\n" + traceback.format_exc())
        return None
    finally:
        for dc, bm in made:
            g.DeleteDC(dc)
            g.DeleteObject(bm)
        u.ReleaseDC(None, scr)


_glass_busy = threading.Lock()


def make_glass_bounded(x, y, w, h, tint, alpha, timeout=1.5):
    """make_glass 를 별도 스레드에서 돌리고 timeout 초 안에 끝나지 않으면 포기한다.
    바탕화면 그림을 받아오는 PrintWindow 는 explorer 에게 직접 요청하는 일이라,
    explorer 가 바쁘면 그동안 위젯 화면까지 같이 멈출 수 있다."""
    if not _glass_busy.acquire(blocking=False):
        return None                       # 앞서 보낸 요청이 아직 묶여 있다
    box = {}

    def work():
        try:
            box["raw"] = make_glass(x, y, w, h, tint, alpha)
        finally:
            _glass_busy.release()
    t = threading.Thread(target=work, daemon=True, name="glass")
    t.start()
    t.join(timeout)
    if t.is_alive():
        log("유리 배경: 바탕화면 그림이 %.1f초 안에 오지 않아 이번엔 단색으로" % timeout)
        return None
    return box.get("raw")


DESK_K = 4          # 드래그를 놓았을 때 색 검사용으로 바탕화면 유리를 1/4 로 줄여 둔다


TRANSCODED = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Themes",
                          "TranscodedWallpaper")


def desktop_dirs():
    """바탕화면 아이콘이 들어 있는 폴더 (내 바탕화면 · 공용 바탕화면)."""
    out = []
    for csidl in (0x10, 0x19):            # CSIDL_DESKTOPDIRECTORY, CSIDL_COMMON_DESKTOPDIRECTORY
        buf = ctypes.create_unicode_buffer(520)
        if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf) == 0:
            out.append(buf.value)
    return out


def wallpaper_sig():
    """바탕화면 모습이 바뀌었는지 알아보는 값. Windows 추천(Spotlight)·슬라이드쇼는 그림이
    바뀔 때 TranscodedWallpaper 를 새로 쓴다. 알려주는 경로는 늦게 바뀌기도 해서 둘 다 본다.
    바탕화면 폴더는 아이콘이 생기거나 지워지거나 이름이 바뀌면 변경 시각이 바뀐다."""
    buf = ctypes.create_unicode_buffer(520)
    user32.SystemParametersInfoW(0x0073, 520, buf, 0)       # SPI_GETDESKWALLPAPER
    sig = [buf.value]
    for p in [buf.value, TRANSCODED] + desktop_dirs():
        try:
            st = os.stat(p)
            sig.append((st.st_mtime_ns, st.st_size))
        except OSError:
            sig.append(None)
    return tuple(sig)


def desk_rect():
    rc = RECT()
    user32.GetWindowRect(user32.FindWindowW("Progman", None), ctypes.byref(rc))
    return rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top


def shrink_raw(raw, w, h, k):
    """BGRA 바이트를 가로세로 k 칸마다 하나씩 골라 작게 만든다."""
    n = len(range(0, w, k))
    out = bytearray()
    for y in range(0, h, k):
        row = raw[y * w * 4:(y + 1) * w * 4]
        b = bytearray(n * 4)
        for ch in range(4):
            b[ch::4] = row[ch::4 * k]
        out += b
    return bytes(out)


def bgra_to_ppm(raw, w, h):
    px = bytearray(w * h * 3)
    px[0::3], px[1::3], px[2::3] = raw[2::4], raw[1::4], raw[0::4]
    return b"P6 %d %d 255\n" % (w, h) + bytes(px)


def region_samples(raw, w, x0, y0, x1, y1, n=40):
    """BGRA 바이트의 사각 영역에서 n×n 개 점의 색."""
    out = []
    for j in range(n):
        yy = int(y0 + (y1 - y0 - 1) * j / max(1, n - 1))
        for i in range(n):
            xx = int(x0 + (x1 - x0 - 1) * i / max(1, n - 1))
            k = (yy * w + xx) * 4
            out.append((raw[k + 2], raw[k + 1], raw[k]))
    return out


def region_avg(raw, w, x0, y0, x1, y1, n=40):
    pts = region_samples(raw, w, x0, y0, x1, y1, n)
    return tuple(sum(p[i] for p in pts) / len(pts) for i in range(3))


def round_rect(c, x0, y0, x1, y1, r, **kw):
    """캔버스에 둥근 사각형. (부드러운 다각형으로 모서리를 근사한다)"""
    r = max(0, min(r, (x1 - x0) / 2.0, (y1 - y0) / 2.0))
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
           x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return c.create_polygon(pts, smooth=True, **kw)


def disc_png(d, color):
    """지름 d 픽셀짜리 원을 가장자리가 부드러운 RGBA PNG 로 만든다.
    Tk 캔버스의 create_oval 은 가장자리를 다듬지 않아 작은 원이 계단져 보인다."""
    r, g, b = rgb(color)
    rad = d / 2.0
    rows = bytearray()
    for y in range(d):
        rows.append(0)
        for x in range(d):
            dist = ((x + 0.5 - rad) ** 2 + (y + 0.5 - rad) ** 2) ** 0.5
            a = min(1.0, max(0.0, rad - dist + 0.5))
            rows += bytes((r, g, b, int(a * 255 + 0.5)))

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", d, d, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(rows))) + chunk(b"IEND", b""))


def _png(w, h, rows):
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(rows))) + chunk(b"IEND", b""))


def gear_png(d, color, teeth=6):
    """d 픽셀짜리 톱니바퀴 아이콘 (RGBA PNG). 톱니 6개, 가운데 구멍 하나.
    픽셀마다 4x4 로 나눠 덮인 비율을 재서 가장자리를 부드럽게 한다."""
    r, g, b = rgb(color)
    c = d / 2.0
    r_out, r_body, r_hole = d * 0.47, d * 0.35, d * 0.15
    step = 2 * math.pi / teeth
    rows = bytearray()
    for y in range(d):
        rows.append(0)
        for x in range(d):
            hit = 0
            for sy in range(4):
                for sx in range(4):
                    dx, dy = x + (sx + 0.5) / 4 - c, y + (sy + 0.5) / 4 - c
                    dist = (dx * dx + dy * dy) ** 0.5
                    if dist < r_hole or dist > r_out:
                        continue
                    if dist <= r_body:
                        hit += 1
                        continue
                    # 톱니: 바깥으로 갈수록 조금 좁아지는 사다리꼴
                    a = (math.atan2(dy, dx) + step / 2) % step - step / 2
                    half = step * (0.30 - 0.08 * (dist - r_body) / (r_out - r_body))
                    if abs(a) <= half:
                        hit += 1
            rows += bytes((r, g, b, int(hit * 255 / 16.0 + 0.5)))
    return _png(d, d, rows)


# ---------- 글꼴 ----------
# 한 글자라도 폰트에 없으면 Tk 가 다른 폰트에서 빌려 와 한 단어 안에 모양이
# 섞인다. 맑은 고딕은 간체자(网·络·传…)가, YaHei 는 한글이 없다.
# Noto Sans CJK SC 는 간체 중국어·한글·라틴을 모두 갖고 있어 하나로 통일된다.
# fonts 폴더가 없을 때는 그 언어를 제대로 쓰는 Windows 기본 글꼴로 물러난다.
# (중국어 화면에 맑은 고딕을 쓰면 간체자가 다른 글꼴에서 섞여 들어온다)
FONT_PREFS = {"zh": ["Noto Sans CJK SC", "Microsoft YaHei UI", "Microsoft YaHei"],
              "other": ["Noto Sans CJK SC", "Malgun Gothic"]}
FONT = "Malgun Gothic"
_fonts_loaded = False


def load_private_fonts():
    """fonts 폴더의 글꼴을 이 프로세스 안에서만 쓰도록 불러온다 (시스템 설치 없음)."""
    global _fonts_loaded
    if _fonts_loaded:
        return
    _fonts_loaded = True
    gdi = ctypes.windll.gdi32
    gdi.AddFontResourceExW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
    for p in sorted(glob.glob(os.path.join(FONT_DIR, "*.otf")) +
                    glob.glob(os.path.join(FONT_DIR, "*.ttf"))):
        if not gdi.AddFontResourceExW(p, 0x10, None):      # 0x10 = FR_PRIVATE
            log("글꼴을 불러오지 못함: %s" % p)


def pick_font(root, lang):
    fams = set(tkfont.families(root))
    for f in FONT_PREFS.get(lang, FONT_PREFS["other"]):
        if f in fams:
            return f
    return "TkDefaultFont"


# ---------- 문구 ----------
TEXT = {
    "ko": {
        "lang_name": "한국어",
        "part_am": "오전", "part_pm": "오후", "part_eve": "저녁",
        "week_n": "{n}주차", "week_now": "이번 주 (학기 몇 번째 주인지)",
        "week_unset_hint": "+ 를 눌러 이번 주가 몇 주차인지 정하면 '1-8주' 같은 주차 범위가 맞게 표시돼요.",
        "weeks_hint": "예: 1-8 또는 1,3,5 · 비우면 학기 내내",
        "week_bad": "주차를 읽지 못했어요 (예: 1-8 또는 1,3,5)",
        "week_need_no": "주차 범위를 쓰려면 설정에서 이번 주가 몇 주차인지 정해 주세요.",
        "tt_add_alt": "+ 이 시간에 다른 수업", "tt_new_chip": "새 수업",
        "tt_add_hint": "같은 시간에 다른 주(单周·双周, 1-8주 등)에 듣는 수업을 추가해요. 과목 이름을 적고 Enter 또는 추가를 누르세요.",
        "settings": "설정", "compact": "컴팩트", "close": "닫기",
        "rep_none": "반복 없음", "rep_weekly": "매주", "rep_biweekly": "격주", "rep_monthly": "매월",
        "tip_repeat": "반복 (누르면 바뀌어요). 여러 날 일정은 달력에서 마지막 날을 Shift+클릭하세요.",
        "n_days": "{n}일간",
        "del_this": "이 날만", "del_after": "이 날부터 전부",
        "up_this_week": "이번 주", "up_next_week": "다음 주", "up_later": "그 이후",
        "tip_upcoming": "전체 보기",
        "upd_check": "새 버전 확인 (하루 한 번)", "upd_get": "DeskCal {v} 받기",
        "upd_install": "DeskCal {v} 설치하고 다시 시작", "upd_dl": "받는 중… {p}%",
        "upd_installing": "설치 중… 곧 다시 켜져요",
        "upd_fail": "자동으로 업데이트하지 못했어요. 다운로드 페이지를 열게요.\n({why})",
        "export_ics": ".ics 내보내기 (Google · Outlook · Apple)",
        "backup_out": "백업 내보내기", "backup_in": "백업 가져오기",
        "backup_confirm": "지금의 일정·시간표·설정을 이 백업으로 바꿀까요?\n지금 데이터는 먼저 따로 저장해 두고, Ctrl+Z 로도 되돌릴 수 있어요.",
        "backup_bad": "DeskCal 백업 파일이 아니에요.", "backup_done": "백업을 불러왔어요.",
        "restore": "바꾸기", "save_fail": "저장하지 못했어요.\n{why}",
        "classes": "수업",
        "cal": "달력", "tt": "시간표", "today": "오늘",
        "month_title": "{y}년 {m}월",
        "tt_title": "시간표  ·  이번 주 {wk}",
        "wd_cal": ["일", "월", "화", "수", "목", "금", "토"],
        "wd_tt": ["월", "화", "수", "목", "금", "토", "일"],
        "weekend_tt": "주말 시간표 (토·일)",
        "wd": ["월", "화", "수", "목", "금", "토", "일"],
        "day_title": "{m}월 {d}일 {wd}요일",
        "short_date": "{m}/{d} ({wd})",
        "odd": "单周", "even": "双周", "odd_s": "单", "even_s": "双",
        "chip_all": "매주", "chip_odd": "单周", "chip_even": "双周",
        "dday_today": "오늘", "dday_past": "지남",
        "no_events": "일정 없음",
        "add": "추가",
        "upcoming": "다가오는 일정",
        "read_fail": "저장된 일정을 읽지 못했습니다.\n기존 파일 보호를 위해 저장이 "
                     "꺼져 있습니다.\n클릭하면 다시 시도합니다.",
        "tt_read_fail": "시간표를 읽지 못해 저장이 꺼져 있습니다.",
        "tt_cell": "{wd}요일 {p}교시",
        "tt_new": "빈 칸이에요. 과목 이름을 적고 Enter 또는 추가를 누르면 저장돼요. 드래그하거나 Ctrl+클릭하면 여러 칸을 한 번에 고를 수 있어요.",
        "tt_multi": "{n}칸 선택됨",
        "tt_multi_hint": "입력한 내용이 선택한 칸 모두에 들어가요. Ctrl+클릭으로 칸을 더하거나 뺄 수 있어요.",
        "tt_overwrite": "다른 수업 {n}칸을 덮어써요",
        "tt_existing": "고친 내용은 자동으로 저장돼요.",
        "course": "과목", "room": "강의실", "weeks": "주차", "color": "색",
        "course_hint": "예: 고급수학", "room_hint": "예: 一教101",
        "del_class": "이 수업 지우기",
        "saved": "자동 저장됨", "deleted": "지웠어요 · Ctrl+Z로 되돌리기",
        "exams": "시험 · 과제 마감",
        "exams_need_title": "과목 이름을 먼저 적으면 시험·과제 날짜를 넣을 수 있어요.",
        "exam_mid": "期中", "exam_fin": "期末", "exam_asg": "최종과제",
        "exam_mid_s": "期中", "exam_fin_s": "期末", "exam_asg_s": "과제 DDL",
        "pick_date": "날짜 고르기", "time_hint": "시간·비고", "clear_date": "날짜 지우기",
        "btn_date": "{m}월 {d}일 ({wd})",
        "event_hint": "새 일정을 적고 Enter",
        "tip_done": "클릭: 완료 표시  ·  우클릭: 색 바꾸기",
        "tip_edit": "클릭해서 고치기",
        "tip_exam": "클릭하면 시간표에서 고칠 수 있어요",
        "tip_delete": "지우기 (Ctrl+Z로 되돌리기)",
        "tip_menu": "설정 (언어 · 테마 · 크기 · 주차)",
        "tip_date": "눌러서 달력에서 날짜 고르기",
        "tip_time": "시간(14:00 · 오후 2시) 또는 비고 (예: 시험, 리포트, 발표)",
        "tip_color": "새 일정에 쓸 색",
        "size": "크기",
        "sizes": ["아주 작게", "작게", "보통", "크게", "아주 크게"],
        "parity": "주차 (单/双)", "set_odd": "이번 주는 单周", "set_even": "이번 주는 双周",
        "lang": "언어", "theme": "테마", "dark": "다크 모드", "light": "라이트 모드",
        "glass": "배경", "glass_soft": "유리 (은은하게)", "glass_clear": "유리 (선명하게)",
        "glass_off": "단색", "now": "지금", "next": "다음",
        "autostart": "윈도우 시작 시 실행",
        "pku_import": "학교 课表 가져오기",
        "pku_done": "{n}개 과목 · {c}칸을 가져왔어요{extra}\n색·이름은 지금처럼 고칠 수 있고, Ctrl+Z로 되돌릴 수 있어요.",
        "pku_skipped": "\n(주말·겹친 수업 {k}개는 넣지 않았어요)",
        "pku_received": "학교에서 받은 과목: {n}개",
        "pku_unscheduled": "요일·교시를 읽지 못해 넣지 못한 과목 {n}개: {names}\n직접 추가해 주세요.",
        "pku_empty": "가져올 수업을 찾지 못했어요.",
        "isop_ask_user": "학번을 입력하세요.\n북대 메일로 인증번호를 보내드려요.",
        "isop_ask_code": "북대 메일로 인증번호를 보냈어요.\n5분 안에 입력해 주세요.",
        "isop_cooldown": "인증번호는 {s}초 뒤에 다시 요청할 수 있어요.",
        "isop_daily_cap": "오늘은 이 학번으로 인증번호를 너무 여러 번 요청했어요 (하루 {n}회). 내일 다시 시도해 주세요.",
        "isop_failed": "课表를 가져오지 못했어요.\n{why}",
        "isop_net": "북대 서버에 연결하지 못했어요. 교외라면 VPN을 켜고 다시 시도해 주세요.",
        "isop_got": "课表를 받았어요 (과목 {n}개).",
        "tip_check": "클릭해서 완료 표시 (다시 누르면 취소)",
        "pku_up_to_date": "학교 课表와 같아요. 바꿀 곳이 없어요.",
        "pku_review_title": "학교 课表와 다른 곳이 {n}개 있어요",
        "pku_review_hint": "반영할 항목만 체크하세요. 반영한 뒤에도 Ctrl+Z로 되돌릴 수 있어요.",
        "pku_applied": "시간표에 반영했어요 · Ctrl+Z로 되돌리기",
        "periods_fmt": "{wd} {a}{b}교시",
        "chg_new": "새 수업: {t} ({cells})",
        "chg_gone": "门户에 없는 수업 지우기: {t} ({cells})",
        "chg_time": "시간 {a} → {b}",
        "chg_room": "강의실 {a} → {b}",
        "chg_week": "주차 {a} → {b}",
        "chg_detail": "칸별 강의실·주차 변경",
        "chg_exam_new": "期末 날짜 추가: {t} · {d} {tm}",
        "chg_exam_diff": "期末 날짜 바꾸기: {t} · {a} → {b}",
        "sel_all": "전체 선택", "sel_none": "선택 해제",
        "apply_sel": "반영하기", "cancel": "취소", "ok": "확인",
        "pku_paused": "북대 门户에서 시간표 가져오기는 지금은 지원하지 않아요.\n\n학교 측의 정식 허가를 기다리고 있어요. 허가가 나면 업데이트로 다시 제공할게요.\n그동안은 시간표 칸을 눌러 직접 입력해 주세요.",
        "open_data": "데이터 폴더 열기", "quit": "종료",
    },
    "en": {
        "lang_name": "English",
        "part_am": "Morning", "part_pm": "Afternoon", "part_eve": "Evening",
        "week_n": "Week {n}", "week_now": "This week (week of the semester)",
        "week_unset_hint": "Press + to set which week of the semester this is, so week ranges like 1-8 show correctly.",
        "weeks_hint": "e.g. 1-8 or 1,3,5 · blank = all semester",
        "week_bad": "Couldn't read the weeks (e.g. 1-8 or 1,3,5)",
        "week_need_no": "To use week ranges, set this week's number in settings.",
        "tt_add_alt": "+ Another class here", "tt_new_chip": "New class",
        "tt_add_hint": "Add a class that meets in this slot on other weeks (odd / even, weeks 1-8 …). Type a course name, then press Enter or Add.",
        "settings": "Settings", "compact": "Compact", "close": "Close",
        "rep_none": "Once", "rep_weekly": "Weekly", "rep_biweekly": "Biweekly", "rep_monthly": "Monthly",
        "tip_repeat": "Repeat (click to change). For a multi-day event, Shift+click the last day on the calendar.",
        "n_days": "{n} days",
        "del_this": "This day only", "del_after": "This and following",
        "up_this_week": "This week", "up_next_week": "Next week", "up_later": "Later",
        "tip_upcoming": "Show all",
        "upd_check": "Check for updates (once a day)", "upd_get": "Download DeskCal {v}",
        "upd_install": "Update to {v} and restart", "upd_dl": "Downloading… {p}%",
        "upd_installing": "Installing… DeskCal will restart",
        "upd_fail": "Couldn't update automatically. Opening the download page instead.\n({why})",
        "export_ics": "Export .ics (Google · Outlook · Apple)",
        "backup_out": "Export backup", "backup_in": "Import backup",
        "backup_confirm": "Replace your events, timetable and settings with this backup?\nYour current data is saved separately first, and Ctrl+Z also undoes it.",
        "backup_bad": "This file isn't a DeskCal backup.", "backup_done": "Backup restored.",
        "restore": "Replace", "save_fail": "Couldn't save.\n{why}",
        "classes": "Classes",
        "cal": "Calendar", "tt": "Timetable", "today": "Today",
        "month_title": "{month} {y}",
        "tt_title": "Timetable  ·  {wk}",
        "wd_cal": ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        "wd_tt": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "weekend_tt": "Show Weekend (Sat/Sun)",
        "wd": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "day_title": "{wd}, {mon} {d}",
        "short_date": "{mon} {d} {wd}",
        "odd": "Odd week", "even": "Even week", "odd_s": "O", "even_s": "E",
        "chip_all": "Every", "chip_odd": "Odd", "chip_even": "Even",
        "dday_today": "Today", "dday_past": "Past",
        "no_events": "No events",
        "add": "Add",
        "upcoming": "Upcoming",
        "read_fail": "Couldn't read saved events.\nSaving is off to protect the "
                     "existing file.\nClick to try again.",
        "tt_read_fail": "Couldn't read the timetable. Saving is off.",
        "tt_cell": "{wd} · Period {p}",
        "tt_new": "Empty slot. Type a course name, then press Enter or Add. Drag or Ctrl+click to select several periods at once.",
        "tt_multi": "{n} periods selected",
        "tt_multi_hint": "What you enter goes into every selected period. Ctrl+click to add or remove periods.",
        "tt_overwrite": "Overwrites {n} periods of other classes",
        "tt_existing": "Changes save automatically.",
        "course": "Course", "room": "Room", "weeks": "Weeks", "color": "Color",
        "course_hint": "e.g. Calculus", "room_hint": "e.g. Room 101",
        "del_class": "Remove this class",
        "saved": "Saved", "deleted": "Removed · Ctrl+Z to undo",
        "exams": "Exams · Deadlines",
        "exams_need_title": "Enter a course name first to add exam and deadline dates.",
        "exam_mid": "Midterm", "exam_fin": "Final", "exam_asg": "Final project",
        "exam_mid_s": "Midterm", "exam_fin_s": "Final", "exam_asg_s": "Project due",
        "pick_date": "Pick a date", "time_hint": "Time", "clear_date": "Clear date",
        "btn_date": "{wdl}, {mon} {d}",
        "event_hint": "Type a new event, then Enter",
        "tip_done": "Click: mark done  ·  Right-click: change color",
        "tip_edit": "Click to edit",
        "tip_exam": "Click to edit it in the timetable",
        "tip_delete": "Delete (Ctrl+Z to undo)",
        "tip_menu": "Settings (language · theme · size · weeks)",
        "tip_date": "Click to pick a date from a calendar",
        "tip_time": "A time (14:00 · 2pm) or a note (e.g. exam, report, presentation)",
        "tip_color": "Color for new events",
        "size": "Size",
        "sizes": ["Tiny", "Small", "Medium", "Large", "Huge"],
        "parity": "Odd / even week", "set_odd": "This week is odd",
        "set_even": "This week is even",
        "lang": "Language", "theme": "Theme", "dark": "Dark", "light": "Light",
        "glass": "Background", "glass_soft": "Glass (subtle)", "glass_clear": "Glass (clear)",
        "glass_off": "Solid", "now": "Now", "next": "Next",
        "autostart": "Start with Windows",
        "pku_import": "Import school timetable",
        "pku_done": "Imported {n} courses, {c} periods.{extra}\nYou can still edit colors and names. Ctrl+Z undoes the import.",
        "pku_skipped": "\n({k} weekend or overlapping classes were left out.)",
        "pku_received": "Courses received from school: {n}",
        "pku_unscheduled": "{n} course(s) had no readable day/period and were not added: {names}\nPlease add them by hand.",
        "pku_empty": "No classes were found.",
        "isop_ask_user": "Enter your student ID.\nWe'll send a verification code to your PKU email.",
        "isop_ask_code": "We sent a code to your PKU email.\nEnter it within 5 minutes.",
        "isop_cooldown": "You can request another code in {s} seconds.",
        "isop_daily_cap": "This ID has requested too many codes today (max {n}). Try again tomorrow.",
        "isop_failed": "Couldn't get your timetable.\n{why}",
        "isop_net": "Couldn't reach the PKU server. Off campus? Turn on the VPN and try again.",
        "isop_got": "Timetable received ({n} courses).",
        "tip_check": "Click to mark as done (click again to undo)",
        "pku_up_to_date": "Your timetable is already up to date.",
        "pku_review_title": "{n} changes from your school timetable",
        "pku_review_hint": "Tick the ones to apply. Ctrl+Z still undoes them afterwards.",
        "pku_applied": "Timetable updated · Ctrl+Z to undo",
        "periods_fmt": "{wd} P{a}{b}",
        "chg_new": "New class: {t} ({cells})",
        "chg_gone": "Remove class not in the portal: {t} ({cells})",
        "chg_time": "time {a} → {b}",
        "chg_room": "room {a} → {b}",
        "chg_week": "weeks {a} → {b}",
        "chg_detail": "room or weeks changed in some periods",
        "chg_exam_new": "Add final date: {t} · {d} {tm}",
        "chg_exam_diff": "Change final date: {t} · {a} → {b}",
        "sel_all": "Select all", "sel_none": "Clear all",
        "apply_sel": "Update selected", "cancel": "Cancel", "ok": "OK",
        "pku_paused": "Importing from the PKU portal isn't available right now.\n\nWe're waiting for official permission from the university. Once it's approved, the import will return in an update.\nUntil then, click a cell in the timetable to add classes by hand.",
        "open_data": "Open data folder", "quit": "Quit",
    },
    "zh": {
        "lang_name": "中文",
        "part_am": "上午", "part_pm": "下午", "part_eve": "晚上",
        "week_n": "第{n}周", "week_now": "本周（学期第几周）",
        "week_unset_hint": "点 + 设置本周是第几周，“1-8周”这类周次范围才能正确显示。",
        "weeks_hint": "如 1-8 或 1,3,5 · 留空 = 整学期",
        "week_bad": "周次格式有误（如 1-8 或 1,3,5）",
        "week_need_no": "要使用周次范围，请先在设置里设定本周是第几周。",
        "tt_add_alt": "+ 同一时段的另一门课", "tt_new_chip": "新课程",
        "tt_add_hint": "添加在同一时段、其他周次上的课程（单周／双周、1-8周等）。输入课程名后按回车或点“添加”。",
        "settings": "设置", "compact": "紧凑", "close": "关闭",
        "rep_none": "不重复", "rep_weekly": "每周", "rep_biweekly": "每两周", "rep_monthly": "每月",
        "tip_repeat": "重复（点击切换）。多日日程：在日历上按住 Shift 点击最后一天。",
        "n_days": "共{n}天",
        "del_this": "仅这一天", "del_after": "此日及以后",
        "up_this_week": "本周", "up_next_week": "下周", "up_later": "以后",
        "tip_upcoming": "查看全部",
        "upd_check": "检查更新（每天一次）", "upd_get": "下载 DeskCal {v}",
        "upd_install": "更新到 {v} 并重启", "upd_dl": "下载中… {p}%",
        "upd_installing": "正在安装… 稍后会自动重启",
        "upd_fail": "无法自动更新，将打开下载页面。\n（{why}）",
        "export_ics": "导出 .ics（Google · Outlook · Apple）",
        "backup_out": "导出备份", "backup_in": "导入备份",
        "backup_confirm": "用这份备份替换现在的日程、课表和设置吗？\n当前数据会先另存一份，也可以用 Ctrl+Z 撤销。",
        "backup_bad": "这不是 DeskCal 的备份文件。", "backup_done": "已恢复备份。",
        "restore": "替换", "save_fail": "保存失败。\n{why}",
        "classes": "课程",
        "cal": "日历", "tt": "课表", "today": "今天",
        "month_title": "{y}年{m}月",
        "tt_title": "课表  ·  本周{wk}",
        "wd_cal": ["日", "一", "二", "三", "四", "五", "六"],
        "wd_tt": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
        "weekend_tt": "显示周末课表（周六/日）",
        "wd": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
        "day_title": "{m}月{d}日 {wd}",
        "short_date": "{m}/{d} {wd}",
        "odd": "单周", "even": "双周", "odd_s": "单", "even_s": "双",
        "chip_all": "每周", "chip_odd": "单周", "chip_even": "双周",
        "dday_today": "今天", "dday_past": "已过",
        "no_events": "暂无日程",
        "add": "添加",
        "upcoming": "即将到来",
        "read_fail": "无法读取已保存的日程。\n为保护原文件，已暂停保存。\n点击重试。",
        "tt_read_fail": "无法读取课表，已暂停保存。",
        "tt_cell": "{wd} 第{p}节",
        "tt_new": "空课时。输入课程名称后按回车或点“添加”即可保存。拖动或按住 Ctrl 点击可一次选择多节。",
        "tt_multi": "已选 {n} 节",
        "tt_multi_hint": "输入的内容会填入所有选中的课时。按住 Ctrl 点击可增减课时。",
        "tt_overwrite": "将覆盖其他课程的 {n} 节",
        "tt_existing": "修改会自动保存。",
        "course": "课程", "room": "教室", "weeks": "周次", "color": "颜色",
        "course_hint": "例：高等数学", "room_hint": "例：一教101",
        "del_class": "删除这节课",
        "saved": "已自动保存", "deleted": "已删除 · Ctrl+Z 撤销",
        "exams": "考试 · 作业截止",
        "exams_need_title": "先输入课程名称，才能添加考试和截止日期。",
        "exam_mid": "期中", "exam_fin": "期末", "exam_asg": "期末大作业",
        "exam_mid_s": "期中", "exam_fin_s": "期末", "exam_asg_s": "大作业DDL",
        "pick_date": "选择日期", "time_hint": "时间/备注", "clear_date": "清除日期",
        "btn_date": "{m}/{d} {wd}",
        "event_hint": "输入新日程，按 Enter",
        "tip_done": "单击：标记完成  ·  右键：更改颜色",
        "tip_edit": "单击修改",
        "tip_exam": "点击在课表中修改",
        "tip_delete": "删除（Ctrl+Z 撤销）",
        "tip_menu": "设置（语言 · 主题 · 大小 · 周次）",
        "tip_date": "点击从日历中选择日期",
        "tip_time": "时间（14:00 · 下午2点）或备注（如：考试、论文、汇报）",
        "tip_color": "新日程的颜色",
        "size": "大小",
        "sizes": ["很小", "小", "中", "大", "很大"],
        "parity": "单双周", "set_odd": "本周是单周", "set_even": "本周是双周",
        "lang": "语言", "theme": "主题", "dark": "深色模式", "light": "浅色模式",
        "glass": "背景", "glass_soft": "毛玻璃（柔和）", "glass_clear": "毛玻璃（清透）",
        "glass_off": "纯色", "now": "现在", "next": "下节",
        "autostart": "开机自动启动",
        "pku_import": "导入学校课表",
        "pku_done": "已导入 {n} 门课、{c} 节。{extra}\n颜色和名称仍可修改，Ctrl+Z 可撤销导入。",
        "pku_skipped": "\n（周末或时间冲突的 {k} 门课未导入）",
        "pku_received": "从学校获取到 {n} 门课",
        "pku_unscheduled": "有 {n} 门课缺少可读取的星期/节次信息，未能导入：{names}\n请手动添加。",
        "pku_empty": "没有找到课程。",
        "isop_ask_user": "请输入学号。\n验证码将发送到你的北大邮箱。",
        "isop_ask_code": "验证码已发送到你的北大邮箱，\n请在 5 分钟内输入。",
        "isop_cooldown": "请 {s} 秒后再请求验证码。",
        "isop_daily_cap": "该学号今天请求验证码次数过多（每日 {n} 次），请明天再试。",
        "isop_failed": "未能获取课表。\n{why}",
        "isop_net": "无法连接北大服务器。如在校外，请连接 VPN 后重试。",
        "isop_got": "已获取课表（{n} 门课）。",
        "tip_check": "点击标记完成（再点一次取消）",
        "pku_up_to_date": "当前课表与学校课表一致，无需更新。",
        "pku_review_title": "与学校课表相比，有 {n} 处变化",
        "pku_review_hint": "请勾选要更新的项目。更新后仍可按 Ctrl+Z 撤销。",
        "pku_applied": "课表已更新 · Ctrl+Z 撤销",
        "periods_fmt": "{wd} 第{a}{b}节",
        "chg_new": "新课程：{t}（{cells}）",
        "chg_gone": "删除门户中没有的课：{t}（{cells}）",
        "chg_time": "时间 {a} → {b}",
        "chg_room": "教室 {a} → {b}",
        "chg_week": "周次 {a} → {b}",
        "chg_detail": "部分节次的教室或周次有变",
        "chg_exam_new": "添加期末日期：{t} · {d} {tm}",
        "chg_exam_diff": "修改期末日期：{t} · {a} → {b}",
        "sel_all": "全选", "sel_none": "取消全选",
        "apply_sel": "更新所选", "cancel": "取消", "ok": "确定",
        "pku_paused": "从北大门户导入课表功能目前暂不支持。\n\n正在等待学校的正式许可，获批后会通过更新重新提供。\n在此之前，请点击课表格子手动添加课程。",
        "open_data": "打开数据文件夹", "quit": "退出",
    },
}
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December"]

# 자유 드래그 리사이즈는 창을 다시 그리느라 버벅여서 없앴다. 정해진 크기 중 고른다.
SIZES = [(520, 400), (640, 490), (780, 590), (940, 710), (1120, 850)]
DEFAULT_SIZE = 2

# ---------- Win32 ----------
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
dwmapi = ctypes.windll.dwmapi


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT),
                ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]


# 창 핸들은 포인터 크기다. 형을 안 정하면 ctypes 가 32비트 int 로 넘겨
# HWND_TOPMOST(-1) 같은 값이 깨진다 (DPI 설정이 조용히 실패했던 것과 같은 함정).
_H = ctypes.c_void_p
user32.GetForegroundWindow.restype = _H
user32.GetParent.restype = _H
user32.GetParent.argtypes = [_H]
user32.FindWindowW.restype = _H
user32.FindWindowExW.restype = _H
user32.FindWindowExW.argtypes = [_H, _H, ctypes.c_wchar_p, ctypes.c_wchar_p]
user32.IsIconic.argtypes = [_H]
user32.GetWindow.restype = _H
user32.GetWindow.argtypes = [_H, ctypes.c_uint]
user32.GetClassNameW.argtypes = [_H, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [_H, ctypes.POINTER(ctypes.c_ulong)]
user32.IsWindowVisible.argtypes = [_H]
user32.GetWindowRect.argtypes = [_H, ctypes.POINTER(RECT)]
user32.SystemParametersInfoW.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p,
                                         ctypes.c_uint]
user32.SetWindowPos.argtypes = [_H, _H, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_uint]
user32.ShowWindow.argtypes = [_H, ctypes.c_int]
user32.MonitorFromWindow.restype = _H
user32.MonitorFromWindow.argtypes = [_H, ctypes.c_uint]
user32.GetMonitorInfoW.argtypes = [_H, ctypes.POINTER(MONITORINFO)]
user32.GetWindowLongW.argtypes = [_H, ctypes.c_int]
user32.SetWindowLongW.argtypes = [_H, ctypes.c_int, ctypes.c_long]

kernel32.CreateEventW.restype = _H
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_bool, ctypes.c_wchar_p]
kernel32.OpenEventW.restype = _H
kernel32.OpenEventW.argtypes = [ctypes.c_uint, ctypes.c_bool, ctypes.c_wchar_p]
kernel32.SetEvent.argtypes = [_H]
kernel32.WaitForSingleObject.argtypes = [_H, ctypes.c_uint]
kernel32.WaitForSingleObject.restype = ctypes.c_uint
kernel32.CloseHandle.argtypes = [_H]
user32.SetForegroundWindow.argtypes = [_H]
user32.AllowSetForegroundWindow.argtypes = [ctypes.c_uint]
SUMMON_EVENT = "DeskCal_summon"      # 아이콘을 다시 누르면 켜져 있는 위젯에 보내는 신호

WIN_TITLE = "DeskCal"
GWL_EXSTYLE, WS_EX_TOOLWINDOW = -20, 0x80
HWND_TOP, HWND_BOTTOM, HWND_TOPMOST, HWND_NOTOPMOST = 0, 1, -1, -2
GW_HWNDNEXT = 2
GW_HWNDPREV = 3
SWP_KEEP = 0x0001 | 0x0002 | 0x0010     # NOSIZE | NOMOVE | NOACTIVATE
SWP_SHOW = 0x0001 | 0x0002 | 0x0040     # NOSIZE | NOMOVE | SHOWWINDOW
SW_SHOWNOACTIVATE = 4
ERROR_ALREADY_EXISTS = 183
MONITOR_NEAREST = 2
DESK_SURFACE_CLASSES = ("Progman", "WorkerW")   # 바탕화면(아이콘·배경)을 그리는 창
DESK_SHELL_CLASSES = (
    "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
    "Windows.UI.Core.CoreWindow", "TopLevelWindowForOverflowXamlIsland",
    "XamlExplorerHostIslandWindow",
)   # 바탕화면 및 윈도우 셸 UI 관련 창
DESK_CLASSES = DESK_SHELL_CLASSES
# 탐색기가 잠깐 띄우는 메뉴(바탕화면 파일 우클릭 메뉴 등). 이게 앞에 와도 다른 앱으로
# 돌아간 게 아니다. Windows 11 새 메뉴는 버전마다 클래스 이름이 달라서, 클래스 대신
# '탐색기 프로세스가 띄운 창인가'로 본다 (is_shell_ui).
SHELL_MENU_CLASSES = ("#32768",)                                   # 클래식 팝업 메뉴
EXPLORER_APP_CLASSES = ("CabinetWClass", "ExploreWClass", "#32770")  # 폴더 창·속성 창은 앱 창


_CLASS_BUF = ctypes.create_unicode_buffer(64)


def win_class(h):
    if not h:
        return ""
    user32.GetClassNameW(h, _CLASS_BUF, 64)
    return _CLASS_BUF.value


def win_pid(h):
    pid = ctypes.c_ulong(0)
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return pid.value


def is_cloaked(h):
    v = ctypes.c_int(0)
    dwmapi.DwmGetWindowAttribute(_H(h), 14, ctypes.byref(v), 4)   # DWMWA_CLOAKED
    return v.value != 0


DPI_MODE = "미설정"   # 모듈로 불러 쓸 때(테스트 등)를 위한 기본값


def set_dpi_awareness():
    """반환값을 반드시 확인한다. 이 API 들은 실패해도 예외를 던지지 않아서,
    try/except 만 걸어두면 실패를 놓치고 대비책이 실행되지 않는다."""
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [_H]
        user32.SetProcessDpiAwarenessContext.restype = ctypes.c_bool
        if user32.SetProcessDpiAwarenessContext(_H(-4)):      # per-monitor v2
            return "per-monitor-v2"
    except Exception:
        pass
    try:
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:
            return "per-monitor"
        if ctypes.windll.shcore.SetProcessDpiAwareness(1) == 0:
            return "system"
    except Exception:
        pass
    try:
        if user32.SetProcessDPIAware():
            return "system(legacy)"
    except Exception:
        pass
    return "none"


# ---------- 윈도우 시작 시 실행 ----------
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "DeskCal"


def launch_command():
    """로그온 때 위젯을 켜는 명령. exe 면 exe, 스크립트면 pythonw + 스크립트."""
    if FROZEN:
        return '"%s" --autostart' % sys.executable
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    return '"%s" "%s" --autostart' % (pyw, os.path.abspath(__file__))


def autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
        return True
    except OSError:
        return False


def set_autostart(on):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, launch_command())
            else:
                try:
                    winreg.DeleteValue(k, RUN_NAME)
                except FileNotFoundError:
                    pass
        log("윈도우 시작 시 실행: %s" % ("켬" if on else "끔"))
    except OSError:
        log("윈도우 시작 시 실행 설정 실패:\n" + traceback.format_exc())


# ---------- 북대 课表 읽기 ----------
# 门户에서 가져오기는 학교 허가를 기다리며 멈춰 두었다 (계산센터: 다른 앱의 통합 로그인
# 등록을 빌려 쓰면 안 된다). 아래는 课表 형식을 읽고 시간표에 합치는 부분으로, 허가를
# 받아 공식 경로로 다시 열 때 그대로 쓴다. 课表 한 칸(courseName)의 형식:
#   과목명(主)<br>上课信息：1-16周 每周 三教305  教师：…  备注：…<br>考试信息：20261230 星期三 下午
PKU_WEEKS = {"每周": "all", "单周": "odd", "双周": "even"}
PKU_DAYS = ["mon", "tue", "wed", "thu", "fri"]
PLACE_HINT = re.compile(r"(场|馆|楼|教|室|中心|院)")


def parse_pku_cell(cell):
    """门户 课表 한 칸의 HTML → [{title, room, week, exam}] (한 칸에 여러 과목일 수 있다)."""
    text = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", "\n", cell or "")))
    out, cur = [], None
    for line in (ln.strip() for ln in text.split("\n")):
        if not line:
            continue
        if line.startswith("上课信息"):
            if cur is None:
                continue
            info = line.split("：", 1)[-1]
            note = info.split("备注：", 1)[1].strip() if "备注：" in info else ""
            m = re.search(r"(每周|单周|双周)\s*(.*)", re.split(r"教师[：:]", info)[0])
            if m:
                cur["week"], cur["room"] = PKU_WEEKS[m.group(1)], m.group(2).strip()
            if not cur["room"] and note and PLACE_HINT.search(note.split()[0]):
                cur["room"] = note.split()[0]          # 예: 备注：五四网球场  自带球拍
        elif line.startswith("考试信息"):
            m = re.search(r"(\d{4})(\d\d)(\d\d)(?:\s*星期.)?\s*(\S*)", line.split("：", 1)[-1])
            if cur is not None and m:
                cur["exam"] = ("%s-%s-%s" % m.group(1, 2, 3), m.group(4))
        else:
            cur = {"title": re.sub(r"\((主|辅)\)$", "", line).strip(), "room": "",
                   "week": "all", "exam": None}
            out.append(cur)
    return [c for c in out if c["title"]]


# 북대 数据共享开放服务平台(ISOP) — 정식 등록한 앱으로 본인 课表를 받는다.
# 앱 KEY·비밀 키는 data/isop.json 에만 둔다 (공개 저장소·배포판에 넣지 않는다).
ISOP_BASE = "https://isop.pku.edu.cn/svcpub/svc"
ISOP_SVC = "STUDENT_COURSE_TABLE_ROOM"
ISOP_FILE = os.path.join(APP_DIR, "isop.json")
ISOP_THROTTLE_FILE = os.path.join(APP_DIR, "isop_throttle.json")
ISOP_MAIL_COOLDOWN = 60          # 인증 메일 재요청 최소 간격(초)
ISOP_MAIL_DAILY_CAP = 5          # 같은 학번으로 하루에 보낼 수 있는 인증 메일 수

# --- ISOP native client & secret protection --------------------------------
try:
    import _isop_client
    HAS_ISOP_CLIENT = True
except ImportError:
    _isop_client = None
    HAS_ISOP_CLIENT = False


def _dpapi_protect(data):
    """Encrypt bytes with Windows DPAPI (per-user). Returns bytes."""
    import ctypes.wintypes as wt
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wt.DWORD), ("pbData", wt.LPBYTE)]
    buf = ctypes.create_string_buffer(data, len(data))
    src = DATA_BLOB(len(data), ctypes.cast(buf, wt.LPBYTE))
    dst = DATA_BLOB()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB), wt.LPCWSTR, ctypes.POINTER(DATA_BLOB),
        wt.LPVOID, wt.LPVOID, wt.DWORD, ctypes.POINTER(DATA_BLOB)]
    crypt32.CryptProtectData.restype = wt.BOOL
    if not crypt32.CryptProtectData(ctypes.byref(src), None, None, None, None, 0,
                                   ctypes.byref(dst)):
        raise ctypes.WinError(ctypes.get_last_error())
    result = ctypes.string_at(dst.pbData, dst.cbData)
    ctypes.windll.kernel32.LocalFree(dst.pbData)   # DPAPI 버퍼는 LocalAlloc → LocalFree
    return result


import ssl


def isop_sign(pairs):
    """MBA-protected C++ native MD5 digest (appSecret never exposed to Python)."""
    if not HAS_ISOP_CLIENT:
        raise RuntimeError("Secure ISOP module missing")
    return _isop_client.sign(urllib.parse.urlencode(pairs))


def isop_call(path, pairs, sort=False, timeout=15):
    """Direct HTTPS call to ISOP endpoint bypassing untrusted CA or broken proxies."""
    if sort:
        pairs = sorted(pairs)
    else:
        pairs = list(pairs)
    sig = isop_sign(pairs)
    q = urllib.parse.urlencode(pairs + [("msg", sig)])
    url = "%s/%s?%s" % (ISOP_BASE, path, q)

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DeskCal/1.2",
            "Accept": "application/json, text/plain, */*",
        }
    )

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
    except Exception as e_first:
        try:
            no_proxy_handler = urllib.request.ProxyHandler({})
            opener = urllib.request.build_opener(no_proxy_handler, urllib.request.HTTPSHandler(context=ctx))
            with opener.open(req, timeout=timeout) as r:
                raw = r.read().decode("utf-8", errors="replace")
        except Exception:
            raise e_first

    try:
        return json.loads(raw)
    except Exception:
        raise RuntimeError(raw[:120] if raw else "Empty response from server")


def _dpapi_unprotect(data):
    """Decrypt DPAPI-protected bytes. Returns bytes."""
    import ctypes.wintypes as wt
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wt.DWORD), ("pbData", wt.LPBYTE)]
    buf = ctypes.create_string_buffer(data, len(data))
    src = DATA_BLOB(len(data), ctypes.cast(buf, wt.LPBYTE))
    dst = DATA_BLOB()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB), wt.LPWSTR, ctypes.POINTER(DATA_BLOB),
        wt.LPVOID, wt.LPVOID, wt.DWORD, ctypes.POINTER(DATA_BLOB)]
    crypt32.CryptUnprotectData.restype = wt.BOOL
    if not crypt32.CryptUnprotectData(ctypes.byref(src), None, None, None, None, 0,
                                     ctypes.byref(dst)):
        raise ctypes.WinError(ctypes.get_last_error())
    result = ctypes.string_at(dst.pbData, dst.cbData)
    ctypes.windll.kernel32.LocalFree(dst.pbData)   # DPAPI 버퍼는 LocalAlloc → LocalFree
    return result





def isop_client_ip():
    """요청한 컴퓨터의 IP (V2 인증 API 가 요구한다)."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
            sk.connect(("162.105.120.174", 443))
            return sk.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def isop_ok(resp):
    """ISOP 课表 응답 성공 여부. 문서엔 'success' 라고 돼 있지만 실제로는 true 가 온다."""
    return resp.get("flag") in (True, "success", "true")


_ISOP_WD = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}


def isop_day(v):
    """요일 값 '1'·'周一'·'星期一' → 0(월)…6(일). 못 읽으면 None."""
    s = str(v if v is not None else "").strip()
    if s.isdigit():
        n = int(s)
        return n - 1 if 1 <= n <= 7 else None
    for ch in reversed(s):
        if ch in _ISOP_WD:
            return _ISOP_WD[ch] - 1
    return None


def isop_periods(a, b):
    """교시 값 ('3','4') · ('第3节','第4节') · ('3-4','') → (3, 4). 시각('19:10')이나 빈 값은 None."""
    txt = "%s %s" % (a if a is not None else "", b if b is not None else "")
    if ":" in txt or "：" in txt:
        return None
    nums = [int(x) for x in re.findall(r"\d+", txt)]
    if not nums:
        return None
    lo, hi = min(nums), max(nums)
    lo, hi = max(lo, 1), min(hi, PERIODS)
    return (lo, hi) if lo <= hi else None


def isop_entries(c):
    """과목 하나의 수업 시간들 [(요일 0~6, 시작 교시, 끝 교시, 원래 항목)]. 못 읽은 항목은 뺀다."""
    out = []
    for j in c.get("jsap") or []:
        di, pr = isop_day(j.get("xq")), isop_periods(j.get("kssj"), j.get("jssj"))
        if di is not None and pr:
            out.append((di, pr[0], pr[1], j))
    return out


def isop_unscheduled(resp):
    """학교에서 받았지만 요일·교시를 읽을 수 없어 시간표에 넣지 못한 과목 이름들."""
    out = []
    for c in resp.get("list") or []:
        title = (c.get("kcmc") or "").strip()
        if title and not isop_entries(c) and title not in out:
            out.append(title)
    return out


def isop_slots(resp, n_days=N_DAYS):
    """ISOP '个人课表及教室' 응답 → parse_pku_table 과 같은 ({(요일, 교시): [과목]}, 주말 수)."""
    slots, weekend = {}, 0
    # 시작 주~끝 주: 가장 흔한 범위(보통 1-16)는 '학기 내내'로 보고 적지 않는다.
    # 그것과 다른 수업(반 학기 등)만 주차 범위를 붙인다.
    spans = []
    for c in resp.get("list") or []:
        for _, _, _, j in isop_entries(c):
            a, b = str(j.get("qsz") or ""), str(j.get("jsz") or "")
            if a.isdigit() and b.isdigit():
                spans.append((int(a), int(b)))
    usual = max(set(spans), key=spans.count) if spans else None

    def weeks_of(j):
        a, b = str(j.get("qsz") or ""), str(j.get("jsz") or "")
        if not (a.isdigit() and b.isdigit()) or (int(a), int(b)) == usual:
            return ""
        return norm_weeks("%s-%s" % (a, b)) or ""
    for c in resp.get("list") or []:
        title = (c.get("kcmc") or "").strip()
        if not title:
            continue
        exam = None
        for e in c.get("ksap") or []:            # 시험 일정: {'ksrq': '20270104', 'kssj': '晚上'}
            d = e.get("ksrq") or ""
            if len(d) == 8 and d.isdigit():
                exam = ("%s-%s-%s" % (d[:4], d[4:6], d[6:]), e.get("kssj", ""))
                break
        for di, a, b, j in isop_entries(c):
            if di >= n_days:
                weekend += 1
                continue
            for p in range(a, b + 1):
                slots.setdefault((di, p), []).append({
                    "title": title, "room": (j.get("skjs") or "").strip(),
                    "week": PKU_WEEKS.get((j.get("dsz") or "").strip(), "all"),
                    "weeks": weeks_of(j), "exam": exam})
    return slots, weekend


def parse_pku_html(text):
    """门户 '我的课表' 페이지를 브라우저로 저장한 html → getCourseInfo.do 응답과 같은 모양."""
    cells = dict(re.findall(r'<td[^>]*id="((?:mon|tue|wed|thu|fri|sat|sun)\d+)"[^>]*>(.*?)</td>',
                            text, re.S))
    return {"success": True,
            "course": [{k: {"courseName": cells.get("%s%d" % (k, i), "")}
                        for k in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
                       for i in range(1, PERIODS + 1)]}


def parse_pku_table(resp, n_days=N_DAYS):
    """getCourseInfo.do 응답 → ({(요일, 교시): [과목…]}, 시간표에 못 넣은 수업 수(주말))."""
    slots, weekend = {}, 0
    all_pku_days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    days = all_pku_days[:n_days]
    extra = all_pku_days[n_days:]
    for i, row in enumerate((resp or {}).get("course") or [], 1):
        for di, key in enumerate(days):
            got = parse_pku_cell((row.get(key) or {}).get("courseName"))
            if got and i <= PERIODS:
                slots[(di, i)] = got
        for key in extra:
            weekend += len(parse_pku_cell((row.get(key) or {}).get("courseName")))
    return slots, weekend


# ---------- 파일 ----------

def log(msg):
    line = "[%s] %s\n" % (dt.datetime.now().strftime("%m-%d %H:%M:%S"), msg)
    for path in (LOG_FILE, os.path.join(HERE, "error.log")):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
            return
        except Exception:
            continue


def load_json(path, default, tries=5):
    """(내용, 읽기성공). 읽기 실패한 채로 저장하면 멀쩡한 파일이 날아가므로
    '파일 없음'(정상)과 '읽지 못함'(위험)을 반드시 구분한다."""
    err = None
    for _ in range(tries):
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                return json.load(f), True
        except FileNotFoundError:
            return default, True
        except Exception as e:
            err = e
            time.sleep(0.4)
    log("%s 를 %d번 시도했지만 읽지 못함: %r — 저장을 막아 기존 파일을 지킨다"
        % (path, tries, err))
    return default, False


def save_json(path, obj):
    os.makedirs(APP_DIR, exist_ok=True)
    if os.path.exists(path):
        try:
            shutil.copyfile(path, path + ".bak")
        except Exception:
            pass
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def key_of(d):
    return d.strftime("%Y-%m-%d")


def parse_date(s):
    """2026-11-02 / 2026.11.02 / 20261102 / 11-02 를 받아준다."""
    s = (s or "").strip().replace(".", "-").replace("/", "-")
    if not s:
        return None
    today = dt.date.today()
    try:
        if len(s) == 8 and s.isdigit():
            return dt.date(int(s[:4]), int(s[4:6]), int(s[6:]))
        parts = [int(p) for p in s.split("-") if p != ""]
        if len(parts) == 3:
            return dt.date(*parts)
        if len(parts) == 2:                     # 연도 생략 = 올해(지났으면 내년)
            d = dt.date(today.year, parts[0], parts[1])
            return d if d >= today else dt.date(today.year + 1, parts[0], parts[1])
    except (ValueError, TypeError):
        return None
    return None


def parse_time(s):
    """사람이 적는 여러 시간 표기를 'HH:MM' 으로. 비었으면 '', 못 알아들으면 None.
    14:00 · 1400 · 14 · 14시 30분 · 오후 2시 · 2시반 · 2pm · 2:30 PM · 下午2点半"""
    s = (s or "").strip().lower().replace(" ", "")
    if not s:
        return ""
    pm = am = False
    for word in ("오후", "p.m.", "pm", "下午", "晚上"):
        if word in s:
            pm, s = True, s.replace(word, "")
    for word in ("오전", "a.m.", "am", "上午", "早上"):
        if word in s:
            am, s = True, s.replace(word, "")
    half = "반" in s or "半" in s
    for a, b in (("시", ":"), ("点", ":"), ("點", ":"), ("분", ""), ("分", ""),
                 ("반", ""), ("半", ""), (".", ":")):
        s = s.replace(a, b)
    s = s.strip(":")
    if ":" in s:
        h, m = s.split(":", 1)
        m = m or "0"
    elif s.isdigit() and len(s) in (3, 4):
        h, m = s[:-2], s[-2:]
    elif s.isdigit():
        h, m = s, "0"
    else:
        return None
    if not (h.isdigit() and m.isdigit()):
        return None
    h, m = int(h), int(m)
    if half and m == 0:
        m = 30
    if pm and h < 12:
        h += 12
    if am and h == 12:
        h = 0
    return "%02d:%02d" % (h, m) if 0 <= h <= 23 and 0 <= m <= 59 else None


def parse_periods(items):
    """['08:00-08:50', ...] → [(480, 530), ...] (하루 중 몇 분째인지)."""
    out = []
    for it in items or []:
        try:
            a, b = it.split("-")
            sh, sm = (int(v) for v in a.strip().split(":"))
            eh, em = (int(v) for v in b.strip().split(":"))
            out.append((sh * 60 + sm, eh * 60 + em))
        except (ValueError, AttributeError):
            log("교시 시간을 읽지 못함: %r — 기본값을 쓴다" % (it,))
            return parse_periods(PERIOD_TIMES) if items is not PERIOD_TIMES else []
    return out


# ---------- 시간표: 주차 범위 · 한 칸의 여러 수업 ----------
# 한 칸("요일-교시")의 값은 대표 수업 하나이고, 같은 시간에 다른 주에 듣는 수업은 그 안의
# "more" 목록에 둔다 (单周·双周가 다른 수업, 반 학기 수업 등). 수업이 하나뿐인 칸은 예전
# 형식 그대로라서 옛 버전이 읽어도 문제없다. 주차는 "week"(매주/单/双)에 더해
# "weeks"("1-8", "1,3,5-7"; 비면 학기 내내)로 적는다.

def parse_weeks(text):
    """'1-8' · '1,3,5-7' · '第1~8周' → {1,…}. 빈 값은 빈 집합(학기 내내), 못 읽으면 None."""
    s = re.sub(r"[第周週주차\s]|weeks?|wk", "", (text or ""), flags=re.I)
    if not s:
        return set()
    out = set()
    for part in re.split(r"[,，、;；/]", s):
        if not part:
            continue
        m = re.fullmatch(r"(\d{1,2})(?:[-~–—〜至](\d{1,2}))?", part)
        if not m:
            return None
        a = int(m.group(1))
        b = int(m.group(2) or a)
        if not 1 <= a <= b <= 30:
            return None
        out.update(range(a, b + 1))
    return out


def format_weeks(ws):
    """{1,2,3,5} → '1-3,5'."""
    out, run = [], []
    for n in sorted(ws) + [None]:
        if run and n is not None and n == run[-1] + 1:
            run.append(n)
            continue
        if run:
            out.append(str(run[0]) if len(run) == 1 else "%d-%d" % (run[0], run[-1]))
        run = [n]
    return ",".join(out)


def norm_weeks(text):
    ws = parse_weeks(text)
    return None if ws is None else format_weeks(ws)


def item_core(it):
    """수업 하나를 비교할 때 쓰는 값 (빠진 항목은 기본값으로 채운다)."""
    return (it.get("title", ""), it.get("room", ""), pc(it.get("color")),
            it.get("week", "all"), it.get("weeks", ""))


def cell_items(tt, key):
    """그 칸의 수업들 (대표 수업이 맨 앞)."""
    it = tt.get(key)
    if not it:
        return []
    return ([{k: v for k, v in it.items() if k != "more"}]
            + [dict(m) for m in (it.get("more") or []) if isinstance(m, dict) and m.get("title")])


def set_cell(tt, key, items):
    items = [{k: v for k, v in it.items() if k != "more"} for it in items if it and it.get("title")]
    if not items:
        tt.pop(key, None)
        return
    head = items[0]
    if len(items) > 1:
        head["more"] = items[1:]
    tt[key] = head


def all_items(tt):
    """시간표의 모든 수업 (칸, 수업). 한 칸에 여럿이면 모두."""
    for key in sorted(tt):
        for it in cell_items(tt, key):
            yield key, it


def item_active(it, odd, week_no):
    """그 주(홀짝 odd, 주차 week_no)에 이 수업이 있는지. 주차를 모르면 범위는 따지지 않는다."""
    week = it.get("week", "all")
    if week != "all" and (week == "odd") != odd:
        return False
    if it.get("weeks") and week_no is not None:
        ws = parse_weeks(it["weeks"])
        if ws and week_no not in ws:
            return False
    return True


# 학교가 주는 시험 시간은 '上午 / 下午 / 晚上' 뿐일 때가 많다. 저장은 받은 그대로 하고,
# 보여줄 때만 지금 언어로 바꾼다 (언어를 바꾸면 따라 바뀌고, 저장 형식은 그대로다).
EXAM_PARTS = {"上午": "part_am", "下午": "part_pm", "晚上": "part_eve"}


COMPACT = (320, 520)        # 컴팩트 모드의 창 크기 (100% 배율 기준)
REPEATS = ["", "weekly", "biweekly", "monthly"]
RELEASES_API = "https://api.github.com/repos/HANSEIDON/DeskCal/releases/latest"
RELEASES_PAGE = "https://github.com/HANSEIDON/DeskCal/releases/latest"
BACKUP_TYPES = {"events.json": dict, "series.json": list, "timetable.json": dict,
                "courses.json": dict, "config.json": dict}


def series_file():
    return os.path.join(APP_DIR, "series.json")


# ---------- 일정 제목에 적은 시간 ----------
# 입력칸을 늘리지 않으려고 시간은 제목에 같이 적게 한다 ("치과 3pm"). 제목은 적은 그대로
# 두고 ("2시 연습" 이 "연습" 이 되면 어색하다), 읽어 낸 시간만 따로 저장해 정렬·내보내기에
# 쓴다. 분명한 표기만, 맨 앞이나 맨 뒤에 있을 때만 알아듣는다 ("수학 3장" 은 시간이 아니다).
_MERID = r"(?:오전|오후|上午|下午|早上|晚上)"
_MIN = r"(?:\d{1,2}(?:분|分)?|\s*\d{1,2}\s*(?:분|分)|\s*반|半)?"
_TIME_TOKEN = (r"(?:" + _MERID + r"\s*\d{1,2}(?::\d{2}|(?:시|点|點)" + _MIN + r")"
               r"|\d{1,2}(?:시|点|點)" + _MIN +
               r"|\d{1,2}:\d{2}(?:\s*[ap]\.?m\.?)?"
               r"|\d{1,2}\s*[ap]\.?m\.?)")
_TIME_END = re.compile(r"^(.*?\S)(?:\s+|(?<=[^\x00-\x7f]))(" + _TIME_TOKEN + r")$", re.I)
_TIME_START = re.compile(r"^(" + _TIME_TOKEN + r")(?:\s+|(?=[^\x00-\x7f]))(\S.*)$", re.I)
_HAS_MERID = re.compile(_MERID + r"|[ap]\.?m", re.I)


def split_time(text):
    """'치과 3pm' → ('치과', '15:00'). 시간이 없으면 (원래 글, '')."""
    text = (text or "").strip()
    for rx, gi_title, gi_tok in ((_TIME_END, 1, 2), (_TIME_START, 2, 1)):
        m = rx.match(text)
        if not m:
            continue
        tok = m.group(gi_tok)
        tm = parse_time(tok)
        if not tm:
            continue
        # 오전·오후를 안 적은 1~6시는 오후로 본다 ("3시 회의" 는 새벽이 아니다)
        if not _HAS_MERID.search(tok) and 1 <= int(tm[:2]) <= 6:
            tm = "%02d%s" % (int(tm[:2]) + 12, tm[2:])
        title = m.group(gi_title).strip(" ,·-–—@")
        if title:
            return title, tm
    return text, ""


def time_of(text):
    """제목에 적힌 시간 ('15:00'). 없으면 ''."""
    return split_time(text)[1]


def extra_time(it):
    """제목에 안 적혀 있어 따로 보여줘야 하는 시간 (제목에 있으면 '')."""
    tm = it.get("time", "")
    return tm if tm and time_of(it.get("title", "")) != tm else ""


# ---------- 반복 · 기간 일정 ----------
# 날짜마다 복사하지 않고 규칙 하나만 저장해 그릴 때 계산한다 (series.json).
# {"title","color","time","start","end"(기간) | "repeat"(weekly/biweekly/monthly),
#  "until","skip":[뺀 날],"done":[끝낸 날]}

def iso_date(v):
    try:
        return dt.date.fromisoformat(v) if v else None
    except (ValueError, TypeError):
        return None


def series_on(s, day):
    """day 에 이 일정이 있는지."""
    start = iso_date(s.get("start"))
    if not start or day < start or day.isoformat() in (s.get("skip") or ()):
        return False
    kind = s.get("repeat")
    if not kind:
        return day <= (iso_date(s.get("end")) or start)
    until = iso_date(s.get("until"))
    if until and day > until:
        return False
    n = (day - start).days
    if kind == "weekly":
        return n % 7 == 0
    if kind == "biweekly":
        return n % 14 == 0
    if kind == "monthly":
        return day.day == start.day
    return False


def series_done_key(s, day):
    return day.isoformat() if s.get("repeat") else s.get("start", "")


def series_done(s, day):
    return series_done_key(s, day) in (s.get("done") or ())


def series_next(s, frm, horizon=400):
    """frm 부터 가장 가까운, 아직 끝내지 않은 날. 기간 일정은 시작 전일 때만."""
    start = iso_date(s.get("start"))
    if not start:
        return None
    if not s.get("repeat"):
        return start if start >= frm and not series_done(s, start) else None
    day = max(frm, start)
    for _ in range(horizon):
        if series_on(s, day) and not series_done(s, day):
            return day
        day += dt.timedelta(days=1)
    return None


# ---------- 내보내기 (.ics · 백업) ----------

def documents_dir():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows"
                            r"\CurrentVersion\Explorer\User Shell Folders") as k:
            path = os.path.expandvars(winreg.QueryValueEx(k, "Personal")[0])
        if os.path.isdir(path):
            return path
    except OSError:
        pass
    path = os.path.join(os.path.expanduser("~"), "Documents")
    return path if os.path.isdir(path) else APP_DIR


def _ics_text(t):
    return ((t or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r", "").replace("\n", "\\n"))


def _ics_fold(line):
    """한 줄은 75바이트까지. 넘으면 다음 줄을 빈칸으로 시작해 잇는다 (글자 중간은 안 자른다)."""
    out, cur, n = [], "", 0
    for ch in line:
        b = len(ch.encode("utf-8"))
        if n + b > 73:
            out.append(cur)
            cur, n = " ", 1
        cur += ch
        n += b
    out.append(cur)
    return out


def build_ics(events, series, courses, tt, periods, odd_monday, today, exam_name, week1=None):
    """일정·반복 일정·시험·수업을 다른 캘린더 앱이 읽는 .ics 글로 만든다.
    시간은 시간대 없이 적는다 (받는 쪽에서 그 컴퓨터의 현지 시간으로 읽는다)."""
    day1 = dt.timedelta(days=1)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    is_time = re.compile(r"^\d\d:\d\d$").match
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//DeskCal//DeskCal//EN",
             "CALSCALE:GREGORIAN"]

    def at(day, tm):
        return dt.datetime.combine(day, dt.time(int(tm[:2]), int(tm[3:5])))

    def add(src, summary, day, tm="", end_day=None, end_tm="", rrule="", skip=(), where=""):
        out = ["BEGIN:VEVENT",
               "UID:" + hashlib.sha1(src.encode("utf-8")).hexdigest()[:24] + "@deskcal",
               "DTSTAMP:" + stamp, "SUMMARY:" + _ics_text(summary)]
        if tm and is_time(tm):
            a = at(day, tm)
            b = at(day, end_tm) if end_tm else a + dt.timedelta(hours=1)
            out += ["DTSTART:" + a.strftime("%Y%m%dT%H%M%S"), "DTEND:" + b.strftime("%Y%m%dT%H%M%S")]
            out += ["EXDATE:" + x.strftime("%Y%m%d") + a.strftime("T%H%M%S") for x in skip]
        else:
            out += ["DTSTART;VALUE=DATE:" + day.strftime("%Y%m%d"),
                    "DTEND;VALUE=DATE:" + ((end_day or day) + day1).strftime("%Y%m%d")]
            out += ["EXDATE;VALUE=DATE:" + x.strftime("%Y%m%d") for x in skip]
        if rrule:
            out.append("RRULE:" + rrule)
        if where:
            out.append("LOCATION:" + _ics_text(where))
        lines.extend(out + ["END:VEVENT"])

    def until(day, tm):
        return ";UNTIL=" + day.strftime("%Y%m%d") + ("T235959" if tm and is_time(tm) else "")

    for key in sorted(events):
        day = iso_date(key)
        for i, it in enumerate(events[key] if day else []):
            add("e|%s|%d|%s" % (key, i, it.get("title", "")), it.get("title", ""), day,
                it.get("time", ""))
    freq = {"weekly": "FREQ=WEEKLY", "biweekly": "FREQ=WEEKLY;INTERVAL=2",
            "monthly": "FREQ=MONTHLY"}
    for i, sr in enumerate(series):
        start = iso_date(sr.get("start"))
        if not start:
            continue
        tm, src = sr.get("time", ""), "s|%d|%s|%s" % (i, sr.get("start"), sr.get("title", ""))
        if sr.get("repeat") in freq:
            rule = freq[sr["repeat"]]
            if iso_date(sr.get("until")):
                rule += until(iso_date(sr["until"]), tm)
            skip = [d for d in (iso_date(x) for x in sr.get("skip") or []) if d]
            add(src, sr.get("title", ""), start, tm, rrule=rule, skip=skip)
        else:
            add(src, sr.get("title", ""), start, end_day=iso_date(sr.get("end")) or start)
    finals = []
    for title in sorted(courses):
        info = courses[title]
        for k in EXAM_KEYS:
            day = parse_date(info.get(k + "_date", ""))
            if not day:
                continue
            if k == "fin":
                finals.append(day)
            note = info.get(k + "_time", "")
            name = "%s · %s" % (exam_name(k), title)
            add("x|%s|%s" % (title, k), name if is_time(note) or not note else
                "%s (%s)" % (name, note), day, note if is_time(note) else "")
    # 수업: 이번 주부터 기말 시험 날(없으면 18주 뒤)까지 매주.
    # 주차 범위가 있고 第1周를 알면 그 주들만 하나씩 적는다.
    last = max([d for d in finals if d >= today] or [today + dt.timedelta(weeks=18)])
    monday = today - dt.timedelta(days=today.weekday())
    odd_now = ((monday - (week1 or odd_monday)).days // 7) % 2 == 0
    for di in range(7):
        found = {}                               # 같은 수업이 있는 교시들
        for p in range(1, PERIODS + 1):
            for it in cell_items(tt, "%d-%d" % (di, p)):
                if it.get("title"):
                    key = (it["title"], it.get("room", ""), it.get("week", "all"),
                           it.get("weeks", ""))
                    found.setdefault(key, (it, []))[1].append(p)
        for it, ps in found.values():
            runs, start, prev = [], ps[0], ps[0]
            for p in ps[1:] + [None]:
                if p is not None and p == prev + 1:
                    prev = p
                    continue
                runs.append((start, prev))
                if p is not None:
                    start = prev = p
            week = it.get("week", "all")
            ws = parse_weeks(it.get("weeks", "")) if it.get("weeks") else None
            for p0, p1 in runs:
                if p1 - 1 >= len(periods):
                    continue
                a_, b_ = periods[p0 - 1][0], periods[p1 - 1][1]
                tm, end_tm = "%02d:%02d" % divmod(a_, 60), "%02d:%02d" % divmod(b_, 60)
                if ws and week1:
                    for n in sorted(ws):
                        day = week1 + dt.timedelta(weeks=n - 1, days=di)
                        if day < monday or (week != "all" and (week == "odd") != (n % 2 == 1)):
                            continue
                        add("c|%d|%d|%s|%d" % (di, p0, it["title"], n), it["title"], day, tm,
                            end_tm=end_tm, where=it.get("room", ""))
                    continue
                first = monday + dt.timedelta(days=di)
                if week != "all" and (week == "odd") != odd_now:
                    first += dt.timedelta(days=7)
                add("c|%d|%d|%s" % (di, p0, it["title"]), it["title"], first, tm, end_tm=end_tm,
                    rrule="FREQ=WEEKLY" + (";INTERVAL=2" if week != "all" else "")
                    + until(last, tm), where=it.get("room", ""))
    lines.append("END:VCALENDAR")
    return "\r\n".join(x for line in lines for x in _ics_fold(line)) + "\r\n"


def read_backup(path):
    """백업 zip 을 읽어 {파일 이름: 내용}. DeskCal 백업이 아니면 None."""
    try:
        out = {}
        with zipfile.ZipFile(path) as z:
            sizes = {i.filename: i.file_size for i in z.infolist()}
            for name, kind in BACKUP_TYPES.items():
                if name not in sizes:
                    continue
                if sizes[name] > 20 * 1024 * 1024:
                    return None
                obj = json.loads(z.read(name).decode("utf-8-sig"))
                if not isinstance(obj, kind):
                    return None
                out[name] = obj
        return out if ("events.json" in out or "timetable.json" in out) else None
    except Exception:
        return None


# ---------- 새 버전 확인 ----------

def version_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:3])


RELEASES_DL = "https://github.com/HANSEIDON/DeskCal/releases/download/"


def fetch_release(timeout=8):
    """GitHub 의 최신 릴리스: {'version', 'setup_url', 'sha256', 'sha_url'}. 보내는 정보는 없다.
    설치 파일은 이 저장소의 릴리스 주소에 있는 'DeskCal-<버전>-Setup.exe' 만 인정한다."""
    req = urllib.request.Request(RELEASES_API, headers={
        "User-Agent": "DeskCal", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read(400000).decode("utf-8"))
    ver = str(data.get("tag_name") or "").lstrip("vV")
    out = {"version": ver, "setup_url": "", "sha256": "", "sha_url": ""}
    for a in data.get("assets") or []:
        name, link = str(a.get("name") or ""), str(a.get("browser_download_url") or "")
        if not link.startswith(RELEASES_DL):
            continue
        if name == "DeskCal-%s-Setup.exe" % ver:
            out["setup_url"] = link
            digest = str(a.get("digest") or "")          # GitHub 이 계산해 주는 값
            if digest.startswith("sha256:"):
                out["sha256"] = digest[7:].lower()
        elif name == "DeskCal-%s-Setup.exe.sha256" % ver:
            out["sha_url"] = link
    return out


def fetch_latest_version(timeout=8):
    """GitHub 에 올라온 최신 버전 번호 ('1.2.3')."""
    return fetch_release(timeout)["version"]


def download_verified(url, dest, sha256, progress=None, timeout=30, limit=300 * 1024 * 1024):
    """url 을 dest 로 받는다. SHA-256 이 sha256 과 다르면 받은 것을 지우고 ValueError.
    (다 받아 확인하기 전에는 dest 가 생기지 않는다)"""
    part = dest + ".part"
    h, got = hashlib.sha256(), 0
    req = urllib.request.Request(url, headers={"User-Agent": "DeskCal"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r, open(part, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            while True:
                chunk = r.read(262144)
                if not chunk:
                    break
                got += len(chunk)
                if got > limit:
                    raise ValueError("file too large")
                h.update(chunk)
                f.write(chunk)
                if progress:
                    progress(got, total)
        if h.hexdigest().lower() != (sha256 or "").lower():
            raise ValueError("checksum mismatch")
        os.replace(part, dest)
    finally:
        if os.path.exists(part):
            os.remove(part)
    return dest


def is_installed():
    """Setup.exe 로 설치한 실행본인지 (제거 프로그램이 옆에 있다). 그럴 때만 앱 안에서
    업데이트한다. 압축을 풀어 쓰는 실행본이나 소스 실행은 다운로드 페이지를 연다."""
    return FROZEN and os.path.exists(os.path.join(os.path.dirname(sys.executable),
                                                  "unins000.exe"))


def update_script(setup, exe):
    """설치 프로그램을 조용히 돌리고, 끝나면 앱을 다시 켜는 배치 파일의 내용.
    앱이 꺼진 뒤에 돌아야 해서(실행 중이면 파일을 못 바꾼다) 따로 띄운다."""
    return ("@echo off\r\n"
            "chcp 65001 >nul\r\n"
            'start "" /wait "%s" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART\r\n'
            'start "" "%s"\r\n'
            'del "%%~f0"\r\n' % (setup, exe))


class DeskCal(tk.Tk):
    def __init__(self):
        super().__init__()
        global FONT
        load_private_fonts()

        self.events, self.data_ok = load_json(DATA_FILE, {})
        self.tt, self.tt_ok = load_json(TT_FILE, {})
        self.courses, self.cs_ok = load_json(COURSE_FILE, {})
        self.series, self.sr_ok = load_json(series_file(), [])
        if not isinstance(self.series, list):
            self.series, self.sr_ok = [], False
        self.conf, _ = load_json(CONF_FILE, {})
        self.normalize_exam_dates()
        self.lang = self.conf.get("lang") if self.conf.get("lang") in TEXT else "en"
        FONT = pick_font(self, self.lang)
        self.theme = self.conf.get("theme") if self.conf.get("theme") in THEMES else "dark"
        apply_theme(self.theme)
        self.view = self.conf.get("view", "cal")
        self.weekend_tt = bool(self.conf.get("weekend_tt", False))
        self.tt_sel = (0, 1)
        self._tt_adding = False        # 고른 칸에 다른 주의 수업을 새로 적는 중
        self.tt_weeks = ""
        self.tt_multi = None           # 드래그·Ctrl+클릭으로 고른 여러 칸 {(요일, 교시)}
        self._tt_anchor = None
        self._tt_base = set()
        self._draft = None
        self.exam_e = {}
        self._exam_loaded = ("", {})
        self.exam_vals = {k: ["", ""] for k in EXAM_KEYS}
        self._picker = self._picker_anchor = self._tip = None
        self._tip_job = self._status_job = None
        self._last_fg = user32.GetForegroundWindow()   # '앞 창이 바뀜' 판정의 기준점
        self.today = dt.date.today()
        self.shown = self.today.replace(day=1)
        self.selected = self.today
        self.color = pc(self.conf.get("color", PALETTE[0]))
        self.size_idx = min(max(int(self.conf.get("size", DEFAULT_SIZE)), 0), len(SIZES) - 1)
        self.compact = bool(self.conf.get("compact", False))
        if self.compact:
            self.view = "cal"              # 컴팩트에는 시간표 화면이 없다
        self.panel_mode = "day"            # 오른쪽 패널: day / upcoming / settings
        self.range_to = None               # Shift+클릭으로 고른 기간의 반대쪽 끝
        self.repeat = ""                   # 새 일정의 반복 (REPEATS)
        self._scroll = self._scroll_mode = None
        self._wheel, self._wheel_t = 0, 0.0
        self._wheel_last, self._wheel_lock = 0.0, False
        self._cls_sig = None
        self._upd_q, self._upd_busy = queue.Queue(), False
        self._upd_state, self._upd_btn, self._upd_dl_q = None, None, queue.Queue()
        latest = self.conf.get("update_latest")
        self.update_ver = latest if (latest and version_tuple(str(latest))
                                     > version_tuple(__version__)) else None
        self.float_mode = "--float" in sys.argv
        # 늘 바탕화면 바로 위에 둔다 ('항상 위' 설정은 없앴다). --float 는 테스트용.
        self.pinned = not self.float_mode
        self.conf.pop("pinned", None)
        self.undo_stack = []
        self._fonts = {}
        self._discs = {}               # 부드러운 원 이미지 (지름, 색) → PhotoImage
        self._drag = None
        self.shell = None
        self.beats = 0
        # 창의 겹침 상태: startup(켠 직후 앞에 보임) / active(내가 앞) /
        # bottom(바탕화면 바로 위) / showdesk('바탕화면 보기' 중이라 바탕화면 위로 올림)
        self._z = "startup"
        self._fg_start = None
        self._topmost = False
        self._shell_pid = (0.0, 0)     # (확인한 시각, 탐색기 프로세스 번호)
        self.glass = self.conf.get("glass") if self.conf.get("glass") in GLASS else "soft"
        self.glass_img = None
        self._glass_org = (0, 0)       # 유리 이미지 왼쪽 위의 화면 좌표
        self._drag_pos = None          # 드래그 중 창이 간 자리 (geometry 가 반영되기 전에도 맞게)
        self._desk = None              # 바탕화면 전체 유리 (드래그 중 밀기만 하면 되도록 미리 만든다)
        self._desk_q = queue.Queue()   # 만드는 스레드 → 화면 스레드 (Tk 는 화면 스레드만 만진다)
        self._desk_job = None          # 다음 '만들기' 예약 (화면을 다시 그리면 다시 잡는다)
        self._desk_poll = None         # 만드는 중인 결과를 기다리는 예약 (취소하면 안 된다)
        self._desk_busy = False
        self._glass_alpha = None
        self._glass_sig = None
        self._wall_sig = wallpaper_sig()       # 바탕화면 그림 (바뀌면 유리를 다시 만든다)
        self._wall_changed = None
        self.periods = parse_periods(self.conf.get("periods") or PERIOD_TIMES)
        self._last_input = time.time()        # 마지막으로 손댄 시각 (오늘로 되돌리기용)
        self._editing = False
        self._summon_t = 0.0
        self._alive = time.time()               # 화면 처리가 살아 있는지 (멈춤 감시용)
        self.autostart = "--autostart" in sys.argv
        self._summon_ev = (None if self.float_mode else
                           kernel32.CreateEventW(None, False, False, SUMMON_EVENT))

        self.title(WIN_TITLE)
        # 안내·확인 창 제목줄에 Tk 기본 아이콘(깃털) 대신 DeskCal 아이콘
        for path in (os.path.join(RES_DIR, "icon.png"), os.path.join(HERE, "docs", "icon.png")):
            if os.path.exists(path):
                try:
                    self._icon = tk.PhotoImage(master=self, file=path)
                    self.iconphoto(True, self._icon)
                except tk.TclError:
                    pass
                break
        self.overrideredirect(True)
        self.configure(bg=BG)
        self.dpi = max(1.0, self.winfo_fpixels("1i") / 96.0)
        x = self.conf.get("x", self.winfo_screenwidth() - self.w() - 60)
        self.geometry("+%d+%d" % (x, self.conf.get("y", 60)))
        self.build()

        self.update_idletasks()
        self.hwnd = user32.GetParent(self.winfo_id()) or self.winfo_id()
        user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE,
                              user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
                              | WS_EX_TOOLWINDOW)
        self.attributes("-topmost", not self.pinned)
        try:                      # Windows 11: 창 모서리를 둥글게
            corner = ctypes.c_int(2)
            dwmapi.DwmSetWindowAttribute(_H(self.hwnd), 33, ctypes.byref(corner), 4)
        except Exception:
            pass
        self.ensure_on_screen()   # hwnd 가 정해진 뒤여야 한다
        self.bind("<FocusOut>", lambda _: self.after(120, self.sync_z))
        self.bind_all("<Control-z>", self.undo)
        self.bind_all("<Control-Z>", self.undo)
        # 한글 입력 상태에서는 <Control-c> 같은 문자 기반 바인딩이 안 걸린다.
        # 키코드로 직접 보면 입력기와 무관하게 동작한다.
        self.bind_class("Entry", "<Control-KeyPress>", self.on_ctrl_key)
        self.bind_all("<ButtonPress>", self.on_any_click, add="+")
        self.bind_all("<Escape>", lambda _: self.close_picker(), add="+")
        for ev in ("<Motion>", "<KeyPress>", "<ButtonPress>", "<MouseWheel>"):
            self.bind_all(ev, self.touch, add="+")
        self.bind_all("<MouseWheel>", self.on_wheel, add="+")
        self._jobs = {"z": self.after(60, self.z_tick),
                      "dog": self.after(60000, self.watchdog),
                      "clock": self.after(30000, self.clock_tick),
                      "wall": self.after(5000, self.wall_tick),
                      # 로그온 직후엔 Windows 가 바탕화면 그림을 조금 늦게 바꾼다. 한 번 더 본다.
                      "glass15": self.after(15000, self.refresh_glass),
                      "glass60": self.after(60000, self.refresh_glass)}
        start_stall_watch(self)
        if not self.float_mode:
            self._jobs["upd"] = self.after(20000, self.update_tick)
            self.init_autostart()
            if self.autostart:          # 로그온 때는 하던 일을 가로채지 않고 바탕화면에
                self._z = "bottom"
                self.lower_to_desktop()
            else:                       # 직접 켰으면 앞으로 나와 바로 쓸 수 있게
                self.summon(quiet=True)
        log("시작 v%s%s (크기 %d, %s/%s, 글꼴 %s, DPI %s, 화면 %dx%d, 창 %dx%d+%d+%d)"
            % (__version__, " exe" if FROZEN else "", self.size_idx, self.lang, self.theme, FONT, DPI_MODE,
               self.winfo_screenwidth(), self.winfo_screenheight(),
               self.w(), self.h(), self.winfo_x(), self.winfo_y()))

    def report_callback_exception(self, exc, val, tb):
        log("콜백 예외:\n" + "".join(traceback.format_exception(exc, val, tb)))

    def destroy(self):
        # 예약해 둔 타이머를 먼저 끊는다. 안 그러면 창이 사라진 뒤에 깨어나 오류를 낸다.
        jobs = list(getattr(self, "_jobs", {}).values())
        jobs += [getattr(self, "_status_job", None), getattr(self, "_tip_job", None),
                 getattr(self, "_desk_job", None), getattr(self, "_desk_poll", None)]
        for job in jobs:
            try:
                if job:
                    self.after_cancel(job)
            except Exception:
                pass
        self.close_picker()
        self.hide_tip()
        self._destroyed = True
        super().destroy()

    # ---------- 문구 ----------

    def t(self, key, **kw):
        v = TEXT[self.lang].get(key, TEXT["en"].get(key, key))
        return v.format(**kw) if kw and isinstance(v, str) else v

    def month_title(self, d):
        return self.t("month_title", y=d.year, m=d.month, month=MONTHS_EN[d.month - 1])

    def short_date(self, d):
        return self.t("short_date", m=d.month, d=d.day, mon=MONTHS_EN[d.month - 1][:3],
                      wd=self.t("wd")[d.weekday()])

    # ---------- 복사 · 붙여넣기 ----------

    def on_ctrl_key(self, e):
        w = e.widget
        kc = e.keycode                      # C=67 V=86 X=88 A=65
        if kc not in (67, 86, 88, 65):
            return None
        try:
            if kc == 65:                    # 전체 선택
                w.select_range(0, "end")
                w.icursor("end")
            elif kc in (67, 88):            # 복사 / 잘라내기
                if w.selection_present():
                    self.clipboard_clear()
                    self.clipboard_append(w.selection_get())
                    if kc == 88:
                        w.delete("sel.first", "sel.last")
            else:                           # 붙여넣기
                try:
                    txt = self.clipboard_get()
                except tk.TclError:
                    return "break"
                if w.selection_present():
                    w.delete("sel.first", "sel.last")
                w.insert("insert", " ".join(txt.split()))
        except Exception:
            log("복사/붙여넣기 예외:\n" + traceback.format_exc())
        return "break"

    # ---------- 单周 / 双周 ----------

    def monday_of(self, d):
        return d - dt.timedelta(days=d.weekday())

    def anchor(self):
        """单周로 지정된 주의 월요일. 없으면 '이번 주가 单周' 로 잡는다."""
        a = self.conf.get("week_anchor")
        if a:
            try:
                return dt.date.fromisoformat(a)
            except ValueError:
                pass
        m = self.monday_of(self.today)
        self.conf["week_anchor"] = m.isoformat()
        return m

    def week1(self):
        """第1周의 월요일. 정해 두지 않았으면 None."""
        return iso_date(self.conf.get("week1"))

    def week_no(self, d):
        """그 날이 학기 몇 번째 주인지. 第1周를 모르면 None."""
        w1 = self.week1()
        return None if not w1 else (self.monday_of(d) - w1).days // 7 + 1

    def is_odd_week(self, d):
        n = self.week_no(d)
        if n is not None:                      # 주차 번호를 알면 홀수 주가 单周
            return n % 2 == 1
        return ((self.monday_of(d) - self.anchor()).days // 7) % 2 == 0

    def week_label(self, d):
        par = self.t("odd") if self.is_odd_week(d) else self.t("even")
        n = self.week_no(d)
        return "%s · %s" % (self.t("week_n", n=n), par) if n is not None and n >= 1 else par

    def item_on(self, it, day):
        """그 날이 든 주에 이 수업이 있는지 (单/双周 + 주차 범위)."""
        return item_active(it, self.is_odd_week(day), self.week_no(day))

    def set_week_no(self, n):
        """이번 주를 第n周로 정한다. 单/双은 주차 번호의 홀짝을 따른다."""
        n = min(max(int(n), 1), 30)
        w1 = self.monday_of(self.today) - dt.timedelta(weeks=n - 1)
        self.conf["week1"] = self.conf["week_anchor"] = w1.isoformat()
        self.save_conf()
        self.render()

    def step_week(self, delta):
        n = self.week_no(self.today)
        if n is None:                          # 처음: 지금의 单/双에 맞는 번호에서 시작
            n = 1 if self.is_odd_week(self.today) else 2
            delta = 0
        self.set_week_no(n + delta)

    def set_week_kind(self, odd):
        """이번 주를 单周(또는 双周)로 다시 지정한다."""
        m = self.monday_of(self.today)
        if self.week1():
            if self.is_odd_week(self.today) != odd:
                w1 = self.week1() - dt.timedelta(days=7)
                self.conf["week1"] = self.conf["week_anchor"] = w1.isoformat()
        else:
            self.conf["week_anchor"] = (m if odd else m - dt.timedelta(days=7)).isoformat()
        self.save_conf()
        self.render()

    # ---------- 크기 · 글꼴 ----------
    # 폰트는 반드시 음수(=픽셀)로 준다. 양수는 '포인트'라서 화면 배율이 150% 면
    # Tk 가 1.5배로 키우는데, 여백과 칸 높이는 픽셀이라 글자만 넘쳐 겹친다.

    def w(self):
        # 프리셋은 100% 배율 기준. 화면 배율만큼 키워야 어느 모니터에서든
        # 눈에 보이는 크기가 같다.
        return int((COMPACT if self.compact else SIZES[self.size_idx])[0] * self.dpi)

    def h(self):
        return int((COMPACT if self.compact else SIZES[self.size_idx])[1] * self.dpi)

    def u(self):
        # 컴팩트는 창은 좁아도 글자는 '보통' 크기 그대로 쓴다
        return self.dpi if self.compact else self.w() / 780.0

    def px(self, n):
        return max(1, int(round(n * self.u())))

    def fpx(self, size):
        return max(9, int(round(size * self.u())))

    def f(self, size, bold=False, strike=False):
        n = self.fpx(size)
        if not strike:
            return (FONT, -n, "bold") if bold else (FONT, -n)
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(family=FONT, size=-n, overstrike=1,
                                           weight="bold" if bold else "normal")
        else:
            self._fonts[key].config(size=-n)
        return self._fonts[key]

    def measure(self, text, px, bold=False):
        key = ("m", bold)
        f = self._fonts.get(key)
        if f is None:
            f = tkfont.Font(family=FONT, size=-px, weight="bold" if bold else "normal")
            self._fonts[key] = f
        else:
            f.config(size=-px)
        return f.measure(text)

    def fit(self, text, px, max_w, bold=False):
        """넘치면 뒤를 잘라 … 로 줄인다. 넘친 글자가 옆 칸을 침범하지 않게."""
        if not text or self.measure(text, px, bold) <= max_w:
            return text
        for i in range(len(text) - 1, 0, -1):
            t = text[:i] + "…"
            if self.measure(t, px, bold) <= max_w:
                return t
        return "…"

    def disc(self, c, cx, cy, r, color, **kw):
        """캔버스 c 에 가장자리가 부드러운 원을 그린다 (중심 cx,cy · 반지름 r)."""
        d = max(2, int(round(r * 2)))
        key = (d, color)
        img = self._discs.get(key)
        if img is None:
            img = self._discs[key] = tk.PhotoImage(master=self, data=disc_png(d, color),
                                                   format="png")
        return c.create_image(int(round(cx - d / 2.0)), int(round(cy - d / 2.0)),
                              image=img, anchor="nw", **kw)

    def gear(self, on):
        d = self.px(19) | 1                     # 홀수 크기라야 가운데가 한 픽셀에 맞는다
        key = ("gear", d, FG if on else MUTED)
        if key not in self._discs:
            self._discs[key] = tk.PhotoImage(master=self, data=gear_png(d, key[2]),
                                             format="png")
        return self._discs[key]

    def cal_size(self):
        """달력·시간표 캔버스의 크기. 화면에 놓이기 전에도 알 수 있게 배치값을 쓴다
        (그래야 처음부터 그려 둘 수 있어, 빈 단색이 한 번 보였다 바뀌는 깜빡임이 없다)."""
        x0, y0, x1, y1 = self.cal_box
        return x1 - x0, y1 - y0

    def set_size(self, idx):
        self.tt_commit()
        self.size_idx = min(max(idx, 0), len(SIZES) - 1)
        self.compact = False
        self.conf["size"] = self.size_idx
        self.build()
        self.ensure_on_screen()
        self.save_conf()

    def set_compact(self):
        """달력 격자 없이 오늘 수업·일정·다가오는 일정만 보이는 작은 창."""
        self.tt_commit()
        self.compact = True
        self.view = self.conf["view"] = "cal"
        self.selected = self.today
        self.range_to = None
        self.build()
        self.ensure_on_screen()
        self.save_conf()

    def set_lang(self, lang):
        global FONT
        self.lang = lang
        FONT = pick_font(self, lang)
        self._fonts.clear()                  # 예전 글꼴로 만들어 둔 것은 버린다
        self.conf["lang"] = lang
        self.build()
        self.save_conf()

    def set_glass(self, key):
        self.glass = key
        self.conf["glass"] = key
        self.build()
        self.save_conf()

    def set_theme(self, name):
        self.theme = name
        self.conf["theme"] = name
        apply_theme(name)
        self.configure(bg=BG)
        self.build()
        self.save_conf()

    # ---------- 창 겹침 순서 ----------
    # '바탕화면 보기'(Win+D)는 창을 숨기지 않는다. 바탕화면 창(Progman)을
    # 모든 창 위로 끌어올린다. 그래서 위젯은 '보이는 상태' 그대로 바탕화면
    # 밑에 깔려 사라진다. 이걸 감지해서 그동안만 바탕화면 위로 올라간다.

    def owns(self, h):
        return win_pid(h) == os.getpid()

    def shell_pid(self):
        """탐색기(바탕화면·작업표시줄) 프로세스 번호. 탐색기가 다시 켜질 수 있어 몇 초마다 새로 본다."""
        now = time.time()
        if now - self._shell_pid[0] > 5:
            tray = user32.FindWindowW("Shell_TrayWnd", None)
            self._shell_pid = (now, win_pid(tray) if tray else 0)
        return self._shell_pid[1]

    def is_shell_ui(self, h, cls):
        """바탕화면·작업표시줄, 그리고 탐색기가 잠깐 띄우는 메뉴(파일 우클릭 메뉴 등)인가.
        이런 창이 앞에 와도 '다른 앱으로 돌아갔다'고 보지 않는다."""
        if cls in DESK_SHELL_CLASSES or cls in SHELL_MENU_CLASSES:
            return True
        if cls in EXPLORER_APP_CLASSES:
            return False
        pid = self.shell_pid()
        return bool(pid) and win_pid(h) == pid

    def is_below(self, top):
        """top 창보다 내 창이 아래에 있는가 (top 에서 아래로 따라 내려가 찾는다)."""
        h, n = user32.GetWindow(top, GW_HWNDNEXT), 0
        while h and n < 3000:
            if h == self.hwnd:
                return True
            h, n = user32.GetWindow(h, GW_HWNDNEXT), n + 1
        return False

    def covering_apps(self):
        """내 바로 아래에 보이는 앱 창이 있는가 = 누가 나를 앞으로 꺼냈는가."""
        h, n = user32.GetWindow(self.hwnd, GW_HWNDNEXT), 0
        while h and n < 3000:
            if win_class(h) in DESK_CLASSES:
                return False
            if user32.IsWindowVisible(h) and not is_cloaked(h):
                r = RECT()
                user32.GetWindowRect(h, ctypes.byref(r))
                if r.right - r.left > 100 and r.bottom - r.top > 100:
                    return True
            h, n = user32.GetWindow(h, GW_HWNDNEXT), n + 1
        return False

    def is_covered_by_desktop(self):
        """바탕화면 창(Progman 또는 WorkerW)이 내 창보다 위에 있어 위젯을 가리고 있는가."""
        for name in DESK_SURFACE_CLASSES:
            h = user32.FindWindowW(name, None)
            while h:
                if user32.IsWindowVisible(h) and self.is_below(h):
                    return h
                h = user32.FindWindowExW(None, h, name, None)
        return None

    def raise_above_desktop(self, desk=None):
        user32.SetWindowPos(self.hwnd, HWND_TOP, 0, 0, 0, 0, SWP_KEEP)
        if (not desk) or self.is_below(desk):          # 바탕화면이 더 높은 층에 있으면 맨 위 층으로
            user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_KEEP)
            self._topmost = True
        self._z = "showdesk"
        log("바탕화면 보기 감지 - 바탕화면 위로 올림%s" % (" (맨 위 층)" if self._topmost else ""))

    def lower_to_desktop(self, why=None):
        if self._z == "showdesk":
            log("바탕화면 보기 끝 - 원래 자리로%s" % (" (앞 창: %s)" % why if why else ""))
        if self._topmost:
            user32.SetWindowPos(self.hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_KEEP)
            self._topmost = False
        user32.SetWindowPos(self.hwnd, HWND_BOTTOM, 0, 0, 0, 0, SWP_KEEP)
        # 바탕화면을 누르면 바탕화면 창이 위젯 위로 올라와 있을 수 있다. 그 상태로 맨 밑에
        # 두면 바탕화면 밑에 깔려 사라지므로, 그때는 바탕화면 창 바로 위에 둔다.
        desk = self.is_covered_by_desktop()
        if desk:
            above = user32.GetWindow(desk, GW_HWNDPREV)
            user32.SetWindowPos(self.hwnd, above or HWND_TOP, 0, 0, 0, 0, SWP_KEEP)
            log("바탕화면이 위에 있어 그 바로 위에 둠")
        self._z = "bottom"

    def summon(self, quiet=False):
        """아이콘으로 불러냈을 때: 맨 앞으로 꺼내 활성 창으로 만든다. 활성 창이 되면
        사용자가 직접 다른 창을 누를 때까지 앞에 있다. (예전엔 '다음에 앞 창이 바뀌면
        내려간다'였는데, 시작 메뉴가 닫히며 앞 창이 저절로 바뀌어 곧바로 숨었다)"""
        if self.view == "cal" and not self.busy():
            self.go_today()
        user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        if self._topmost:
            user32.SetWindowPos(self.hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_KEEP)
            self._topmost = False
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_KEEP)
        if self.pinned:                       # 맨 앞으로 올린 뒤 '항상 위' 는 다시 푼다
            user32.SetWindowPos(self.hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_KEEP)
        ok = bool(user32.SetForegroundWindow(self.hwnd))
        self._z, self._summon_t = "summoned", time.time()
        self._fg_start = user32.GetForegroundWindow()
        if not quiet:
            log("아이콘으로 불러냄 (활성 창 %s)" % ("됨" if ok else "안 됨 — 앞에만 둠"))

    def sync_z(self):
        """지금 앞에 있는 창을 보고 위젯이 있어야 할 층을 정한다.
        층이 '바뀔 때만' SetWindowPos 를 부른다. 예전에 3초마다 무조건 불렀더니
        창이 멈춰서 Windows 가 강제 종료했다."""
        if not self.pinned:
            return
        if self._drag:
            # 드래그 중에는 층을 건드리지 않는다. SetWindowPos 가 창을 다시
            # 매핑하면 달력 캔버스가 <Configure> 를 받아 유리가 지워져 단색이
            # 되는 버그가 나기 때문이다.
            return
        fg = user32.GetForegroundWindow()
        fg_cls = win_class(fg) if fg else ""
        is_desk_shell = (not fg) or self.owns(fg) or self.is_shell_ui(fg, fg_cls)

        if self._z == "showdesk":
            # 바탕화면 보기 중에는 바탕화면·작업표시줄·탐색기 메뉴나 위젯을 만지는 동안 그대로 둔다.
            # 진짜 다른 앱 창(Chrome 등)으로 돌아갔을 때만 바탕화면 보기를 끝낸다.
            if fg and not is_desk_shell:
                if user32.IsWindowVisible(fg) and not is_cloaked(fg):
                    self.lower_to_desktop(why=fg_cls)
            return

        if fg and self.owns(fg):                      # 위젯을 쓰는 중
            self._z = "active"
            return

        if self._z in ("startup", "summoned"):   # 켜거나 불러낸 직후엔 앞에 둔다
            if self._fg_start is None:
                self._fg_start = fg
            # 불러낸 뒤 2초 안의 앞 창 변화는 시작 메뉴가 닫히는 등 저절로 생긴 것이다
            if fg == self._fg_start or time.time() - self._summon_t < 2.0:
                self._fg_start = fg
                return

        # 바탕화면 보기(Win+D 또는 작업표시줄 바탕화면 보기 버튼 클릭) 감지:
        desk_cover = None
        if fg_cls in DESK_SURFACE_CLASSES and self.is_below(fg):
            desk_cover = fg
        elif is_desk_shell:
            desk_cover = self.is_covered_by_desktop()

        if desk_cover:
            self.raise_above_desktop(desk_cover)
            return

        if self._z != "bottom":
            self.lower_to_desktop()
        elif self.covering_apps():             # 두 번 실행해서 앞으로 꺼내진 경우
            self._z, self._fg_start = "startup", fg

    def z_tick(self):
        # GetForegroundWindow 와 클래스 이름 확인뿐이라 아주 싸다.
        self._alive = time.time()
        try:
            if self._summon_ev and kernel32.WaitForSingleObject(self._summon_ev, 0) == 0:
                self.summon()
            if user32.IsIconic(self.hwnd):
                user32.ShowWindow(self.hwnd, 9)       # SW_RESTORE: 최소화되었으면 복구
            elif not user32.IsWindowVisible(self.hwnd):
                user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            # 다른 앱으로 '옮겨가는 순간'에만 날짜 달력·설명 풍선을 닫는다.
            # (앞 창이 내 것이 아니라는 이유만으로 닫으면 열자마자 닫힐 수 있다)
            fg = user32.GetForegroundWindow()
            if fg != getattr(self, "_last_fg", None):
                self._last_fg = fg
                if fg and not self.owns(fg):
                    self.close_picker()
                    self.hide_tip()
            self.sync_z()
        except Exception:
            log("z_tick 예외:\n" + traceback.format_exc())
        self._jobs["z"] = self.after(60, self.z_tick)

    def work_area(self):
        """작업 표시줄을 뺀, 창이 걸쳐 있는 모니터의 사용 가능 영역."""
        hmon = user32.MonitorFromWindow(self.hwnd, MONITOR_NEAREST)
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if hmon and user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            r = mi.rcWork
            return r.left, r.top, r.right, r.bottom
        return 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()

    def ensure_on_screen(self):
        """모니터를 빼면 저장된 좌표가 화면 밖을 가리킨다. 완전히 안으로 밀어넣는다."""
        if not hasattr(self, "hwnd"):
            return
        l, t, r, b = self.work_area()
        x, y, w, h = self.winfo_x(), self.winfo_y(), self.w(), self.h()
        nx = min(max(x, l), max(l, r - w))
        ny = min(max(y, t), max(t, b - h))
        if (nx, ny) == (x, y):
            return
        self.geometry("+%d+%d" % (nx, ny))
        self.update_idletasks()   # 이걸 빼면 winfo_x() 가 옛 좌표라 보정이 저장되지 않는다
        self.save_conf()
        if self.glass_img:
            self.build()
        log("화면 안으로 보정: (%d,%d) -> (%d,%d), 작업영역 %d,%d~%d,%d"
            % (x, y, nx, ny, l, t, r, b))

    def touch(self, _=None):
        self._last_input = time.time()

    def busy(self):
        """적던 글이 있거나 날짜 달력이 열려 있으면 화면을 함부로 바꾸지 않는다."""
        if getattr(self, "_picker", None) or self._editing:
            return True
        try:
            return bool(self.entry_w.get().strip())
        except (AttributeError, tk.TclError):
            return False

    def clock_tick(self):
        try:
            today = dt.date.today()
            if today != self.today:                    # 자정이 지났다
                old, self.today = self.today, today
                if self.selected == old:
                    self.selected, self.shown = today, today.replace(day=1)
                self.render()
            idle = time.time() - self._last_input
            if (self.view == "cal" and idle >= IDLE_RETURN and not self.busy()
                    and (self.selected != self.today
                         or self.shown != self.today.replace(day=1))):
                self.go_today()                        # 한동안 손대지 않으면 오늘로
            if self.view == "tt":
                self.tick_now()                        # '지금 수업' 표시를 옮긴다
            if self.compact and self.panel_mode == "day" and not self.busy():
                st = self.period_state()
                if (self.today, st[:2] if st else None) != self._cls_sig:
                    self.render_panel()                # 컴팩트의 '지금 수업' 강조
        except Exception:
            log("clock_tick 예외:\n" + traceback.format_exc())
        self._jobs["clock"] = self.after(30000, self.clock_tick)

    def refresh_glass(self):
        """바탕화면이 바뀌었으면(슬라이드쇼 등) 유리 배경을 다시 만든다."""
        if not self.glass_img or self._drag or self.busy():
            return
        x, y = self.window_pos()
        W, H = self.w(), self.h()
        raw = make_glass_bounded(x, y, W, H, BASE, self._glass_alpha or GLASS[self.glass])
        if raw:
            sig = tuple(int(v) // 6 for v in region_avg(raw, W, 0, 0, W, H))
            # 경계에서 한 칸씩 흔들리는 건 무시한다 (괜히 전체를 다시 그리면 깜빡인다)
            if not self._glass_sig or max(abs(a - b) for a, b in zip(sig, self._glass_sig)) > 1:
                log("바탕화면이 바뀌어 유리 배경을 다시 만든다")
                self._desk = None              # 드래그용 바탕화면 사진도 낡았다
                self.build()

    def wall_tick(self):
        """바탕화면 그림이 바뀌면 (Windows 추천·슬라이드쇼) 유리를 새 그림으로 다시 만든다.
        바뀌는 애니메이션이 끝나도록 2초 기다리고, 글을 쓰는 중이면 끝날 때까지 미룬다."""
        try:
            sig = wallpaper_sig()
            if sig != self._wall_sig:
                self._wall_sig = sig              # 드래그용 바탕화면 사진은 이제 낡았다
                self._wall_changed = time.time()
            if (self._wall_changed and time.time() - self._wall_changed >= 2
                    and not self._drag and not self.busy()):
                self._wall_changed = None
                if self.glass_img:
                    log("바탕화면 그림이 바뀌어 유리를 다시 만든다")
                    self.build()
        except Exception:
            log("wall_tick 예외:\n" + traceback.format_exc())
        self._jobs["wall"] = self.after(5000 if not self._wall_changed else 1000,
                                        self.wall_tick)

    def watchdog(self):
        try:
            self.beats += 1
            if self.beats % 30 == 0:
                log("heartbeat %d분" % self.beats)
            self.ensure_on_screen()
            if not self.data_ok:
                self.reload_data()
            if self.beats % 10 == 0 and time.time() - self._last_input > 60:
                self.refresh_glass()
        except Exception:
            log("watchdog 예외:\n" + traceback.format_exc())
        self._jobs["dog"] = self.after(60000, self.watchdog)

    # ---------- 화면 구성 ----------

    # ---------- 배치 · 유리 배경 ----------

    def layout(self):
        """창 안 배치를 숫자로 정한다. 유리 배경의 패널 평균색을 잴 때도 쓴다."""
        W, H = self.w(), self.h()
        if self.compact:                      # 카드 하나가 창을 다 쓴다
            self.pad = self.px(12)
            self.head_h = self.px(54)
            self.card_box = (self.pad, self.head_h, W - self.pad, H - self.pad)
            self.cal_box = (0, 0, 0, 0)
            ins = self.px(14)
        else:
            self.pad = self.px(18)
            self.head_h = self.px(66)
            pw = int(W * 0.38)
            gap = self.px(18)
            self.card_box = (W - self.pad - pw, self.head_h, W - self.pad, H - self.pad)
            self.cal_box = (self.pad, self.head_h, W - self.pad - pw - gap, H - self.pad)
            ins = self.px(16)
        x0, y0, x1, y1 = self.card_box
        self.panel_box = (x0 + ins, y0 + ins, x1 - ins, y1 - ins)
        self.panel_w = self.panel_box[2] - self.panel_box[0]

    def window_pos(self):
        try:
            _, _, x, y = re.split(r"[x+]", self.geometry())[:4]
            return int(x), int(y)
        except Exception:
            return self.winfo_x(), self.winfo_y()

    def make_background(self):
        """창 뒤 바탕화면으로 유리 배경을 만들고, 그 색에 맞춰 나머지 색을 정한다.
        (드래그용 바탕화면 전체 유리는 조금 뒤에 따로 만든다: prepare_desk)"""
        self.layout()
        apply_theme(self.theme)
        W, H = self.w(), self.h()
        alpha = GLASS.get(self.glass)
        if not alpha:
            self.glass_img = self._desk = None
            return
        x, y = self.window_pos()
        raw = None
        for _ in range(8):
            raw = make_glass_bounded(x, y, W, H, BASE, alpha)
            if raw:
                break
            time.sleep(0.12)          # 드래그 재촬영이 한창이면 잠시 양보하고 재시도
        if not raw:
            return                    # 기존 유리를 지우지 않는다 (단색으로 보이는 것 방지)
        # 유리 위에 바로 그리는 글자(달력 숫자 등)가 가장 밝은 곳(라이트 모드는 가장
        # 어두운 곳)에서도 4.5:1 이상 대비가 나도록, 모자라면 덮개를 더 진하게 한다.
        # 평균으로도 7:1 이 되게 한다 (밝은 바탕화면에서 '선명하게'도 읽기 편하도록).
        for _ in range(6):
            pts = region_samples(raw, W, 0, 0, W, H, 30)
            worst = min(contrast(FG, p) for p in pts)
            avg = contrast(FG, region_avg(raw, W, 0, 0, W, H))
            if (worst >= 4.5 and avg >= 7) or alpha >= 0.92:
                break
            alpha = min(0.92, alpha + 0.06)
            raw2 = make_glass_bounded(x, y, W, H, BASE, alpha)
            if not raw2:
                break
            raw = raw2
        try:
            img = tk.PhotoImage(master=self, data=bgra_to_ppm(raw, W, H),
                                format="ppm")
        except tk.TclError:
            log("유리 배경 이미지를 만들지 못함:\n" + traceback.format_exc())
            return
        self.glass_img = img          # 성공한 뒤에야 교체한다
        if self._desk and self._desk["key"][:2] != (alpha, BASE):
            self._desk = None
        self._glass_org = (x, y)
        self._glass_alpha = alpha
        avg_all = region_avg(raw, W, 0, 0, W, H)
        avg_panel = region_avg(raw, W, self.card_box[0], self.card_box[1],
                               self.card_box[2], self.card_box[3])
        self._glass_sig = tuple(int(v) // 6 for v in avg_all)
        derive_colors(avg_all, avg_panel)

    def build(self, capture=True):
        """창 안을 (다시) 그린다. 캔버스와 패널은 처음 한 번만 만들고, 그 뒤로는 같은
        것을 제자리에서 다시 칠한다. 부수고 새로 만들면 그 사이 빈 창이 보여 번쩍인다.
        capture=False 면 바탕화면을 다시 받아 오지 않고 지금 유리·색을 그대로 쓴다."""
        if self._drag:
            return                            # 드래그 중에는 다시 그리지 않는다
        first = self.shell is None
        if not first:
            self.tt_commit()                   # 크기·언어·테마를 바꿔도 적던 건 저장
            self.close_picker()
            self.hide_tip()
        self._discs = {}
        W, H = self.w(), self.h()
        self.geometry("%dx%d" % (W, H))
        if capture:
            self.make_background()
        else:
            self.layout()
        self.configure(bg=BG)

        # 창 전체가 캔버스 한 장이다. 위젯은 배경이 불투명해 유리 위에 올리면 네모난
        # 자국이 생기므로, 유리 위에 보이는 머리줄과 달력은 캔버스에 직접 그린다.
        if first:
            c = self.shell = self.base = tk.Canvas(self, width=W, height=H, bg=BG,
                                                  highlightthickness=0, bd=0)
            # 오른쪽 패널 = 유리 위의 카드. 내용(self.panel)은 다시 그릴 때마다 새로 만들어
            # 이 틀 안에서 갈아 끼운다 (render_panel).
            self.panel_host = tk.Frame(c, bg=CARD)
            self.panel = tk.Frame(self.panel_host, bg=CARD)
            self._panel_win = c.create_window(0, 0, window=self.panel_host, anchor="nw")
            self.cal = tk.Canvas(c, bg=BG, highlightthickness=0, bd=0)   # 달력·시간표
            self._cal_win = c.create_window(0, 0, window=self.cal, anchor="nw")
            self.cal.bind("<Configure>", lambda _: self.draw())
            self.cal.bind("<Button-1>", self.on_click)
            self.cal.bind("<Shift-Button-1>", self.on_shift_click)
            self.cal.bind("<Control-Button-1>", self.on_tt_ctrl_click)
            self.cal.bind("<B1-Motion>", self.on_tt_drag)
            self.cal.bind("<ButtonRelease-1>", self.on_tt_release)
            self.cal.bind("<Button-3>", self.menu)
            c.bind("<ButtonPress-1>", self.drag_start)
            c.bind("<B1-Motion>", self.drag_move)
            c.bind("<ButtonRelease-1>", self.drag_end)
            c.bind("<Button-3>", self.menu)
            c.pack(fill="both", expand=True)
        c = self.base
        c.config(width=W, height=H, bg=BG)
        c.delete("glass")
        c.delete("frame")
        if self.glass_img:
            ix, iy = self.glass_shift()
            c.create_image(ix, iy, image=self.glass_img, anchor="nw", tags="glass")
        c.create_rectangle(0, 0, W - 1, H - 1, outline=mix(BG, FG, 0.16), tags="frame")
        x0, y0, x1, y1 = self.card_box
        round_rect(c, x0, y0, x1, y1, self.px(18), fill=CARD, outline=mix(CARD, FG, 0.10),
                   tags="frame")
        px0, py0, px1, py1 = self.panel_box
        self.panel_host.config(bg=CARD, width=px1 - px0, height=py1 - py0)
        c.coords(self._panel_win, px0, py0)
        cx0, cy0, cx1, cy1 = self.cal_box
        self.cal.config(bg=BG, width=max(1, cx1 - cx0), height=max(1, cy1 - cy0))
        c.coords(self._cal_win, cx0, cy0)
        c.itemconfig(self._cal_win, state="hidden" if self.compact else "normal")
        self.draw_header()
        self.render()
        self.schedule_desk(1500)

    def recolor_from_desk(self):
        """드래그를 놓은 자리에 맞게 색을 다시 맞춘다. 바탕화면을 다시 받아 오지 않고,
        드래그 때 쓰던 바탕화면 유리에서 그 자리의 색을 읽는다 (다시 받아 오면 0.2초쯤
        멈췄다가 화면이 통째로 바뀌어 번쩍인다). 그 유리로는 글자 대비가 모자라면 False."""
        if not self.desk_ready() or self.glass_img is not self._desk["img"]:
            return False
        l, t, w, h = self._desk["key"][2]
        k = DESK_K
        sw, sh = len(range(0, w, k)), len(range(0, h, k))
        x, y = self.window_pos()

        def box(x0, y0, x1, y1):
            return (max(0, (x + x0 - l) // k), max(0, (y + y0 - t) // k),
                    min(sw, (x + x1 - l) // k), min(sh, (y + y1 - t) // k))
        x0, y0, x1, y1 = box(0, 0, self.w(), self.h())
        if x1 - x0 < 4 or y1 - y0 < 4:
            return False
        small = self._desk["small"]
        avg_all = region_avg(small, sw, x0, y0, x1, y1)
        worst = min(contrast(FG, p) for p in region_samples(small, sw, x0, y0, x1, y1, 30))
        if self._glass_alpha < 0.92 and (worst < 4.5 or contrast(FG, avg_all) < 7):
            return False
        sig = tuple(int(v) // 6 for v in avg_all)
        if sig == self._glass_sig:
            self.move_glass()                  # 색이 그대로다: 유리만 맞추면 된다
            return True
        cx0, cy0, cx1, cy1 = box(*self.card_box)
        avg_panel = (region_avg(small, sw, cx0, cy0, cx1, cy1)
                     if cx1 - cx0 >= 2 and cy1 - cy0 >= 2 else avg_all)
        apply_theme(self.theme)
        derive_colors(avg_all, avg_panel)
        self._glass_sig = sig
        self.build(capture=False)
        return True

    def glass_under(self, c, ox, oy):
        """캔버스 c 의 맨 아래에 유리 배경의 해당 부분을 깐다 (c 가 창 안 ox,oy 에 있을 때)."""
        if self.glass_img:
            ix, iy = self.glass_shift()
            c.create_image(ix - ox, iy - oy, image=self.glass_img, anchor="nw", tags="glass")

    # ---------- 드래그 중 유리 배경을 따라 움직임 ----------
    # 드래그 중에 바탕화면을 계속 다시 받아 오면 한 번에 0.2초쯤 걸려 늘 뒤처진다.
    # 대신 바탕화면 전체를 흐린 유리 한 장으로 미리 만들어 두고, 창이 움직이면 그
    # 그림을 반대로 밀기만 한다 (한 번 미는 데 1ms 안쪽). 그러면 창 뒤의 바탕화면이
    # 창에 붙어 실시간으로 비친다.

    def glass_shift(self):
        """유리 이미지를 창 안 어디에 놓아야 바탕화면과 맞는지 (창 왼쪽 위 기준)."""
        wx, wy = self._drag_pos or self.window_pos()
        return self._glass_org[0] - wx, self._glass_org[1] - wy

    def move_glass(self):
        ix, iy = self.glass_shift()
        for c, (ox, oy) in ((self.base, (0, 0)), (self.cal, self.cal_box[:2])):
            for it in c.find_withtag("glass"):
                if c.itemcget(it, "image") != str(self.glass_img):
                    c.itemconfig(it, image=self.glass_img)
                c.coords(it, ix - ox, iy - oy)

    def desk_ready(self):
        """미리 만든 바탕화면 유리가 지금 색·투명도·화면 크기에 맞는지."""
        d = self._desk
        return bool(d and d["key"] == (self._glass_alpha, BASE, desk_rect(), self._wall_sig))

    def prepare_desk(self):
        """바탕화면 전체 유리를 뒤에서 만든다. 그림 받기·흐리기는 다른 스레드에서,
        Tk 이미지로 바꾸는 것(40ms 쯤)만 화면 스레드에서 한다."""
        self._desk_job = None
        if not self.glass_img or self.desk_ready() or self._desk_busy:
            return
        if not _glass_busy.acquire(blocking=False):
            self._desk_job = self.after(1000, self.prepare_desk)   # 다른 촬영 중이면 나중에
            return
        self._desk_busy = True
        key = (self._glass_alpha, BASE, desk_rect(), self._wall_sig)

        def work():
            try:
                l, t, w, h = key[2]
                raw = make_glass(l, t, w, h, BASE, key[0])
                if raw:
                    self._desk_q.put((key, bgra_to_ppm(raw, w, h), shrink_raw(raw, w, h, DESK_K)))
            except Exception:
                log("바탕화면 유리 만들기 실패:\n" + traceback.format_exc())
            finally:
                _glass_busy.release()
        threading.Thread(target=work, daemon=True, name="glass-desk").start()
        self._desk_poll = self.after(60, self.take_desk)

    def schedule_desk(self, ms):
        if self._desk_job:
            self.after_cancel(self._desk_job)
        self._desk_job = self.after(ms, self.prepare_desk)

    def take_desk(self):
        running = _glass_busy.locked()         # 먼저 본다: 끝났다면 결과는 이미 큐에 있다
        try:
            key, ppm, small = self._desk_q.get_nowait()
        except queue.Empty:
            if running:
                self._desk_poll = self.after(60, self.take_desk)
            else:                                  # 실패로 끝남: 잠시 뒤 다시
                self._desk_poll, self._desk_busy = None, False
                self.schedule_desk(30000)
            return
        self._desk_poll, self._desk_busy = None, False
        if key[:2] != (self._glass_alpha, BASE) or key[3] != self._wall_sig:
            self.schedule_desk(500)            # 만드는 사이 테마·투명도가 바뀌었다: 새로
            return
        try:
            img = tk.PhotoImage(master=self, data=ppm, format="ppm")
        except tk.TclError:
            log("바탕화면 유리 이미지를 만들지 못함:\n" + traceback.format_exc())
            return
        self._desk = {"key": key, "img": img, "small": small}
        if self._drag:                     # 늦게 도착했으면 드래그 중에라도 바꿔 낀다
            self.use_desk()

    def use_desk(self):
        if self.desk_ready():
            self.glass_img = self._desk["img"]
            self._glass_org = self._desk["key"][2][:2]
            self.move_glass()

    def desk_fits(self):
        """드래그를 놓은 자리에서도 지금 색이 그대로 맞는지 (맞으면 다시 만들 필요 없음)."""
        if not self.desk_ready() or self.glass_img is not self._desk["img"]:
            return False
        l, t, w, h = self._desk["key"][2]
        k = DESK_K
        sw, sh = len(range(0, w, k)), len(range(0, h, k))
        x, y = self.window_pos()
        x0, y0 = max(0, (x - l) // k), max(0, (y - t) // k)
        x1, y1 = min(sw, (x - l + self.w()) // k), min(sh, (y - t + self.h()) // k)
        if x1 - x0 < 4 or y1 - y0 < 4:
            return False
        small = self._desk["small"]
        sig = tuple(int(v) // 6 for v in region_avg(small, sw, x0, y0, x1, y1))
        worst = min(contrast(FG, p) for p in region_samples(small, sw, x0, y0, x1, y1, 30))
        return sig == self._glass_sig and (worst >= 4.5 or self._glass_alpha >= 0.92)

    # ---------- 머리줄 (유리 위에 직접 그림) ----------

    def set_title(self, text):
        self.base.itemconfig("title", text=text)

    def title_text(self):
        return self.base.itemcget("title", "text")

    def head_button(self, tag, x1, cy, label, cmd, active=False, size=12, tip=None):
        """오른쪽 끝이 x1 인 알약 모양 버튼을 그리고 왼쪽 끝 x 를 돌려준다."""
        c = self.base
        fnt = self.f(size, active)
        tw = self.measure(label, self.fpx(size), active)
        w = tw + self.px(26)
        h = self.px(34)
        x0 = x1 - w
        def on():                              # 설정 버튼은 설정이 열려 있는 동안 켜져 있다
            return active or (tag == "b_menu" and self.panel_mode == "settings")

        def idle():
            return SEL_BG if on() else mix(BG, FG, 0.10)
        round_rect(c, x0, cy - h / 2, x1, cy + h / 2, h / 2, fill=idle(), outline="",
                   tags=("head", "btn", tag, tag + "_bg"))
        if tag == "b_menu":                     # 설정 버튼은 글자 대신 직접 그린 톱니바퀴
            c.create_image(int((x0 + x1) / 2), int(cy), image=self.gear(on()),
                           tags=("head", "btn", tag, tag + "_tx"))
        else:
            c.create_text((x0 + x1) / 2, cy, text=label, font=fnt,
                          fill=FG if on() else MUTED, tags=("head", "btn", tag, tag + "_tx"))
        c.tag_bind(tag, "<Button-1>", lambda e: cmd(e))
        c.tag_bind(tag, "<Enter>", lambda e: (c.itemconfig(
            tag + "_bg", fill=SEL_BG if on() else mix(BG, FG, 0.18)), c.config(cursor="hand2")))
        c.tag_bind(tag, "<Leave>", lambda e: (c.itemconfig(tag + "_bg", fill=idle()),
                                              c.config(cursor="")))
        if tip:
            self.tip_canvas(c, tag, tip)
        return x0

    def draw_header(self):
        c = self.base
        c.delete("head")
        c.config(cursor="")                    # 누른 버튼이 사라지면 <Leave> 가 오지 않는다
        W, cy = self.w(), self.head_h * 0.52
        gap = self.px(8)
        c.create_text(self.pad + self.px(4), cy, anchor="w", text="", fill=FG,
                      font=self.f(17 if self.compact else 21, True), tags=("head", "title"))
        # 톱니바퀴: 누르면 바로 아래 카드가 설정으로 바뀐다 (≡ 는 메뉴가 펼쳐질 것처럼 보였다)
        x = self.head_button("b_menu", W - self.pad, cy, "≡", self.menu, size=15,
                             tip=self.t("tip_menu"))
        if self.update_ver:                      # 새 버전이 있으면 ≡ 에 점
            box = c.bbox("b_menu_bg")
            self.disc(c, box[2] - self.px(7), box[1] + self.px(7), self.px(4), ACCENT,
                      tags=("head", "btn", "b_menu"))
        if self.compact:
            if self.selected != self.today:      # 다른 날을 보고 있으면 돌아오는 버튼
                self.head_button("b_today", x - gap, cy, self.t("today"),
                                 lambda e: self.go_today())
            return
        for key in ("tt", "cal"):                # 달력 / 시간표 전환
            x = self.head_button("b_" + key, x - gap, cy, self.t(key),
                                 lambda e, k=key: self.set_view(k), active=self.view == key)
        if self.view == "cal":                   # 시간표에는 월 이동이 의미가 없다
            x -= self.px(10)
            x = self.head_button("b_next", x - gap, cy, "›", lambda e: self.shift(1), size=15)
            x = self.head_button("b_today", x - self.px(4), cy, self.t("today"),
                                 lambda e: self.go_today())
            self.head_button("b_prev", x - self.px(4), cy, "‹", lambda e: self.shift(-1),
                             size=15)

    def tip_canvas(self, c, tag, text):
        def show():
            self.hide_tip()
            box = c.bbox(tag)
            if not box:
                return
            t = tk.Toplevel(self)
            t.overrideredirect(True)
            t.attributes("-topmost", True)
            tk.Label(t, text=text, bg=FG, fg=CARD, font=self.f(10),
                     padx=self.px(8), pady=self.px(4)).pack()
            t.update_idletasks()
            x = c.winfo_rootx() + box[2] - t.winfo_reqwidth()
            t.geometry("+%d+%d" % (max(0, x), c.winfo_rooty() + box[3] + self.px(6)))
            self._tip = t

        def enter(_):
            self.hide_tip()
            self._tip_job = self.after(450, show)
        c.tag_bind(tag, "<Enter>", enter, add="+")
        c.tag_bind(tag, "<Leave>", lambda _: self.hide_tip(), add="+")

    def set_view(self, key):
        self.tt_commit()                       # 화면을 바꾸기 전에 저장
        if key == self.view or self.compact:
            return
        self.view = key
        self.conf["view"] = key
        self.panel_mode = "day"
        self._tt_adding = False
        self.range_to = None
        # 탭만 바꾸는 데 창 전체를 다시 만들 필요는 없다 (바탕화면을 다시 받아 오느라
        # 끊기고 깜빡였다). 머리줄 버튼과 내용만 다시 그린다.
        self.close_picker()
        self.hide_tip()
        self.draw_header()
        self.render()
        self.save_conf()

    def draw(self):
        if self.compact:
            return
        if self.view == "tt":
            self.draw_tt()
        else:
            self.draw_grid()

    def on_click(self, e):
        if self.view == "tt":
            self.on_tt_click(e)
        else:
            self.on_grid_click(e)

    def render(self):
        if self.compact:
            self.set_title(self.day_title(self.selected))
        elif self.view == "tt":
            self.set_title(self.t("tt_title", wk=self.week_label(self.today)))
        else:
            self.set_title(self.month_title(self.shown))
        self.draw()
        self.render_panel()

    def day_title(self, d):
        return self.t("day_title", m=d.month, d=d.day, wd=self.t("wd")[d.weekday()],
                      mon=MONTHS_EN[d.month - 1][:3])

    # ---------- 달력 ----------

    def dot_color(self, col):
        col = pc(col)
        return col if THEME == "dark" else mix(col, "#000000", 0.18)

    def range_span(self):
        """Shift+클릭으로 고른 기간 (첫날, 끝날). 없으면 None."""
        if self.range_to and self.range_to != self.selected:
            return tuple(sorted((self.selected, self.range_to)))
        return None

    def day_marks(self, day):
        """그 날 달력 칸에 표시할 것: ([(모양, 색, 제목, 끝냄)], [기간 일정 (색, 시작?, 끝?)])."""
        marks, bands = [], []
        for kind, title, _ in self.exams_on(day):
            marks.append(("sq", self.dot_color(self.course_color(title)),
                          "%s · %s" % (self.t("exam_%s_s" % kind), title),
                          self.exam_done(title, kind)))
        for it in self.events.get(key_of(day), []):
            marks.append(("dot", self.dot_color(it.get("color", PALETTE[0])),
                          it.get("title", ""), bool(it.get("done"))))
        for sr in self.series:
            if not series_on(sr, day):
                continue
            col = self.dot_color(sr.get("color", PALETTE[0]))
            if sr.get("repeat"):
                marks.append(("dot", col, sr.get("title", ""), series_done(sr, day)))
            else:
                bands.append((DIM if series_done(sr, day) else col,
                              sr.get("start") == day.isoformat(),
                              (sr.get("end") or sr.get("start")) == day.isoformat()))
        return marks, bands

    def draw_grid(self):
        if self.compact:
            return
        c = self.cal
        W, H = self.cal_size()
        c.delete("all")
        self.glass_under(c, self.cal_box[0], self.cal_box[1])
        self.weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(
            self.shown.year, self.shown.month)
        self.gut = max(20.0, W * 0.055)      # 单/双 표시용 왼쪽 여백
        self.cw = (W - self.gut) / 7.0
        self.hh = max(18.0, H * 0.085)
        self.ch = (H - self.hh) / float(len(self.weeks))
        # 글자는 칸의 짧은 변 기준. 세로만 보면 세로로 늘였을 때 폭을 넘어 잘린다.
        unit = min(self.cw, self.ch)
        f_day = max(10, int(unit * 0.33))
        f_hdr = max(9, int(min(self.hh * 0.46, self.cw * 0.24)))
        r = max(2, int(unit * 0.05))
        pad = max(4.0, unit * 0.15)
        rad = max(4, int(unit * 0.18))
        # 큰 크기에서는 점 대신 일정 제목을 칸에 바로 적는다
        f_pre = max(10, int(unit * 0.135))
        lh = f_pre * 1.5
        preview = self.size_idx >= 3
        band_h = max(2, self.px(3))
        span = self.range_span()

        for i, d in enumerate(self.t("wd_cal")):
            c.create_text(self.gut + (i + 0.5) * self.cw, self.hh * 0.42, text=d,
                          fill=SUN if i == 0 else SAT if i == 6 else MUTED,
                          font=(FONT, -f_hdr))
        c.create_line(self.gut + pad, self.hh - 1, W - pad, self.hh - 1, fill=GRID)

        for ri, week in enumerate(self.weeks):
            # 그 주가 单周인지 双周인지 왼쪽에 표시 (주 계산은 월요일 기준)
            odd = self.is_odd_week(week[1])
            wn = self.week_no(week[1])             # 주차 번호를 알면 번호를 적는다
            c.create_text(self.gut * 0.5, self.hh + ri * self.ch + pad * 0.7 + f_day * 0.7,
                          text=str(wn) if wn is not None and 1 <= wn <= 30 else
                          self.t("odd_s") if odd else self.t("even_s"),
                          fill=MUTED if odd else DIM,
                          font=(FONT, -max(9, int(f_hdr * 0.9))))
            for ci, day in enumerate(week):
                x0, y0 = self.gut + ci * self.cw, self.hh + ri * self.ch
                x1 = x0 + self.cw
                # 칸 전체를 칠하면 세로로 긴 막대가 되므로 높이를 제한한다
                # (제목을 적는 큰 크기에서는 칸을 다 쓴다)
                yb = y0 + (self.ch - 3 if preview else min(self.ch - 3, unit * 1.12))
                if span and span[0] <= day <= span[1]:
                    round_rect(c, x0 + 3, y0 + 3, x1 - 3, yb, rad, outline="",
                               fill=SEL_BG if day in (self.selected, self.range_to) else TODAY)
                elif day == self.selected:
                    round_rect(c, x0 + 3, y0 + 3, x1 - 3, yb, rad, fill=SEL_BG, outline="")
                ny = y0 + pad * 0.7 + f_day * 0.7          # 숫자의 세로 중심
                if day == self.today:                     # 오늘은 강조색 동그라미
                    tw = self.measure(str(day.day), f_day, True)
                    cx, rr = round(x0 + pad + tw / 2.0), f_day * 0.86
                    self.disc(c, cx, round(ny), rr, ACCENT)
                    c.create_text(cx, ny, text=str(day.day), fill=ACCENT_INK,
                                  font=(FONT, -f_day, "bold"))
                else:
                    fg = (DIM if day.month != self.shown.month else
                          SUN if ci == 0 else SAT if ci == 6 else FG)
                    c.create_text(x0 + pad, ny, text=str(day.day), fill=fg, anchor="w",
                                  font=(FONT, -f_day))
                found, bands = self.day_marks(day)
                bands = bands[:3]
                band_step = band_h + self.px(2)
                top = ny + f_day * 0.95 + len(bands) * band_step
                n_lines = int((y0 + self.ch - self.px(6) - top) // lh) if preview else 0
                cy = min(ny + f_day * 1.25 + r, yb - r - 3)
                # 기간 일정은 옆 칸으로 이어지는 얇은 띠. 제목을 적는 큰 크기에서는 숫자
                # 바로 아래, 아니면 점 아래에 둔다 (칸 맨 아래에 두면 아랫줄 것처럼 보인다).
                band_top = (ny + f_day * 0.85 if preview else
                            min(cy + r + self.px(4), y0 + self.ch - len(bands) * band_step - 1))
                for k, (col, first, last) in enumerate(bands):
                    by = band_top + k * band_step
                    c.create_rectangle(x0 + (pad if first else 0), by,
                                       x1 - (pad if last else 0), by + band_h,
                                       fill=col, outline="", tags="band")
                if n_lines >= 1 and found:
                    # 제목 미리보기: 줄마다 표시 + 제목, 다 못 적으면 마지막 줄에 +N
                    show, more = found, 0
                    if len(found) > n_lines:
                        more = len(found) - (n_lines - 1)
                        show = found[:n_lines - 1]
                    # 칸이 좁아 제목이 몇 글자 못 들어간다. 숫자보다 왼쪽에서 시작한다.
                    mx = x0 + self.px(6) + r
                    tx = mx + r + self.px(4)
                    for k, (shape, col, title, done) in enumerate(show):
                        ly = top + k * lh + lh / 2
                        if shape == "sq":
                            c.create_rectangle(mx - r, ly - r, mx + r, ly + r,
                                               fill="" if done else col,
                                               outline=DIM if done else "")
                        elif done:
                            c.create_oval(mx - r, ly - r, mx + r, ly + r, fill="", outline=DIM)
                        else:
                            self.disc(c, mx, ly, r, col, tags="dot")
                        c.create_text(tx, ly, anchor="w", fill=DIM if done else FG,
                                      font=(FONT, -f_pre), tags="preview",
                                      text=self.fit(title, f_pre, x1 - self.px(3) - tx))
                    if more:
                        c.create_text(tx, top + len(show) * lh + lh / 2, anchor="w",
                                      text="+%d" % more, fill=MUTED, font=(FONT, -f_pre))
                    continue
                # 시험·과제 마감은 네모, 일정은 동그라미 (시험이 먼저)
                evs = [m for m in found if m[0] == "dot"]
                all_done = bool(evs) and all(m[3] for m in evs)
                marks = ([("sq", m[1]) for m in found if m[0] == "sq" and not m[3]]
                         + [("dot", m[1]) for m in evs if not m[3]]
                         + ([("ring", DIM)] if all_done else [])
                         + [("sq_done", m[1]) for m in found if m[0] == "sq" and m[3]])
                step = r * 2 + self.px(4)
                fit = max(1, int((x1 - 3 - (x0 + pad)) // step))
                more = 0
                if len(marks) > fit:                   # 다 못 그리면 마지막 자리에 +N
                    more = len(marks) - (fit - 1)
                    marks = marks[:fit - 1]
                for k, (shape, col) in enumerate(marks):
                    cx = x0 + pad + r + k * (r * 2 + self.px(4))
                    if shape == "sq":
                        c.create_rectangle(cx - r, cy - r, cx + r, cy + r, fill=col, outline="")
                    elif shape == "sq_done":                 # 끝낸 시험은 빈 네모
                        c.create_rectangle(cx - r, cy - r, cx + r, cy + r, fill="", outline=DIM)
                    elif shape == "ring":                    # 그 날 일정을 다 끝냄
                        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill="", outline=DIM)
                    else:
                        self.disc(c, cx, cy, r, col, tags="dot")
                if more:
                    c.create_text(x0 + pad + len(marks) * step, cy, text="+%d" % more,
                                  anchor="w", fill=MUTED, font=(FONT, -max(8, int(r * 3.2))))

    def grid_day(self, e):
        if not getattr(self, "weeks", None) or e.y < self.hh or e.x < self.gut:
            return None
        ci = int((e.x - self.gut) // self.cw)
        ri = int((e.y - self.hh) // self.ch)
        if 0 <= ri < len(self.weeks) and 0 <= ci < 7:
            return self.weeks[ri][ci]
        return None

    def on_grid_click(self, e):
        day = self.grid_day(e)
        if day:
            self.select(day)

    def on_shift_click(self, e):
        """Shift+클릭: 고른 날부터 이 날까지를 기간으로 잡는다 (방학·여행 같은 여러 날 일정)."""
        if self.view == "tt":
            return self.on_tt_click(e)
        day = self.grid_day(e)
        if day and day != self.selected:
            self.range_to, self.repeat, self.panel_mode = day, "", "day"
            self.draw_grid()
            self.render_panel()
            try:
                self.entry_w.focus_set()
            except (AttributeError, tk.TclError):
                pass
        return "break"

    def select(self, day):
        self.selected = day
        self.range_to = None
        self.panel_mode = "day"
        if self.compact:
            self.draw_header()
            self.render()
            return
        if day.month != self.shown.month:
            self.shown = day.replace(day=1)
            self.set_title(self.month_title(self.shown))
        self.draw_grid()
        self.render_panel()

    def shift(self, n):
        m = self.shown.month + n
        self.shown = dt.date(self.shown.year + (m - 1) // 12, (m - 1) % 12 + 1, 1)
        self.render()

    def go_today(self):
        self.today = dt.date.today()
        self.shown = self.today.replace(day=1)
        self.selected = self.today
        self.range_to = None
        if self.compact:
            self.draw_header()
        self.render()

    # ---------- 시간표 ----------

    def tt_key(self, day, period):
        return "%d-%d" % (day, period)

    def wrap2(self, text, px, max_w, bold=False):
        """두 줄까지 나눈다. 둘째 줄도 넘치면 … 로 줄인다. 띄어쓰기가 있으면 그 자리에서."""
        if self.measure(text, px, bold) <= max_w:
            return [text]
        cut = 1
        while cut < len(text) and self.measure(text[:cut + 1], px, bold) <= max_w:
            cut += 1
        sp = text.rfind(" ", 0, cut + 1)
        latin = text[:cut].isascii()
        if sp > 0 and (latin or sp > cut // 2):
            cut = sp                     # 영어는 단어 중간에서 자르지 않는다
        elif latin and text[cut - 1].isalpha() and text[cut].isalpha():
            # 띄어쓰기 없는 긴 영어 단어는 하이픈을 붙여 나눈다 (Microecon- / omics)
            while cut > 2 and self.measure(text[:cut] + "-", px, bold) > max_w:
                cut -= 1
            return [text[:cut] + "-", self.fit(text[cut:], px, max_w, bold)]
        else:
            # 중국어 줄바꿈 규칙: 괄호 부분은 통째로 다음 줄로 (高等数学 / （B）),
            # 여는 괄호로 줄을 끝내거나 닫는 문장부호로 줄을 시작하지 않는다.
            p = max(text.rfind(o, 0, cut) for o in "（(《【「")
            if p > 0 and p >= cut // 2:
                cut = p
            while cut > 1 and (text[cut - 1] in "（(《【「" or text[cut] in "）)，。、》】」：；！？"):
                cut -= 1
        first, rest = text[:cut].rstrip(), text[cut:].lstrip()
        return [first, self.fit(rest, px, max_w, bold)] if rest else [first]

    def shown_item(self, key, sel_keys=()):
        """시간표 칸에 그릴 수업. 고른 칸은 고치는 중인 대표 수업, 나머지 칸은 이번 주에
        있는 수업 (없으면 대표 수업)."""
        items = cell_items(self.tt, key)
        if not items:
            return None
        if key not in sel_keys:
            for it in items:
                if self.item_on(it, self.today):
                    return it
        return items[0]

    def tt_blocks(self, pick=None):
        """세로로 붙어 있는 같은 수업을 (요일, 시작교시, 칸수, 내용) 으로 묶는다.
        pick(칸) 이 없으면 칸의 대표 수업으로 묶는다 (고칠 때의 단위)."""
        def get(di, p):
            key = self.tt_key(di, p)
            if pick:
                return pick(key)
            items = cell_items(self.tt, key)
            return items[0] if items else None

        out = []
        for di in range(self.n_days):
            p = 1
            while p <= PERIODS:
                it = get(di, p)
                if not it:
                    p += 1
                    continue
                span = 1
                while p + span <= PERIODS:
                    nxt = get(di, p + span)
                    if not nxt or item_core(nxt) != item_core(it):
                        break
                    span += 1
                out.append((di, p, span, it))
                p += span
        return out

    def bring_front(self, key, it, to_back=False):
        """그 수업을 칸의 대표로 올린다 (세로로 이어진 칸 모두). 고치는 코드는 대표 수업만
        다루므로, 고르려는 수업을 먼저 대표로 올려 둔다. 내용은 바뀌지 않는다.
        to_back 이면 반대로 맨 뒤로 보낸다 (바로 뒤에 있던 수업이 대표가 된다)."""
        core = item_core(it)
        di, p = (int(v) for v in key.split("-"))

        def has(q):
            return any(item_core(x) == core for x in cell_items(self.tt, self.tt_key(di, q)))
        if not has(p):
            return
        a = b = p
        while a > 1 and has(a - 1):
            a -= 1
        while b < PERIODS and has(b + 1):
            b += 1
        changed = False
        for q in range(a, b + 1):
            k = self.tt_key(di, q)
            items = cell_items(self.tt, k)
            i = next(i for i, x in enumerate(items) if item_core(x) == core)
            if to_back and len(items) > 1:
                items.append(items.pop(i))
                set_cell(self.tt, k, items)
                changed = True
            elif i and not to_back:
                items.insert(0, items.pop(i))
                set_cell(self.tt, k, items)
                changed = True
        if changed:
            self.save_tt()

    def period_state(self, now=None):
        """('now', 교시, 진행비율) / ('next', 교시, 0) / None. 주말이면 None."""
        now = now or dt.datetime.now()
        if now.weekday() >= self.n_days:
            return None
        m = now.hour * 60 + now.minute + now.second / 60.0
        for i, (a, b) in enumerate(self.periods[:PERIODS], 1):
            if a <= m < b:
                return ("now", i, (m - a) / float(b - a))
            if m < a:                     # 쉬는 시간: 30분 안에 시작하는 다음 수업
                return ("next", i, 0.0) if a - m <= 30 else None
        return None

    def period_text(self, p):
        if p - 1 >= len(self.periods):
            return ""
        a, b = self.periods[p - 1]
        return "%02d:%02d–%02d:%02d" % (a // 60, a % 60, b // 60, b % 60)

    def block_colors(self, col):
        """수업 타일의 (바탕, 테두리, 글자, 보조 글자). 글자는 바탕과 7:1 이상."""
        # 색은 살리되 글자 대비가 모자라면 바탕을 테마 쪽으로 조금씩 옮긴다
        tone = BASE if THEME == "dark" else "#ffffff"
        fill = toward(mix(col, tone, 0.55), tone, 7.2, FG, step=0.08)
        edge = mix(col, fill, 0.25)
        sub = toward(mix(FG, fill, 0.30), FG, 4.6, fill)
        return fill, edge, FG, sub

    def draw_tt(self):
        if self.compact:
            return
        c = self.cal
        W, H = self.cal_size()
        c.delete("all")
        self.glass_under(c, self.cal_box[0], self.cal_box[1])
        odd_now = self.is_odd_week(self.today)
        self.tgut = max(28.0, W * 0.10)           # 교시 번호 + 시작 시각
        self.thh = max(18.0, H * 0.06)            # 요일 머리글
        self.tcw = (W - self.tgut) / float(self.n_days)
        self.tch = (H - self.thh) / float(PERIODS)
        f_hdr = max(8, int(min(self.thh * 0.52, self.tcw * 0.20)))
        f_num = max(8, int(min(self.tch * 0.34, self.tgut * 0.30)))
        f_tm = max(7, int(f_num * 0.64))
        rad = max(4, int(min(self.tcw, self.tch) * 0.16))
        today_col = self.today.weekday()
        state = self.period_state()
        cur_p = state[1] if state and state[0] == "now" else None
        self._now_sig = (self.today, state[:2] if state else None)

        for i, d in enumerate(self.t("wd_tt")[:self.n_days]):
            x0, x1 = self.tgut + i * self.tcw, self.tgut + (i + 1) * self.tcw
            on = i == today_col
            if on:
                round_rect(c, x0 + 3, 2, x1 - 3, self.thh - 3, rad, fill=TODAY, outline="")
            c.create_text((x0 + x1) / 2, self.thh * 0.48, text=d, fill=FG if on else MUTED,
                          font=(FONT, -f_hdr, "bold") if on else (FONT, -f_hdr))

        show_time = self.tch > f_num * 2.4
        for p in range(1, PERIODS + 1):
            y0 = self.thh + (p - 1) * self.tch
            ym = y0 + self.tch / 2
            hot = p == cur_p
            num_font = (FONT, -f_num, "bold") if hot else (FONT, -f_num)
            if show_time and p - 1 < len(self.periods):
                c.create_text(self.tgut * 0.45, ym - f_tm * 0.62, text=str(p),
                              fill=ACCENT if hot else MUTED, font=num_font)
                c.create_text(self.tgut * 0.45, ym + f_num * 0.58,
                              text=self.period_text(p)[:5], fill=ACCENT if hot else DIM,
                              font=(FONT, -f_tm))
            else:
                c.create_text(self.tgut * 0.45, ym, text=str(p),
                              fill=ACCENT if hot else MUTED, font=num_font)
            if p > 1:
                c.create_line(self.tgut + 4, y0, W - 4, y0, fill=GRID, dash=(2, 4))

        # 지금 시각 가로선은 블록보다 먼저 그려 블록 뒤로 숨긴다. 위에 그리면
        # 과목명 글자를 가로질러 읽기 어렵다. (빈 칸에서는 보이고, 점은 위에 남긴다)
        if state and state[0] == "now" and 0 <= today_col < self.n_days:
            y = self.thh + (state[1] - 1 + state[2]) * self.tch
            lx0 = self.tgut + today_col * self.tcw
            c.create_line(lx0 + 2, y, lx0 + self.tcw - 2, y, fill=ACCENT, width=2,
                          tags="nowline")

        # 세로로 이어진 같은 수업은 한 블록으로 묶어 글자를 한 번만 그린다.
        pad = self.px(2) if self.n_days == 7 else self.px(3)
        f_ttl = max(8, int(min(self.tch * 0.32, self.tcw * 0.15)))
        f_sub = max(8, int(f_ttl * 0.82))
        boxes, now_boxes = {}, {}
        sel_keys = set(self.block_keys())
        self._tt_stacks = []                    # 겹친 카드: (요일, 교시, 칸수, 앞 카드, 전체 자리)
        peek = max(6, int(min(self.tcw * 0.10, self.tch * 0.24)))
        for di, p, span, it in self.tt_blocks(lambda k: self.shown_item(k, sel_keys)):
            kind = it.get("week", "all")
            now_on = self.item_on(it, self.today)
            col = pc(it.get("color", PALETTE[4]))
            x0 = self.tgut + di * self.tcw + pad
            y0 = self.thh + (p - 1) * self.tch + pad
            x1 = self.tgut + (di + 1) * self.tcw - pad
            y1 = self.thh + (p - 1 + span) * self.tch - pad
            # 같은 시간에 다른 주의 수업이 더 있으면 카드를 겹쳐 놓는다. 뒤 카드는 오른쪽
            # 아래로 조금 삐져나오고, 거기를 누르면 앞으로 나온다. 그 주에 없는 수업은 점선.
            here = cell_items(self.tt, self.tt_key(di, p))
            at = next((i for i, x in enumerate(here) if item_core(x) == item_core(it)), 0)
            backs = (here[at + 1:] + here[:at])[:2]
            nb = len(backs)
            if nb:
                full = (x0, y0, x1, y1)
                for k in reversed(range(nb)):
                    b = backs[k]
                    bcol = pc(b.get("color", PALETTE[4]))
                    bx0, by0 = x0 + (k + 1) * peek, y0 + (k + 1) * peek
                    bx1, by1 = x1 - (nb - 1 - k) * peek, y1 - (nb - 1 - k) * peek
                    if self.item_on(b, self.today):
                        bfill, bedge = self.block_colors(bcol)[:2]
                        round_rect(c, bx0, by0, bx1, by1, rad, fill=bfill, outline=bedge,
                                   width=max(1, self.px(1.5)), tags="back")
                    else:
                        round_rect(c, bx0, by0, bx1, by1, rad, fill=mix(bcol, BG, 0.62),
                                   outline=mix(bcol, BG, 0.1), dash=(3, 3), tags="back")
                x1, y1 = x1 - nb * peek, y1 - nb * peek
                self._tt_stacks.append((di, p, span, (x0, y0, x1, y1), full))
            if now_on:
                fill, edge, ink, sub = self.block_colors(col)
                round_rect(c, x0, y0, x1, y1, rad, fill=fill, outline=edge,
                           width=max(1, self.px(1.5)))
                for p2 in range(p, p + span):
                    now_boxes[(di, p2)] = (x0, y0, x1, y1)
            else:
                # 뒤에 카드가 있으면 비쳐 보이지 않게 옅게 칠한다
                round_rect(c, x0, y0, x1, y1, rad, fill=mix(col, BG, 0.9) if nb else "",
                           outline=mix(col, BG, 0.3), dash=(3, 3))
                ink, sub = MUTED, DIM
            for p2 in range(p, p + span):
                boxes[(di, p2)] = (x0, y0, x1, y1)
            tx0 = x0 + self.px(4)
            inner = x1 - tx0 - self.px(4)
            lh = f_ttl * 1.4
            title = it.get("title", "")
            # 이름이 길면 높이가 되는 한 두 줄로. '中国神…' 보다 '中国神话 / 研究' 가 낫다.
            titles = (self.wrap2(title, f_ttl, inner, True) if (y1 - y0) > lh * 2.2
                      else [self.fit(title, f_ttl, inner, True)])
            lines = [(t, f_ttl, ink, True) for t in titles]
            extra = it.get("room", "")
            if kind != "all":
                extra = (extra + " · " if extra else "") + self.t("chip_" + kind)
            if it.get("weeks"):
                extra = (extra + " · " if extra else "") + it["weeks"]
            if extra and (y1 - y0) > lh * (len(lines) + 0.9) + self.px(6):
                lines.append((self.fit(extra, f_sub, inner, False), f_sub, sub, False))
            top = (y0 + y1) / 2 - (len(lines) - 1) * lh / 2
            for i, (txt, size, fill_c, bold) in enumerate(lines):
                c.create_text((tx0 + x1) / 2, top + i * lh, text=txt, fill=fill_c,
                              font=(FONT, -size, "bold") if bold else (FONT, -size))

        if self.tt_multi:                       # 여러 칸: 칸마다 강조색 테두리
            for di, p in self.tt_multi:
                x0 = self.tgut + di * self.tcw + pad
                y0 = self.thh + (p - 1) * self.tch + pad
                round_rect(c, x0 + 1, y0 + 1, x0 + self.tcw - 2 * pad - 1,
                           y0 + self.tch - 2 * pad - 1, max(2, rad - 2),
                           fill="", outline=ACCENT, width=2)
        else:
            di, p = self.tt_sel                 # 고른 칸 (수업이면 그 블록 전체)
            sx0, sy0, sx1, sy1 = boxes.get((di, p)) or (
                self.tgut + di * self.tcw + pad, self.thh + (p - 1) * self.tch + pad,
                self.tgut + (di + 1) * self.tcw - pad, self.thh + p * self.tch - pad)
            round_rect(c, sx0 + 2, sy0 + 2, sx1 - 2, sy1 - 2, max(2, rad - 2), fill="",
                       outline=mix(FG, BG, 0.30), width=2)

        # 지금 수업 (쉬는 시간이면 다음 수업)
        if state and 0 <= today_col < self.n_days:
            kind_s, p, frac = state
            box = now_boxes.get((today_col, p)) or (
                self.tgut + today_col * self.tcw + pad, self.thh + (p - 1) * self.tch + pad,
                self.tgut + (today_col + 1) * self.tcw - pad, self.thh + p * self.tch - pad)
            bx0, by0, bx1, by1 = box
            if kind_s == "now":
                round_rect(c, bx0 - 2, by0 - 2, bx1 + 2, by1 + 2, rad + 2, fill="",
                           outline=ACCENT, width=3)
                y = self.thh + (p - 1 + frac) * self.tch     # 지금 시각 표시 점
                lx0 = self.tgut + today_col * self.tcw
                self.disc(c, lx0, y, 4, ACCENT, tags="nowdot")
            else:
                round_rect(c, bx0 - 1, by0 - 1, bx1 + 1, by1 + 1, rad + 1, fill="",
                           outline=ACCENT, width=2, dash=(4, 3))
            label = self.t("now" if kind_s == "now" else "next")
            f_tag = max(8, int(f_sub * 0.9))
            tw = self.measure(label, f_tag, True) + self.px(10)
            th = f_tag * 1.6
            round_rect(c, bx1 - tw - self.px(3), by0 + self.px(3), bx1 - self.px(3),
                       by0 + self.px(3) + th, th / 2, fill=ACCENT, outline="")
            c.create_text(bx1 - self.px(3) - tw / 2, by0 + self.px(3) + th / 2, text=label,
                          fill=ACCENT_INK, font=(FONT, -f_tag, "bold"))

    def tt_cell_at(self, e, clamp=False):
        if self.view != "tt" or not hasattr(self, "tcw"):
            return None
        di = int((e.x - self.tgut) // self.tcw)
        p = int((e.y - self.thh) // self.tch) + 1
        if clamp:                              # 드래그 중엔 표 밖으로 나가도 끝 칸으로
            return min(max(di, 0), self.n_days - 1), min(max(p, 1), PERIODS)
        if e.x < self.tgut or e.y < self.thh or not (0 <= di < self.n_days and 1 <= p <= PERIODS):
            return None
        return di, p

    def tt_selection(self):
        """지금 고른 칸들. 여러 칸을 골랐으면 그 칸들, 아니면 고른 칸의 수업 블록."""
        if self.tt_multi:
            return set(self.tt_multi)
        return {tuple(int(v) for v in k.split("-")) for k in self.block_keys()}

    def tick_now(self):
        """시간표의 '지금' 표시를 갱신한다. 교시가 바뀔 때만 전체를 다시 그리고, 같은 교시
        안에서는 지금 시각 선과 점만 제자리에서 옮긴다 (30초마다 전체를 다시 그리면 화면이
        깜빡여 가만히 있어도 뭔가 움직이는 것처럼 보였다)."""
        state = self.period_state()
        if getattr(self, "_now_sig", None) != (self.today, state[:2] if state else None):
            self.draw_tt()
            return
        if not (state and state[0] == "now"):
            return
        c = self.cal
        y = self.thh + (state[1] - 1 + state[2]) * self.tch
        lx0 = self.tgut + self.today.weekday() * self.tcw
        c.coords("nowline", lx0 + 2, y, lx0 + self.tcw - 2, y)
        c.coords("nowdot", int(round(lx0 - 4)), int(round(y - 4)))

    def on_tt_click(self, e):
        cell = self.tt_cell_at(e)
        if not cell:
            return
        self.tt_commit()                       # 다른 칸으로 옮기기 전에 적던 걸 저장
        self.panel_mode = "day"
        self._tt_adding = False
        key = self.tt_key(*cell)
        seen = self.shown_item(key, set(self.block_keys()))
        if seen:                               # 눈에 보이던 수업을 고치게 한다
            self.bring_front(key, seen)
            # 삐져나온 뒤 카드를 눌렀으면 앞 카드를 맨 뒤로 보내 뒤 카드가 앞으로 나오게 한다
            for sdi, sp, sspan, fr, full in getattr(self, "_tt_stacks", []):
                if (sdi == cell[0] and sp <= cell[1] < sp + sspan
                        and (e.x > fr[2] or e.y > fr[3]) and e.x <= full[2] and e.y <= full[3]):
                    self.bring_front(key, seen, to_back=True)
                    break
        self.tt_sel, self.tt_multi = cell, None
        self._tt_anchor, self._tt_base = cell, set()
        self._tt_press, self._tt_dragging = (e.x, e.y), False
        self.draw_tt()
        self.render_panel()
        if not self.tt.get(self.tt_key(*cell)):
            self.tt_title.focus_set()          # 빈 칸이면 바로 타이핑할 수 있게

    def on_tt_ctrl_click(self, e):
        """Ctrl+클릭: 칸을 더하거나 뺀다. 이어서 끌면 범위를 더한다."""
        cell = self.tt_cell_at(e)
        if not cell:
            return "break"
        self.tt_commit()
        self.panel_mode = "day"
        self._tt_adding = False
        sel = self.tt_selection()
        sel ^= {cell}
        if not sel:
            sel = {cell}
        if self.tt_sel not in sel:
            self.tt_sel = min(sel)
        self.tt_multi = sel if len(sel) > 1 else None
        self._tt_anchor, self._tt_base = cell, set(sel)
        self._tt_press, self._tt_dragging = (e.x, e.y), False
        self.draw_tt()
        self.render_panel()
        return "break"

    def on_tt_drag(self, e):
        if self.view != "tt" or not self._tt_anchor:
            return
        press = getattr(self, "_tt_press", None)
        if press and not getattr(self, "_tt_dragging", False):
            # 클릭하다 손이 조금 밀린 것은 드래그로 보지 않는다. 칸 경계 근처를 누르면
            # 몇 픽셀만 움직여도 옆 칸까지 골라져 버렸다. 칸 크기의 1/3 넘게 끌어야 시작한다.
            need = max(self.px(10), min(self.tcw, self.tch) * 0.35)
            if max(abs(e.x - press[0]), abs(e.y - press[1])) < need:
                return
            self._tt_dragging = True
        cur = self.tt_cell_at(e, clamp=True)
        (a, b), (c, d) = self._tt_anchor, cur
        rect = {(x, y) for x in range(min(a, c), max(a, c) + 1)
                for y in range(min(b, d), max(b, d) + 1)}
        sel = self._tt_base | rect
        new = sel if len(sel) > 1 else None
        if new != self.tt_multi:
            self.panel_mode = "day"
            self._tt_adding = False
            self.tt_multi = new
            self.draw_tt()                     # 패널은 손을 뗄 때 한 번만 다시 그린다
            self._tt_dragged = True

    def on_tt_release(self, e):
        if self.view == "tt" and getattr(self, "_tt_dragged", False):
            self._tt_dragged = False
            self.render_panel()
            if self.tt_multi:
                self.tt_title.focus_set()

    # ---------- 공용 부품 ----------

    def hint_entry(self, parent, size, hint, **kw):
        """비어 있을 때 회색 예시 글씨가 보이는 입력칸. 예시는 입력칸 위에 얹은
        라벨이라 실제 값에는 섞이지 않는다."""
        e = tk.Entry(parent, bg=SUNK, fg=FG, insertbackground=FG, relief="flat",
                     font=self.f(size), **kw)
        var = tk.StringVar(master=e)
        e.config(textvariable=var)
        e._var = var
        lab = tk.Label(e, text=hint, bg=SUNK, fg=DIM, font=self.f(size), cursor="xterm")
        lab.bind("<Button-1>", lambda _: e.focus_set())

        def update(*_):
            if var.get():
                lab.place_forget()
            else:
                lab.place(x=2, rely=0.5, anchor="w")
        var.trace_add("write", update)
        update()
        return e

    def button(self, parent, text, cmd, kind="primary", size=11):
        colors = {"primary": (SEL_BG, FG, FG), "plain": (SUNK, FG, FG),
                  "danger": (SUNK, MUTED, SUN)}[kind]
        b = tk.Label(parent, text=text, bg=colors[0], fg=colors[1],
                     font=self.f(size, kind == "primary"),
                     padx=self.px(14), pady=self.px(6), cursor="hand2")
        b.bind("<Button-1>", lambda _: cmd())
        b.bind("<Enter>", lambda e: e.widget.config(fg=colors[2], bg=LINE), add="+")
        b.bind("<Leave>", lambda e: e.widget.config(fg=colors[1], bg=colors[0]), add="+")
        return b

    def swatches(self, parent, current, on_pick):
        sw = tk.Frame(parent, bg=CARD)
        chip = self.px(18)
        for col in PALETTE:
            ring = tk.Frame(sw, bg=FG if col == pc(current) else CARD)
            ring.pack(side="left", padx=(0, self.px(5)))
            cc = tk.Frame(ring, bg=col, width=chip, height=chip, cursor="hand2")
            cc.pack(padx=self.px(2), pady=self.px(2))
            cc.bind("<Button-1>", lambda e, c2=col: on_pick(c2))
        return sw

    def tip(self, w, text):
        """마우스를 올려 두면 설명이 뜬다. 아이콘만 보고는 뭘 하는지 모르는 곳에."""
        def show():
            self.hide_tip()
            if not w.winfo_exists():
                return
            t = tk.Toplevel(self)
            t.overrideredirect(True)
            t.attributes("-topmost", True)
            tk.Label(t, text=text, bg=FG, fg=CARD, font=self.f(10),
                     padx=self.px(8), pady=self.px(4)).pack()
            t.geometry("+%d+%d" % (w.winfo_rootx(),
                                   w.winfo_rooty() + w.winfo_height() + self.px(4)))
            self._tip = t

        def enter(_):
            self.hide_tip()
            self._tip_job = self.after(450, show)
        w.bind("<Enter>", enter, add="+")
        w.bind("<Leave>", lambda _: self.hide_tip(), add="+")
        w.bind("<ButtonPress>", lambda _: self.hide_tip(), add="+")

    def hide_tip(self):
        if getattr(self, "_tip_job", None):
            self.after_cancel(self._tip_job)
            self._tip_job = None
        if getattr(self, "_tip", None):
            self._tip.destroy()
            self._tip = None

    def btn_date(self, d):
        return self.t("btn_date", m=d.month, d=d.day, wd=self.t("wd")[d.weekday()],
                      wdl=self.t("wd")[d.weekday()], mon=MONTHS_EN[d.month - 1][:3])

    def pill_colors(self, n):
        """D-day 배지 색. 가까울수록 눈에 띄되 쨍하지 않게 옅은 바탕 + 진한 글자."""
        if n < 0:
            return SUNK, DIM
        if n > 7:
            return SUNK, MUTED
        col = URGENT if n <= 1 else SOON
        if THEME == "dark":
            return mix(col, CARD, 0.68), mix(col, "#ffffff", 0.35)
        return mix(col, CARD, 0.70), mix(col, "#000000", 0.50)

    def pill(self, parent, d):
        """D-day 배지. 오늘·내일 빨강, 일주일 안 주황, 그 뒤 회색."""
        bg, fg = self.pill_colors((d - self.today).days)
        return tk.Label(parent, text=self.dday_text(d), bg=bg, fg=fg,
                        font=self.f(10, True), padx=self.px(7), pady=self.px(2))

    # ---------- 날짜 고르기 ----------

    def open_picker(self, anchor, current, on_pick):
        """작은 달력을 띄워 날짜를 고르게 한다. 날짜 형식을 외울 필요가 없다."""
        self.close_picker()
        top = tk.Toplevel(self, bg=LINE)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        body = tk.Frame(top, bg=CARD)
        body.pack(padx=1, pady=1)
        state = {"m": (current or self.today).replace(day=1)}
        self._picker, self._picker_anchor = top, anchor

        def pick(d):
            self.close_picker()
            on_pick(d)

        def move(n):
            m = state["m"].month + n
            state["m"] = dt.date(state["m"].year + (m - 1) // 12, (m - 1) % 12 + 1, 1)
            draw()

        def draw():
            for w in body.winfo_children():
                w.destroy()
            m = state["m"]
            hd = tk.Frame(body, bg=CARD)
            hd.pack(fill="x", padx=self.px(10), pady=(self.px(10), self.px(4)))
            for txt, n, side in (("‹", -1, "left"), ("›", 1, "right")):
                b = tk.Label(hd, text=txt, bg=CARD, fg=MUTED, font=self.f(16),
                             padx=self.px(8), cursor="hand2")
                b.pack(side=side)
                b.bind("<Button-1>", lambda e, k=n: move(k))
            tk.Label(hd, text=self.month_title(m), bg=CARD, fg=FG,
                     font=self.f(13, True)).pack(side="left", expand=True)
            g = tk.Frame(body, bg=CARD)
            g.pack(padx=self.px(10))
            for i, wd in enumerate(self.t("wd_cal")):
                tk.Label(g, text=wd, bg=CARD, font=self.f(10),
                         fg=SUN if i == 0 else SAT if i == 6 else DIM
                         ).grid(row=0, column=i, pady=(0, self.px(2)))
            weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(m.year, m.month)
            for r, wk in enumerate(weeks, 1):
                for c, d in enumerate(wk):
                    on, today = d == current, d == self.today
                    bg = SEL_BG if on else TODAY if today else CARD
                    fg = (DIM if d.month != m.month else
                          SUN if c == 0 else SAT if c == 6 else FG)
                    b = tk.Label(g, text=str(d.day), bg=bg, fg=fg, width=3,
                                 font=self.f(12, today or on), pady=self.px(4),
                                 cursor="hand2")
                    b.grid(row=r, column=c, padx=1, pady=1)
                    b.bind("<Button-1>", lambda e, dd=d: pick(dd))
                    b.bind("<Enter>", lambda e: e.widget.config(bg=HOVER)
                           if e.widget.cget("bg") == CARD else None)
                    b.bind("<Leave>", lambda e, o=bg: e.widget.config(bg=o))
            ft = tk.Frame(body, bg=CARD)
            ft.pack(fill="x", padx=self.px(10), pady=self.px(10))
            self.button(ft, self.t("today"), lambda: pick(self.today), "plain", 10
                        ).pack(side="left")
            if current:
                self.button(ft, self.t("clear_date"), lambda: pick(None), "danger", 10
                            ).pack(side="right")

        draw()
        top.update_idletasks()
        l, t, r, b = self.work_area()
        w, h = top.winfo_reqwidth(), top.winfo_reqheight()
        x = min(max(anchor.winfo_rootx(), l), r - w)
        y = anchor.winfo_rooty() + anchor.winfo_height() + self.px(4)
        if y + h > b:                                   # 아래 공간이 없으면 위로
            y = anchor.winfo_rooty() - h - self.px(4)
        top.geometry("+%d+%d" % (x, max(t, y)))

    def close_picker(self):
        if getattr(self, "_picker", None):
            try:
                self._picker.destroy()
            except tk.TclError:
                pass
        self._picker = self._picker_anchor = None

    def on_any_click(self, e):
        """달력 창 밖을 누르면 닫는다. 날짜 칸 자체를 눌렀을 땐 열린 채로."""
        p = getattr(self, "_picker", None)
        if not p:
            return
        try:
            w = str(e.widget)
            if w.startswith(str(p)) or (self._picker_anchor is not None
                                        and w.startswith(str(self._picker_anchor))):
                return
        except Exception:
            pass
        self.close_picker()

    # ---------- 시간표 패널 ----------

    def field_label(self, parent, text, row):
        tk.Label(parent, text=text, bg=CARD, fg=MUTED, font=self.f(11), anchor="w"
                 ).grid(row=row, column=0, sticky="w", padx=(0, self.px(12)),
                        pady=self.px(5))

    def panel_tt(self):
        di, p = self.tt_sel
        here = cell_items(self.tt, self.tt_key(di, p))     # 이 칸의 수업들 (대표가 맨 앞)
        if not here or self.tt_multi:
            self._tt_adding = False
        it = {} if self._tt_adding else (here[0] if here else {})
        draft = self._draft if (self._draft and self._draft.get("cell") == self.tt_sel) else None
        self._draft = None
        pw = self.panel_w

        top = tk.Frame(self.panel, bg=CARD)
        top.pack(fill="x")
        multi = sorted(self.tt_multi) if self.tt_multi else None
        if multi:
            tk.Label(top, text=self.t("tt_multi", n=len(multi)), bg=CARD, fg=FG,
                     font=self.f(16, True)).pack(side="left")
            hint = self.t("tt_multi_hint")
            title0 = it.get("title")
            others = sum(1 for c in multi if self.tt.get(self.tt_key(*c))
                         and self.tt[self.tt_key(*c)].get("title") != title0)
        else:
            tk.Label(top, text=self.t("tt_cell", wd=self.t("wd")[di], p=p), bg=CARD, fg=FG,
                     font=self.f(16, True)).pack(side="left")
            tk.Label(top, text=self.period_text(p), bg=CARD,
                     fg=MUTED, font=self.f(10)).pack(side="right")
            hint, others = self.t("tt_add_hint" if self._tt_adding else
                                  "tt_existing" if it else "tt_new"), 0
        tk.Label(self.panel, text=hint, bg=CARD,
                 fg=MUTED, font=self.f(11), anchor="w", justify="left",
                 wraplength=pw - self.px(4)).pack(fill="x", pady=(self.px(4), self.px(4)))
        self._new_chip = None
        if not multi and (len(here) > 1 or self._tt_adding):
            # 이 시간의 수업들. 눌러서 고칠 수업을 바꾼다.
            chips = tk.Frame(self.panel, bg=CARD)
            chips.pack(fill="x", pady=(self.px(2), self.px(2)))
            n = len(here) + (1 if self._tt_adding else 0)
            room_w = max(self.px(30), (pw - n * self.px(27)) // n)
            off_bg = mix(CARD, FG, 0.13)
            for i, x in enumerate(here):
                on = i == 0 and not self._tt_adding
                text = x.get("title", "")
                tag = (self.t("chip_" + x["week"]) if x.get("week", "all") != "all" else "")
                tag = " · ".join(v for v in (tag, x.get("weeks", "")) if v)
                text = self.fit(text + (" · " + tag if tag else ""), self.fpx(11), room_w, on)
                b = tk.Label(chips, text=text, bg=ACCENT if on else off_bg,
                             fg=ACCENT_INK if on else FG, font=self.f(11, on),
                             padx=self.px(10), pady=self.px(5), cursor="hand2")
                b.pack(side="left", padx=(0, self.px(5)))
                if not on:
                    b.bind("<Button-1>", lambda e, k=i: self.tt_pick_alt(k))
            if self._tt_adding:
                self._new_chip = tk.Label(chips, text=self.t("tt_new_chip"), bg=ACCENT,
                                          fg=ACCENT_INK, font=self.f(11, True),
                                          padx=self.px(10), pady=self.px(5))
                self._new_chip.pack(side="left")
        if others:
            tk.Label(self.panel, text=self.t("tt_overwrite", n=others), bg=CARD, fg=SUN,
                     font=self.f(11), anchor="w").pack(fill="x")
        tk.Frame(self.panel, bg=CARD, height=self.px(8)).pack(fill="x")
        if not self.tt_ok:
            tk.Label(self.panel, bg=CARD, fg=SUN, font=self.f(10), anchor="w",
                     justify="left", wraplength=pw - self.px(8),
                     text=self.t("tt_read_fail")).pack(fill="x", pady=(0, self.px(8)))

        # 과목 / 강의실 / 주차 / 색 — 왼쪽에 이름, 오른쪽에 입력
        form = tk.Frame(self.panel, bg=CARD)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        self.field_label(form, self.t("course"), 0)
        self.tt_title = self.hint_entry(form, 13, self.t("course_hint"))
        shown_t, shown_r = it.get("title", ""), it.get("room", "")
        if self.tt_multi:
            items = [self.tt.get(self.tt_key(*c)) for c in self.tt_multi]
            same = all(items) and len({(x.get("title"), x.get("room", "")) for x in items}) == 1
            shown_t, shown_r = ((items[0].get("title", ""), items[0].get("room", ""))
                                if same else ("", ""))
        self._tt_loaded = (shown_t, shown_r)
        self.tt_title.insert(0, draft["title"] if draft else shown_t)
        self.tt_title.grid(row=0, column=1, sticky="ew", ipady=self.px(6), pady=self.px(3))
        self.field_label(form, self.t("room"), 1)
        self.tt_room = self.hint_entry(form, 13, self.t("room_hint"))
        self.tt_room.insert(0, draft["room"] if draft else shown_r)
        self.tt_room.grid(row=1, column=1, sticky="ew", ipady=self.px(6), pady=self.px(3))
        for w in (self.tt_title, self.tt_room):
            w.bind("<Return>", lambda _: self.tt_enter())
            w.bind("<FocusOut>", lambda _: self.tt_commit(), add="+")
        self.tt_title.bind("<KeyRelease>", self.tt_title_changed)

        self.field_label(form, self.t("weeks"), 2)
        kinds = tk.Frame(form, bg=CARD)
        kinds.grid(row=2, column=1, sticky="w", pady=self.px(3))
        self.tt_week = it.get("week", "all") if it else getattr(self, "tt_week", "all")
        for k in WEEK_KEYS:
            on = k == self.tt_week
            b = tk.Label(kinds, text=self.t("chip_" + k), bg=SEL_BG if on else SUNK,
                         fg=FG if on else MUTED, font=self.f(11, on),
                         padx=self.px(12), pady=self.px(4), cursor="hand2")
            b.pack(side="left", padx=(0, self.px(4)))
            b.bind("<Button-1>", lambda e, kk=k: self.tt_set_week(kk))
        # 주차 범위: 1-8 (반 학기), 1,3,5 (띄엄띄엄). 비우면 학기 내내.
        self.tt_weeks = it.get("weeks", "") if it else ""
        self.tt_weeks_e = self.hint_entry(form, 11, self.t("weeks_hint"))
        self.tt_weeks_e.insert(0, draft.get("weeks", self.tt_weeks) if draft else self.tt_weeks)
        self.tt_weeks_e.grid(row=3, column=1, sticky="ew", ipady=self.px(4), pady=self.px(3))
        self.tt_weeks_e.bind("<Return>", lambda _: self.tt_enter())
        self.tt_weeks_e.bind("<FocusOut>", lambda _: self.tt_commit(), add="+")
        self.field_label(form, self.t("color"), 4)
        self.tt_color = pc(it.get("color", getattr(self, "tt_color", PALETTE[4])))
        self.swatches(form, self.tt_color, self.tt_set_color).grid(row=4, column=1,
                                                                    sticky="w")
        if self.tt_weeks and self.week1() is None:
            tk.Label(self.panel, text=self.t("week_need_no"), bg=CARD, fg=SUN, font=self.f(10),
                     anchor="w", justify="left", wraplength=pw - self.px(8)
                     ).pack(fill="x", pady=(self.px(4), 0))

        # 저장 상태 + 지우기
        act = tk.Frame(self.panel, bg=CARD)
        act.pack(fill="x", pady=(self.px(10), 0))
        self.status_lbl = tk.Label(act, text="", bg=CARD, fg=OK, font=self.f(10))
        self.status_lbl.pack(side="left")
        self.del_btn = self.button(act, self.t("del_class"), self.tt_delete, "danger", 10)
        if not it:
            # 새로 넣을 때는 누를 버튼이 있어야 '저장됐다'는 확신이 든다 (Enter 로도 된다).
            # 이미 있는 수업을 고칠 때는 지금처럼 자동 저장.
            self.button(act, self.t("add"), self.tt_save_new, "primary", 11).pack(side="right")
        if it:
            self.del_btn.pack(side="right")
            if not multi:                      # 같은 시간에 다른 주의 수업 추가
                self.button(act, self.t("tt_add_alt"), self.tt_add_alt, "plain", 10
                            ).pack(side="right", padx=(0, self.px(6)))

        # ----- 시험 · 과제 (과목 단위로 저장되어 같은 과목 칸끼리 공유된다) -----
        tk.Frame(self.panel, bg=LINE, height=1).pack(fill="x", pady=(self.px(14),
                                                                    self.px(10)))
        tk.Label(self.panel, text=self.t("exams"), bg=CARD, fg=FG, font=self.f(12, True),
                 anchor="w").pack(fill="x", pady=(0, self.px(6)))
        cur_title = ((draft.get("title") if draft else it.get("title", "")) or "").strip()
        info = self.courses.get(cur_title, {})
        # 지금 화면에 보여주는 값. 날짜는 달력에서 고르므로 'YYYY-MM-DD' 로만 들고 있다.
        self.exam_vals = {}
        for k in EXAM_KEYS:
            dv = draft.get(k + "_date") if draft else None
            tv = draft.get(k + "_time") if draft else None
            self.exam_vals[k] = [dv if dv is not None else info.get(k + "_date", ""),
                                 tv if tv is not None else info.get(k + "_time", "")]
        # 어떤 과목의 정보를 불러왔는지 기억해 두고, 저장할 때 이것과 비교해
        # '사용자가 실제로 고쳤는지'를 판단한다. (빈 칸 = 지움 으로 보면 안 된다)
        self._exam_loaded = (cur_title,
                             {k: (info.get(k + "_date", ""), info.get(k + "_time", ""))
                              for k in EXAM_KEYS})
        self.exam_box = tk.Frame(self.panel, bg=CARD)
        self.exam_box.pack(fill="x")
        self.build_exams()

    def build_exams(self):
        for w in self.exam_box.winfo_children():
            w.destroy()
        self.exam_e = {}
        if not self.tt_title.get().strip():
            tk.Label(self.exam_box, text=self.t("exams_need_title"), bg=CARD, fg=DIM,
                     font=self.f(11), anchor="w", justify="left",
                     wraplength=self.panel_w - self.px(4)).pack(fill="x")
            return
        g = tk.Frame(self.exam_box, bg=CARD)
        g.pack(fill="x")
        g.columnconfigure(1, weight=1)
        for row, k in enumerate(EXAM_KEYS):
            d_iso, tm = self.exam_vals[k]
            d = parse_date(d_iso)
            tk.Label(g, text=self.t("exam_" + k), bg=CARD, fg=FG, font=self.f(11),
                     anchor="w").grid(row=row, column=0, sticky="w",
                                      padx=(0, self.px(10)), pady=self.px(4))
            # 날짜 칸 = 누르면 달력이 뜨는 버튼. D-day 배지는 칸 안쪽 오른쪽에 넣어
            # 따로 자리를 차지하지 않게 한다 (좁은 크기에서 날짜 글자가 잘리던 문제).
            box = tk.Frame(g, bg=SUNK, cursor="hand2")
            box.grid(row=row, column=1, sticky="ew", pady=self.px(3))
            db = tk.Label(box, text=self.btn_date(d) if d else self.t("pick_date"),
                          bg=SUNK, fg=FG if d else DIM, font=self.f(12), anchor="w",
                          padx=self.px(8), pady=self.px(6), cursor="hand2")
            db.pack(side="left", fill="x", expand=True)
            parts = [box, db]
            if d:
                pl = self.pill(box, d)
                pl.pack(side="right", padx=(0, self.px(6)))
                parts.append(pl)
            for w in parts:
                w.bind("<Button-1>", lambda e, kk=k, a=box: self.open_picker(
                    a, parse_date(self.exam_vals[kk][0]),
                    lambda d2, k2=kk: self.set_exam_date(k2, d2)))
            self.hover_group(parts, [box, db], SUNK, LINE)
            self.tip(box, self.t("tip_date"))
            te = self.hint_entry(g, 12, self.t("time_hint"), width=9)
            te.insert(0, self.note_out(tm))
            te.grid(row=row, column=2, padx=(self.px(6), 0), ipady=self.px(6), pady=self.px(3))
            te.bind("<Return>", lambda _: self.tt_commit())
            te.bind("<FocusOut>", lambda _: self.tt_commit(), add="+")
            self.tip(te, self.t("tip_time"))
            self.exam_e[k] = (db, te)

    def hover_group(self, triggers, paint, idle, hot):
        """여러 위젯을 한 덩어리처럼 강조한다. 안쪽 위젯으로 옮겨 갈 때 깜빡이지 않게."""
        root = str(triggers[0])

        def put(col):
            for w in paint:
                w.config(bg=col)

        def leave(e):
            w = self.winfo_containing(e.x_root, e.y_root)
            if w is not None and str(w).startswith(root):
                return
            put(idle)
        for w in triggers:
            w.bind("<Enter>", lambda e: put(hot), add="+")
            w.bind("<Leave>", leave, add="+")

    def set_exam_date(self, k, d):
        self.exam_vals[k][0] = d.isoformat() if d else ""
        self.tt_commit()
        self.build_exams()

    def set_status(self, key):
        lbl = getattr(self, "status_lbl", None)
        if not lbl or not lbl.winfo_exists():
            return
        lbl.config(text=self.t(key), fg=OK)
        if getattr(self, "_status_job", None):
            self.after_cancel(self._status_job)
        self._status_job = self.after(
            4000, lambda: lbl.winfo_exists() and lbl.config(text=""))

    def exam_values(self):
        return {k: tuple(v) for k, v in self.exam_vals.items()}

    def tt_title_changed(self, _=None):
        """이미 시험 정보가 있는 과목 이름을 적으면 그 정보를 채워 보여준다.
        사용자가 시험 칸을 이미 고쳤다면 건드리지 않는다."""
        try:
            title = self.tt_title.get().strip()
        except tk.TclError:
            return
        had_exams = bool(self.exam_e)
        loaded_title, loaded_vals = self._exam_loaded
        changed = False
        if title != loaded_title and self.exam_values() == loaded_vals:
            if title in self.courses:
                info = self.courses.get(title, {})
                new_vals = {k: (info.get(k + "_date", ""), info.get(k + "_time", ""))
                            for k in EXAM_KEYS}
                changed = new_vals != self.exam_values()
                self.exam_vals = {k: list(v) for k, v in new_vals.items()}
                self._exam_loaded = (title, new_vals)
            elif not loaded_title or any(it.get("title") == loaded_title
                                         for _, it in all_items(self.tt)):
                new_vals = {k: ("", "") for k in EXAM_KEYS}
                changed = new_vals != self.exam_values()
                self.exam_vals = {k: list(v) for k, v in new_vals.items()}
                self._exam_loaded = (title, new_vals)
            else:
                self._exam_loaded = (title, loaded_vals)
        # 한 글자 칠 때마다 다시 그리지 않는다: 값이 바뀌었거나, 과목명이
        # 생기거나 없어져서 칸을 열고 닫아야 할 때만.
        if changed or bool(title) != had_exams:
            self.build_exams()

    def tt_draft(self):
        """패널을 다시 그려도 적던 내용이 살아남도록 지금 값을 담아 둔다."""
        try:
            d = {"cell": self.tt_sel, "title": self.tt_title.get(),
                 "room": self.tt_room.get(), "weeks": self.tt_weeks_e.get()}
        except (tk.TclError, AttributeError):
            return None
        for k in EXAM_KEYS:
            d[k + "_date"], d[k + "_time"] = self.exam_vals[k]
        return d

    def tt_commit(self):
        """시간표 패널의 내용을 저장한다. 바뀐 게 없으면 아무것도 안 한다.
        저장 버튼 없이 Enter, 다른 칸으로 넘어갈 때, 색·주차를 누를 때 불린다."""
        if self.view != "tt" or not getattr(self, "tt_title", None):
            return False
        try:
            title, room = self.tt_title.get().strip(), self.tt_room.get().strip()
        except tk.TclError:
            return False
        for k, (db, te) in self.exam_e.items():
            # 시간으로 알아들으면 14:00 처럼 정리하고, 아니면 적은 그대로 메모로 둔다.
            # (실제로 '中期报告' 처럼 메모를 적어 쓰고 있었다)
            raw = self.note_in(te.get().strip())
            tm = parse_time(raw)
            if tm and raw != tm:
                te.delete(0, "end")
                te.insert(0, tm)                # 14시 → 14:00
            self.exam_vals[k][1] = tm if tm is not None else raw
        bad_weeks = False
        try:                                    # 주차 범위: 읽을 수 있으면 '1-8' 꼴로 정리한다
            raw = self.tt_weeks_e.get().strip()
            nw = norm_weeks(raw)
            if nw is None:
                bad_weeks = True
            else:
                self.tt_weeks = nw
                if raw != nw:
                    self.tt_weeks_e.delete(0, "end")
                    self.tt_weeks_e.insert(0, nw)
        except (tk.TclError, AttributeError):
            pass
        key = self.tt_key(*self.tt_sel)
        old = self.tt.get(key)
        keys = self.block_keys()
        old_titles = {self.tt[k].get("title", "").strip() for k in keys if self.tt.get(k)}
        loaded_t = getattr(self, "_tt_loaded", ("", ""))[0].strip()
        if loaded_t:
            old_titles.add(loaded_t)
        new = ({"title": title, "room": room, "color": self.tt_color, "week": self.tt_week}
               if title else None)
        if new and self.tt_weeks:
            new["weeks"] = self.tt_weeks
        if self._tt_adding:
            # 이 시간에 다른 주의 수업을 새로 넣는다. 있던 수업은 그대로 두고 그 앞에 둔다.
            if not new:
                return False
            self.push_undo()
            for k in keys:
                set_cell(self.tt, k, [dict(new)] + cell_items(self.tt, k))
            self._tt_adding = False
            self._tt_loaded = (title, room)
            self.save_tt()
            if self._new_chip is not None and self._new_chip.winfo_exists():
                self._new_chip.config(text=self.fit(title, self.fpx(11), self.px(120), True))
            if not self.tt_commit():            # 시험 정보까지 저장 (없으면 여기서 마무리)
                self.draw_tt()
                self.del_btn.pack(side="right")
                self.set_status("saved")
            return True
        # 빠진 항목은 기본값으로 채워 비교한다. 안 그러면 아무것도 안 고쳐도
        # 저장할 때마다 '바뀜'이 돼 되돌리기 기록이 쌓인다.
        updates = {}
        if self.tt_multi:
            # 다른 곳을 누를 때도 저장이 불린다. 고치지 않았는데 바꾸거나, 비어 있는
            # 과목명 때문에 고른 칸의 수업을 지우는 일이 없게 한다.
            lt, lr = getattr(self, "_tt_loaded", ("", ""))
            t_ch, r_ch = bool(title) and title != lt, room != lr
            for k in keys:
                cur = self.tt.get(k)
                if t_ch:
                    nv = {"title": title, "room": room if (r_ch or not cur) else cur.get("room", ""),
                          "color": self.tt_color, "week": self.tt_week}
                    if self.tt_weeks:
                        nv["weeks"] = self.tt_weeks
                    if cur and cur.get("more"):
                        nv["more"] = cur["more"]
                elif r_ch and cur:
                    nv = dict(cur, room=room)
                else:
                    continue
                if nv != cur:
                    updates[k] = nv
            cell_changed = bool(updates)
        else:
            cell_changed = any((item_core(new) if new else None)
                               != (item_core(self.tt[k]) if self.tt.get(k) else None)
                               for k in keys)
        vals = self.exam_values()
        exam_changed = bool(title) and vals != self._exam_loaded[1]
        if not cell_changed and not exam_changed:
            if bad_weeks:
                try:
                    self.status_lbl.config(text=self.t("week_bad"), fg=SUN)
                except tk.TclError:
                    pass
            return False
        self.push_undo()
        if cell_changed:
            if self.tt_multi:
                self.tt.update(updates)
                self._tt_loaded = (title or self._tt_loaded[0], room)
            else:
                for k in keys:                  # 같은 칸의 다른 수업('more')은 그대로 둔다
                    set_cell(self.tt, k, ([dict(new)] if new else [])
                             + cell_items(self.tt, k)[1:])
            self.save_tt()

        active = self.active_courses()
        cs_changed = False
        for ot in old_titles:
            if ot and ot not in active and ot in self.courses:
                if title and title not in self.courses:
                    self.courses[title] = self.courses.pop(ot)
                    cs_changed = True
                else:
                    self.courses.pop(ot, None)
                    cs_changed = True

        if exam_changed:
            info, old = {}, self.courses.get(title, {})
            for k, (dv, tv) in vals.items():
                if dv:
                    info[k + "_date"], info[k + "_time"] = dv, tv
                    if old.get(k + "_done") and old.get(k + "_date") == dv:
                        info[k + "_done"] = True
            if info:
                self.courses[title] = info
            else:
                self.courses.pop(title, None)
            cs_changed = True
            self._exam_loaded = (title, vals)
        elif cs_changed and title in self.courses:
            self._exam_loaded = (title, vals)

        if cs_changed:
            self.save_courses()
        self.cleanup_orphan_courses()
        self.draw_tt()
        if self.tt.get(key):
            self.del_btn.pack(side="right")
        else:
            self.del_btn.pack_forget()
        self.set_status("saved")
        if bad_weeks:
            self.status_lbl.config(text=self.t("week_bad"), fg=SUN)
        return True

    def block_keys(self):
        """고른 칸이 속한 수업 블록(세로로 이어진 같은 수업)의 모든 칸. 화면에는 한 덩어리로
        보이므로 고칠 때도 한꺼번에 고친다 (한 칸만 바뀌면 블록이 갈라져 안 바뀐 것처럼 보인다)."""
        if self.tt_multi:
            return [self.tt_key(*c) for c in sorted(self.tt_multi)]
        di, p = self.tt_sel
        for bdi, bp, span, _ in self.tt_blocks():
            if bdi == di and bp <= p < bp + span:
                return [self.tt_key(bdi, q) for q in range(bp, bp + span)]
        return [self.tt_key(di, p)]

    def tt_set_week(self, kind):
        self.tt_commit()
        self._draft = self.tt_draft()
        self.tt_week = kind
        if self._tt_adding:
            self.render_panel()
            return
        it = self.tt.get(self.tt_key(*self.tt_sel))
        keys = [k for k in self.block_keys() if self.tt.get(k)]
        if any(self.tt[k].get("week", "all") != kind for k in keys):
            self.push_undo()
            for k in keys:
                self.tt[k]["week"] = kind
            self.save_tt()
            self.draw_tt()
        self.render_panel()
        if it:
            self.set_status("saved")

    def tt_set_color(self, col):
        col = pc(col)
        self.tt_commit()
        self._draft = self.tt_draft()
        self.tt_color = col
        if self._tt_adding:
            self.render_panel()
            return
        it = self.tt.get(self.tt_key(*self.tt_sel))
        keys = [k for k in self.block_keys() if self.tt.get(k)]
        if any(pc(self.tt[k].get("color")) != col for k in keys):
            self.push_undo()
            for k in keys:
                self.tt[k]["color"] = col
            self.save_tt()
            self.draw_tt()
        self.render_panel()
        if it:
            self.set_status("saved")

    def tt_save_new(self):
        """'추가' 버튼: 적은 수업을 저장하고 패널을 '고치는 중' 상태로 바꾼다."""
        try:
            title = self.tt_title.get().strip()
        except tk.TclError:
            return
        if not title:
            self.tt_title.focus_set()
            return
        self.tt_commit()
        if self.tt_multi:
            # 여러 칸을 골라 수업을 넣었으면 선택을 푼다. 넣고 난 뒤에도 칸마다 파란
            # 테두리가 남아 있으면 아직 끝나지 않은 것처럼 보인다. 넣은 수업은 골라 둔다.
            self.tt_sel = min(self.tt_multi)
            self.tt_multi = None
            self._tt_anchor, self._tt_base = self.tt_sel, set()
            self.draw_tt()
        self._draft = None
        self.render_panel()
        self.set_status("saved")

    def tt_enter(self):
        """입력칸에서 Enter. 여러 칸을 고른 상태면 저장하고 선택을 푼다 ('추가' 버튼과 같다)."""
        if self.tt_multi:
            self.tt_save_new()
        else:
            self.tt_commit()

    def tt_pick_alt(self, i):
        """이 칸의 i 번째 수업을 고칠 대상으로 바꾼다."""
        key = self.tt_key(*self.tt_sel)
        items = cell_items(self.tt, key)
        target = items[i] if i < len(items) else None
        self.tt_commit()
        self._tt_adding = False
        if target:
            self.bring_front(key, target)
        self.draw_tt()
        self.render_panel()

    def tt_add_alt(self):
        """이 시간에 다른 주에 듣는 수업을 새로 적기 시작한다 (单周 수업 옆에 双周 수업 등)."""
        self.tt_commit()
        items = cell_items(self.tt, self.tt_key(*self.tt_sel))
        if not items or self.tt_multi:
            return
        self._tt_adding = True
        self.tt_week = {"odd": "even", "even": "odd"}.get(items[0].get("week", "all"), "all")
        used = {pc(x.get("color")) for _, x in all_items(self.tt)}
        self.tt_color = next((c for c in PALETTE if c not in used), PALETTE[0])
        self._draft = None
        self.render_panel()
        self.tt_title.focus_set()

    def note_out(self, tm):
        """시험 시간·비고를 화면에 보여줄 글로: '晚上' → '저녁' / 'Evening'."""
        key = EXAM_PARTS.get((tm or "").strip())
        return self.t(key) if key else tm

    def note_in(self, text):
        """화면에 적힌 글을 저장할 값으로: 어느 언어의 '저녁'·'Evening' 이든 '晚上' 으로."""
        low = (text or "").strip().lower()
        for zh, key in EXAM_PARTS.items():
            if any(low == str(TEXT[lang].get(key, "")).lower() for lang in TEXT):
                return zh
        return text

    def dday_text(self, s):
        d = parse_date(s) if isinstance(s, str) else s
        if not d:
            return ""
        n = (d - self.today).days
        return self.t("dday_today") if n == 0 else ("D-%d" % n if n > 0 else self.t("dday_past"))

    def tt_delete(self):
        keys = self.block_keys()
        if not any(self.tt.get(k) for k in keys):
            return
        del_titles = {self.tt[k].get("title", "").strip() for k in keys if self.tt.get(k)}
        self.push_undo()
        for k in keys:                          # 같은 칸의 다른 수업이 있으면 그게 대표가 된다
            set_cell(self.tt, k, cell_items(self.tt, k)[1:])
        self.save_tt()
        active = self.active_courses()
        cs_changed = False
        for t in del_titles:
            if t and t not in active and t in self.courses:
                self.courses.pop(t, None)
                cs_changed = True
        if cs_changed:
            self.save_courses()
        self.render()
        self.set_status("deleted")

    # ---------- 일정 패널 ----------

    def render_panel(self):
        self.close_picker()
        self.hide_tip()
        self._editing = False
        # 새 일정 칸에 적던 글은 다시 그려도 남긴다 (체크·삭제·색 변경, 자정 넘김 등으로
        # 패널이 새로 그려질 때 적던 글이 사라졌다).
        draft = ""
        try:
            draft = self.entry_w.get()
        except (AttributeError, tk.TclError):
            pass
        keep, sc, cv = None, self._scroll, None   # 목록을 다시 그려도 보던 자리를 지킨다
        if sc is not None and self._scroll_mode == self.scroll_key():
            try:
                keep = sc.yview()[0]
            except tk.TclError:
                pass
        self._scroll = None
        # 새 내용을 다 만든 뒤에 예전 것 위에 덮고, 그 다음에 예전 것을 치운다. 먼저 비우면
        # 그 사이 빈 카드가 몇 프레임 보여 누를 때마다 번쩍인다.
        on = self.panel_mode == "settings"     # 설정 버튼의 켜짐 표시를 맞춘다
        self.base.itemconfig("b_menu_bg", fill=SEL_BG if on else mix(BG, FG, 0.10))
        self.base.itemconfig("b_menu_tx", image=self.gear(on))
        old = self.panel
        self.panel = new = tk.Frame(self.panel_host, bg=CARD)
        try:
            self.fill_panel(draft, keep)
        finally:
            # 위젯 수십 개를 화면에 올리는 데 0.05초쯤 걸리고 그동안은 빈 칸으로 보인다.
            # 그래서 카드 밖(보이지 않는 곳)에서 다 올려 둔 다음 한 번에 제자리로 옮긴다.
            px0, py0, px1, py1 = self.panel_box
            new.place(x=(px1 - px0) + 40, y=0, width=px1 - px0, height=py1 - py0)
            new.update_idletasks()
            cv = self._scroll
            if keep and cv is not None:            # 보던 자리로 돌려놓은 다음에 보여준다
                box = cv.bbox("all")
                if box:
                    cv.config(scrollregion=(0, 0, box[2], box[3]))
                    cv.yview_moveto(keep)
            new.place(x=0, y=0, width=px1 - px0, height=py1 - py0)
            old.destroy()

    def scroll_key(self):
        """지금 패널이 어떤 목록인지. 같은 목록을 다시 그릴 때만 보던 자리를 지킨다."""
        if self.panel_mode == "settings":
            return "settings"
        return ("tt", self.tt_sel) if self.view == "tt" else self.panel_mode

    def fill_panel(self, draft, keep=None):
        if self.panel_mode == "settings":
            self.panel_settings()
        elif self.view == "tt":
            # 수업이 겹치거나 창이 작으면 내용이 카드보다 길어진다. 가져오기 버튼은 맨 아래에
            # 붙여 두고, 나머지는 휠로 넘길 수 있게 한다 (전에는 아래가 잘려 보이지 않았다).
            outer = self.panel
            self.button(outer, self.t("pku_import"), self.import_pku, "plain", 10
                        ).pack(side="bottom", anchor="w", pady=(self.px(10), 0))
            self.panel = self.scroll_area(outer)
            try:
                self.panel_tt()
            finally:
                self.panel = outer
        elif self.panel_mode == "upcoming":
            self.panel_upcoming()
        else:
            self.panel_day(draft)
            return
        self._scroll_mode = self.scroll_key()

    def panel_day(self, draft=""):
        d = self.selected
        span = self.range_span()
        if self.compact:
            self.make_classes(d)               # 날짜는 머리줄에 있다. 그 날 수업부터 보여준다
        else:
            if span:
                title = "%s – %s" % (self.short_date(span[0]), self.short_date(span[1]))
                sub = self.t("n_days", n=(span[1] - span[0]).days + 1)
            else:
                title = self.day_title(d)
                n = (d - self.today).days
                sub = (self.t("dday_today") if n == 0 else
                       ("D%+d" % -n if n < 0 else "D-%d" % n))
            tk.Label(self.panel, bg=CARD, fg=FG, font=self.f(14 if span else 16, True),
                     anchor="w", text=self.fit(title, self.fpx(14 if span else 16),
                                               self.panel_w, True)).pack(fill="x")
            tk.Label(self.panel, bg=CARD, fg=MUTED, font=self.f(11), anchor="w", text=sub
                     ).pack(fill="x", pady=(self.px(2), self.px(10)))

        if not self.data_ok:
            warn = tk.Label(self.panel, bg=CARD, fg=SUN, font=self.f(10), anchor="w",
                            justify="left", wraplength=self.panel_w - self.px(8),
                            cursor="hand2", text=self.t("read_fail"))
            warn.pack(fill="x", pady=(0, self.px(8)))
            warn.bind("<Button-1>", lambda _: self.reload_data())

        items = self.events.get(key_of(d), [])
        exams = self.exams_on(d)
        for k, title, tm in exams:
            self.make_exam_row(k, title, tm)
        rows = ([(it.get("time", ""), "ev", i, it) for i, it in enumerate(items)]
                + [(sr.get("time", ""), "sr", i, sr) for i, sr in enumerate(self.series)
                   if series_on(sr, d)])
        if not rows and not exams:
            tk.Label(self.panel, text=self.t("no_events"), bg=CARD, fg=DIM,
                     font=self.f(12), anchor="w").pack(fill="x", pady=(0, self.px(4)))
        # 시간을 적은 일정은 시간순으로, 안 적은 일정은 그 위에 적은 순서대로
        for tm, kind, i, it in sorted(rows, key=lambda x: (x[0] != "", x[0])):
            if kind == "ev":
                self.make_row(i, it)
            else:
                self.make_series_row(i, it, d)
        self.make_form()
        if draft:
            self.entry_w.insert(0, draft)
        self.make_upcoming()

    def classes_on(self, day):
        """그 날의 수업 [(시작 교시, 칸수, 내용)]. 그 주에 없는 수업(单/双周, 주차 범위)은 뺀다."""
        di = day.weekday()

        def at(p):
            for it in cell_items(self.tt, self.tt_key(di, p)):
                if it.get("title") and self.item_on(it, day):
                    return it
            return None
        out, p = [], 1
        while p <= PERIODS:
            it = at(p)
            if not it:
                p += 1
                continue
            span = 1
            while p + span <= PERIODS:
                nx = at(p + span)
                if not nx or (nx.get("title"), nx.get("room", "")) != (it.get("title"),
                                                                      it.get("room", "")):
                    break
                span += 1
            out.append((p, span, it))
            p += span
        return out

    def make_classes(self, day):
        st = self.period_state() if day == self.today else None
        self._cls_sig = (self.today, st[:2] if st else None)
        rows = self.classes_on(day)
        if not rows:
            return
        cur = st[1] if st and st[0] == "now" else None
        tw = self.measure("00:00", self.fpx(11), True) + self.px(4)
        for p, span, it in rows:
            hot = cur is not None and p <= cur < p + span
            r = tk.Frame(self.panel, bg=CARD)
            r.pack(fill="x", pady=self.px(2))
            tm = tk.Frame(r, bg=CARD, width=tw, height=self.px(22))
            tm.pack(side="left")
            tm.pack_propagate(False)
            tk.Label(tm, text=self.period_text(p)[:5], bg=CARD, fg=ACCENT if hot else MUTED,
                     font=self.f(11, hot), anchor="w").pack(fill="both", expand=True)
            tk.Frame(r, bg=self.dot_color(pc(it.get("color"))), width=max(2, self.px(3)),
                     height=self.px(18)).pack(side="left", padx=(self.px(4), self.px(8)))
            room = self.fit(it.get("room", ""), self.fpx(10), int(self.panel_w * 0.3))
            if room:
                tk.Label(r, text=room, bg=CARD, fg=DIM, font=self.f(10)).pack(side="right")
            left = (self.panel_w - tw - self.px(18) - self.measure(room, self.fpx(10))
                    - self.px(8))
            tk.Label(r, text=self.fit(it.get("title", ""), self.fpx(12), left, hot), bg=CARD,
                     fg=FG, font=self.f(12, hot), anchor="w").pack(side="left", fill="x",
                                                                  expand=True)
        tk.Frame(self.panel, bg=LINE, height=1).pack(fill="x", pady=(self.px(8), self.px(8)))

    def hoverable(self, row):
        """줄에 마우스를 올리면 배경을 살짝 바꿔 '누를 수 있는 줄'임을 보여준다."""
        kids = [row] + list(row.winfo_children())

        def paint(c):
            for w in kids:
                try:
                    w.config(bg=c)
                except tk.TclError:
                    pass

        def leave(e):
            w = self.winfo_containing(e.x_root, e.y_root)
            if w is not None and str(w).startswith(str(row)):
                return                         # 줄 안의 다른 부분으로 옮겨간 것
            paint(CARD)
        for w in kids:
            w.bind("<Enter>", lambda _: paint(HOVER), add="+")
            w.bind("<Leave>", leave, add="+")

    # ---------- 시험 (시간표의 과목 정보를 달력에서도 보여준다) ----------

    def active_courses(self):
        """현재 시간표에 실제로 등록된 과목명 집합 (공백 제외)."""
        return {it.get("title", "").strip() for _, it in all_items(self.tt)
                if it.get("title", "").strip()}

    def cleanup_orphan_courses(self):
        """시간표에서 삭제되거나 변경되어 더 이상 시간표에 존재하지 않는 과목의
        시험·과제 정보를 courses.json 에서 정리한다."""
        if not self.tt or not self.tt_ok:
            return
        active = self.active_courses()
        orphans = [t for t in self.courses if t not in active]
        if orphans:
            for t in orphans:
                self.courses.pop(t, None)
            if self.cs_ok:
                save_json(COURSE_FILE, self.courses)
                log("시간표에 없는 이전 과목 시험 정보 %d개 정리: %s" %
                    (len(orphans), ", ".join(orphans)))

    def normalize_exam_dates(self):
        """예전 버전은 시험 날짜를 '11-09' 처럼 연도 없이 적게 했다. 연도를 붙여 정리해
        둔다 (지난 날짜면 내년으로 본다 — parse_date 와 같은 규칙)."""
        changed = 0
        for info in self.courses.values():
            for k in EXAM_KEYS:
                v = info.get(k + "_date")
                d = parse_date(v) if v else None
                if d and v != d.isoformat():
                    info[k + "_date"] = d.isoformat()
                    changed += 1
        if changed and self.cs_ok:
            save_json(COURSE_FILE, self.courses)
            log("시험 날짜 %d개를 연도가 붙은 형식으로 정리" % changed)

    def exams_on(self, day):
        """그 날의 시험·과제 마감 [(종류, 과목, 시간)]. courses.json 을 그대로 읽으므로
        시간표에서 고치면 달력에도 바로 반영된다."""
        return [(k, title, info.get(k + "_time", ""))
                for title, info in sorted(self.courses.items()) for k in EXAM_KEYS
                if parse_date(info.get(k + "_date", "")) == day]

    def course_color(self, title):
        for _, it in all_items(self.tt):
            if it.get("title") == title:
                return pc(it.get("color"))
        return URGENT

    def goto_course(self, title):
        """시간표로 넘어가 그 과목의 첫 칸을 고른다 (시험 날짜는 거기서 고친다)."""
        found = sorted(((int(key.split("-")[0]), int(key.split("-")[1])), key, it)
                       for key, it in all_items(self.tt) if it.get("title") == title)
        if found:
            self.tt_sel = found[0][0]
            self.bring_front(found[0][1], found[0][2])
        self.set_view("tt")

    def check_box(self, parent, col, done, square, on_click):
        """완료 체크박스. 아직이면 색 테두리만, 마우스를 올리면 ✓ 를 흐리게 미리 보여주고,
        완료면 색을 채우고 ✓. 작은 색 점은 누를 수 있는 것처럼 보이지 않아서 바꿨다."""
        box = self.px(26)
        c = tk.Canvas(parent, width=box, height=box, bg=CARD, highlightthickness=0,
                      cursor="hand2")
        m, r = box * 0.5, box * 0.27
        w = max(2, self.px(2))
        shape = c.create_rectangle if square else c.create_oval
        if square:
            r *= 0.92
        tick = (m - r * 0.5, m + r * 0.02, m - r * 0.12, m + r * 0.42, m + r * 0.55, m - r * 0.42)
        if done:
            if square:
                shape(m - r, m - r, m + r, m + r, fill=mix(col, CARD, 0.25), outline="")
            else:
                self.disc(c, m, m, r, mix(col, CARD, 0.25))
            c.create_line(*tick, fill=CARD, width=w, capstyle="round", joinstyle="round")
        else:
            if square:
                shape(m - r, m - r, m + r, m + r, fill="", outline=col, width=w)
            else:                              # 고리 = 색 원 위에 카드색 원
                self.disc(c, m, m, r + w / 2.0, col)
                self.disc(c, m, m, r - w / 2.0, CARD)
            hint = c.create_line(*tick, fill=mix(col, CARD, 0.45), width=w,
                                 capstyle="round", joinstyle="round", state="hidden")
            c.bind("<Enter>", lambda e: c.itemconfig(hint, state="normal"), add="+")
            c.bind("<Leave>", lambda e: c.itemconfig(hint, state="hidden"), add="+")
        c.bind("<Button-1>", lambda e: on_click())
        return c

    def exam_done(self, title, kind):
        return bool(self.courses.get(title, {}).get(kind + "_done"))

    def toggle_exam(self, title, kind):
        info = self.courses.get(title)
        if info is None:
            return
        self.push_undo()
        if info.get(kind + "_done"):
            info.pop(kind + "_done", None)
        else:
            info[kind + "_done"] = True
        self.save_courses()
        self.render()

    def make_exam_row(self, kind, title, tm):
        tm = self.note_out(tm)
        row = tk.Frame(self.panel, bg=CARD, cursor="hand2")
        row.pack(fill="x", pady=self.px(1))
        done = self.exam_done(title, kind)
        box = self.check_box(row, self.dot_color(self.course_color(title)), done, True,
                             lambda: self.toggle_exam(title, kind))
        box.pack(side="left", padx=(self.px(2), 0))
        self.tip(box, self.t("tip_check"))
        if tm:
            tk.Label(row, text=tm, bg=CARD, fg=DIM if done else MUTED, font=self.f(11)
                     ).pack(side="right", padx=(self.px(4), self.px(8)))
        lab = tk.Label(row, text="%s · %s" % (self.t("exam_" + kind), title), bg=CARD,
                       fg=DIM if done else FG, font=self.f(13, not done, strike=done),
                       anchor="w", justify="left", cursor="hand2",
                       wraplength=self.panel_w - self.px(90), pady=self.px(4))
        lab.pack(side="left", fill="x", expand=True, padx=(self.px(6), 0))
        for w in [row] + [w for w in row.winfo_children() if w is not box]:
            w.bind("<Button-1>", lambda e, t=title: self.goto_course(t))
        self.tip(lab, self.t("tip_exam"))
        self.hoverable(row)

    def make_row(self, idx, it):
        row = tk.Frame(self.panel, bg=CARD)
        row.pack(fill="x", pady=self.px(1))
        done = bool(it.get("done"))
        col = self.dot_color(it.get("color", PALETTE[0]))

        dot = self.check_box(row, col, done, False, lambda i=idx: self.toggle_done(i))
        dot.pack(side="left", padx=(self.px(2), 0))
        dot.bind("<Button-3>", lambda e, i=idx: self.color_menu(e, i))
        self.tip(dot, self.t("tip_done"))

        x = tk.Label(row, text="×", bg=CARD, fg=DIM, font=self.f(15), cursor="hand2",
                     padx=self.px(6))
        x.pack(side="right")
        x.bind("<Button-1>", lambda e, i=idx: self.delete(i))
        x.bind("<Enter>", lambda e: e.widget.config(fg=SUN), add="+")
        x.bind("<Leave>", lambda e: e.widget.config(fg=DIM), add="+")
        self.tip(x, self.t("tip_delete"))
        tm = extra_time(it)
        if tm:                                  # 제목에 없는 시간만 따로 보여준다
            tk.Label(row, text=tm, bg=CARD, fg=DIM if done else MUTED, font=self.f(11)
                     ).pack(side="right", padx=(self.px(4), 0))

        title = tk.Label(row, text=it["title"], bg=CARD, fg=DIM if done else FG,
                         font=self.f(13, strike=done), anchor="w", justify="left",
                         wraplength=self.panel_w - self.px(80 + (44 if tm else 0)),
                         cursor="xterm", pady=self.px(4))
        title.pack(side="left", fill="x", expand=True, padx=(self.px(6), 0))
        # 한 번 클릭으로 고친다. 더블클릭은 해볼 생각을 하기 어렵다.
        title.bind("<Button-1>", lambda e, i=idx, rr=row: self.edit(i, rr))
        self.tip(title, self.t("tip_edit"))
        self.hoverable(row)

    def make_series_row(self, si, sr, day):
        """반복·기간 일정 한 줄. 고치면 그 일정 전체가 바뀐다."""
        row = tk.Frame(self.panel, bg=CARD)
        row.pack(fill="x", pady=self.px(1))
        done = series_done(sr, day)
        col = self.dot_color(sr.get("color", PALETTE[0]))
        dot = self.check_box(row, col, done, False,
                             lambda: self.toggle_series_done(si, day))
        dot.pack(side="left", padx=(self.px(2), 0))
        self.tip(dot, self.t("tip_check"))
        x = tk.Label(row, text="×", bg=CARD, fg=DIM, font=self.f(15), cursor="hand2",
                     padx=self.px(6))
        x.pack(side="right")
        x.bind("<Button-1>", lambda e: self.series_delete(si, day, row))
        x.bind("<Enter>", lambda e: e.widget.config(fg=SUN), add="+")
        x.bind("<Leave>", lambda e: e.widget.config(fg=DIM), add="+")
        self.tip(x, self.t("tip_delete"))
        if sr.get("repeat"):
            tag = "↻ " + (extra_time(sr) or self.t("rep_" + sr["repeat"]))
        else:
            a, b = iso_date(sr.get("start")), iso_date(sr.get("end")) or iso_date(sr.get("start"))
            tag = "%d/%d–%d/%d" % (a.month, a.day, b.month, b.day)
        tag_w = self.measure(tag, self.fpx(10)) + self.px(6)
        tk.Label(row, text=tag, bg=CARD, fg=DIM, font=self.f(10)
                 ).pack(side="right", padx=(self.px(4), 0))
        title = tk.Label(row, text=sr.get("title", ""), bg=CARD, fg=DIM if done else FG,
                         font=self.f(13, strike=done), anchor="w", justify="left",
                         wraplength=max(self.px(60), self.panel_w - self.px(80) - tag_w),
                         cursor="xterm", pady=self.px(4))
        title.pack(side="left", fill="x", expand=True, padx=(self.px(6), 0))

        def commit(text):
            self.push_undo()
            sr["title"] = text
            if sr.get("repeat"):               # 기간 일정에는 시간이 없다
                sr["time"] = time_of(text)
            self.save_series()
        title.bind("<Button-1>", lambda e: self.inline_edit(row, sr.get("title", ""), commit))
        self.tip(title, self.t("tip_edit"))
        self.hoverable(row)

    def toggle_series_done(self, si, day):
        if si >= len(self.series):
            return
        sr = self.series[si]
        self.push_undo()
        key, done = series_done_key(sr, day), list(sr.get("done") or [])
        if key in done:
            done.remove(key)
        else:
            done.append(key)
        sr["done"] = done
        self.save_series()
        self.render()

    def series_delete(self, si, day, row):
        """기간 일정은 통째로 지운다. 반복 일정은 '이 날만 / 이 날부터 전부' 를 고르게 한다."""
        if si >= len(self.series):
            return
        sr = self.series[si]
        self.hide_tip()

        def drop(mode):
            self.push_undo()
            start = iso_date(sr.get("start"))
            if mode == "this":
                sr["skip"] = list(sr.get("skip") or []) + [day.isoformat()]
            elif mode == "after" and start and day > start:
                sr["until"] = (day - dt.timedelta(days=1)).isoformat()
            else:
                self.series.remove(sr)
            self.save_series()
            self.render()
        if not sr.get("repeat"):
            drop("all")
            return
        bar = tk.Frame(self.panel, bg=CARD)
        bar.pack(fill="x", pady=self.px(3), before=row)
        row.pack_forget()
        self.button(bar, self.t("del_this"), lambda: drop("this"), "plain", 10
                    ).pack(side="left")
        self.button(bar, self.t("del_after"), lambda: drop("after"), "danger", 10
                    ).pack(side="left", padx=(self.px(6), 0))
        self.button(bar, self.t("cancel"), self.render_panel, "plain", 10).pack(side="right")

    def save_series(self):
        if not self.sr_ok:
            log("반복 일정을 읽지 못한 상태 - 저장을 건너뛴다")
            return
        save_json(series_file(), self.series)

    def inline_edit(self, row, initial, on_commit):
        """줄을 입력칸으로 바꿔 그 자리에서 고친다. Enter·다른 곳 클릭: 저장, Esc: 취소."""
        self.hide_tip()
        self._editing = True
        e = self.hint_entry(self.panel, 13, "")
        e.insert(0, initial)
        e.pack(fill="x", pady=self.px(2), ipady=self.px(5), before=row)
        row.pack_forget()
        e.focus_set()
        e.select_range(0, "end")
        state = {"closed": False}

        def commit(_=None):
            if state["closed"]:
                return
            state["closed"] = True
            t = e.get().strip()
            if t and t != initial:
                on_commit(t)
            self.render()

        def cancel(_=None):
            state["closed"] = True
            self.render()

        e.bind("<Return>", commit)
        e.bind("<FocusOut>", commit)
        e.bind("<Escape>", cancel)

    def edit(self, idx, row):
        items = self.events.get(key_of(self.selected), [])
        if idx >= len(items):
            return
        it = items[idx]

        def commit(text):
            self.push_undo()
            it["title"] = text
            if time_of(text):
                it["time"] = time_of(text)
            else:
                it.pop("time", None)
            self.save()
        self.inline_edit(row, it["title"], commit)

    def make_form(self):
        wrap = tk.Frame(self.panel, bg=CARD)
        wrap.pack(fill="x", pady=(self.px(12), 0))
        top = tk.Frame(wrap, bg=CARD)
        top.pack(fill="x", pady=(0, self.px(6)))
        sw = self.swatches(top, self.color, self.set_color)
        sw.pack(side="left")
        self.tip(sw, self.t("tip_color"))
        if not self.range_span():              # 기간 일정은 반복하지 않는다
            on = bool(self.repeat)
            # 색 칩 옆에 남는 폭 안에서만 적는다 (넘치면 앞의 ↻ 가 잘려 안 보였다)
            chips = len(PALETTE) * (self.px(18) + 2 * self.px(2) + self.px(5))
            name = self.fit(self.t("rep_" + (self.repeat or "none")), self.fpx(10),
                            self.panel_w - chips - self.px(10)
                            - self.measure("↻ ", self.fpx(10), on), on)
            rp = tk.Label(top, text="↻ " + name, bg=CARD,
                          fg=ACCENT if on else DIM, font=self.f(10, on), cursor="hand2")
            rp.pack(side="right")
            rp.bind("<Button-1>", lambda e: self.cycle_repeat())
            self.tip(rp, self.t("tip_repeat"))
        line = tk.Frame(wrap, bg=CARD)
        line.pack(fill="x")
        # 시간은 제목에 같이 적는다 (따로 칸을 두면 용도가 안 보인다)
        self.button(line, self.t("add"), self.add).pack(side="right",
                                                        padx=(self.px(6), 0))
        self.entry_w = self.hint_entry(line, 13, self.t("event_hint"))
        self.entry_w.pack(side="left", fill="x", expand=True, ipady=self.px(6))
        self.entry_w.bind("<Return>", lambda _: self.add())

    def cycle_repeat(self):
        self.repeat = REPEATS[(REPEATS.index(self.repeat) + 1) % len(REPEATS)]
        self.render_panel()
        self.entry_w.focus_set()
        self.entry_w.icursor("end")

    def upcoming_rows(self):
        """다가오는 일 [(날짜, 제목, 시간, 색)] — 일정·반복 일정·시험을 날짜순으로."""
        rows = []
        for k, items in self.events.items():
            try:
                d = dt.date.fromisoformat(k)
            except ValueError:
                continue
            if d >= self.today:
                rows += [(d, it.get("title", ""), extra_time(it), it.get("color", PALETTE[0]),
                          it.get("time", "")) for it in items if not it.get("done")]
        for sr in self.series:                 # 반복 일정은 가장 가까운 한 번만
            d = series_next(sr, self.today)
            if d:
                rows.append((d, sr.get("title", ""), extra_time(sr),
                             sr.get("color", PALETTE[0]), sr.get("time", "")))
        # 시험·과제도 함께 보여준다. 과목 이름을 붙여야 뭐의 시험인지 알 수 있다.
        for title, info in self.courses.items():
            for k in EXAM_KEYS:
                d = parse_date(info.get(k + "_date", ""))
                if d and d >= self.today and not info.get(k + "_done"):
                    # 시험 종류를 앞에 둔다. 과목명이 길어 잘릴 때 '期中'이 잘리면 안 된다.
                    rows.append((d, "%s · %s" % (self.t("exam_%s_s" % k), title),
                                 self.note_out(info.get(k + "_time", "")),
                                 self.course_color(title), info.get(k + "_time", "")))
        rows.sort(key=lambda r: (r[0], r[4] or ""))
        return [r[:4] for r in rows]

    def upcoming_row(self, box, d, title, tm, col, width=None):
        width = width or self.panel_w
        f_t, f_d = self.fpx(12), self.fpx(10)
        pill_w = self.measure("D-000", self.fpx(10), True) + self.px(14)
        dot_w = self.px(14)
        # 날짜가 가까울수록 눈에 띄게: 오늘·내일 빨강, 일주일 안 주황, 그 뒤 회색
        pbg, pfg = self.pill_colors((d - self.today).days)
        r = tk.Frame(box, bg=CARD)
        r.pack(fill="x", pady=self.px(3))
        pill = tk.Frame(r, bg=pbg, width=pill_w, height=self.px(24))
        pill.pack(side="left")
        pill.pack_propagate(False)
        tk.Label(pill, text=self.dday_text(d), bg=pbg, fg=pfg,
                 font=self.f(10, True)).pack(expand=True)

        when = self.fit(self.short_date(d) + (" " + tm if tm else ""), f_d,
                        int(self.panel_w * 0.34))
        tk.Label(r, text=when, bg=CARD, fg=MUTED, font=self.f(10)
                 ).pack(side="right")
        dot = tk.Canvas(r, width=dot_w, height=dot_w, bg=CARD, highlightthickness=0)
        dot.pack(side="left", padx=(self.px(8), self.px(2)))
        self.disc(dot, dot_w / 2.0, dot_w / 2.0, max(2, dot_w * 0.22), self.dot_color(col))
        room = (width - pill_w - dot_w - self.px(18)
                - self.measure(when, f_d) - self.px(8))
        tk.Label(r, text=self.fit(title, f_t, room), bg=CARD, fg=FG,
                 font=self.f(12), anchor="w").pack(side="left", fill="x", expand=True)
        # 줄을 누르면 그 날짜로 간다 (배지는 제 색을 지켜야 하니 배경을 바꾸지 않는다)
        plain = [r] + [w for w in r.winfo_children() if w is not pill]
        for w in plain + [pill] + pill.winfo_children():
            w.config(cursor="hand2")
            w.bind("<Button-1>", lambda e, dd=d: self.select(dd))
            w.bind("<Enter>", lambda e, ws=plain: [x.config(bg=HOVER) for x in ws], add="+")
            w.bind("<Leave>", lambda e, ws=plain: [x.config(bg=CARD) for x in ws], add="+")

    def make_upcoming(self):
        rows = self.upcoming_rows()
        if not rows:
            return
        box = tk.Frame(self.panel, bg=CARD)
        box.pack(fill="x", side="bottom", pady=(self.px(14), 0))
        tk.Frame(box, bg=LINE, height=1).pack(fill="x", pady=(0, self.px(10)))
        hd = tk.Frame(box, bg=CARD)
        hd.pack(fill="x", pady=(0, self.px(6)))
        tk.Label(hd, text=self.t("upcoming"), bg=CARD, fg=FG, font=self.f(12, True),
                 anchor="w").pack(side="left")
        tk.Label(hd, text=str(len(rows)), bg=CARD, fg=DIM, font=self.f(11)
                 ).pack(side="left", padx=(self.px(6), 0))
        tk.Label(hd, text="›", bg=CARD, fg=DIM, font=self.f(13)).pack(side="right")
        for w in [hd] + hd.winfo_children():   # 제목을 누르면 전체 목록
            w.config(cursor="hand2")
            w.bind("<Button-1>", lambda e: self.show_upcoming())
            self.tip(w, self.t("tip_upcoming"))
        for row in rows[:3 if self.compact else 5]:
            self.upcoming_row(box, *row)

    def show_upcoming(self):
        self.panel_mode = "upcoming"
        self.render_panel()

    def close_mode(self):
        self.panel_mode = "day"
        self.render_panel()

    def scroll_area(self, parent):
        """휠로 넘기는 세로 목록. 안쪽 프레임을 돌려준다."""
        cv = tk.Canvas(parent, bg=CARD, highlightthickness=0, bd=0,
                       yscrollincrement=self.px(30))
        cv.pack(fill="both", expand=True)
        inner = tk.Frame(cv, bg=CARD)
        bw = max(2, self.px(3))
        cv.create_window(0, 0, window=inner, anchor="nw", width=self.panel_w - bw - self.px(5))
        thumb = tk.Frame(cv, bg=LINE)          # 아래에 더 있을 때만 보이는 얇은 막대

        def sync(*_):
            if not cv.winfo_exists():
                return
            a, b = cv.yview()
            if b - a >= 0.999:
                thumb.place_forget()
            else:
                thumb.place(relx=1.0, x=-bw, rely=a, relheight=b - a, width=bw)

        def resized(e):
            cv.config(scrollregion=(0, 0, e.width, e.height))
            cv.after_idle(sync)
        inner.bind("<Configure>", resized)
        cv.bind("<Configure>", lambda e: cv.after_idle(sync))
        cv._sync = sync
        self._scroll = cv
        return inner

    def on_wheel(self, e):
        """목록 위에서는 목록을 넘기고, 달력 위에서는 달을 넘긴다."""
        try:
            w = self.winfo_containing(e.x_root, e.y_root)
        except (KeyError, tk.TclError):
            return
        if w is None:
            return
        cv = self._scroll
        if cv is not None and cv.winfo_exists() and str(w).startswith(str(self.panel_host)):
            if cv.yview() != (0.0, 1.0):
                cv.yview_scroll(-1 if e.delta > 0 else 1, "units")
                cv._sync()
            return
        if w is self.cal and self.view == "cal" and not self.compact:
            # 휠 마우스는 한 칸(120)에 한 달. 터치패드는 한 번 쓸 때 작은 값이 수십 번,
            # 손을 뗀 뒤에도 관성으로 계속 들어온다. 그걸 다 셌더니 한 번 쓸면 여러 달이
            # 넘어갔다. 그래서 터치패드는 '한 번 쓸기 = 한 달' 로 한다: 한 달을 넘긴 뒤에는
            # 입력이 잠깐(0.25초) 끊길 때까지 더 넘기지 않는다.
            now = time.time()
            if now - self._wheel_last > 0.25:      # 새 동작의 시작
                self._wheel, self._wheel_lock = 0, False
            self._wheel_last = now
            fine = abs(e.delta) < 120              # 터치패드처럼 잘게 오는 입력
            if fine and self._wheel_lock:
                return
            self._wheel += e.delta
            if abs(self._wheel) >= 120 and now - self._wheel_t > 0.2:
                n = -1 if self._wheel > 0 else 1
                self._wheel, self._wheel_t, self._wheel_lock = 0, now, fine
                self.shift(n)

    def panel_head(self, text, count=None):
        """목록·설정 패널의 머리줄: 제목 + 닫기(×)."""
        hd = tk.Frame(self.panel, bg=CARD)
        hd.pack(fill="x", pady=(0, self.px(8)))
        tk.Label(hd, text=text, bg=CARD, fg=FG, font=self.f(16, True)).pack(side="left")
        if count is not None:
            tk.Label(hd, text=str(count), bg=CARD, fg=DIM, font=self.f(12)
                     ).pack(side="left", padx=(self.px(8), 0))
        x = tk.Label(hd, text="×", bg=CARD, fg=MUTED, font=self.f(18), cursor="hand2",
                     padx=self.px(4))
        x.pack(side="right")
        x.bind("<Button-1>", lambda e: self.close_mode())
        x.bind("<Enter>", lambda e: e.widget.config(fg=FG), add="+")
        x.bind("<Leave>", lambda e: e.widget.config(fg=MUTED), add="+")
        self.tip(x, self.t("close"))

    def panel_upcoming(self):
        """다가오는 일 전체. 이번 주 / 다음 주 / 그 이후로 묶는다."""
        rows = self.upcoming_rows()
        self.panel_head(self.t("upcoming"), len(rows))
        inner = self.scroll_area(self.panel)
        if not rows:
            tk.Label(inner, text=self.t("no_events"), bg=CARD, fg=DIM, font=self.f(12),
                     anchor="w").pack(fill="x")
            return
        sunday = self.today + dt.timedelta(days=6 - self.today.weekday())
        last = None
        for d, title, tm, col in rows:
            group = ("up_this_week" if d <= sunday else
                     "up_next_week" if d <= sunday + dt.timedelta(days=7) else "up_later")
            if group != last:
                tk.Label(inner, text=self.t(group), bg=CARD, fg=MUTED, font=self.f(10, True),
                         anchor="w").pack(fill="x", pady=(self.px(8) if last else 0,
                                                          self.px(2)))
                last = group
            self.upcoming_row(inner, d, title, tm, col, self.panel_w - self.px(10))

    # ---------- 설정 패널 ----------

    def menu(self, e=None):
        """≡ 또는 우클릭: 오른쪽 카드에 설정을 연다 (다시 누르면 닫는다)."""
        self.tt_commit()
        self.panel_mode = "day" if self.panel_mode == "settings" else "settings"
        self.render_panel()

    def seg(self, parent, label, options, cmd):
        """이름 한 줄 + 고르는 버튼들. options: [(값, 글, 켜짐)]. 폭이 모자라면 줄을 바꾼다."""
        tk.Label(parent, text=label, bg=CARD, fg=MUTED, font=self.f(11), anchor="w"
                 ).pack(fill="x", pady=(self.px(12), self.px(5)))
        row, used, gap = None, 0, self.px(5)
        # 고른 것은 강조색으로 채우고, 나머지도 본문 글자색으로 또렷하게
        off_bg = mix(CARD, FG, 0.13)
        for val, text, on in options:
            wd = self.measure(text, self.fpx(12), on) + self.px(24) + gap + 4
            if row is None or used + wd > self.panel_w - self.px(10):
                row = tk.Frame(parent, bg=CARD)
                row.pack(fill="x", pady=(0, gap))
                used = 0
            b = tk.Label(row, text=text, bg=ACCENT if on else off_bg,
                         fg=ACCENT_INK if on else FG, font=self.f(12, on),
                         padx=self.px(12), pady=self.px(6), cursor="hand2")
            b.pack(side="left", padx=(0, gap))
            b.bind("<Button-1>", lambda e, v=val: cmd(v))
            if not on:
                b.bind("<Enter>", lambda e: e.widget.config(bg=mix(CARD, FG, 0.24)), add="+")
                b.bind("<Leave>", lambda e: e.widget.config(bg=off_bg), add="+")
            used += wd

    def toggle_row(self, parent, text, on, cmd):
        row = tk.Frame(parent, bg=CARD, cursor="hand2")
        row.pack(fill="x", pady=self.px(1))
        box = self.check_box(row, ACCENT if on else MUTED, on, True, cmd)
        box.pack(side="left")
        lab = tk.Label(row, text=text, bg=CARD, fg=FG, font=self.f(13), anchor="w",
                       justify="left", cursor="hand2",
                       wraplength=self.panel_w - self.px(50), pady=self.px(5))
        lab.pack(side="left", fill="x", expand=True, padx=(self.px(4), 0))
        for w in (row, lab):
            w.bind("<Button-1>", lambda e: cmd())
        self.hoverable(row)

    def panel_settings(self):
        self.panel_head(self.t("settings"))
        box = self.scroll_area(self.panel)
        if self.update_ver:
            self._upd_btn = self.button(box, self.upd_label(), self.open_release,
                                        "primary", 11)
            self._upd_btn.pack(fill="x", pady=(0, self.px(4)))
        self.seg(box, self.t("lang"),
                 [(code, TEXT[code]["lang_name"], code == self.lang) for code in TEXT],
                 self.set_lang)
        self.seg(box, self.t("theme"),
                 [(n, self.t(n), n == self.theme) for n in ("dark", "light")], self.set_theme)
        self.seg(box, self.t("glass"),
                 [(k, self.t("glass_" + k), k == self.glass) for k in ("soft", "clear", "off")],
                 self.set_glass)
        sizes = [(-1, self.t("compact"), self.compact)] + [
            (i, self.t("sizes")[i], i == self.size_idx and not self.compact)
            for i in range(len(SIZES))]
        self.seg(box, self.t("size"), sizes,
                 lambda i: self.set_compact() if i < 0 else self.set_size(i))
        # 이번 주가 몇 주차인지: − / + 로 맞춘다. 单/双은 번호의 홀짝을 따른다.
        tk.Label(box, text=self.t("week_now"), bg=CARD, fg=MUTED, font=self.f(11), anchor="w"
                 ).pack(fill="x", pady=(self.px(12), self.px(5)))
        wrow = tk.Frame(box, bg=CARD)
        wrow.pack(fill="x")
        off_bg = mix(CARD, FG, 0.13)
        for text, delta in (("−", -1), (None, 0), ("+", 1)):
            if text is None:
                tk.Label(wrow, text=self.week_label(self.today), bg=ACCENT, fg=ACCENT_INK,
                         font=self.f(12, True), padx=self.px(12), pady=self.px(6)
                         ).pack(side="left", padx=(0, self.px(5)))
                continue
            b = tk.Label(wrow, text=text, bg=off_bg, fg=FG, font=self.f(12, True),
                         padx=self.px(13), pady=self.px(6), cursor="hand2")
            b.pack(side="left", padx=(0, self.px(5)))
            b.bind("<Button-1>", lambda e, dd=delta: self.step_week(dd))
            b.bind("<Enter>", lambda e: e.widget.config(bg=mix(CARD, FG, 0.24)), add="+")
            b.bind("<Leave>", lambda e: e.widget.config(bg=off_bg), add="+")
        if self.week_no(self.today) is None:
            tk.Label(box, text=self.t("week_unset_hint"), bg=CARD, fg=DIM, font=self.f(10),
                     anchor="w", justify="left", wraplength=self.panel_w - self.px(16)
                     ).pack(fill="x", pady=(self.px(5), 0))
        tk.Frame(box, bg=LINE, height=1).pack(fill="x", pady=(self.px(14), self.px(8)))
        self.toggle_row(box, self.t("weekend_tt"), self.weekend_tt, self.toggle_weekend_tt)
        auto = autostart_enabled()
        self.toggle_row(box, self.t("autostart"), auto,
                        lambda: (self.set_autostart_pref(not auto), self.render_panel()))
        upd = bool(self.conf.get("update_check", True))
        self.toggle_row(box, self.t("upd_check"), upd, lambda: self.set_update_check(not upd))
        tk.Frame(box, bg=LINE, height=1).pack(fill="x", pady=self.px(10))

        def act(text, cmd, kind="plain"):
            b = self.button(box, text, cmd, kind, 12)
            b.config(anchor="w", bg=mix(CARD, FG, 0.13), fg=FG if kind == "plain" else SUN)
            b.bind("<Enter>", lambda e: e.widget.config(bg=mix(CARD, FG, 0.24)))
            b.bind("<Leave>", lambda e: e.widget.config(bg=mix(CARD, FG, 0.13)))
            b.pack(fill="x", pady=self.px(3))
        act(self.t("export_ics"), self.export_ics)
        act(self.t("backup_out"), self.export_backup)
        act(self.t("backup_in"), self.import_backup)
        act(self.t("open_data"), lambda: subprocess.Popen(["explorer", APP_DIR]))
        act(self.t("quit"), self.quit_app, "danger")
        tk.Label(box, text="DeskCal %s" % __version__, bg=CARD, fg=DIM, font=self.f(10),
                 anchor="w").pack(fill="x", pady=(self.px(8), self.px(4)))

    # ---------- 내보내기 · 백업 ----------

    def reveal(self, path):
        """탐색기에서 그 파일을 골라 보여준다."""
        if not self.float_mode:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])

    def export_ics(self, path=None):
        """다른 캘린더 앱(Google · Outlook · Apple)에 넣을 수 있는 .ics 파일을 만든다."""
        self.tt_commit()
        text = build_ics(self.events, self.series, self.courses, self.tt, self.periods,
                         self.anchor(), self.today, lambda k: self.t("exam_" + k),
                         week1=self.week1())
        show = path is None
        path = path or os.path.join(documents_dir(), "DeskCal.ics")
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        except OSError as e:
            self.notice(self.t("save_fail", why=str(e)))
            return None
        if show:
            self.reveal(path)
        return path

    def backup_data(self):
        conf = {k: v for k, v in self.conf.items() if not k.startswith("update_")}
        return {"events.json": self.events, "series.json": self.series,
                "timetable.json": self.tt, "courses.json": self.courses, "config.json": conf}

    def export_backup(self, path=None):
        """일정·시간표·설정을 zip 하나로 묶는다 (다른 컴퓨터의 DeskCal 로 옮길 때)."""
        self.tt_commit()
        self.save_conf()
        show = path is None
        path = path or os.path.join(documents_dir(),
                                    "DeskCal-backup-%s.zip" % self.today.strftime("%Y%m%d"))
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                for name, obj in self.backup_data().items():
                    z.writestr(name, json.dumps(obj, ensure_ascii=False, indent=2))
        except OSError as e:
            self.notice(self.t("save_fail", why=str(e)))
            return None
        if show:
            self.reveal(path)
        return path

    def import_backup(self, path=None, ask=True):
        global FONT
        if path is None:
            path = filedialog.askopenfilename(
                parent=self, initialdir=documents_dir(),
                filetypes=[("DeskCal backup", "*.zip"), ("*", "*.*")])
            if not path:
                return False
        data = read_backup(path)
        if not data:
            self.notice(self.t("backup_bad"))
            return False
        if ask and not self.confirm(self.t("backup_confirm"), self.t("restore")):
            return False
        # 지금 데이터를 따로 남겨 둔다 (되돌리기와 별개로, 껐다 켠 뒤에도 찾을 수 있게)
        self.export_backup(os.path.join(
            APP_DIR, "before-restore-%s.zip" % time.strftime("%Y%m%d-%H%M%S")))
        self.push_undo()
        if "events.json" in data and self.data_ok:
            self.events = data["events.json"]
            self.save()
        if "series.json" in data and self.sr_ok:
            self.series = data["series.json"]
            self.save_series()
        if "timetable.json" in data and self.tt_ok:
            self.tt = data["timetable.json"]
            self.save_tt()
        if "courses.json" in data and self.cs_ok:
            self.courses = data["courses.json"]
            self.save_courses()
        conf = data.get("config.json") or {}
        for k in ("lang", "theme", "glass", "size", "compact", "color", "week_anchor", "week1",
                  "periods", "weekend_tt"):
            if k in conf:
                self.conf[k] = conf[k]
        if self.conf.get("lang") in TEXT:
            self.lang = self.conf["lang"]
        if self.conf.get("theme") in THEMES:
            self.theme = self.conf["theme"]
        if self.conf.get("glass") in GLASS:
            self.glass = self.conf["glass"]
        try:
            self.size_idx = min(max(int(self.conf.get("size", self.size_idx)), 0),
                                len(SIZES) - 1)
        except (TypeError, ValueError):
            pass
        self.compact = bool(self.conf.get("compact", False))
        if self.compact:
            self.view = "cal"
        self.color = pc(self.conf.get("color", self.color))
        self.weekend_tt = bool(self.conf.get("weekend_tt", False))
        self.periods = parse_periods(self.conf.get("periods") or PERIOD_TIMES)
        FONT = pick_font(self, self.lang)
        self._fonts.clear()
        self.panel_mode = "day"
        self.build()
        self.ensure_on_screen()
        self.save_conf()
        log("백업을 불러왔다: %s" % os.path.basename(path))
        if ask:
            self.notice(self.t("backup_done"))
        return True

    def confirm(self, text, yes):
        """예/취소를 묻는 창. 예를 누르면 True."""
        top = self.dialog()
        pad = self.px(18)
        tk.Label(top, text=text, bg=CARD, fg=FG, font=self.f(12), anchor="w", justify="left",
                 wraplength=self.px(400)).pack(fill="x", padx=pad, pady=(pad, 0))
        out = []

        def ok(_=None):
            out.append(True)
            top.destroy()
        bar = tk.Frame(top, bg=CARD)
        bar.pack(fill="x", padx=pad, pady=pad)
        self.button(bar, self.t("cancel"), top.destroy, "plain", 11).pack(side="right")
        self.button(bar, yes, ok, "primary", 11).pack(side="right", padx=(0, self.px(6)))
        top.bind("<Return>", ok)
        top.bind("<Escape>", lambda e: top.destroy())
        self.place_dialog(top)
        top.grab_set()
        self.wait_window(top)
        return bool(out)

    # ---------- 새 버전 확인 ----------
    # 하루 한 번 GitHub 에 최신 버전 번호만 묻는다 (보내는 정보 없음). 설정에서 끌 수 있고,
    # 연결이 안 되면 조용히 넘어간다. 새 버전이 있으면 ≡ 에 점, 설정 맨 위에 받기 버튼.

    def set_update_check(self, on):
        self.conf["update_check"] = bool(on)
        if not on and self.update_ver:
            self.update_ver = None
            self.conf.pop("update_latest", None)
            title = self.title_text()
            self.draw_header()
            self.set_title(title)
        self.save_conf()
        self.render_panel()

    def upd_label(self):
        st = self._upd_state
        if st and st[0] == "dl":
            return self.t("upd_dl", p=st[1])
        if st:
            return self.t("upd_installing")
        return self.t("upd_install" if is_installed() else "upd_get", v=self.update_ver)

    def refresh_upd_btn(self):
        b = self._upd_btn
        try:
            if b is not None and b.winfo_exists():
                b.config(text=self.upd_label())
        except tk.TclError:
            pass

    def open_release(self):
        """업데이트 버튼. 설치본이면 설치 파일을 받아 확인한 뒤 바로 설치하고 다시 켠다.
        그 밖에는(압축본·소스 실행) 다운로드 페이지를 연다."""
        if self._upd_state:
            return                              # 이미 받는 중
        if not is_installed():
            os.startfile(RELEASES_PAGE)
            return
        self._upd_state = ("dl", 0)
        self.refresh_upd_btn()
        q = self._upd_dl_q = queue.Queue()

        def work():
            try:
                rel = fetch_release()
                if not rel["setup_url"]:
                    raise ValueError("no installer in the release")
                sha = rel["sha256"]
                if not sha and rel["sha_url"]:  # 릴리스에 같이 올린 .sha256 파일
                    req = urllib.request.Request(rel["sha_url"], headers={"User-Agent": "DeskCal"})
                    with urllib.request.urlopen(req, timeout=15) as r:
                        sha = (r.read(4096).decode("utf-8", "replace").split() or [""])[0].lower()
                if not re.fullmatch(r"[0-9a-f]{64}", sha or ""):
                    raise ValueError("no checksum for the installer")
                folder = os.path.join(APP_DIR, "update")
                os.makedirs(folder, exist_ok=True)
                dest = os.path.join(folder, "DeskCal-%s-Setup.exe" % rel["version"])
                download_verified(rel["setup_url"], dest, sha,
                                  lambda g, t: q.put(("dl", int(g * 100 / t) if t else 0)))
                q.put(("ok", dest))
            except Exception as e:
                q.put(("fail", "%s: %s" % (type(e).__name__, e)))
        threading.Thread(target=work, daemon=True, name="update-dl").start()
        self._jobs["upd_dl"] = self.after(200, self.update_poll)

    def update_poll(self):
        last = None
        try:
            while True:
                last = self._upd_dl_q.get_nowait()
        except queue.Empty:
            pass
        if last and last[0] == "fail":
            self.update_failed(last[1])
            return
        if last and last[0] == "ok":
            self._upd_state = ("install", 0)
            self.refresh_upd_btn()
            self.run_installer(last[1])
            return
        if last:
            self._upd_state = last
            self.refresh_upd_btn()
        self._jobs["upd_dl"] = self.after(200, self.update_poll)

    def update_failed(self, why):
        """받기·확인·실행 어디서든 실패하면 예전처럼 다운로드 페이지를 연다."""
        self._upd_state = None
        self.refresh_upd_btn()
        log("자동 업데이트 실패: %s" % why)
        self.notice(self.t("upd_fail", why=why))
        os.startfile(RELEASES_PAGE)

    def run_installer(self, setup):
        exe = sys.executable
        if any(ch in setup + exe for ch in '"%'):      # 배치 파일에 안전하게 적을 수 없는 경로
            self.update_failed("unsupported path")
            return
        try:
            bat = os.path.join(os.path.dirname(setup), "update.bat")
            with open(bat, "w", encoding="utf-8", newline="") as f:
                f.write(update_script(setup, exe))
            # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP: 창 없이, 앱이 꺼져도 계속 돈다
            subprocess.Popen(["cmd.exe", "/c", bat], creationflags=0x08000000 | 0x00000200,
                             close_fds=True)
        except OSError as e:
            self.update_failed(str(e))
            return
        log("업데이트 설치 시작: %s" % os.path.basename(setup))
        self.after(400, self.quit_app)          # 앱이 꺼져야 설치 프로그램이 파일을 바꿀 수 있다

    def update_tick(self):
        try:
            if not getattr(self, "_upd_cleaned", False) and not self._upd_state:
                self._upd_cleaned = True       # 지난 업데이트 때 받아 둔 설치 파일을 치운다
                shutil.rmtree(os.path.join(APP_DIR, "update"), ignore_errors=True)
            last = float(self.conf.get("update_checked", 0) or 0)
            if (self.conf.get("update_check", True) and not self._upd_busy
                    and time.time() - last > 20 * 3600):
                self._upd_busy = True

                def work():
                    try:
                        self._upd_q.put(fetch_latest_version())
                    except Exception:
                        self._upd_q.put("")    # 연결 안 됨 (교내망·방화벽): 조용히 넘어간다
                threading.Thread(target=work, daemon=True, name="update").start()
            try:
                found = self._upd_q.get_nowait()
            except queue.Empty:
                found = None
            if found is not None:
                self._upd_busy = False
                self.apply_latest(found)
        except Exception:
            log("update_tick 예외:\n" + traceback.format_exc())
        self._jobs["upd"] = self.after(3000 if self._upd_busy else 3600 * 1000,
                                       self.update_tick)

    def apply_latest(self, found):
        """확인 결과를 반영한다. found: '1.2.3' 또는 ''(확인 실패)."""
        now = time.time()
        if not version_tuple(found):
            self.conf["update_checked"] = now - 16 * 3600      # 4시간 뒤 다시
        else:
            self.conf["update_checked"] = now
            self.conf["update_latest"] = found
            newer = found if version_tuple(found) > version_tuple(__version__) else None
            if newer != self.update_ver:
                self.update_ver = newer
                log("새 버전 확인: %s (지금 %s)" % (found, __version__))
                if not self._drag:
                    title = self.title_text()
                    self.draw_header()         # ≡ 의 점만 바꾼다 (적던 글을 건드리지 않게)
                    self.set_title(title)
        save_json(CONF_FILE, self.conf)

    # ---------- 데이터 ----------

    def push_undo(self):
        self.undo_stack.append(json.dumps({"e": self.events, "t": self.tt,
                                           "c": self.courses, "s": self.series},
                                          ensure_ascii=False))
        if len(self.undo_stack) > 40:
            self.undo_stack.pop(0)

    def undo(self, _=None):
        if not self.undo_stack:
            return "break"
        snap = json.loads(self.undo_stack.pop())
        self.events, self.tt = snap["e"], snap["t"]
        self.courses = snap.get("c", self.courses)
        self.series = snap.get("s", self.series)
        self.save()
        self.save_tt()
        self.save_courses()
        self.save_series()
        self.render()
        return "break"

    def add(self):
        t = self.entry_w.get().strip()
        if not t:
            self.entry_w.focus_set()
            return
        self.push_undo()
        tm = time_of(t)                        # "치과 3pm" → 15:00 (제목은 그대로)
        span = self.range_span()
        if span:                               # Shift+클릭으로 고른 기간
            self.series.append({"title": t, "color": self.color,
                                "start": key_of(span[0]), "end": key_of(span[1])})
            self.save_series()
            self.range_to = None
        elif self.repeat:
            self.series.append({"title": t, "color": self.color, "time": tm,
                                "start": key_of(self.selected), "repeat": self.repeat})
            self.save_series()
            self.repeat = ""
        else:
            it = {"title": t, "color": self.color, "done": False}
            if tm:
                it["time"] = tm
            self.events.setdefault(key_of(self.selected), []).append(it)
            self.save()
        self.entry_w.delete(0, "end")          # 다시 그릴 때 적던 글로 되살아나지 않게
        self.render()
        self.entry_w.focus_set()

    def items_today(self):
        return self.events.get(key_of(self.selected), [])

    def toggle_done(self, idx):
        items = self.items_today()
        if idx < len(items):
            self.push_undo()
            items[idx]["done"] = not items[idx].get("done")
            self.save()
            self.render()

    def delete(self, idx):
        k = key_of(self.selected)
        items = self.events.get(k, [])
        if idx < len(items):
            self.push_undo()
            items.pop(idx)
            if not items:
                self.events.pop(k, None)
            self.save()
            self.render()

    def set_color(self, col):
        # 적던 글은 render_panel 이 새 입력칸으로 옮겨 담는다.
        self.color = col
        self.conf["color"] = col
        self.render()
        try:
            self.entry_w.focus_set()
            self.entry_w.icursor("end")
        except Exception:
            pass

    def apply_color(self, idx, col):
        items = self.items_today()
        if idx < len(items):
            self.push_undo()
            items[idx]["color"] = col
            self.save()
            self.render()

    def save(self):
        if not self.data_ok:
            log("데이터를 읽지 못한 상태 - 저장을 건너뛴다")
            return
        save_json(DATA_FILE, self.events)

    def save_tt(self):
        if not self.tt_ok:
            log("시간표를 읽지 못한 상태 - 저장을 건너뛴다")
            return
        save_json(TT_FILE, self.tt)

    def save_courses(self):
        if not self.cs_ok:
            log("과목 정보를 읽지 못한 상태 - 저장을 건너뛴다")
            return
        save_json(COURSE_FILE, self.courses)

    def reload_data(self):
        events, ok = load_json(DATA_FILE, None, tries=1)
        if not ok:
            return False
        self.events = events if events is not None else {}
        self.data_ok = True
        self.undo_stack = []
        log("데이터를 다시 불러왔다 (%d일치)" % len(self.events))
        self.render()
        return True

    def save_conf(self):
        self.conf.update({"x": self.winfo_x(), "y": self.winfo_y(), "size": self.size_idx,
                          "color": self.color, "lang": self.lang, "theme": self.theme,
                          "glass": self.glass, "compact": self.compact})
        save_json(CONF_FILE, self.conf)

    # ---------- 창 이동 · 메뉴 ----------

    def drag_start(self, e):
        self._drag = None
        c = self.base
        under = c.find_overlapping(e.x, e.y, e.x, e.y)     # 누른 자리 아래 항목들
        if any("btn" in c.gettags(i) for i in under):
            return                                 # 버튼 위에서는 끌지 않는다
        self._drag = (e.x_root - self.winfo_x(), e.y_root - self.winfo_y())
        self._drag_from = (self.winfo_x(), self.winfo_y())
        sig = wallpaper_sig()
        if sig != self._wall_sig:
            self._wall_sig, self._wall_changed = sig, time.time()
        if self.glass_img:
            if self.desk_ready():
                self.use_desk()
            elif not self._desk_busy:          # 아직 없으면 지금 바로 만들기 시작
                if self._desk_job:
                    self.after_cancel(self._desk_job)
                self.prepare_desk()

    def drag_move(self, e):
        if self._drag:
            pos = (e.x_root - self._drag[0], e.y_root - self._drag[1])
            if pos == self._drag_pos:
                return
            self._drag_pos = pos
            if not getattr(self, "_drag_job", None):   # 밀린 움직임은 한 번에 처리한다
                self._drag_job = self.after_idle(self.drag_frame)

    def drag_frame(self):
        """창 이동 한 번. 유리를 먼저 새 자리에 맞춰 둔 뒤 창을 옮기고 곧바로 그린다.
        (창을 먼저 옮기면 다시 그리기 전 한 순간 유리가 창과 같이 밀려 보여 덜컥거린다)"""
        self._drag_job = None
        if not self._drag or not self._drag_pos:
            return
        if self.glass_img:
            self.move_glass()
        self.geometry("+%d+%d" % self._drag_pos)
        self.update_idletasks()

    def drag_end(self, _):
        if self._drag:
            if getattr(self, "_drag_job", None):    # 마지막 움직임을 빠뜨리지 않는다
                self.after_cancel(self._drag_job)
                self.drag_frame()
            self._drag = None
            self.update_idletasks()
            self._drag_pos = None
            self.save_conf()
            if self.glass_img and self.window_pos() != self._drag_from:
                if not self.recolor_from_desk():
                    self.build()               # 대비가 모자라다: 유리부터 다시 만든다

    def popup(self, m, e):
        # grab 을 놓지 않으면 창이 입력을 먹은 채 "응답 없음" 으로 강제 종료된다
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def new_menu(self, parent):
        return tk.Menu(parent, tearoff=0, bg=CARD, fg=FG, font=(FONT, -self.fpx(13)),
                       activebackground=SEL_BG, activeforeground=FG, bd=0)

    def radio(self, menu, label, on, cmd):
        menu.add_command(label=("●  " if on else "     ") + label, command=cmd)

    def color_menu(self, e, idx):
        if idx >= len(self.items_today()):
            return
        m = self.new_menu(self)
        for col in PALETTE:
            m.add_command(label="██████", foreground=col, activeforeground=col,
                          command=lambda c=col, i=idx: self.apply_color(i, c))
        self.popup(m, e)

    def init_autostart(self):
        """처음 켤 때는 '윈도우 시작 시 실행'을 켜 둔다. 메뉴에서 끈 뒤에는 다시 켜지 않는다."""
        if "autostart" not in self.conf:
            self.set_autostart_pref(True)
        elif self.conf.get("autostart") is True:
            # 켜 둔 설정인데 등록이 사라졌거나(다른 설치본을 제거하면 같이 지워진다)
            # 폴더를 옮겨 경로가 달라졌으면 다시 등록한다.
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                    cur = winreg.QueryValueEx(k, RUN_NAME)[0]
            except OSError:
                cur = None
            if cur != launch_command():
                log("윈도우 시작 시 실행 등록이 %s - 다시 등록" % ("없음" if cur is None else "다른 경로"))
                set_autostart(True)


    @property
    def n_days(self):
        return 7 if getattr(self, "weekend_tt", False) else 5

    def toggle_weekend_tt(self):
        self.weekend_tt = not self.weekend_tt
        self.conf["weekend_tt"] = self.weekend_tt
        self.save_conf()
        if self.tt_sel[0] >= self.n_days:
            self.tt_sel = (0, self.tt_sel[1])
        if self.tt_multi:
            self.tt_multi = {(di, p) for di, p in self.tt_multi if di < self.n_days}
        self.render()

    def set_autostart_pref(self, on):
        set_autostart(on)
        self.conf["autostart"] = on            # 사용자가 고른 값을 기억한다
        self.save_conf()

    def isop_conf(self):
        """authCode from DPAPI in isop.json (appKey/appSecret hidden in native module)."""
        if not HAS_ISOP_CLIENT:
            log("ISOP secure native module not loaded")
            return None
        conf, ok = load_json(ISOP_FILE, {})
        if not ok:
            return None
        raw = conf.get("authCode", "")
        auth_code = ""
        if raw:
            try:
                auth_code = _dpapi_unprotect(bytes.fromhex(raw)).decode("utf-8")
            except Exception:
                if len(raw) == 32 and all(c in "0123456789abcdefABCDEF" for c in raw):
                    auth_code = raw
                else:
                    auth_code = ""
        return {
            "user": conf.get("user", ""),
            "authCode": auth_code,
            "authDate": conf.get("authDate", ""),
        }

    def isop_mail_gate(self, user):
        """인증 메일 남용 방지: 전체 쿨다운 + 학번당 하루 횟수. 막히면 안내 문구, 통과면 None."""
        data, _ = load_json(ISOP_THROTTLE_FILE, {})
        left = ISOP_MAIL_COOLDOWN - (time.time() - data.get("last", 0))
        if left > 0:
            return self.t("isop_cooldown", s=int(left) + 1)
        if (data.get("day") == self.today.isoformat()
                and data.get("counts", {}).get(user, 0) >= ISOP_MAIL_DAILY_CAP):
            return self.t("isop_daily_cap", n=ISOP_MAIL_DAILY_CAP)
        return None

    def isop_mail_record(self, user):
        """인증 메일을 실제로 보낸 뒤 호출 — 보낸 시각과 학번별 횟수를 남긴다."""
        data, _ = load_json(ISOP_THROTTLE_FILE, {})
        if data.get("day") != self.today.isoformat():
            data["day"], data["counts"] = self.today.isoformat(), {}
        data["last"] = time.time()
        data.setdefault("counts", {})[user] = data.get("counts", {}).get(user, 0) + 1
        save_json(ISOP_THROTTLE_FILE, data)

    def isop_authorize(self, conf):
        """학번 → 북대 메일 인증번호 → 권한 코드(6개월). 성공하면 isop.json 에 저장."""
        if not HAS_ISOP_CLIENT:
            self.notice(self.t("isop_failed", why="Secure client module missing"))
            return None
        user = self.ask_text(self.t("isop_ask_user"), conf.get("user", ""))
        if not user:
            return None
        user = user.strip()
        gate = self.isop_mail_gate(user)
        if gate:
            self.notice(gate)
            return None

        base = [
            ("appKey", _isop_client.get_app_key()),
            ("clientIp", isop_client_ip()),
            ("svcId", ISOP_SVC),
            ("timestamp", str(int(time.time() * 1000))),
            ("user", user),
        ]
        try:
            r = isop_call("oauth/validcode2mail/v2", base, sort=True)
        except Exception as e:
            log("ISOP 인증 메일 통신 오류: %s" % e)
            self.notice(self.t("isop_failed", why=str(e)))
            return None

        if not r.get("success"):
            log("ISOP 인증번호 요청 실패: %s" % {k: v for k, v in r.items() if k != "msg"})
            self.notice(self.t("isop_failed", why=r.get("msg") or str(r)))
            return None
        self.isop_mail_record(user)

        code = self.ask_text(self.t("isop_ask_code"))
        if not code:
            return None

        pairs = [p for p in base if p[0] != "timestamp"] + [
            ("timestamp", str(int(time.time() * 1000))),
            ("validCode", code.strip()),
        ]
        try:
            r = isop_call("oauth/authcode/v2", pairs, sort=True)
        except Exception as e:
            log("ISOP 인증코드 통신 오류: %s" % e)
            self.notice(self.t("isop_failed", why=str(e)))
            return None

        if not r.get("success") or not r.get("authCode"):
            log("ISOP 권한 코드 받기 실패: %s" % {k: v for k, v in r.items() if k != "authCode"})
            self.notice(self.t("isop_failed", why=r.get("msg") or str(r)))
            return None

        try:
            protected = _dpapi_protect(r["authCode"].encode("utf-8")).hex()
        except Exception:
            protected = r["authCode"]
        save_json(ISOP_FILE, {
            "user": user,
            "authCode": protected,
            "authDate": self.today.isoformat(),
        })
        conf.update(user=user, authCode=r["authCode"], authDate=self.today.isoformat())
        log("ISOP 권한 코드 받음 (6개월 유효)")
        return conf

    def isop_fetch(self, conf):
        if not HAS_ISOP_CLIENT:
            return {"flag": False, "msg": "Client missing"}
        pairs = [
            ("user", conf["authCode"]),
            ("appKey", _isop_client.get_app_key()),
            ("timestamp", str(int(time.time() * 1000))),
        ]
        return isop_call("pro/student/coursetableroom", pairs, sort=False)

    def import_isop(self, conf):
        try:
            if not conf.get("authCode"):
                conf = self.isop_authorize(conf)
                if not conf:
                    return
            try:
                resp = self.isop_fetch(conf)
            except Exception as e:
                log("기존 권한 코드로 课表 가져오기 실패, 재인증 시도: %s" % e)
                conf = self.isop_authorize(dict(conf, authCode=""))
                if not conf:
                    return
                resp = self.isop_fetch(conf)
            if not isop_ok(resp):                        # 권한 코드가 만료됐을 수 있다
                log("ISOP 课表 요청 실패, 다시 인증: %s" % str(resp)[:200])
                conf = self.isop_authorize(dict(conf, authCode=""))
                if not conf:
                    return
                resp = self.isop_fetch(conf)
        except Exception as e:
            log("ISOP 요청 오류:\n" + traceback.format_exc())
            err_msg = str(e)
            if hasattr(e, "reason"):
                err_msg = str(e.reason)
            self.notice(self.t("isop_failed", why=f"{self.t('isop_net')}\n({err_msg})"))
            return
        if not isop_ok(resp):
            self.notice(self.t("isop_failed", why=resp.get("msg") or str(resp)[:120]))
            return
        log("ISOP 课表 받음: 과목 %d개" % len(resp.get("list") or []))
        for c in resp.get("list") or []:
            if (c.get("kcmc") or "").strip() and not isop_entries(c):
                raw = [{k: j.get(k) for k in ("xq", "kssj", "jssj", "dsz", "qsz", "jsz")}
                       for j in (c.get("jsap") or [])]
                log("ISOP: 시간을 읽지 못한 과목 %s (%s) jsap=%r"
                    % (c.get("kcmc"), c.get("zxjhbh") or "", raw))
        self.review_pku(resp)                            # 바뀐 점을 보여주고 고른 것만 적용



    def import_pku(self):
        """정식 등록한 ISOP 앱 설정(data/isop.json)이 있으면 그걸로 가져온다. 없으면 설정에
        저장된 课表 파일(pku_import_file)에서, 그것도 없으면 '준비 중' 안내."""
        conf = self.isop_conf()
        if conf:
            self.import_isop(conf)
            return
        path = self.conf.get("pku_import_file")
        if not (path and os.path.exists(path)):
            self.notice(self.t("pku_paused"))
            return
        try:
            with open(path, encoding="utf-8-sig", errors="replace") as f:
                raw = f.read()
            resp = (parse_pku_html(raw) if path.lower().endswith((".html", ".htm"))
                    else json.loads(raw))
        except (OSError, ValueError):
            log("课表 파일을 읽지 못함:\n" + traceback.format_exc())
            self.notice(self.t("pku_empty"))
            return
        self.review_pku(resp)

    def fmt_cells(self, cells):
        """{(요일, 교시)} → '수 3–4교시, 금 5–6교시' (이어진 교시는 묶는다)."""
        out = []
        for di in sorted({d for d, _ in cells}):
            ps = sorted(p for d, p in cells if d == di)
            start = prev = ps[0]
            for p in ps[1:] + [None]:
                if p is not None and p == prev + 1:
                    prev = p
                    continue
                out.append(self.t("periods_fmt", wd=self.t("wd")[di], a=start,
                                  b=("" if start == prev else "–%d" % prev)))
                if p is not None:
                    start = prev = p
        return ", ".join(out)

    def pku_changes(self, resp):
        """가져온 课表와 지금 시간표의 차이. [{kind, title, text, on, ...}] 와 못 넣은 수."""
        slots, skipped = isop_slots(resp, n_days=7) if "list" in resp else parse_pku_table(resp, n_days=7)
        if any(di >= 5 for di, _ in slots.keys()) and not self.weekend_tt:
            self.weekend_tt = True
            self.conf["weekend_tt"] = True
            self.save_conf()
        portal = {}
        for (di, p), cs in sorted(slots.items()):
            seen = set()
            for c in cs:                             # 같은 시간에 单周·双周 수업이 따로 있을 수 있다
                if c["title"] in seen:               # 같은 과목이 한 칸에 두 번이면 첫 것만
                    skipped += 1
                    continue
                seen.add(c["title"])
                portal.setdefault(c["title"], {"cells": {}, "exam": None})
                portal[c["title"]]["cells"][(di, p)] = (c["room"], c["week"], c.get("weeks", ""))
                portal[c["title"]]["exam"] = portal[c["title"]]["exam"] or c["exam"]
        mine = {}
        for key, it in all_items(self.tt):
            di, p = (int(v) for v in key.split("-"))
            mine.setdefault(it.get("title"), {})[(di, p)] = (it.get("room", ""),
                                                             it.get("week", "all"),
                                                             it.get("weeks", ""))
        wk = {"all": self.t("chip_all"), "odd": self.t("chip_odd"), "even": self.t("chip_even")}

        def wname(v):                                # '单周 1-8'
            return (wk[v[1]] + " " + v[2]).strip()
        out = []
        for title, info in portal.items():
            new, old = info["cells"], mine.get(title)
            if old:                                  # 학교 자료에 교실이 비면 (체육 등) 직접 적은 교실 유지
                mine_room = next((v[0] for v in old.values() if v[0]), "")
                new = info["cells"] = {k: (v[0] or old.get(k, (mine_room,))[0] or mine_room,
                                           v[1], v[2]) for k, v in new.items()}
            if old is None:
                out.append({"kind": "set", "title": title, "cells": new, "on": True,
                            "text": self.t("chg_new", t=title, cells=self.fmt_cells(new))})
            elif new != old:
                parts = []
                if set(new) != set(old):
                    parts.append(self.t("chg_time", a=self.fmt_cells(old), b=self.fmt_cells(new)))
                rooms_o = sorted({v[0] for v in old.values()})
                rooms_n = sorted({v[0] for v in new.values()})
                if rooms_o != rooms_n:
                    parts.append(self.t("chg_room", a=" / ".join(rooms_o) or "—",
                                        b=" / ".join(rooms_n) or "—"))
                weeks_o = sorted({wname(v) for v in old.values()})
                weeks_n = sorted({wname(v) for v in new.values()})
                if weeks_o != weeks_n:
                    parts.append(self.t("chg_week", a=" / ".join(weeks_o),
                                        b=" / ".join(weeks_n)))
                if not parts:                        # 칸마다 강의실·주차가 엇갈리게 바뀐 경우
                    parts.append(self.t("chg_detail"))
                out.append({"kind": "set", "title": title, "cells": new, "on": True,
                            "text": "%s: %s" % (title, ", ".join(parts))})
            if info["exam"]:
                d_new, tm = info["exam"]
                cur = self.courses.get(title, {})
                d_cur = parse_date(cur.get("fin_date", ""))
                if not d_cur:                        # 비어 있을 때만 기본으로 채운다
                    out.append({"kind": "exam", "title": title, "exam": info["exam"], "on": True,
                                "text": self.t("chg_exam_new", t=title,
                                               d=self.btn_date(parse_date(d_new)), tm=self.note_out(tm))})
                elif d_cur.isoformat() != d_new:     # 직접 적은 날짜와 다르면 고를 수 있게만
                    out.append({"kind": "exam", "title": title, "exam": info["exam"], "on": False,
                                "text": self.t("chg_exam_diff", t=title,
                                               a=self.btn_date(d_cur),
                                               b=self.btn_date(parse_date(d_new)))})
        for title, cells in mine.items():
            if title not in portal:                  # 门户에 없는 수업: 지우는 건 직접 골라야
                out.append({"kind": "gone", "title": title, "on": False,
                            "text": self.t("chg_gone", t=title, cells=self.fmt_cells(cells))})
        return out, skipped

    def apply_changes(self, changes):
        """고른 변경만 적용한다. Ctrl+Z 한 번으로 전부 되돌린다."""
        if not changes:
            return
        self.tt_commit()
        self.push_undo()
        colors = {}
        for _, it in all_items(self.tt):
            colors.setdefault(it.get("title"), it.get("color"))
        free = [c for c in PALETTE if c not in colors.values()] or PALETTE
        n_new = 0
        placed = {}                                  # 칸마다 이번에 넣은 수업 수 (받은 순서를 지킨다)
        for ch in changes:
            title = ch["title"]
            if ch["kind"] in ("set", "gone"):
                for k in list(self.tt):              # 그 과목만 뺀다 (같은 칸의 다른 수업은 둔다)
                    items = cell_items(self.tt, k)
                    kept = [x for x in items if x.get("title") != title]
                    if len(kept) != len(items):
                        set_cell(self.tt, k, kept)
                if ch["kind"] == "gone":
                    self.courses.pop(title, None)
            if ch["kind"] == "set":
                if not colors.get(title):
                    colors[title] = free[n_new % len(free)]
                    n_new += 1
                for (di, p), v in ch["cells"].items():
                    new = {"title": title, "room": v[0], "color": colors[title], "week": v[1]}
                    if len(v) > 2 and v[2]:
                        new["weeks"] = v[2]
                    k = self.tt_key(di, p)           # 같은 시간의 다른 수업은 지우지 않고 뒤에 둔다
                    items = cell_items(self.tt, k)
                    items.insert(placed.get(k, 0), new)
                    placed[k] = placed.get(k, 0) + 1
                    set_cell(self.tt, k, items)
            elif ch["kind"] == "exam":
                info = self.courses.setdefault(title, {})
                info["fin_date"], info["fin_time"] = ch["exam"]
                info.pop("fin_done", None)
        self.save_tt()
        self.save_courses()
        self.render()
        log("课表 변경 %d개 적용" % len(changes))

    def apply_pku(self, resp):
        """기본으로 체크된 변경을 모두 적용한다 (확인 창 없이)."""
        changes, _ = self.pku_changes(resp)
        self.apply_changes([c for c in changes if c["on"]])

    def screen_rect(self):
        """위젯의 실제 화면 위치 (x, y, 너비, 높이). 바탕화면에 붙어 있으면 winfo_root* 가
        바탕화면 기준 좌표를 돌려줘서 안내창이 왼쪽 위로 가므로 Win32 로 직접 잰다."""
        r = RECT()
        if user32.GetWindowRect(self.hwnd, ctypes.byref(r)) and r.right > r.left:
            return r.left, r.top, r.right - r.left, r.bottom - r.top
        return self.winfo_rootx(), self.winfo_rooty(), self.w(), self.winfo_height()

    def place_dialog(self, top):
        """안내창을 위젯 가운데(조금 위쪽)에 두되 화면 밖으로 나가지 않게. 자리를 잡은 뒤에 보여준다."""
        top.update_idletasks()
        wx, wy, ww, wh = self.screen_rect()
        w, h = top.winfo_reqwidth(), top.winfo_reqheight()
        l, t, r, b = self.work_area()
        x = min(max(wx + (ww - w) // 2, l), r - w)
        y = min(max(wy + max(0, (wh - h) // 3), t), b - h)
        top.geometry("+%d+%d" % (x, y))
        top.deiconify()
        top.lift()
        top.focus_force()
        self.keep_front(top)

    def dialog(self):
        top = tk.Toplevel(self, bg=CARD)
        top.withdraw()                                   # 왼쪽 위에 잠깐 떴다 옮겨지지 않게
        top.title("DeskCal")
        top.attributes("-topmost", True)
        top.transient(self)
        top.resizable(False, False)
        return top

    def notice(self, text):
        """tkmsg.showinfo 대신. 기본 알림은 바탕화면에 붙은 위젯 기준으로 엉뚱한 곳에 뜬다."""
        top = self.dialog()
        pad = self.px(18)
        tk.Label(top, text=text, bg=CARD, fg=FG, font=self.f(12), anchor="w", justify="left",
                 wraplength=self.px(400)).pack(fill="x", padx=pad, pady=(pad, 0))
        bar = tk.Frame(top, bg=CARD)
        bar.pack(fill="x", padx=pad, pady=pad)
        self.button(bar, self.t("ok"), top.destroy, "primary", 11).pack(side="right")
        top.bind("<Return>", lambda e: top.destroy())
        top.bind("<Escape>", lambda e: top.destroy())
        self.place_dialog(top)
        top.grab_set()
        self.wait_window(top)

    def keep_front(self, top):
        """다른 창에 갔다 와도 안내창이 위젯 뒤에 숨지 않게 계속 맨 앞에 둔다."""
        def tick():
            if top.winfo_exists():
                top.lift()
                top.after(400, tick)
        tick()

    def ask_text(self, prompt, initial=""):
        """위젯 위 가운데에 뜨는 입력 창 (기본 askstring 은 작고 엉뚱한 곳에 뜬다)."""
        top = self.dialog()
        pad = self.px(18)
        tk.Label(top, text=prompt, bg=CARD, fg=FG, font=self.f(13), anchor="w", justify="left",
                 wraplength=self.px(380)).pack(fill="x", padx=pad, pady=(pad, self.px(10)))
        var = tk.StringVar(master=top, value=initial)
        ent = tk.Entry(top, textvariable=var, bg=SUNK, fg=FG, insertbackground=FG, relief="flat",
                       font=self.f(15), highlightthickness=1, highlightbackground=LINE,
                       highlightcolor=ACCENT, width=24)
        ent.pack(fill="x", padx=pad, ipady=self.px(6))
        out = []

        def ok(_=None):
            out.append(var.get())
            top.destroy()
        bar = tk.Frame(top, bg=CARD)
        bar.pack(fill="x", padx=pad, pady=pad)
        self.button(bar, self.t("cancel"), top.destroy, "plain", 11).pack(side="right")
        self.button(bar, self.t("ok"), ok, "primary", 11).pack(side="right", padx=(0, self.px(6)))
        ent.bind("<Return>", ok)
        top.bind("<Escape>", lambda e: top.destroy())
        self.place_dialog(top)
        ent.focus_set()
        ent.icursor("end")
        top.grab_set()
        self.wait_window(top)
        return out[0] if out else None

    def review_pku(self, resp):
        """바뀐 점을 보여주고, 체크한 것만 적용한다."""
        changes, skipped = self.pku_changes(resp)
        info = []
        if "list" in resp:
            info.append(self.t("pku_received", n=len(resp.get("list") or [])))
            missing = isop_unscheduled(resp)
            if missing:
                info.append(self.t("pku_unscheduled", n=len(missing), names="、".join(missing)))
        if not changes:
            self.notice("\n\n".join([self.t("pku_up_to_date")] + info))
            return
        if self.view != "tt":
            self.set_view("tt")
        top = self.dialog()
        pad = self.px(16)
        tk.Label(top, text=self.t("pku_review_title", n=len(changes)), bg=CARD, fg=FG,
                 font=self.f(15, True), anchor="w").pack(fill="x", padx=pad, pady=(pad, 0))
        tk.Label(top, text=self.t("pku_review_hint"), bg=CARD, fg=MUTED, font=self.f(11),
                 anchor="w", justify="left").pack(fill="x", padx=pad, pady=(self.px(4), self.px(10)))
        body = tk.Frame(top, bg=CARD)
        body.pack(fill="both", expand=True, padx=pad)
        rows = []
        for ch in changes:
            v = tk.BooleanVar(master=top, value=ch["on"])
            cb = tk.Checkbutton(body, text=ch["text"], variable=v, bg=CARD, fg=FG,
                                activebackground=CARD, activeforeground=FG, selectcolor=SUNK,
                                font=self.f(12), anchor="w", justify="left", cursor="hand2",
                                wraplength=self.px(560), highlightthickness=0, bd=0)
            cb.pack(fill="x", pady=self.px(3))
            rows.append((ch, v))
        if skipped:
            tk.Label(top, text=self.t("pku_skipped", k=skipped).strip(), bg=CARD, fg=DIM,
                     font=self.f(10), anchor="w").pack(fill="x", padx=pad, pady=(self.px(6), 0))
        for line in info:                      # 받은 과목 수 · 시간을 못 읽은 과목
            tk.Label(top, text=line, bg=CARD, fg=DIM, font=self.f(10), anchor="w", justify="left",
                     wraplength=self.px(560)).pack(fill="x", padx=pad, pady=(self.px(6), 0))
        bar = tk.Frame(top, bg=CARD)
        bar.pack(fill="x", padx=pad, pady=pad)

        def set_all(val):
            for _, v in rows:
                v.set(val)

        def apply():
            chosen = [ch for ch, v in rows if v.get()]
            top.destroy()
            self.apply_changes(chosen)
            if chosen:
                self.set_status("pku_applied")
        self.button(bar, self.t("sel_all"), lambda: set_all(True), "plain", 10).pack(side="left")
        self.button(bar, self.t("sel_none"), lambda: set_all(False), "plain", 10
                    ).pack(side="left", padx=(self.px(6), 0))
        self.button(bar, self.t("cancel"), top.destroy, "plain", 11).pack(side="right")
        self.button(bar, self.t("apply_sel"), apply, "primary", 11
                    ).pack(side="right", padx=(0, self.px(6)))
        self.place_dialog(top)
        self._review = top

    def quit_app(self):
        self.tt_commit()
        self.save_conf()
        log("종료 (메뉴)")
        self.destroy()


def already_running():
    global _mutex
    _mutex = kernel32.CreateMutexW(None, False, "DeskCal_single_instance")
    if kernel32.GetLastError() != ERROR_ALREADY_EXISTS:
        return False
    hwnd = user32.FindWindowW(None, WIN_TITLE)
    if hwnd:
        # 사용자가 방금 누른 이 프로그램은 앞 창이 될 권리가 있다. 그 권리를 켜져 있는
        # 위젯에 넘겨줘야 위젯이 스스로 활성 창이 될 수 있다.
        user32.AllowSetForegroundWindow(win_pid(hwnd))
    ev = kernel32.OpenEventW(0x0002, False, SUMMON_EVENT)     # EVENT_MODIFY_STATE
    if ev:
        kernel32.SetEvent(ev)
        kernel32.CloseHandle(ev)
        log("이미 실행 중 - 기존 창을 불러냄")
    return True


def start_stall_watch(app):
    """화면 처리가 4초 넘게 멈추면, 그 순간 어느 코드에 있었는지 로그에 남긴다.
    Windows 가 '응답 없음'으로 강제 종료하기 전에 원인을 잡기 위한 장치다.
    (화면 쪽이 멈춰도 이 감시는 별도 스레드라 계속 돈다)"""
    main_id = threading.main_thread().ident

    def run():
        reported = False
        last = time.time()
        while True:
            time.sleep(1.0)
            # Tk 는 여기서 부르면 안 된다: 다른 스레드의 Tk 호출은 화면 스레드로 넘겨져
            # 처리되므로, 화면이 멈춰 있으면 이 감시까지 같이 멈춘다. 그래서 깃발만 본다.
            if getattr(app, "_destroyed", False):
                return
            now = time.time()
            if now - last > 3:              # 이 스레드도 멈춰 있었다 = 절전에서 깨어남
                app._alive = now
            last = now
            stuck = now - app._alive
            if stuck > 4 and not reported:
                frame = sys._current_frames().get(main_id)
                where = "".join(traceback.format_stack(frame)) if frame else "(알 수 없음)"
                log("화면 처리가 %.0f초째 멈춤 — 지금 실행 중인 코드:\n%s" % (stuck, where))
                reported = True
            elif stuck < 2 and reported:
                log("화면 처리 다시 살아남")
                reported = False
    threading.Thread(target=run, daemon=True, name="stall-watch").start()


if __name__ == "__main__":
    # 파이썬 오류 없이 갑자기 꺼질 때(Tk 내부 충돌 등) 어디서 죽었는지 남긴다
    import faulthandler
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        _crash = open(os.path.join(APP_DIR, "crash.log"), "a", encoding="utf-8")
        _crash.write("--- %s start pid %d\n" % (dt.datetime.now().isoformat(" ", "seconds"), os.getpid()))
        _crash.flush()
        faulthandler.enable(_crash)
    except OSError:
        pass
    DPI_MODE = set_dpi_awareness()
    os.makedirs(APP_DIR, exist_ok=True)
    if already_running():
        sys.exit(0)
    try:
        DeskCal().mainloop()
    except Exception:
        log("치명적 예외:\n" + traceback.format_exc())
        raise
