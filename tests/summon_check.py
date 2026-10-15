# -*- coding: utf-8 -*-
"""아이콘으로 불러내기 확인: 숨어 있는 위젯을 '사용자가 켠 것과 같은 조건'으로 불러내고,
계속 보이는지, 다른 창을 누르면 다시 뒤로 가는지 화면으로 확인한다.
실제 위젯(data 폴더)이 --autostart 로 떠 있는 상태에서 돌린다. 마우스를 잠깐 쓴다."""
import ctypes, os, struct, subprocess, sys, time
import tkinter as tk

u, g = ctypes.windll.user32, ctypes.windll.gdi32
u.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
u.SetProcessDpiAwarenessContext.restype = ctypes.c_bool
u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
H = ctypes.c_void_p
for name, a, r in (("GetForegroundWindow", [], H), ("FindWindowW", [ctypes.c_wchar_p, ctypes.c_wchar_p], H),
                   ("GetDC", [H], H), ("ReleaseDC", [H, H], None),
                   ("PrintWindow", [H, H, ctypes.c_uint], None),
                   ("GetWindowRect", [H, ctypes.c_void_p], None)):
    f = getattr(u, name); f.argtypes = a
    if r:
        f.restype = r
g.CreateCompatibleDC.restype = H; g.CreateCompatibleDC.argtypes = [H]
g.CreateCompatibleBitmap.restype = H
g.CreateCompatibleBitmap.argtypes = [H, ctypes.c_int, ctypes.c_int]
g.SelectObject.argtypes = [H, H]
g.BitBlt.argtypes = [H] + [ctypes.c_int] * 4 + [H, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
g.GetDIBits.argtypes = [H, H, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p,
                        ctypes.c_uint]
g.DeleteObject.argtypes = [H]; g.DeleteDC.argtypes = [H]


class RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]


class PT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def grab(hwnd, rc, screen):
    w, h = rc.r - rc.l, rc.b - rc.t
    scr = u.GetDC(None); mdc = g.CreateCompatibleDC(scr)
    bmp = g.CreateCompatibleBitmap(scr, w, h); g.SelectObject(mdc, bmp)
    if screen:
        g.BitBlt(mdc, 0, 0, w, h, scr, rc.l, rc.t, 0x00CC0020)
    else:
        u.PrintWindow(hwnd, mdc, 2)
    hdr = ctypes.create_string_buffer(struct.pack("<IiiHHIIiiII", 40, w, -h, 1, 32, 0, 0, 0, 0, 0, 0), 44)
    buf = ctypes.create_string_buffer(w * h * 4)
    g.GetDIBits(mdc, bmp, 0, h, buf, hdr, 0)
    g.DeleteObject(bmp); g.DeleteDC(mdc); u.ReleaseDC(None, scr)
    return buf.raw


def visible(hwnd):
    rc = RECT(); u.GetWindowRect(hwnd, ctypes.byref(rc))
    w, h = rc.r - rc.l, rc.b - rc.t
    ref, scr = grab(hwnd, rc, False), grab(hwnd, rc, True)
    same = tot = 0
    for y in range(8, h - 8, max(1, h // 40)):
        for x in range(8, w - 8, max(1, w // 40)):
            k = (y * w + x) * 4
            tot += 1
            same += all(abs(ref[k + i] - scr[k + i]) <= 14 for i in range(3))
    return 100.0 * same / tot


def click_at(x, y):
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.1)
    u.mouse_event(0x02, 0, 0, 0, 0)
    u.mouse_event(0x04, 0, 0, 0, 0)


results = []


def check(cond, msg):
    results.append(bool(cond))
    print(("PASS" if cond else "FAIL") + " - " + msg)


saved = PT(); u.GetCursorPos(ctypes.byref(saved))
widget = u.FindWindowW(None, "DeskCal")
if not widget:
    print("실행 중인 위젯이 없음"); sys.exit(2)
v0 = visible(widget)
print("처음: 화면에 보이는 위젯 %.0f%% (다른 창 뒤에 숨어 있어야 함)" % v0)

# '사용자가 누른 프로그램' 흉내: 작은 창을 진짜로 클릭해 앞 창 권한을 얻은 뒤 두 번째 실행
root = tk.Tk()
root.overrideredirect(True)
root.attributes("-topmost", True)
root.geometry("220x70+20+20")
tk.Label(root, text="테스트 창", font=("Malgun Gothic", 14), bg="#334", fg="white").pack(fill="both", expand=True)
root.update()
time.sleep(0.3)
click_at(root.winfo_rootx() + 100, root.winfo_rooty() + 35)
for _ in range(10):
    root.update(); time.sleep(0.05)
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
subprocess.Popen([pyw, os.path.join(here, "deskcal.py")], cwd=here)
for _ in range(30):
    root.update(); time.sleep(0.05)
time.sleep(0.5)
fg = u.GetForegroundWindow()
v1 = visible(widget)
check(fg == widget, "두 번째 실행 → 위젯이 활성 창이 됨")
check(v1 > 90, "불러낸 직후 화면에 보임 (%.0f%%)" % v1)
time.sleep(3.0)
v2 = visible(widget)
check(v2 > 90, "3초 뒤에도 계속 보임 (%.0f%%) — 예전엔 0.3초 만에 사라졌다" % v2)
click_at(root.winfo_rootx() + 100, root.winfo_rooty() + 35)    # 다른 창을 누름
for _ in range(30):
    root.update(); time.sleep(0.05)
v3 = visible(widget)
check(v3 < 50, "다른 창을 누르면 다시 뒤로 (보이는 비율 %.0f%%)" % v3)
root.destroy()
u.SetCursorPos(saved.x, saved.y)
n = results.count(False)
print("\n불러내기 확인: %d개 중 %d개 통과" % (len(results), len(results) - n))
sys.exit(1 if n else 0)
