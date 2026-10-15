# -*- coding: utf-8 -*-
"""README 용 스크린샷을 만든다: python tests/make_screenshots.py
실제 바탕화면 대신 만들어 낸 배경 그림을 위젯 뒤에 깔고, 예시 일정으로 위젯을 띄워
화면을 찍는다. 사용자의 데이터·바탕화면은 쓰지 않는다. (화면에 몇 초씩 창이 뜬다)
결과: docs/*.png"""
import ctypes
import datetime as dt
import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "docs")
SHOTS = {  # 이름: (화면, 테마, 언어)
    "calendar-dark": ("cal", "dark", "en"),
    "timetable-dark": ("tt", "dark", "en"),
    "calendar-light": ("cal", "light", "en"),
    "timetable-light-zh": ("tt", "light", "zh"),
}
TODAY = dt.date(2026, 10, 14)                   # 예시의 '오늘' (수요일, 3교시 수업 중)
NOW = dt.datetime(2026, 10, 14, 10, 35)
X0, Y0, MARGIN = 120, 110, 72                   # 배경 창 위치와 위젯 둘레 여백

BLUE, PURPLE, GREEN, ORANGE, PINK, GRAY, YELLOW = (
    "#84b5e6", "#ac97e2", "#86c796", "#eba77a", "#e8949b", "#9ea4b3", "#e3c66f")


def demo_data():
    def cls(title, room, color, week="all"):
        return {"title": title, "room": room, "color": color, "week": week}
    tt = {}
    for day, first, n, item in (
            (0, 1, 2, cls("Calculus II", "A-201", BLUE)),
            (0, 3, 2, cls("Psych 101", "B-105", PURPLE)),
            (0, 7, 2, cls("Data Structures", "CS-302", GREEN)),
            (1, 1, 2, cls("Linear Algebra", "A-110", ORANGE)),
            (1, 5, 2, cls("Academic Writing", "L-12", PINK)),
            (1, 10, 2, cls("Chinese Mythology", "H-08", GRAY)),
            (2, 3, 2, cls("Data Structures", "CS-302", GREEN)),
            (2, 5, 2, cls("Pickleball", "Gym 2", YELLOW)),
            (3, 1, 2, cls("Calculus II", "A-201", BLUE)),
            (3, 3, 2, cls("Microeconomics", "E-210", ORANGE)),
            (3, 7, 3, cls("Database Lab", "CS-Lab 4", GREEN)),
            (4, 3, 2, cls("Psych 101", "B-105", PURPLE)),
            (4, 5, 2, cls("Research Seminar", "S-301", GRAY, "odd"))):
        for p in range(first, first + n):
            tt["%d-%d" % (day, p)] = item
    courses = {
        "Data Structures": {"mid_date": "2026-10-28", "mid_time": "14:00",
                            "asg_date": "2026-10-16", "asg_time": "23:59"},
        "Calculus II": {"mid_date": "2026-10-21", "mid_time": "09:00",
                        "fin_date": "2026-12-29", "fin_time": "09:00"},
        "Psych 101": {"mid_date": "2026-11-04", "mid_time": "Essay exam"},
    }

    def ev(title, color, done=False):
        return {"title": title, "color": color, "done": done}
    events = {
        "2026-10-02": [ev("Pay tuition", PINK, True)],
        "2026-10-05": [ev("Course registration opens 10:00", PINK, True)],
        "2026-10-09": [ev("Return library books", YELLOW, True)],
        "2026-10-14": [ev("Submit lab report", GREEN, True),
                       ev("Study group – Calculus 4pm", BLUE),
                       ev("Photography club 7pm", PURPLE)],
        "2026-10-15": [ev("Add/drop deadline", PINK)],
        "2026-10-20": [ev("Dentist 3pm", GRAY)],
        "2026-10-23": [ev("Team project sync", ORANGE)],
        "2026-10-27": [ev("Career fair", PURPLE)],
        "2026-10-30": [ev("Halloween party", ORANGE)],
    }
    return tt, courses, events


def wallpaper(w, h):
    """부드러운 색 덩어리가 겹친 배경 그림. (R, G, B) 바이트 세 개를 돌려준다."""
    top, bot = (40, 52, 92), (22, 26, 44)
    blobs = [((0.85, 0.12), 0.38, (242, 140, 107)), ((0.12, 0.88), 0.42, (63, 184, 175)),
             ((0.45, 0.45), 0.35, (138, 111, 223)), ((0.92, 0.92), 0.25, (242, 196, 107)),
             ((0.05, 0.10), 0.22, (90, 140, 230))]
    gx = [[math.exp(-((x / w - cx) / s) ** 2) for x in range(w)] for (cx, _), s, _ in blobs]
    gy = [[math.exp(-((y / h - cy) / s) ** 2) for y in range(h)] for (_, cy), s, _ in blobs]
    R, G, B = bytearray(w * h), bytearray(w * h), bytearray(w * h)
    for y in range(h):
        t = y / (h - 1)
        base = [top[i] + (bot[i] - top[i]) * t for i in range(3)]
        rowk = [gy[k][y] for k in range(len(blobs))]
        o = y * w
        for x in range(w):
            r, g, b = base
            for k, (_, _, col) in enumerate(blobs):
                a = 0.85 * rowk[k] * gx[k][x]
                r += (col[0] - r) * a
                g += (col[1] - g) * a
                b += (col[2] - b) * a
            R[o + x], G[o + x], B[o + x] = int(r), int(g), int(b)
    return bytes(R), bytes(G), bytes(B)


