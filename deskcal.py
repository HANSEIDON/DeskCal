# -*- coding: utf-8 -*-
"""바탕화면에 상시 떠 있는 달력 + 시간표 위젯."""
import calendar
import ctypes
import datetime as dt
import glob
import html
import importlib.util
import json
import os
import queue
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import tkinter as tk
import tkinter.font as tkfont
import tkinter.messagebox as tkmsg
import winreg

__version__ = "1.1.2"
HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN = getattr(sys, "frozen", False)          # PyInstaller 로 묶은 exe 로 실행 중
RES_DIR = getattr(sys, "_MEIPASS", HERE)        # 함께 묶인 파일(글꼴)이 있는 곳


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


def wallpaper_sig():
    """바탕화면 그림이 바뀌었는지 알아보는 값. Windows 추천(Spotlight)·슬라이드쇼는 그림이
    바뀔 때 TranscodedWallpaper 를 새로 쓴다. 알려주는 경로는 늦게 바뀌기도 해서 둘 다 본다."""
    buf = ctypes.create_unicode_buffer(520)
    user32.SystemParametersInfoW(0x0073, 520, buf, 0)       # SPI_GETDESKWALLPAPER
    sig = [buf.value]
    for p in (buf.value, TRANSCODED):
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
        "cal": "달력", "tt": "시간표", "today": "오늘",
        "month_title": "{y}년 {m}월",
        "tt_title": "시간표  ·  이번 주 {wk}",
        "wd_cal": ["일", "월", "화", "수", "목", "금", "토"],
        "wd_tt": ["월", "화", "수", "목", "금"],
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
        "tt_new": "빈 칸이에요. 과목 이름을 적으면 바로 저장돼요.",
        "tt_existing": "고친 내용은 자동으로 저장돼요.",
        "course": "과목", "room": "강의실", "weeks": "주차", "color": "색",
        "course_hint": "예: 고급수학", "room_hint": "예: 一教101",
        "del_class": "이 수업 지우기",
        "saved": "자동 저장됨", "deleted": "지웠어요 · Ctrl+Z로 되돌리기",
        "exams": "시험 · 과제 마감",
        "exams_need_title": "과목 이름을 먼저 적으면 시험·과제 날짜를 넣을 수 있어요.",
        "exam_mid": "期中考试", "exam_fin": "期末考试", "exam_asg": "최종과제",
        "exam_mid_s": "期中", "exam_fin_s": "期末", "exam_asg_s": "과제 DDL",
        "pick_date": "날짜 고르기", "time_hint": "시간·메모", "clear_date": "날짜 지우기",
        "btn_date": "{m}월 {d}일 ({wd})",
        "event_hint": "새 일정을 적고 Enter",
        "tip_done": "클릭: 완료 표시  ·  우클릭: 색 바꾸기",
        "tip_edit": "클릭해서 고치기",
        "tip_exam": "클릭하면 시간표에서 고칠 수 있어요",
        "tip_delete": "지우기 (Ctrl+Z로 되돌리기)",
        "tip_menu": "설정 (언어 · 테마 · 크기 · 주차)",
        "tip_date": "눌러서 달력에서 날짜 고르기",
        "tip_time": "시간(14:00 · 오후 2시 · 2pm) 또는 짧은 메모",
        "tip_color": "새 일정에 쓸 색",
        "size": "크기",
        "sizes": ["아주 작게", "작게", "보통", "크게", "아주 크게"],
        "parity": "주차 (单/双)", "set_odd": "이번 주는 单周", "set_even": "이번 주는 双周",
        "pin_top": "항상 위로 (창에 안 가려짐)",
        "pin_desk": "바탕화면에 두기 (다른 창에 가려짐)",
        "lang": "언어", "theme": "테마", "dark": "다크 모드", "light": "라이트 모드",
        "glass": "배경", "glass_soft": "유리 (은은하게)", "glass_clear": "유리 (선명하게)",
        "glass_off": "단색", "now": "지금", "next": "다음",
        "autostart": "윈도우 시작 시 실행",
        "pku_import": "북대 门户에서 시간표 가져오기",
        "pku_login_title": "북대 门户 로그인 — 로그인하면 시간표를 가져와요",
        "pku_waiting": "열린 창에서 로그인해 주세요 (계속 로딩만 되면 VPN을 끄고 다시 시도)",
        "pku_done": "{n}개 과목 · {c}칸을 가져왔어요{extra}\n색·이름은 지금처럼 고칠 수 있고, Ctrl+Z로 되돌릴 수 있어요.",
        "pku_skipped": "\n(주말·겹친 수업 {k}개는 넣지 않았어요)",
        "pku_empty": "가져올 수업을 찾지 못했어요.",
        "pku_failed": "로그인 창이 닫혀서 가져오지 못했어요.",
        "pku_need_webview": "로그인 창을 띄우려면 먼저 설치가 필요해요:\n\npip install pywebview",
        "open_data": "데이터 폴더 열기", "quit": "종료",
    },
    "en": {
        "lang_name": "English",
        "cal": "Calendar", "tt": "Timetable", "today": "Today",
        "month_title": "{month} {y}",
        "tt_title": "Timetable  ·  {wk}",
        "wd_cal": ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        "wd_tt": ["Mon", "Tue", "Wed", "Thu", "Fri"],
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
        "tt_new": "Empty slot. Type a course name and it saves automatically.",
        "tt_existing": "Changes save automatically.",
        "course": "Course", "room": "Room", "weeks": "Weeks", "color": "Color",
        "course_hint": "e.g. Calculus", "room_hint": "e.g. Room 101",
        "del_class": "Remove this class",
        "saved": "Saved", "deleted": "Removed · Ctrl+Z to undo",
        "exams": "Exams · Deadlines",
        "exams_need_title": "Enter a course name first to add exam and deadline dates.",
        "exam_mid": "Midterm", "exam_fin": "Final exam", "exam_asg": "Final project",
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
        "tip_time": "A time (14:00 · 2pm) or a short note",
        "tip_color": "Color for new events",
        "size": "Size",
        "sizes": ["Tiny", "Small", "Medium", "Large", "Huge"],
        "parity": "Odd / even week", "set_odd": "This week is odd",
        "set_even": "This week is even",
        "pin_top": "Always on top",
        "pin_desk": "Keep on desktop (behind windows)",
        "lang": "Language", "theme": "Theme", "dark": "Dark", "light": "Light",
        "glass": "Background", "glass_soft": "Glass (subtle)", "glass_clear": "Glass (clear)",
        "glass_off": "Solid", "now": "Now", "next": "Next",
        "autostart": "Start with Windows",
        "pku_import": "Import timetable from PKU portal",
        "pku_login_title": "PKU portal sign-in — your timetable is imported after you sign in",
        "pku_waiting": "Sign in in the new window (if it keeps loading, turn off your VPN and retry)",
        "pku_done": "Imported {n} courses, {c} periods.{extra}\nYou can still edit colors and names. Ctrl+Z undoes the import.",
        "pku_skipped": "\n({k} weekend or overlapping classes were left out.)",
        "pku_empty": "No classes were found.",
        "pku_failed": "The sign-in window was closed before the timetable was imported.",
        "pku_need_webview": "The sign-in window needs pywebview. Install it first:\n\npip install pywebview",
        "open_data": "Open data folder", "quit": "Quit",
    },
    "zh": {
        "lang_name": "中文",
        "cal": "日历", "tt": "课表", "today": "今天",
        "month_title": "{y}年{m}月",
        "tt_title": "课表  ·  本周{wk}",
        "wd_cal": ["日", "一", "二", "三", "四", "五", "六"],
        "wd_tt": ["周一", "周二", "周三", "周四", "周五"],
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
        "tt_new": "空课时。输入课程名称即可自动保存。",
        "tt_existing": "修改会自动保存。",
        "course": "课程", "room": "教室", "weeks": "周次", "color": "颜色",
        "course_hint": "例：高等数学", "room_hint": "例：一教101",
        "del_class": "删除这节课",
        "saved": "已自动保存", "deleted": "已删除 · Ctrl+Z 撤销",
        "exams": "考试 · 作业截止",
        "exams_need_title": "先输入课程名称，才能添加考试和截止日期。",
        "exam_mid": "期中考试", "exam_fin": "期末考试", "exam_asg": "期末大作业",
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
        "tip_time": "时间（14:00 · 下午2点 · 2pm）或简短备注",
        "tip_color": "新日程的颜色",
        "size": "大小",
        "sizes": ["很小", "小", "中", "大", "很大"],
        "parity": "单双周", "set_odd": "本周是单周", "set_even": "本周是双周",
        "pin_top": "始终置顶",
        "pin_desk": "放在桌面（会被其他窗口遮住）",
        "lang": "语言", "theme": "主题", "dark": "深色模式", "light": "浅色模式",
        "glass": "背景", "glass_soft": "毛玻璃（柔和）", "glass_clear": "毛玻璃（清透）",
        "glass_off": "纯色", "now": "现在", "next": "下节",
        "autostart": "开机自动启动",
        "pku_import": "从北大门户导入课表",
        "pku_login_title": "登录北大门户 — 登录后自动导入课表",
        "pku_waiting": "请在弹出的窗口中登录（一直加载的话，请关闭 VPN 后重试）",
        "pku_done": "已导入 {n} 门课、{c} 节。{extra}\n颜色和名称仍可修改，Ctrl+Z 可撤销导入。",
        "pku_skipped": "\n（周末或时间冲突的 {k} 门课未导入）",
        "pku_empty": "没有找到课程。",
        "pku_failed": "登录窗口已关闭，未能导入课表。",
        "pku_need_webview": "需要先安装 pywebview 才能打开登录窗口：\n\npip install pywebview",
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
SWP_KEEP = 0x0001 | 0x0002 | 0x0010     # NOSIZE | NOMOVE | NOACTIVATE
SWP_SHOW = 0x0001 | 0x0002 | 0x0040     # NOSIZE | NOMOVE | SHOWWINDOW
SW_SHOWNOACTIVATE = 4
ERROR_ALREADY_EXISTS = 183
MONITOR_NEAREST = 2
DESK_CLASSES = ("Progman", "WorkerW")   # 바탕화면(아이콘·배경)을 그리는 창


def win_class(h):
    b = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(h, b, 64)
    return b.value


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


# ---------- 북대 门户 课表 가져오기 ----------
# 门户 课表 페이지(publicQuery/#/myCourseTable)는 로그인한 뒤 아래 두 주소에서 JSON 을
# 받아 그린다. course[i] 가 (i+1)교시 줄이고 mon..sun 의 courseName 이 칸의 HTML 이다:
#   과목명(主)<br>上课信息：1-16周 每周 三教305  教师：…  备注：…<br>考试信息：20261230 星期三 下午
PKU_PAGE = "https://portal.pku.edu.cn/publicQuery/#/myCourseTable"
# 课表 페이지(publicQuery)는 门户와 따로 로그인한다. 로그인 전에 열면 로딩만 하므로,
# 통합 로그인(IAAA)에서 publicQuery 용으로 로그인하고 publicQuery/ssoLogin.do 로 돌아온다.
PKU_LOGIN = ("https://iaaa.pku.edu.cn/iaaa/oauth.jsp?appID=portalPublicQuery&appName="
             "%E5%8C%97%E4%BA%AC%E5%A4%A7%E5%AD%A6%E6%A0%A1%E5%86%85%E4%BF%A1%E6%81%AF"
             "%E9%97%A8%E6%88%B7&redirectUrl=https%3A%2F%2Fportal.pku.edu.cn%2FpublicQuery"
             "%2FssoLogin.do%3FmoduleID%3DmyCourseTable")
# 페이지를 멈추지 않게 비동기로 받아 window.__dc 에 둔다 (null=받는 중, ''=실패).
PKU_FETCH_JS = r"""(function(){
 if(window.__dcBusy) return 'busy'; window.__dcBusy=1; window.__dc=null;
 var base='/publicQuery/ctrl/topic/myCourseTable/', o={credentials:'same-origin'};
 fetch(base+'getXndXqList.do',o).then(function(r){return r.json();}).then(function(a){
   if(!a.success) throw 0; var x=a.nowXnxq.xndxq;
   return fetch(base+'getCourseInfo.do?xndxq='+encodeURIComponent(x),o)
     .then(function(r){return r.json();}).then(function(b){
       if(!b.success) throw 0; b.xndxq=x; window.__dc=JSON.stringify(b);});
 }).catch(function(){window.__dc='';}).then(function(){window.__dcBusy=0;});
 return 'started';})()"""
PKU_READY_JS = ("location.host=='portal.pku.edu.cn' && location.pathname.indexOf('/publicQuery/')==0"
                " && location.pathname.indexOf('login.jsp')<0 && document.readyState=='complete'")
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


def parse_pku_table(resp):
    """getCourseInfo.do 응답 → ({(요일, 교시): [과목…]}, 시간표에 못 넣은 수업 수(주말))."""
    slots, weekend = {}, 0
    for i, row in enumerate((resp or {}).get("course") or [], 1):
        for di, key in enumerate(PKU_DAYS):
            got = parse_pku_cell((row.get(key) or {}).get("courseName"))
            if got and i <= PERIODS:
                slots[(di, i)] = got
        for key in ("sat", "sun"):
            weekend += len(parse_pku_cell((row.get(key) or {}).get("courseName")))
    return slots, weekend


def pku_login(out_path, lang="en"):
    """(별도 프로세스) 门户 로그인 창을 띄우고, 로그인되면 课表 JSON 을 out_path 에 쓴다.
    비밀번호는 북대 로그인 페이지에 사용자가 직접 넣는다. 이 코드는 보지 않는다.
    쿠키는 남기지 않는다(private_mode)."""
    import webview
    win = webview.create_window(TEXT.get(lang, TEXT["en"])["pku_login_title"], PKU_LOGIN,
                                width=1100, height=800)

    def work():
        last = None
        end = time.time() + 900                       # 15분 안에 로그인하지 않으면 닫는다
        while time.time() < end:
            time.sleep(1.5)
            try:
                where = win.evaluate_js("location.host + location.pathname.split(';')[0]")
                if where != last:                     # 어디까지 왔는지 (세션 ID·토큰은 남기지 않음)
                    log("门户 로그인 창: %s" % where)
                    last = where
                if not win.evaluate_js(PKU_READY_JS):
                    continue                          # 아직 로그인 중이거나 페이지를 읽는 중
                result = win.evaluate_js("window.__dc")
                if result is None:
                    win.evaluate_js(PKU_FETCH_JS)     # 받기 시작 (이미 받는 중이면 무시)
                    continue
            except Exception:
                return                                # 사용자가 창을 닫았다
            if result:
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(result)
                win.destroy()
                return
            win.evaluate_js("window.__dc=null")       # 실패: 잠시 뒤 다시
        win.destroy()
    webview.start(work, private_mode=True)
    return 0 if os.path.exists(out_path) else 2


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


class DeskCal(tk.Tk):
    def __init__(self):
        super().__init__()
        global FONT
        load_private_fonts()

        self.events, self.data_ok = load_json(DATA_FILE, {})
        self.tt, self.tt_ok = load_json(TT_FILE, {})
        self.courses, self.cs_ok = load_json(COURSE_FILE, {})
        self.conf, _ = load_json(CONF_FILE, {})
        self.normalize_exam_dates()
        self.lang = self.conf.get("lang") if self.conf.get("lang") in TEXT else "en"
        FONT = pick_font(self, self.lang)
        self.theme = self.conf.get("theme") if self.conf.get("theme") in THEMES else "dark"
        apply_theme(self.theme)
        self.view = self.conf.get("view", "cal")
        self.tt_sel = (0, 1)
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
        self.float_mode = "--float" in sys.argv
        self.pinned = False if self.float_mode else self.conf.get("pinned", True)
        self.undo_stack = []
        self._fonts = {}
        self._drag = None
        self.shell = None
        self.beats = 0
        # 창의 겹침 상태: startup(켠 직후 앞에 보임) / active(내가 앞) /
        # bottom(바탕화면 바로 위) / showdesk('바탕화면 보기' 중이라 바탕화면 위로 올림)
        self._z = "startup"
        self._fg_start = None
        self._topmost = False
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
        self._jobs = {"z": self.after(300, self.z_tick),
                      "dog": self.after(60000, self.watchdog),
                      "clock": self.after(30000, self.clock_tick),
                      "wall": self.after(5000, self.wall_tick),
                      # 로그온 직후엔 Windows 가 바탕화면 그림을 조금 늦게 바꾼다. 한 번 더 본다.
                      "glass15": self.after(15000, self.refresh_glass),
                      "glass60": self.after(60000, self.refresh_glass)}
        start_stall_watch(self)
        if not self.float_mode:
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

    def is_odd_week(self, d):
        return ((self.monday_of(d) - self.anchor()).days // 7) % 2 == 0

    def week_label(self, d):
        return self.t("odd") if self.is_odd_week(d) else self.t("even")

    def set_week_kind(self, odd):
        """이번 주를 单周(또는 双周)로 다시 지정한다."""
        m = self.monday_of(self.today)
        self.conf["week_anchor"] = (m if odd else m - dt.timedelta(days=7)).isoformat()
        self.save_conf()
        self.render()

    # ---------- 크기 · 글꼴 ----------
    # 폰트는 반드시 음수(=픽셀)로 준다. 양수는 '포인트'라서 화면 배율이 150% 면
    # Tk 가 1.5배로 키우는데, 여백과 칸 높이는 픽셀이라 글자만 넘쳐 겹친다.

    def w(self):
        # 프리셋은 100% 배율 기준. 화면 배율만큼 키워야 어느 모니터에서든
        # 눈에 보이는 크기가 같다.
        return int(SIZES[self.size_idx][0] * self.dpi)

    def h(self):
        return int(SIZES[self.size_idx][1] * self.dpi)

    def u(self):
        return self.w() / 780.0

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

    def set_size(self, idx):
        self.size_idx = min(max(idx, 0), len(SIZES) - 1)
        self.conf["size"] = self.size_idx
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

    def raise_above_desktop(self, desk):
        user32.SetWindowPos(self.hwnd, HWND_TOP, 0, 0, 0, 0, SWP_KEEP)
        if self.is_below(desk):          # 바탕화면이 더 높은 층에 있으면 맨 위 층으로
            user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_KEEP)
            self._topmost = True
        self._z = "showdesk"
        log("바탕화면 보기 감지 - 바탕화면 위로 올림%s" % (" (맨 위 층)" if self._topmost else ""))

    def lower_to_desktop(self):
        if self._z == "showdesk":
            log("바탕화면 보기 끝 - 원래 자리로")
        if self._topmost:
            user32.SetWindowPos(self.hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_KEEP)
            self._topmost = False
        user32.SetWindowPos(self.hwnd, HWND_BOTTOM, 0, 0, 0, 0, SWP_KEEP)
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
        if not fg:
            return
        desk = win_class(fg) in DESK_CLASSES
        if self._z == "showdesk":
            # 바탕화면 보기 중에는 바탕화면이나 위젯을 만지는 동안 그대로 둔다.
            # (위젯을 눌렀다가 바탕화면을 누르면 내려가서 다시 사라지던 문제)
            if not desk and not self.owns(fg):
                self.lower_to_desktop()        # 다른 창으로 돌아감 = 바탕화면 보기 끝
            return
        if self.owns(fg):                      # 위젯을 쓰는 중
            self._z = "active"
            return
        if self._z in ("startup", "summoned"):   # 켜거나 불러낸 직후엔 앞에 둔다
            if self._fg_start is None:
                self._fg_start = fg
            # 불러낸 뒤 2초 안의 앞 창 변화는 시작 메뉴가 닫히는 등 저절로 생긴 것이다
            if fg == self._fg_start or time.time() - self._summon_t < 2.0:
                self._fg_start = fg
                return
        if desk and self.is_below(fg):         # 바탕화면이 나를 덮었다 = 바탕화면 보기
            self.raise_above_desktop(fg)
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
            if not user32.IsWindowVisible(self.hwnd):
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
        self._jobs["z"] = self.after(300, self.z_tick)

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
                self.draw_tt()                         # '지금 수업' 표시를 옮긴다
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
            if sig != self._glass_sig:
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

    def build(self):
        if self._drag:
            return                            # 드래그 중에는 캔버스를 재생성하지 않는다
        if self.shell:
            self.tt_commit()                   # 크기·언어·테마를 바꿔도 적던 건 저장
            self.close_picker()
            self.hide_tip()
            self.shell.destroy()
        W, H = self.w(), self.h()
        self.geometry("%dx%d" % (W, H))
        self.make_background()
        self.configure(bg=BG)

        # 창 전체가 캔버스 한 장이다. 위젯은 배경이 불투명해 유리 위에 올리면 네모난
        # 자국이 생기므로, 유리 위에 보이는 머리줄과 달력은 캔버스에 직접 그린다.
        c = self.shell = self.base = tk.Canvas(self, width=W, height=H, bg=BG,
                                              highlightthickness=0, bd=0)
        c.pack(fill="both", expand=True)
        if self.glass_img:
            c.create_image(0, 0, image=self.glass_img, anchor="nw", tags="glass")
        c.create_rectangle(0, 0, W - 1, H - 1, outline=mix(BG, FG, 0.16))

        x0, y0, x1, y1 = self.card_box           # 오른쪽 패널 = 유리 위의 카드
        round_rect(c, x0, y0, x1, y1, self.px(18), fill=CARD, outline=mix(CARD, FG, 0.10))
        px0, py0, px1, py1 = self.panel_box
        self.panel = tk.Frame(c, bg=CARD, width=px1 - px0, height=py1 - py0)
        self.panel.pack_propagate(False)
        c.create_window(px0, py0, window=self.panel, anchor="nw")

        cx0, cy0, cx1, cy1 = self.cal_box        # 달력·시간표 = 유리 위에 바로
        self.cal = tk.Canvas(c, bg=BG, highlightthickness=0, bd=0,
                             width=cx1 - cx0, height=cy1 - cy0)
        c.create_window(cx0, cy0, window=self.cal, anchor="nw")
        self.cal.bind("<Configure>", lambda _: self.draw())
        self.cal.bind("<Button-1>", self.on_click)
        self.cal.bind("<Button-3>", self.menu)

        c.bind("<ButtonPress-1>", self.drag_start)
        c.bind("<B1-Motion>", self.drag_move)
        c.bind("<ButtonRelease-1>", self.drag_end)
        c.bind("<Button-3>", self.menu)
        self.draw_header()
        self.render()
        self.schedule_desk(1500)

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
        idle = SEL_BG if active else mix(BG, FG, 0.10)
        hover = SEL_BG if active else mix(BG, FG, 0.18)
        round_rect(c, x0, cy - h / 2, x1, cy + h / 2, h / 2, fill=idle, outline="",
                   tags=("head", "btn", tag, tag + "_bg"))
        c.create_text((x0 + x1) / 2, cy, text=label, font=fnt,
                      fill=FG if active else MUTED, tags=("head", "btn", tag))
        c.tag_bind(tag, "<Button-1>", lambda e: cmd(e))
        c.tag_bind(tag, "<Enter>", lambda e: (c.itemconfig(tag + "_bg", fill=hover),
                                              c.config(cursor="hand2")))
        c.tag_bind(tag, "<Leave>", lambda e: (c.itemconfig(tag + "_bg", fill=idle),
                                              c.config(cursor="")))
        if tip:
            self.tip_canvas(c, tag, tip)
        return x0

    def draw_header(self):
        c = self.base
        c.delete("head")
        W, cy = self.w(), self.head_h * 0.52
        gap = self.px(8)
        c.create_text(self.pad + self.px(4), cy, anchor="w", text="", fill=FG,
                      font=self.f(21, True), tags=("head", "title"))
        x = self.head_button("b_menu", W - self.pad, cy, "≡", self.menu, size=15,
                             tip=self.t("tip_menu"))
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
        self.view = key
        self.conf["view"] = key
        self.build()
        self.save_conf()

    def draw(self):
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
        if self.view == "tt":
            self.set_title(self.t("tt_title", wk=self.week_label(self.today)))
        else:
            self.set_title(self.month_title(self.shown))
        self.draw()
        self.render_panel()

    # ---------- 달력 ----------

    def dot_color(self, col):
        col = pc(col)
        return col if THEME == "dark" else mix(col, "#000000", 0.18)

    def draw_grid(self):
        c = self.cal
        W, H = c.winfo_width(), c.winfo_height()
        if W < 40 or H < 40:
            # 아직 크기가 잡히지 않은 캔버스는 지우지 않는다 (지우면 유리가 사라진다)
            return
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

        for i, d in enumerate(self.t("wd_cal")):
            c.create_text(self.gut + (i + 0.5) * self.cw, self.hh * 0.42, text=d,
                          fill=SUN if i == 0 else SAT if i == 6 else MUTED,
                          font=(FONT, -f_hdr))
        c.create_line(self.gut + pad, self.hh - 1, W - pad, self.hh - 1, fill=GRID)

        for ri, week in enumerate(self.weeks):
            # 그 주가 单周인지 双周인지 왼쪽에 표시 (주 계산은 월요일 기준)
            odd = self.is_odd_week(week[1])
            c.create_text(self.gut * 0.5, self.hh + ri * self.ch + pad * 0.7 + f_day * 0.7,
                          text=self.t("odd_s") if odd else self.t("even_s"),
                          fill=MUTED if odd else DIM,
                          font=(FONT, -max(9, int(f_hdr * 0.9))))
            for ci, day in enumerate(week):
                x0, y0 = self.gut + ci * self.cw, self.hh + ri * self.ch
                x1 = x0 + self.cw
                # 칸 전체를 칠하면 세로로 긴 막대가 되므로 높이를 제한한다
                yb = y0 + min(self.ch - 3, unit * 1.12)
                if day == self.selected:
                    round_rect(c, x0 + 3, y0 + 3, x1 - 3, yb, rad, fill=SEL_BG, outline="")
                ny = y0 + pad * 0.7 + f_day * 0.7          # 숫자의 세로 중심
                if day == self.today:                     # 오늘은 강조색 동그라미
                    tw = self.measure(str(day.day), f_day, True)
                    cx, rr = x0 + pad + tw / 2.0, f_day * 0.86
                    c.create_oval(cx - rr, ny - rr, cx + rr, ny + rr, fill=ACCENT, outline="")
                    c.create_text(cx, ny, text=str(day.day), fill=ACCENT_INK,
                                  font=(FONT, -f_day, "bold"))
                else:
                    fg = (DIM if day.month != self.shown.month else
                          SUN if ci == 0 else SAT if ci == 6 else FG)
                    c.create_text(x0 + pad, ny, text=str(day.day), fill=fg, anchor="w",
                                  font=(FONT, -f_day))
                colors, done_only = [], True
                for it in self.events.get(key_of(day), []):
                    col = self.dot_color(it.get("color", PALETTE[0]))
                    if not it.get("done"):
                        done_only = False
                        if col not in colors:
                            colors.append(col)
                cy = min(ny + f_day * 1.25 + r, yb - r - 3)
                # 시험·과제 마감은 네모, 일정은 동그라미 (시험이 먼저)
                exams = []
                for _, title, _ in self.exams_on(day):
                    col = self.dot_color(self.course_color(title))
                    if col not in exams:
                        exams.append(col)
                marks = [("sq", col) for col in exams] + [("dot", col) for col in colors]
                for k, (shape, col) in enumerate(marks[:4]):
                    cx = x0 + pad + r + k * (r * 2 + self.px(4))
                    if cx + r >= x1 - 3:
                        break
                    if shape == "sq":
                        c.create_rectangle(cx - r, cy - r, cx + r, cy + r, fill=col, outline="")
                    else:
                        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=col, outline="")
                if done_only and self.events.get(key_of(day)) and not exams:
                    cx = x0 + pad + r            # 그 날 할 일을 다 끝냄
                    c.create_oval(cx - r, cy - r, cx + r, cy + r, fill="", outline=DIM)

    def on_grid_click(self, e):
        if not getattr(self, "weeks", None) or e.y < self.hh or e.x < self.gut:
            return
        ci = int((e.x - self.gut) // self.cw)
        ri = int((e.y - self.hh) // self.ch)
        if 0 <= ri < len(self.weeks) and 0 <= ci < 7:
            self.select(self.weeks[ri][ci])

    def select(self, day):
        self.selected = day
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

    def tt_blocks(self):
        """세로로 붙어 있는 같은 수업을 (요일, 시작교시, 칸수, 내용) 으로 묶는다."""
        def same(a, b):
            return all(a.get(k) == b.get(k) for k in ("title", "room", "color")) \
                and a.get("week", "all") == b.get("week", "all")

        out = []
        for di in range(N_DAYS):
            p = 1
            while p <= PERIODS:
                it = self.tt.get(self.tt_key(di, p))
                if not it:
                    p += 1
                    continue
                span = 1
                while p + span <= PERIODS:
                    nxt = self.tt.get(self.tt_key(di, p + span))
                    if not nxt or not same(nxt, it):
                        break
                    span += 1
                out.append((di, p, span, it))
                p += span
        return out

    def period_state(self, now=None):
        """('now', 교시, 진행비율) / ('next', 교시, 0) / None. 주말이면 None."""
        now = now or dt.datetime.now()
        if now.weekday() >= N_DAYS:
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
        c = self.cal
        W, H = c.winfo_width(), c.winfo_height()
        if W < 40 or H < 40:
            return
        c.delete("all")
        self.glass_under(c, self.cal_box[0], self.cal_box[1])
        odd_now = self.is_odd_week(self.today)
        self.tgut = max(28.0, W * 0.10)           # 교시 번호 + 시작 시각
        self.thh = max(18.0, H * 0.06)            # 요일 머리글
        self.tcw = (W - self.tgut) / float(N_DAYS)
        self.tch = (H - self.thh) / float(PERIODS)
        f_hdr = max(9, int(min(self.thh * 0.52, self.tcw * 0.20)))
        f_num = max(8, int(min(self.tch * 0.34, self.tgut * 0.30)))
        f_tm = max(7, int(f_num * 0.64))
        rad = max(4, int(min(self.tcw, self.tch) * 0.16))
        today_col = self.today.weekday()
        state = self.period_state()
        cur_p = state[1] if state and state[0] == "now" else None

        for i, d in enumerate(self.t("wd_tt")):
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
        if state and state[0] == "now" and 0 <= today_col < N_DAYS:
            y = self.thh + (state[1] - 1 + state[2]) * self.tch
            lx0 = self.tgut + today_col * self.tcw
            c.create_line(lx0 + 2, y, lx0 + self.tcw - 2, y, fill=ACCENT, width=2)

        # 세로로 이어진 같은 수업은 한 블록으로 묶어 글자를 한 번만 그린다.
        pad = self.px(3)
        f_ttl = max(10, int(min(self.tch * 0.32, self.tcw * 0.15)))
        f_sub = max(9, int(f_ttl * 0.82))
        boxes, now_boxes = {}, {}
        for di, p, span, it in self.tt_blocks():
            kind = it.get("week", "all")
            now_on = kind == "all" or (kind == "odd") == odd_now
            col = pc(it.get("color", PALETTE[4]))
            x0 = self.tgut + di * self.tcw + pad
            y0 = self.thh + (p - 1) * self.tch + pad
            x1 = self.tgut + (di + 1) * self.tcw - pad
            y1 = self.thh + (p - 1 + span) * self.tch - pad
            if now_on:
                fill, edge, ink, sub = self.block_colors(col)
                round_rect(c, x0, y0, x1, y1, rad, fill=fill, outline=edge,
                           width=max(1, self.px(1.5)))
                for p2 in range(p, p + span):
                    now_boxes[(di, p2)] = (x0, y0, x1, y1)
            else:
                round_rect(c, x0, y0, x1, y1, rad, fill="", outline=mix(col, BG, 0.3),
                           dash=(3, 3))
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
            if extra and (y1 - y0) > lh * (len(lines) + 0.9) + self.px(6):
                lines.append((self.fit(extra, f_sub, inner, False), f_sub, sub, False))
            top = (y0 + y1) / 2 - (len(lines) - 1) * lh / 2
            for i, (txt, size, fill_c, bold) in enumerate(lines):
                c.create_text((tx0 + x1) / 2, top + i * lh, text=txt, fill=fill_c,
                              font=(FONT, -size, "bold") if bold else (FONT, -size))

        di, p = self.tt_sel                     # 고른 칸 (수업이면 그 블록 전체)
        sx0, sy0, sx1, sy1 = boxes.get((di, p)) or (
            self.tgut + di * self.tcw + pad, self.thh + (p - 1) * self.tch + pad,
            self.tgut + (di + 1) * self.tcw - pad, self.thh + p * self.tch - pad)
        round_rect(c, sx0 + 2, sy0 + 2, sx1 - 2, sy1 - 2, max(2, rad - 2), fill="",
                   outline=mix(FG, BG, 0.30), width=2)

        # 지금 수업 (쉬는 시간이면 다음 수업)
        if state and 0 <= today_col < N_DAYS:
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
                c.create_oval(lx0 - 4, y - 4, lx0 + 4, y + 4, fill=ACCENT, outline="")
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

    def on_tt_click(self, e):
        if not hasattr(self, "tcw") or e.x < self.tgut or e.y < self.thh:
            return
        di = int((e.x - self.tgut) // self.tcw)
        p = int((e.y - self.thh) // self.tch) + 1
        if 0 <= di < N_DAYS and 1 <= p <= PERIODS:
            self.tt_commit()                   # 다른 칸으로 옮기기 전에 적던 걸 저장
            self.tt_sel = (di, p)
            self.draw_tt()
            self.render_panel()
            if not self.tt.get(self.tt_key(di, p)):
                self.tt_title.focus_set()      # 빈 칸이면 바로 타이핑할 수 있게

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
        it = self.tt.get(self.tt_key(di, p), {})
        draft = self._draft if (self._draft and self._draft.get("cell") == self.tt_sel) else None
        self._draft = None
        pw = self.panel_w

        top = tk.Frame(self.panel, bg=CARD)
        top.pack(fill="x")
        tk.Label(top, text=self.t("tt_cell", wd=self.t("wd")[di], p=p), bg=CARD, fg=FG,
                 font=self.f(16, True)).pack(side="left")
        tk.Label(top, text=self.period_text(p), bg=CARD,
                 fg=MUTED, font=self.f(10)).pack(side="right")
        tk.Label(self.panel, text=self.t("tt_existing" if it else "tt_new"), bg=CARD,
                 fg=MUTED, font=self.f(11), anchor="w", justify="left",
                 wraplength=pw - self.px(4)).pack(fill="x", pady=(self.px(4), self.px(12)))
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
        self.tt_title.insert(0, draft["title"] if draft else it.get("title", ""))
        self.tt_title.grid(row=0, column=1, sticky="ew", ipady=self.px(6), pady=self.px(3))
        self.field_label(form, self.t("room"), 1)
        self.tt_room = self.hint_entry(form, 13, self.t("room_hint"))
        self.tt_room.insert(0, draft["room"] if draft else it.get("room", ""))
        self.tt_room.grid(row=1, column=1, sticky="ew", ipady=self.px(6), pady=self.px(3))
        for w in (self.tt_title, self.tt_room):
            w.bind("<Return>", lambda _: self.tt_commit())
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
        self.field_label(form, self.t("color"), 3)
        self.tt_color = pc(it.get("color", getattr(self, "tt_color", PALETTE[4])))
        self.swatches(form, self.tt_color, self.tt_set_color).grid(row=3, column=1,
                                                                    sticky="w")

        # 저장 상태 + 지우기
        act = tk.Frame(self.panel, bg=CARD)
        act.pack(fill="x", pady=(self.px(10), 0))
        self.status_lbl = tk.Label(act, text="", bg=CARD, fg=OK, font=self.f(10))
        self.status_lbl.pack(side="left")
        self.del_btn = self.button(act, self.t("del_class"), self.tt_delete, "danger", 10)
        if it:
            self.del_btn.pack(side="right")

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
        self.button(self.panel, self.t("pku_import"), self.import_pku, "plain", 10
                    ).pack(side="bottom", anchor="w", pady=(self.px(10), 0))

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
            te.insert(0, tm)
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
            info = self.courses.get(title, {})
            new_vals = {k: (info.get(k + "_date", ""), info.get(k + "_time", ""))
                        for k in EXAM_KEYS}
            changed = new_vals != self.exam_values()
            self.exam_vals = {k: list(v) for k, v in new_vals.items()}
            self._exam_loaded = (title, new_vals)
        # 한 글자 칠 때마다 다시 그리지 않는다: 값이 바뀌었거나, 과목명이
        # 생기거나 없어져서 칸을 열고 닫아야 할 때만.
        if changed or bool(title) != had_exams:
            self.build_exams()

    def tt_draft(self):
        """패널을 다시 그려도 적던 내용이 살아남도록 지금 값을 담아 둔다."""
        try:
            d = {"cell": self.tt_sel, "title": self.tt_title.get(),
                 "room": self.tt_room.get()}
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
            raw = te.get().strip()
            tm = parse_time(raw)
            if tm and raw != tm:
                te.delete(0, "end")
                te.insert(0, tm)                # 14시 → 14:00
            self.exam_vals[k][1] = tm if tm is not None else raw
        key = self.tt_key(*self.tt_sel)
        old = self.tt.get(key)
        new = ({"title": title, "room": room, "color": self.tt_color, "week": self.tt_week}
               if title else None)
        # 빠진 항목은 기본값으로 채워 비교한다. 안 그러면 아무것도 안 고쳐도
        # 저장할 때마다 '바뀜'이 돼 되돌리기 기록이 쌓인다.
        cell_changed = new != (dict({"room": "", "week": "all"}, **old) if old else None)
        vals = self.exam_values()
        exam_changed = bool(title) and vals != self._exam_loaded[1]
        if not cell_changed and not exam_changed:
            return False
        self.push_undo()
        if cell_changed:
            if new:
                self.tt[key] = new
            else:
                self.tt.pop(key, None)
            self.save_tt()
        if exam_changed:
            info = {}
            for k, (dv, tv) in vals.items():
                if dv:
                    info[k + "_date"], info[k + "_time"] = dv, tv
            if info:
                self.courses[title] = info
            else:
                self.courses.pop(title, None)
            self.save_courses()
            self._exam_loaded = (title, vals)
        self.draw_tt()
        if self.tt.get(key):
            self.del_btn.pack(side="right")
        else:
            self.del_btn.pack_forget()
        self.set_status("saved")
        return True

    def tt_set_week(self, kind):
        self.tt_commit()
        self._draft = self.tt_draft()
        self.tt_week = kind
        it = self.tt.get(self.tt_key(*self.tt_sel))
        if it and it.get("week") != kind:
            self.push_undo()
            it["week"] = kind
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
        it = self.tt.get(self.tt_key(*self.tt_sel))
        if it and pc(it.get("color")) != col:
            self.push_undo()
            it["color"] = col
            self.save_tt()
            self.draw_tt()
        self.render_panel()
        if it:
            self.set_status("saved")

    def dday_text(self, s):
        d = parse_date(s) if isinstance(s, str) else s
        if not d:
            return ""
        n = (d - self.today).days
        return self.t("dday_today") if n == 0 else ("D-%d" % n if n > 0 else self.t("dday_past"))

    def tt_delete(self):
        if not self.tt.get(self.tt_key(*self.tt_sel)):
            return
        self.push_undo()
        self.tt.pop(self.tt_key(*self.tt_sel), None)
        self.save_tt()
        self.render()
        self.set_status("deleted")

    # ---------- 일정 패널 ----------

    def render_panel(self):
        self.close_picker()
        self.hide_tip()
        self._editing = False
        for wgt in self.panel.winfo_children():
            wgt.destroy()
        if self.view == "tt":
            self.panel_tt()
            return
        d = self.selected
        tk.Label(self.panel, bg=CARD, fg=FG, font=self.f(16, True), anchor="w",
                 text=self.t("day_title", m=d.month, d=d.day, wd=self.t("wd")[d.weekday()],
                             mon=MONTHS_EN[d.month - 1][:3])).pack(fill="x")
        n = (d - self.today).days
        tk.Label(self.panel, bg=CARD, fg=MUTED, font=self.f(11), anchor="w",
                 text=self.t("dday_today") if n == 0 else
                 ("D%+d" % -n if n < 0 else "D-%d" % n)
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
        if not items and not exams:
            tk.Label(self.panel, text=self.t("no_events"), bg=CARD, fg=DIM,
                     font=self.f(12), anchor="w").pack(fill="x", pady=(0, self.px(4)))
        for i, it in enumerate(items):
            self.make_row(i, it)
        self.make_form()
        self.make_upcoming()

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
        for key in sorted(self.tt):
            if self.tt[key].get("title") == title:
                return pc(self.tt[key].get("color"))
        return URGENT

    def goto_course(self, title):
        """시간표로 넘어가 그 과목의 첫 칸을 고른다 (시험 날짜는 거기서 고친다)."""
        cells = sorted((int(a), int(b)) for a, b in
                       (key.split("-") for key, it in self.tt.items()
                        if it.get("title") == title))
        if cells:
            self.tt_sel = cells[0]
        self.set_view("tt")

    def make_exam_row(self, kind, title, tm):
        row = tk.Frame(self.panel, bg=CARD, cursor="hand2")
        row.pack(fill="x", pady=self.px(1))
        box = self.px(26)
        mark = tk.Canvas(row, width=box, height=box, bg=CARD, highlightthickness=0)
        mark.pack(side="left", padx=(self.px(2), 0))
        m, r = box * 0.5, box * 0.2
        mark.create_rectangle(m - r, m - r, m + r, m + r, outline="",
                              fill=self.dot_color(self.course_color(title)))
        if tm:
            tk.Label(row, text=tm, bg=CARD, fg=MUTED, font=self.f(11)
                     ).pack(side="right", padx=(self.px(4), self.px(8)))
        tk.Label(row, text="%s · %s" % (self.t("exam_" + kind), title), bg=CARD, fg=FG,
                 font=self.f(13, True), anchor="w", justify="left",
                 wraplength=self.panel_w - self.px(90), pady=self.px(4)
                 ).pack(side="left", fill="x", expand=True, padx=(self.px(6), 0))
        for w in [row] + list(row.winfo_children()):
            w.bind("<Button-1>", lambda e, t=title: self.goto_course(t))
        self.tip(row, self.t("tip_exam"))
        self.hoverable(row)

    def make_row(self, idx, it):
        row = tk.Frame(self.panel, bg=CARD)
        row.pack(fill="x", pady=self.px(1))
        done = bool(it.get("done"))
        col = self.dot_color(it.get("color", PALETTE[0]))

        box = self.px(26)
        dot = tk.Canvas(row, width=box, height=box, bg=CARD, highlightthickness=0,
                        cursor="hand2")
        dot.pack(side="left", padx=(self.px(2), 0))
        m, r = box * 0.5, box * 0.22
        if done:
            dot.create_oval(m - r, m - r, m + r, m + r, outline=DIM, fill="")
            dot.create_line(m - r * 0.55, m, m - r * 0.1, m + r * 0.5,
                            m + r * 0.6, m - r * 0.55, fill=MUTED, width=max(1, self.px(2)))
        else:
            dot.create_oval(m - r, m - r, m + r, m + r, fill=col, outline="")
        dot.bind("<Button-1>", lambda e, i=idx: self.toggle_done(i))
        dot.bind("<Button-3>", lambda e, i=idx: self.color_menu(e, i))
        self.tip(dot, self.t("tip_done"))

        x = tk.Label(row, text="×", bg=CARD, fg=DIM, font=self.f(15), cursor="hand2",
                     padx=self.px(6))
        x.pack(side="right")
        x.bind("<Button-1>", lambda e, i=idx: self.delete(i))
        x.bind("<Enter>", lambda e: e.widget.config(fg=SUN), add="+")
        x.bind("<Leave>", lambda e: e.widget.config(fg=DIM), add="+")
        self.tip(x, self.t("tip_delete"))

        title = tk.Label(row, text=it["title"], bg=CARD, fg=DIM if done else FG,
                         font=self.f(13, strike=done), anchor="w", justify="left",
                         wraplength=self.panel_w - self.px(80), cursor="xterm",
                         pady=self.px(4))
        title.pack(side="left", fill="x", expand=True, padx=(self.px(6), 0))
        # 한 번 클릭으로 고친다. 더블클릭은 해볼 생각을 하기 어렵다.
        title.bind("<Button-1>", lambda e, i=idx, rr=row: self.edit(i, rr))
        self.tip(title, self.t("tip_edit"))
        self.hoverable(row)

    def edit(self, idx, row):
        items = self.events.get(key_of(self.selected), [])
        if idx >= len(items):
            return
        self.hide_tip()
        self._editing = True
        e = self.hint_entry(self.panel, 13, "")
        e.insert(0, items[idx]["title"])
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
            if t and t != items[idx]["title"]:
                self.push_undo()
                items[idx]["title"] = t
                self.save()
            self.render()

        def cancel(_=None):
            state["closed"] = True
            self.render()

        e.bind("<Return>", commit)
        e.bind("<FocusOut>", commit)
        e.bind("<Escape>", cancel)

    def make_form(self):
        wrap = tk.Frame(self.panel, bg=CARD)
        wrap.pack(fill="x", pady=(self.px(12), 0))
        sw = self.swatches(wrap, self.color, self.set_color)
        sw.pack(fill="x", pady=(0, self.px(6)))
        self.tip(sw, self.t("tip_color"))
        line = tk.Frame(wrap, bg=CARD)
        line.pack(fill="x")
        # 시간은 제목에 같이 적는다 (따로 칸을 두면 용도가 안 보인다)
        self.button(line, self.t("add"), self.add).pack(side="right",
                                                        padx=(self.px(6), 0))
        self.entry_w = self.hint_entry(line, 13, self.t("event_hint"))
        self.entry_w.pack(side="left", fill="x", expand=True, ipady=self.px(6))
        self.entry_w.bind("<Return>", lambda _: self.add())

    def make_upcoming(self):
        rows = []
        for k, items in self.events.items():
            try:
                d = dt.date.fromisoformat(k)
            except ValueError:
                continue
            if d >= self.today:
                rows += [(d, it.get("title", ""), "", it.get("color", PALETTE[0]))
                         for it in items if not it.get("done")]
        # 시험·과제도 함께 보여준다. 과목 이름을 붙여야 뭐의 시험인지 알 수 있다.
        for title, info in self.courses.items():
            for k in EXAM_KEYS:
                d = parse_date(info.get(k + "_date", ""))
                if d and d >= self.today:
                    # 시험 종류를 앞에 둔다. 과목명이 길어 잘릴 때 '期中'이 잘리면 안 된다.
                    rows.append((d, "%s · %s" % (self.t("exam_%s_s" % k), title),
                                 info.get(k + "_time", ""),
                                 self.course_color(title)))
        if not rows:
            return
        rows.sort(key=lambda r: (r[0], r[2] or ""))

        box = tk.Frame(self.panel, bg=CARD)
        box.pack(fill="x", side="bottom", pady=(self.px(14), 0))
        tk.Frame(box, bg=LINE, height=1).pack(fill="x", pady=(0, self.px(10)))
        hd = tk.Frame(box, bg=CARD)
        hd.pack(fill="x", pady=(0, self.px(6)))
        tk.Label(hd, text=self.t("upcoming"), bg=CARD, fg=FG, font=self.f(12, True),
                 anchor="w").pack(side="left")
        tk.Label(hd, text=str(len(rows)), bg=CARD, fg=DIM, font=self.f(11)
                 ).pack(side="left", padx=(self.px(6), 0))

        f_t, f_d = self.fpx(12), self.fpx(10)
        pill_w = self.measure("D-000", self.fpx(10), True) + self.px(14)
        dot_w = self.px(14)
        for d, title, tm, col in rows[:5]:
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
            q = dot_w * 0.22
            dot.create_oval(dot_w / 2 - q, dot_w / 2 - q, dot_w / 2 + q, dot_w / 2 + q,
                            fill=self.dot_color(col), outline="")
            room = (self.panel_w - pill_w - dot_w - self.px(18)
                    - self.measure(when, f_d) - self.px(8))
            tk.Label(r, text=self.fit(title, f_t, room), bg=CARD, fg=FG,
                     font=self.f(12), anchor="w").pack(side="left", fill="x", expand=True)

    # ---------- 데이터 ----------

    def push_undo(self):
        self.undo_stack.append(json.dumps({"e": self.events, "t": self.tt,
                                           "c": self.courses}, ensure_ascii=False))
        if len(self.undo_stack) > 40:
            self.undo_stack.pop(0)

    def undo(self, _=None):
        if not self.undo_stack:
            return "break"
        snap = json.loads(self.undo_stack.pop())
        self.events, self.tt = snap["e"], snap["t"]
        self.courses = snap.get("c", self.courses)
        self.save()
        self.save_tt()
        self.save_courses()
        self.render()
        return "break"

    def add(self):
        t = self.entry_w.get().strip()
        if not t:
            self.entry_w.focus_set()
            return
        self.push_undo()
        self.events.setdefault(key_of(self.selected), []).append(
            {"title": t, "color": self.color, "done": False})
        self.save()
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
        # 화면을 다시 그리면 입력칸이 새로 만들어져 적던 내용이 날아간다.
        # 색만 바꾸려던 건데 글이 사라지면 안 되므로 그대로 옮겨 담는다.
        txt = ""
        try:
            txt = self.entry_w.get()
        except Exception:
            pass
        self.color = col
        self.conf["color"] = col
        self.render()
        try:
            if txt:
                self.entry_w.insert(0, txt)
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
                          "glass": self.glass})
        if not self.float_mode:
            self.conf["pinned"] = self.pinned
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
            self._drag_pos = (e.x_root - self._drag[0], e.y_root - self._drag[1])
            self.geometry("+%d+%d" % self._drag_pos)
            if self.glass_img:
                self.move_glass()

    def drag_end(self, _):
        if self._drag:
            self._drag = None
            self.update_idletasks()
            self._drag_pos = None
            self.save_conf()
            if self.glass_img and self.window_pos() != self._drag_from:
                if self.desk_fits():
                    self.move_glass()          # 이미 맞는 바탕화면이 비친다
                else:
                    self.build()               # 놓은 자리 바탕이 달라 색을 다시 맞춘다

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

    def menu(self, e):
        m = self.new_menu(self)
        lang = self.new_menu(m)
        for code in TEXT:
            self.radio(lang, TEXT[code]["lang_name"], code == self.lang,
                       lambda c=code: self.set_lang(c))
        m.add_cascade(label=self.t("lang"), menu=lang)

        theme = self.new_menu(m)
        for name in ("dark", "light"):
            self.radio(theme, self.t(name), name == self.theme,
                       lambda n=name: self.set_theme(n))
        m.add_cascade(label=self.t("theme"), menu=theme)

        bgm = self.new_menu(m)
        for key in ("soft", "clear", "off"):
            self.radio(bgm, self.t("glass_" + key), key == self.glass,
                       lambda k=key: self.set_glass(k))
        m.add_cascade(label=self.t("glass"), menu=bgm)

        sizes = self.new_menu(m)
        for i, (ww, hh) in enumerate(SIZES):
            self.radio(sizes, "%s  (%d×%d)" % (self.t("sizes")[i], ww, hh),
                       i == self.size_idx, lambda k=i: self.set_size(k))
        m.add_cascade(label=self.t("size"), menu=sizes)

        wk = self.new_menu(m)
        odd = self.is_odd_week(self.today)
        self.radio(wk, self.t("set_odd"), odd, lambda: self.set_week_kind(True))
        self.radio(wk, self.t("set_even"), not odd, lambda: self.set_week_kind(False))
        m.add_cascade(label=self.t("parity"), menu=wk)
        m.add_command(label=self.t("pku_import"), command=self.import_pku)

        m.add_command(label=self.t("pin_top") if self.pinned else self.t("pin_desk"),
                      command=self.toggle_pin)
        on = autostart_enabled()
        self.radio(m, self.t("autostart"), on, lambda: self.set_autostart_pref(not on))
        m.add_separator()
        m.add_command(label=self.t("open_data"),
                      command=lambda: subprocess.Popen(["explorer", APP_DIR]))
        m.add_command(label=self.t("quit"), command=self.quit_app)
        self.popup(m, e)

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

    def set_autostart_pref(self, on):
        set_autostart(on)
        self.conf["autostart"] = on            # 사용자가 고른 값을 기억한다
        self.save_conf()

    def toggle_pin(self):
        self.pinned = not self.pinned
        self.attributes("-topmost", not self.pinned)
        if self.pinned:
            self._topmost = False
            self.lower_to_desktop()
        else:
            user32.SetWindowPos(self.hwnd, HWND_TOP, 0, 0, 0, 0, SWP_SHOW)
        self.save_conf()

    # ---------- 북대 门户에서 가져오기 ----------

    def import_pku(self):
        """로그인 창을 별도 프로세스로 띄운다 (웹 창과 Tk 는 한 프로세스에서 같이 못 돈다)."""
        if getattr(self, "_pku_proc", None) and self._pku_proc.poll() is None:
            return
        if not FROZEN and not importlib.util.find_spec("webview"):
            tkmsg.showinfo("DeskCal", self.t("pku_need_webview"), parent=self)
            return
        out = os.path.join(tempfile.gettempdir(), "deskcal_pku_%d.json" % os.getpid())
        if os.path.exists(out):
            os.remove(out)
        cmd = [sys.executable] + ([] if FROZEN else [os.path.abspath(__file__)])
        self._pku_proc = subprocess.Popen(cmd + ["--pku-login", out, self.lang])
        self._pku_out = out
        if self.view != "tt":
            self.set_view("tt")
        self.set_status("pku_waiting")
        self._jobs["pku"] = self.after(1000, self.pku_wait)

    def pku_wait(self):
        if self._pku_proc.poll() is None:
            self._jobs["pku"] = self.after(1000, self.pku_wait)
            return
        try:
            with open(self._pku_out, encoding="utf-8") as f:
                resp = json.load(f)
            os.remove(self._pku_out)
        except (OSError, ValueError):
            tkmsg.showinfo("DeskCal", self.t("pku_failed"), parent=self)
            return
        self.apply_pku(resp)

    def apply_pku(self, resp):
        """가져온 课表를 시간표에 넣는다. 같은 과목은 원래 색을 유지하고, 그 과목이 있던
        옛 칸은 지운다(옮겨진 수업). 직접 넣은 다른 수업은 그대로 둔다."""
        slots, skipped = parse_pku_table(resp)
        if not slots:
            tkmsg.showinfo("DeskCal", self.t("pku_empty"), parent=self)
            return
        self.tt_commit()
        self.push_undo()
        titles = {c["title"] for cs in slots.values() for c in cs}
        colors = {}
        for it in self.tt.values():
            colors.setdefault(it.get("title"), it.get("color"))
        used = [colors[t] for t in titles if colors.get(t)]
        free = [c for c in PALETTE if c not in used] or PALETTE
        for k in [k for k, it in self.tt.items() if it.get("title") in titles]:
            del self.tt[k]
        for (di, p), cs in sorted(slots.items()):
            c = cs[0]
            skipped += len(cs) - 1                   # 한 칸에는 한 과목만 넣을 수 있다
            if not colors.get(c["title"]):
                colors[c["title"]] = free[len([t for t in colors if t in titles]) % len(free)]
            self.tt[self.tt_key(di, p)] = {"title": c["title"], "room": c["room"],
                                           "color": colors[c["title"]], "week": c["week"]}
            if c["exam"] and not self.courses.get(c["title"], {}).get("fin_date"):
                info = self.courses.setdefault(c["title"], {})   # 직접 적어둔 날짜는 그대로
                info["fin_date"], info["fin_time"] = c["exam"]
        self.save_tt()
        self.save_courses()
        self.render()
        n_cells = sum(1 for _ in slots)
        log("门户 课表 가져옴: %d과목, %d칸, 제외 %d" % (len(titles), n_cells, skipped))
        tkmsg.showinfo("DeskCal", self.t(
            "pku_done", n=len(titles), c=n_cells,
            extra=self.t("pku_skipped", k=skipped) if skipped else ""), parent=self)

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
    if "--pku-login" in sys.argv:            # 门户 로그인 창 (위젯이 띄우는 별도 프로세스)
        i = sys.argv.index("--pku-login")
        sys.exit(pku_login(sys.argv[i + 1], sys.argv[i + 2] if len(sys.argv) > i + 2 else "en"))
    DPI_MODE = set_dpi_awareness()
    os.makedirs(APP_DIR, exist_ok=True)
    if already_running():
        sys.exit(0)
    try:
        DeskCal().mainloop()
    except Exception:
        log("치명적 예외:\n" + traceback.format_exc())
        raise
