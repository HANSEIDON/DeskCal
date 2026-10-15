# -*- coding: utf-8 -*-
"""진짜 마우스 클릭·키 입력으로 주요 흐름을 확인한다 (임시 폴더 사용, 실제 데이터 무관).
약 10초 동안 마우스와 키보드를 쓰고, 끝나면 커서를 원래 자리로 돌려놓는다.
한글 입력 상태여도 괜찮도록 숫자만 입력한다."""
import ctypes
import datetime as dt
import json
import os
import sys
import tempfile

sys.argv = [sys.argv[0], "--float"]
tmp = tempfile.mkdtemp(prefix="deskcal_real_")
os.environ["DESKCAL_DIR"] = tmp
json.dump({"x": 120, "y": 80, "pinned": False, "view": "tt", "size": 2},
          open(os.path.join(tmp, "config.json"), "w"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import deskcal  # noqa: E402

deskcal.DPI_MODE = deskcal.set_dpi_awareness()
u = ctypes.windll.user32


class PT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


saved_cursor = PT()
u.GetCursorPos(ctypes.byref(saved_cursor))
app = deskcal.DeskCal()
TODAY = dt.date.today()
results = []


def check(cond, msg):
    results.append(bool(cond))
    print(("PASS" if cond else "FAIL") + " - " + msg)


def click_at(x, y):
    u.SetCursorPos(int(x), int(y))
    u.mouse_event(0x02, 0, 0, 0, 0)
    u.mouse_event(0x04, 0, 0, 0, 0)


def click(w, dx=None, dy=None):
    click_at(w.winfo_rootx() + (dx if dx is not None else w.winfo_width() // 2),
             w.winfo_rooty() + (dy if dy is not None else w.winfo_height() // 2))


def keys(text):
    for ch in text:
        vk = {"\n": 0x0D, "\t": 0x09}.get(ch, ord(ch.upper()))
        u.keybd_event(vk, 0, 0, 0)
        u.keybd_event(vk, 0, 2, 0)


def walk(w, out):
    for ch in w.winfo_children():
        out.append(ch)
        walk(ch, out)
    return out


def label(root, text):
    return [w for w in walk(root, []) if w.winfo_class() == "Label" and w.cget("text") == text]


steps = []


def step(fn):
    steps.append(fn)
    return fn


@step
def s_cell():
    c = app.cal
    click_at(c.winfo_rootx() + app.tgut + 2.5 * app.tcw, c.winfo_rooty() + app.thh + 6.5 * app.tch)


@step
def s_type_title():
    check(app.tt_sel == (2, 7), "시간표 칸을 클릭하면 그 칸이 선택됨")
    check(app.focus_get() == app.tt_title, "빈 칸이면 과목 칸에 바로 커서가 감")
    keys("1234\n")


@step
def s_saved():
    tt = json.load(open(deskcal.TT_FILE, encoding="utf-8"))
    check(tt.get("2-7", {}).get("title") == "1234", "과목명 입력 후 Enter 키로 저장")
    check(app.status_lbl.cget("text") == app.t("saved"), "'%s' 이 보임" % app.t("saved"))
    click(app.exam_e["mid"][0])


@step
def s_pick():
    check(app._picker is not None and app._picker.winfo_exists(), "시험 날짜 칸을 누르면 달력이 뜸")
    day = [w for w in label(app._picker, "20") if w.cget("fg") != deskcal.DIM][0]
    click(day)


@step
def s_time():
    crs = json.load(open(deskcal.COURSE_FILE, encoding="utf-8"))
    want = TODAY.replace(day=20).isoformat()
    check(crs.get("1234", {}).get("mid_date") == want, "달력에서 누른 날짜가 저장됨 (%s)" % want)
    check(app._picker is None, "날짜를 고르면 달력이 닫힘")
    click(app.exam_e["mid"][1])


@step
def s_time_type():
    keys("1400\t")


@step
def s_time_check():
    crs = json.load(open(deskcal.COURSE_FILE, encoding="utf-8"))
    check(crs.get("1234", {}).get("mid_time") == "14:00" and app.exam_e["mid"][1].get() == "14:00",
          "시간 '1400' 입력 후 Tab → 14:00 으로 저장")
    x0, y0, x1, y1 = app.base.bbox("b_cal")           # 머리줄 탭은 캔버스에 그려져 있다
    click_at(app.base.winfo_rootx() + (x0 + x1) // 2, app.base.winfo_rooty() + (y0 + y1) // 2)


@step
def s_cal_add():
    check(app.view == "cal", "'달력' 탭을 누르면 달력으로 전환")
    click(app.entry_w)


@step
def s_cal_type():
    keys("5678\n")


@step
def s_cal_added():
    check([i["title"] for i in app.events.get(TODAY.isoformat(), [])] == ["5678"],
          "새 일정 입력 후 Enter 로 추가")
    click(label(app.panel, "5678")[0])


@step
def s_edit():
    check(any(w.winfo_class() == "Entry" and w.get() == "5678" for w in walk(app.panel, [])),
          "일정 제목을 한 번 클릭하면 고치는 칸이 열림")
    keys("9999\n")


@step
def s_edited():
    check(app.events[TODAY.isoformat()][0]["title"] == "9999", "고친 뒤 Enter 로 저장")
    x = label(app.panel, "×")[0]
    u.SetCursorPos(x.winfo_rootx() + 4, x.winfo_rooty() + 4)


@step
def s_tip():
    check(app._tip is not None and app._tip.winfo_children()[0].cget("text") == app.t("tip_delete"),
          "× 위에 마우스를 올리면 설명 풍선")
    app.quit()


def run(i=0):
    if i < len(steps):
        try:
            steps[i]()
        except Exception as e:
            check(False, "%s 단계에서 오류: %r" % (steps[i].__name__, e))
            app.quit()
            return
        app.after(900, run, i + 1)


app.after(1500, run)
app.mainloop()
u.SetCursorPos(saved_cursor.x, saved_cursor.y)
try:
    app.destroy()
except Exception:
    pass
n = results.count(False)
print("\n실제 입력 확인: %d개 중 %d개 통과" % (len(results), len(results) - n))
sys.exit(1 if n else 0)