def shoot(name):
    view, theme, lang = SHOTS[name]
    tmp = tempfile.mkdtemp(prefix="deskcal_shot_")
    os.environ["DESKCAL_DIR"] = tmp
    sys.argv = ["deskcal", "--float"]
    sys.path.insert(0, HERE)
    import deskcal as d
    d.DPI_MODE = d.set_dpi_awareness()
    tt, courses, events = demo_data()
    for fname, obj in (("timetable.json", tt), ("courses.json", courses),
                       ("events.json", events)):
        json.dump(obj, open(os.path.join(tmp, fname), "w", encoding="utf-8"), ensure_ascii=False)
    # 위젯이 놓일 자리 (물리 픽셀). 크기는 위젯을 만들어 봐야 알 수 있다.
    probe = d.tk.Tk()
    dpi = max(1.0, probe.winfo_fpixels("1i") / 96.0)
    probe.destroy()
    ww, wh = int(d.SIZES[2][0] * dpi), int(d.SIZES[2][1] * dpi)
    fw, fh = ww + 2 * MARGIN, wh + 2 * MARGIN
    json.dump({"x": X0 + MARGIN, "y": Y0 + MARGIN, "size": 2, "view": view, "theme": theme,
               "lang": lang, "glass": "clear", "week_anchor": "2026-09-07",
               "color": BLUE}, open(os.path.join(tmp, "config.json"), "w"))

    R, G, B = wallpaper(fw, fh)

    def fake_glass(x, y, w, h, tint, alpha, shrink=72):
        """바탕화면 대신 만든 배경 그림에서 위젯 뒤 부분을 잘라 덮개색을 씌운다."""
        tr, tg, tb = d.rgb(tint)
        out = bytearray(w * h * 4)
        ox, oy = x - X0, y - Y0
        for ch, src, tv in ((2, R, tr), (1, G, tg), (0, B, tb)):
            table = bytes(int(v * (1 - alpha) + tv * alpha) for v in range(256))
            rows = b"".join(src[(oy + j) * fw + ox:(oy + j) * fw + ox + w] for j in range(h))
            out[ch::4] = rows.translate(table)
        return bytes(out)
    d.make_glass = fake_glass
    d.DeskCal.prepare_desk = lambda self: None          # 드래그용 전체 바탕화면은 필요 없다

    app = d.DeskCal()
    app.today = app.selected = TODAY
    app.shown = TODAY.replace(day=1)
    real_state = app.period_state
    app.period_state = lambda now=None: real_state(NOW)
    app.tt_sel = (2, 3)                                  # 수요일 3교시 (지금 수업)
    app.render()

    back = d.tk.Toplevel(app)                            # 위젯 뒤에 까는 배경 그림 창
    back.overrideredirect(True)
    back.attributes("-topmost", True)
    back.geometry("%dx%d+%d+%d" % (fw, fh, X0, Y0))
    ppm = bytearray(fw * fh * 3)
    ppm[0::3], ppm[1::3], ppm[2::3] = R, G, B
    img = d.tk.PhotoImage(master=app, data=b"P6 %d %d 255\n" % (fw, fh) + bytes(ppm),
                          format="ppm")
    d.tk.Label(back, image=img, bd=0).pack()
    ctypes.windll.user32.SetCursorPos(5, 5)
    for _ in range(4):
        app.attributes("-topmost", True)
        app.lift()
        app.update()
        time.sleep(0.4)

    u, g = ctypes.windll.user32, ctypes.windll.gdi32
    H = ctypes.c_void_p
    g.CreateCompatibleDC.restype = H
    g.CreateCompatibleBitmap.restype = H
    u.GetDC.restype = H
    scr = u.GetDC(None)
    mdc = g.CreateCompatibleDC(H(scr))
    bmp = g.CreateCompatibleBitmap(H(scr), fw, fh)
    g.SelectObject(H(mdc), H(bmp))
    g.BitBlt(H(mdc), 0, 0, fw, fh, H(scr), X0, Y0, 0x00CC0020)
    hdr = ctypes.create_string_buffer(
        struct.pack("<IiiHHIIiiII", 40, fw, -fh, 1, 32, 0, 0, 0, 0, 0, 0), 44)
    buf = ctypes.create_string_buffer(fw * fh * 4)
    g.GetDIBits(H(mdc), H(bmp), 0, fh, buf, hdr, 0)
    g.DeleteObject(H(bmp))
    g.DeleteDC(H(mdc))
    u.ReleaseDC(None, H(scr))
    shot = d.tk.PhotoImage(master=app, data=d.bgra_to_ppm(buf.raw, fw, fh), format="ppm")
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name + ".png")
    shot.write(path, format="png")
    print(path)
    app.destroy()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        shoot(sys.argv[1])
    else:                       # 하나씩 새 프로세스로 (테마·글꼴 같은 전역 상태가 섞이지 않게)
        for n in SHOTS:
            subprocess.run([sys.executable, os.path.abspath(__file__), n], check=True)
