# -*- coding: utf-8 -*-
"""deskcal 회귀 테스트. 실제 데이터(data 폴더)는 건드리지 않고 매번 임시 폴더에서 돈다.

    "C:\\Program Files\\Python312\\python.exe" tests\\test_deskcal.py
"""
import ctypes
import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import time

sys.argv = [sys.argv[0], "--float"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["DESKCAL_DIR"] = tempfile.mkdtemp(prefix="deskcal_test_")
import deskcal  # noqa: E402

RESULTS = []


def check(cond, msg):
    RESULTS.append(bool(cond))
    print(("PASS" if cond else "FAIL") + " - " + msg)


def fresh(files=None, conf=None):
    """새 임시 폴더를 만들어 그 폴더를 쓰는 앱을 띄운다."""
    d = tempfile.mkdtemp(prefix="deskcal_test_")
    for mod_attr, name in (("APP_DIR", ""), ("DATA_FILE", "events.json"),
                           ("TT_FILE", "timetable.json"), ("COURSE_FILE", "courses.json"),
                           ("CONF_FILE", "config.json"), ("LOG_FILE", "error.log")):
        setattr(deskcal, mod_attr, os.path.join(d, name) if name else d)
    for name, obj in (files or {}).items():
        with open(os.path.join(d, name), "w", encoding="utf-8") as f:
            if isinstance(obj, str):
                f.write(obj)
            else:
                json.dump(obj, f, ensure_ascii=False)
    c = {"x": 40, "y": 40, "pinned": False, "lang": "ko"}   # 대부분 한국어 문구로 확인
    c.update(conf or {})
    with open(os.path.join(d, "config.json"), "w", encoding="utf-8") as f:
        json.dump(c, f)
    app = deskcal.DeskCal()
    app.update()
    return app, d


class E:
    def __init__(self, x=0, y=0, w=None, kc=0):
        self.x, self.y, self.widget, self.keycode, self.state = x, y, w, kc, 4
        self.x_root = self.y_root = 100


TODAY = dt.date.today()
T = TODAY.isoformat()


def section(name):
    print("\n== %s ==" % name)


# ------------------------------------------------------------------
section("데이터 보호 · 실행 취소")
REAL = {T: [{"title": "지켜져야 할 일정", "time": "", "color": "#e0555f", "done": False}]}
app, d = fresh({"events.json": REAL})
check(app.data_ok and app.events == REAL, "정상 파일을 읽음")
app.selected = TODAY
app.render()
app.entry_w.insert(0, "새 일정")
app.add()
n_add = len(app.events[T])
app.undo()
check(n_add == 2 and app.events == REAL, "추가 → Ctrl+Z 로 원상복구")
app.delete(0)
gone = T not in app.events
app.undo()
check(gone and app.events == REAL, "삭제 → Ctrl+Z 로 복구")
app.toggle_done(0)
done = app.events[T][0]["done"]
app.undo()
check(done and not app.events[T][0]["done"], "완료 체크 → Ctrl+Z 로 복구")
check(app.f(8, strike=True).cget("overstrike") == 1, "완료 항목은 취소선 글꼴")
check(json.load(open(deskcal.DATA_FILE, encoding="utf-8")) == REAL, "디스크 내용 = 메모리")
check(os.path.exists(deskcal.DATA_FILE + ".bak"), "저장할 때 .bak 백업")
app.destroy()

app, d = fresh({"events.json": "{ 깨진 JSON"})
check(not app.data_ok, "깨진 파일을 감지 (data_ok=False)")
app.entry_w.insert(0, "저장되면 안 됨")
app.add()
check(open(deskcal.DATA_FILE, encoding="utf-8").read() == "{ 깨진 JSON",
      "읽기 실패 상태에서 추가해도 원본을 덮어쓰지 않음")
with open(deskcal.DATA_FILE, "w", encoding="utf-8") as f:
    json.dump(REAL, f, ensure_ascii=False)
check(app.reload_data() and app.data_ok and app.events == REAL, "파일 복구 후 재로드")
app.destroy()

# ------------------------------------------------------------------
section("일정 입력: 추가 버튼 · 시간 칸 제거")
app, d = fresh()
app.selected = TODAY
app.render()
app.update()                # 배치가 끝나야 버튼이 클릭을 받는다


def walk(w, out):
    for ch in w.winfo_children():
        out.append(ch)
        walk(ch, out)
    return out


entries = [w for w in walk(app.panel, []) if w.winfo_class() == "Entry"]
check(len(entries) == 1, "달력 입력칸은 하나뿐 (용도 모를 작은 칸 없음): %d개" % len(entries))
btns = [w for w in walk(app.panel, []) if w.winfo_class() == "Label"
        and w.cget("text") == app.t("add")]
check(len(btns) == 1, "'%s' 버튼이 있음" % app.t("add"))
app.entry_w.insert(0, "버튼으로 추가")
btns[0].event_generate("<Button-1>", x=3, y=3)     # 좌표가 없으면 Tk 가 무시한다
app.update()
check([i["title"] for i in app.events.get(T, [])] == ["버튼으로 추가"], "버튼 클릭으로 추가됨")
before = json.dumps(app.events)
app.entry_w.delete(0, "end")
app.add()
check(json.dumps(app.events) == before, "빈 칸에서 추가를 눌러도 아무것도 안 생김")
app.entry_w.insert(0, "적던 일정")
app.set_color(deskcal.PALETTE[3])
check(app.entry_w.get() == "적던 일정" and app.color == deskcal.PALETTE[3],
      "적다가 색을 바꿔도 글이 남음")
app.destroy()

# ------------------------------------------------------------------
section("다가오는 일정")
ev = {(TODAY + dt.timedelta(days=k)).isoformat():
      [{"title": "%d일 뒤 일정 %s" % (k, "아주 긴 제목이라서 패널 폭을 넘어갈 것" * (k == 3)),
        "time": "", "color": "#4f9de0", "done": False}] for k in (0, 1, 3, 5, 9, 20, 40)}
ev[(TODAY + dt.timedelta(days=2)).isoformat()] = [
    {"title": "끝낸 일", "time": "", "color": "#4f9de0", "done": True}]
courses = {"고급수학": {"mid_date": (TODAY + dt.timedelta(days=4)).isoformat(),
                        "mid_time": "09:00"}}
app, d = fresh({"events.json": ev, "courses.json": courses}, {"size": 2})
app.selected = TODAY
app.render()
app.update()
labels = [w for w in walk(app.panel, []) if w.winfo_class() == "Label"]
texts = [w.cget("text") for w in labels]
check(app.t("upcoming") in texts, "제목 '%s' 표시" % app.t("upcoming"))
head = [w for w in labels if w.cget("text") == app.t("upcoming")][0]
box = head.master.master
check(head.master.winfo_children()[1].cget("text") == "8",
      "남은 개수 표시 (완료한 일 제외 일정 7 + 시험 1 = 8)")
rows = [r for r in box.winfo_children() if r.winfo_class() == "Frame"
        and r not in (head.master,) and r.winfo_children()]
pills = [r.winfo_children()[0].winfo_children()[0] for r in rows]
pill_txt = [p.cget("text") for p in pills]
check(pill_txt[:5] == [app.t("dday_today"), "D-1", "D-3", "D-4", "D-5"],
      "가까운 순서로 5개: %s" % pill_txt[:5])
check(pills[0].cget("bg") == app.pill_colors(0)[0] == app.pill_colors(1)[0]
      and pills[1].cget("bg") == app.pill_colors(1)[0], "오늘·내일은 붉은 배지")
check(pills[2].cget("bg") == app.pill_colors(3)[0] != app.pill_colors(0)[0], "일주일 안은 주황 배지")
check(app.pill_colors(20)[0] == deskcal.SUNK, "일주일 넘게 남으면 회색 배지")
check(any("期中" in t for t in texts), "시험(期中)도 함께 표시")
long_lbl = [w for w in labels if str(w.cget("text")).startswith("3일 뒤")][0]
check(long_lbl.cget("text").endswith("…"), "긴 제목은 … 로 잘림: %r" % long_lbl.cget("text"))
row = long_lbl.master
app.update()
check(row.winfo_reqwidth() <= app.panel_w + 2,
      "잘린 줄이 패널 폭을 넘지 않음 (%d <= %d)" % (row.winfo_reqwidth(), app.panel_w))
app.destroy()

# ------------------------------------------------------------------
section("언어 · 테마 · 대비")


def lum(h):
    def ch(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = deskcal.rgb(h)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def head_texts(app):
    c = app.base
    return [c.itemcget(i, "text") for i in c.find_withtag("head") if c.type(i) == "text"]


app, d = fresh(conf={"lang": None})
check(app.lang == "en" and app.title_text() == app.today.strftime("%B %Y"),
      "언어를 고른 적 없으면 영어: %r" % app.title_text())
app.destroy()
for code in deskcal.TEXT:
    check(set(deskcal.TEXT[code]) == set(deskcal.TEXT["ko"]), "%s 문구 키가 한국어와 같음" % code)
app, d = fresh()
app.shown = dt.date(2026, 10, 1)
app.set_lang("zh")
app.update()
check(app.title_text() == "2026年10月", "중국어 제목: %r" % app.title_text())
labels = [w.cget("text") for w in walk(app, []) if w.winfo_class() == "Label"]
check("添加" in labels and "日历" in head_texts(app) and "今天" in head_texts(app),
      "중국어 버튼/탭: %s" % head_texts(app))
check(deskcal.FONT == "Noto Sans CJK SC", "중국어도 같은 글꼴: %s" % deskcal.FONT)
app.set_view("tt")
app.update()
check(app.title_text().startswith("课表") and app.t("tt_cell", wd="周一", p=3) == "周一 第3节",
      "중국어 시간표: %r" % app.title_text())
app.set_view("cal")
keep = deskcal.FONT_PREFS["zh"][0]
deskcal.FONT_PREFS["zh"][0] = "없는 글꼴"
check(deskcal.pick_font(app, "zh").startswith("Microsoft YaHei"),
      "fonts 폴더가 없으면 중국어는 YaHei 로 (맑은 고딕은 간체자가 없음)")
deskcal.FONT_PREFS["zh"][0] = keep
app.destroy()
app, d = fresh()
app.shown = dt.date(2026, 10, 1)
app.set_lang("en")
app.update()
check(app.title_text() == "October 2026", "영어 제목: %r" % app.title_text())
labels = [w.cget("text") for w in walk(app, []) if w.winfo_class() == "Label"]
check("Add" in labels and "Calendar" in head_texts(app) and "Today" in head_texts(app),
      "영어 버튼/탭: %s" % head_texts(app))
check(json.load(open(deskcal.CONF_FILE))["lang"] == "en", "언어 설정이 저장됨")
app.set_view("tt")
app.update()
check(app.title_text().startswith("Timetable"), "시간표 제목도 영어")
app.set_view("cal")
app.set_lang("ko")
app.update()
check(app.title_text() == "2026년 10월", "한국어로 되돌림")

for theme in ("dark", "light"):
    for glass in ("soft", "clear", "off"):
        app.glass = glass
        app.set_theme(theme)
        app.update()
        cr_fg = contrast(deskcal.FG, deskcal.CARD)
        cr_mu = contrast(deskcal.MUTED, deskcal.CARD)
        cr_bg = contrast(deskcal.FG, deskcal.BG)
        check(cr_fg >= 7 and cr_mu >= 4.5 and cr_bg >= 7,
              "%s/%s 글자 대비: 본문 %.1f · 흐린 글자 %.1f · 유리 위 %.1f (기준 7 · 4.5 · 7)"
              % (theme, glass, cr_fg, cr_mu, cr_bg))
check(app.theme == "light" and app.panel.cget("bg") == deskcal.CARD
      and lum(deskcal.CARD) > 0.6, "라이트 모드: 밝은 패널 %s" % deskcal.CARD)
check(json.load(open(deskcal.CONF_FILE))["theme"] == "light", "테마 설정이 저장됨")
app.destroy()
app, d2 = fresh(conf={"theme": "light", "lang": "en"})
check(app.theme == "light" and lum(deskcal.CARD) > 0.6 and app.lang == "en",
      "다시 켜도 라이트 모드·영어 유지")
app.set_theme("dark")
check(lum(deskcal.CARD) < 0.15, "다크 모드로 되돌림 (어두운 패널 %s)" % deskcal.CARD)
app.destroy()

# ------------------------------------------------------------------
section("글꼴")
app, d = fresh()
check(deskcal.FONT == "Noto Sans CJK SC", "Noto Sans CJK SC 사용: %s" % deskcal.FONT)
gdi = ctypes.windll.gdi32
gdi.CreateFontW.restype = ctypes.c_void_p
gdi.CreateFontW.argtypes = [ctypes.c_int] * 5 + [ctypes.c_uint] * 8 + [ctypes.c_wchar_p]
gdi.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi.CreateCompatibleDC.restype = ctypes.c_void_p
gdi.GetGlyphIndicesW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int,
                                 ctypes.c_void_p, ctypes.c_uint]
dc = gdi.CreateCompatibleDC(None)
gdi.SelectObject(dc, gdi.CreateFontW(-20, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, deskcal.FONT))
ui = "".join(sorted({ch for lang in deskcal.TEXT.values() for v in lang.values()
                     for ch in ("".join(v) if isinstance(v, list) else v)}))
ui += "网络传播数据治理面向对象程序设计世界社会主义概论匹克球×›‹·…"
buf = (ctypes.c_ushort * len(ui))()
gdi.GetGlyphIndicesW(dc, ui, len(ui), buf, 1)
miss = "".join(c for c, g in zip(ui, buf) if g == 0xFFFF and not c.isspace() and c != "\n")
check(not miss, "모든 화면 글자 + 중국어 과목명이 한 글꼴에 있음 (없는 글자: %r)" % miss)
app.destroy()

# ------------------------------------------------------------------
section("달력 클릭 판정")
app, d = fresh()
base = dt.date(2026, 9, 1)
fails = checked = 0
for size in ((520, 420), (900, 800), (1300, 1100)):
    app.geometry("%dx%d" % size)
    app.update()
    app.shown = base
    app.draw_grid()
    rows = len(app.weeks)
    for ri in range(rows):
        for ci in range(7):
            app.shown = base
            app.draw_grid()
            want = app.weeks[ri][ci]
            app.on_grid_click(E(app.gut + (ci + 0.5) * app.cw, app.hh + (ri + 0.5) * app.ch))
            checked += 1
            fails += app.selected != want
check(fails == 0, "3가지 크기 × 모든 칸 %d개 클릭 (실패 %d)" % (checked, fails))
app.shown = base
app.draw_grid()
keep = app.selected
app.on_grid_click(E(app.gut * 0.5, app.hh + app.ch * 0.5))
app.on_grid_click(E(app.gut + app.cw, app.hh * 0.5))
check(app.selected == keep, "单/双 여백과 요일 머리글 클릭은 무시")
app.shown = base
app.draw_grid()
want = app.weeks[0][0]
app.on_grid_click(E(app.gut + 0.5 * app.cw, app.hh + 0.5 * app.ch))
check(app.selected == want and app.shown == want.replace(day=1), "다른 달 칸 → 그 달로 이동")
app.destroy()

# ------------------------------------------------------------------
section("单周 / 双周")
app, d = fresh()
nxt, prv = TODAY + dt.timedelta(days=7), TODAY - dt.timedelta(days=7)
check(app.is_odd_week(TODAY) and not app.is_odd_week(nxt) and not app.is_odd_week(prv)
      and app.is_odd_week(TODAY + dt.timedelta(days=14)), "이번 주 单, 앞뒤 주 双, 2주 뒤 单")
mon = app.monday_of(TODAY)
check(all(app.is_odd_week(mon + dt.timedelta(days=i)) for i in range(7)),
      "같은 주는 월~일 모두 같은 판정")
app.set_week_kind(False)
check(not app.is_odd_week(TODAY) and app.is_odd_week(nxt), "이번 주를 双周로 바꾸기")
app.destroy()

# ------------------------------------------------------------------
section("시간표 · 자동 저장")
app, d = fresh(conf={"view": "tt", "size": 3})
app.tt_sel = (0, 3)
app.render_panel()
app.update()
labels = [w.cget("text") for w in walk(app.panel, []) if w.winfo_class() == "Label"]
check("저장" not in labels and "Save" not in labels, "저장 버튼이 없음 (자동 저장)")
check(app.t("exams_need_title") in labels, "과목명 전엔 시험 칸 대신 안내 문구")
hint = app.tt_title.winfo_children()[0]
check(app.tt_title.get() == "" and hint.winfo_ismapped(),
      "빈 칸엔 회색 예시 글씨 '%s' (값에는 안 섞임)" % hint.cget("text"))
app.tt_title.insert(0, "고급수학")
app.tt_title_changed()
app.update()
check(not hint.winfo_ismapped(), "글을 적으면 예시 글씨가 사라짐")
check(len(app.exam_e) == 3, "과목명을 적으면 시험 칸 3개가 열림")
app.tt_room.insert(0, "A302")
app.tt_commit()                                   # = Enter / 칸 밖으로 나갈 때
app.update()
saved = json.load(open(deskcal.TT_FILE, encoding="utf-8"))
check(saved.get("0-3", {}).get("title") == "고급수학" and saved["0-3"]["room"] == "A302",
      "Enter 만으로 저장")
check(app.status_lbl.cget("text") == app.t("saved"), "'%s' 표시" % app.t("saved"))
check(app.del_btn.winfo_ismapped(), "저장되면 '%s' 버튼이 나타남" % app.t("del_class"))
app.tt_room.delete(0, "end")
app.tt_room.insert(0, "B101")
app.on_tt_click(E(app.tgut + 2.5 * app.tcw, app.thh + 4.5 * app.tch))
check(json.load(open(deskcal.TT_FILE, encoding="utf-8"))["0-3"]["room"] == "B101",
      "적다가 다른 칸을 누르면 저장됨")
# 테스트 창은 활성 창이 아니라 focus_get() 이 비어 있다. 창이 활성화되면 갈 곳을 본다.
app.update()
check(app.tt_sel == (2, 5) and app.focus_lastfor() == app.tt_title,
      "빈 칸으로 가면 바로 타이핑 가능")
app.tt_sel = (0, 3)
app.render_panel()
app.tt_set_color(deskcal.PALETTE[3])
app.tt_set_week("odd")
saved = json.load(open(deskcal.TT_FILE, encoding="utf-8"))["0-3"]
check(saved["color"] == deskcal.PALETTE[3] and saved["week"] == "odd", "색·주차는 누르자마자 저장")
del app.tt["0-3"]["week"], app.tt["0-3"]["room"]   # 손으로 고친 파일처럼 항목이 빠진 칸
n_undo = len(app.undo_stack)
app.render_panel()
app.tt_commit()
check(len(app.undo_stack) == n_undo, "빠진 항목이 있는 칸을 안 고치고 저장해도 '바뀜'으로 안 잡힘")
for th in ("dark", "light"):
    deskcal.apply_theme(th)
    worst = min(min(deskcal.contrast(ink, fill), deskcal.contrast(sub, fill) * 7 / 4.5)
                for fill, _, ink, sub in map(app.block_colors, deskcal.PALETTE))
    check(worst >= 7.0 - 1e-6, "%s: 수업 타일 글자 대비 7:1, 보조 글자 4.5:1 이상" % th)
deskcal.apply_theme(app.theme)
app.tt_sel = (1, 1)
app.render_panel()
app.tt_room.insert(0, "적던 강의실")
app.tt_set_color(deskcal.PALETTE[2])
check(app.tt_room.get() == "적던 강의실", "과목명 없이 적던 강의실도 색을 바꿔도 유지")

section("시험 · 과제 날짜 (달력에서 고르기)")
app.tt_sel = (0, 3)
app.render_panel()
app.update()
db, te = app.exam_e["mid"]
check(db.cget("text") == app.t("pick_date"), "날짜 칸은 형식 설명 대신 '%s' 버튼" % app.t("pick_date"))
db.event_generate("<Button-1>", x=3, y=3)
app.update()
check(app._picker is not None and app._picker.winfo_exists(), "누르면 작은 달력이 뜸")
target = TODAY.replace(day=15)
days = [w for w in walk(app._picker, []) if w.winfo_class() == "Label"
        and w.cget("text") == "15" and w.cget("fg") != deskcal.DIM]
days[0].event_generate("<Button-1>", x=3, y=3)
app.update()
check(app._picker is None, "날짜를 누르면 달력이 닫힘")
crs = json.load(open(deskcal.COURSE_FILE, encoding="utf-8"))
check(crs.get("고급수학", {}).get("mid_date") == target.isoformat(), "고른 날짜가 바로 저장됨")
db, te = app.exam_e["mid"]
check(db.cget("text") == app.btn_date(target),
      "날짜 칸에 읽기 쉽게 표시: '%s'" % db.cget("text"))
te.insert(0, "오후 2시")
app.tt_commit()
crs = json.load(open(deskcal.COURSE_FILE, encoding="utf-8"))
check(te.get() == "14:00" and crs["고급수학"]["mid_time"] == "14:00",
      "'오후 2시' 를 14:00 으로 알아듣고 고쳐 보여줌")
te.delete(0, "end")
te.insert(0, "中期报告")
app.tt_commit()
crs = json.load(open(deskcal.COURSE_FILE, encoding="utf-8"))
check(te.get() == "中期报告" and crs["고급수학"]["mid_time"] == "中期报告",
      "시간이 아닌 글(예: 中期报告)은 메모로 그대로 저장")
app.render_panel()
check(app.exam_e["mid"][1].get() == "中期报告", "다시 열어도 메모가 그대로")
te = app.exam_e["mid"][1]
db = app.exam_e["mid"][0]
te.delete(0, "end")
te.insert(0, "14:00")
app.tt_commit()
db.event_generate("<Button-1>", x=3, y=3)
app.update()
app.on_any_click(E(w=app.cal))
check(app._picker is None, "달력 밖을 누르면 닫힘")
db.event_generate("<Button-1>", x=3, y=3)
app.update()
clr = [w for w in walk(app._picker, []) if w.winfo_class() == "Label"
       and w.cget("text") == app.t("clear_date")]
clr[0].event_generate("<Button-1>", x=3, y=3)
app.update()
check("고급수학" not in json.load(open(deskcal.COURSE_FILE, encoding="utf-8"))
      and app.exam_e["mid"][0].cget("text") == app.t("pick_date"), "'날짜 지우기'로 지움")
app.undo()
check(app.courses.get("고급수학", {}).get("mid_date") == target.isoformat(),
      "지운 것도 Ctrl+Z 로 되돌아옴")
app.render_panel()

app.tt_sel = (2, 5)
app.render_panel()
app.tt_title.delete(0, "end")
app.tt_title.insert(0, "고급수학")
app.tt_title_changed()
check(app.exam_e["mid"][0].cget("text") == app.btn_date(target),
      "과목명을 적으면 그 과목 시험 날짜가 자동으로 채워짐")
app.tt_commit()
crs = json.load(open(deskcal.COURSE_FILE, encoding="utf-8"))
check(crs.get("고급수학", {}).get("mid_date") == target.isoformat(),
      "다른 칸에 같은 과목을 적어도 시험 정보가 안 지워짐")
app.tt_delete()
check("2-5" not in app.tt and app.status_lbl.cget("text") == app.t("deleted"),
      "수업 지우기 + '%s' 안내" % app.t("deleted"))
app.undo()
check(app.tt.get("2-5", {}).get("title") == "고급수학", "Ctrl+Z 로 복구")

section("시간표 그리기 · 클릭")
app.tt = {}
for p in (1, 2, 3):
    app.tt["0-%d" % p] = {"title": "연강", "room": "A", "color": "#4f9de0", "week": "all"}
app.tt["1-1"] = {"title": "격주", "room": "X", "color": "#4f9de0", "week": "odd"}
app.tt["1-2"] = {"title": "격주", "room": "X", "color": "#4f9de0", "week": "even"}
app.tt_sel = (0, 1)
app.render()
blocks = app.tt_blocks()
check(any(b[0] == 0 and b[1] == 1 and b[2] == 3 for b in blocks), "1~3교시 연강은 한 블록")
check(len([b for b in blocks if b[0] == 1]) == 2, "单周·双周가 다르면 따로")
app.update()
fails = 0
for di in range(deskcal.N_DAYS):
    for p in range(1, deskcal.PERIODS + 1):
        app.on_tt_click(E(app.tgut + (di + 0.5) * app.tcw, app.thh + (p - 0.5) * app.tch))
        fails += app.tt_sel != (di, p)
check(fails == 0, "시간표 60칸 클릭 판정 (실패 %d)" % fails)
inner = app.tcw - app.px(8)
cut = app.fit("面向对象程序设计JAVA上机实验", 18, inner, True)
check(app.measure(cut, 18, True) <= inner and cut.endswith("…"), "긴 과목명은 칸 안으로 잘림")
app.destroy()

# ------------------------------------------------------------------
section("과목명 두 줄 나누기")
app, d = fresh()
wmax = app.measure("Data Struct", 20, True)
check(app.wrap2("Data Structures", 20, wmax, True) == ["Data", "Structures"],
      "영어는 단어 사이에서 나눔: %r" % app.wrap2("Data Structures", 20, wmax, True))
lines = app.wrap2("Microeconomics", 20, app.measure("Microecon", 20, True), True)
check(len(lines) == 2 and lines[0].endswith("-") and lines[0][:-1] + lines[1] == "Microeconomics",
      "띄어쓰기 없는 긴 영어 단어는 하이픈으로: %r" % lines)
check(app.wrap2("中国神话研究", 20, app.measure("中国神话", 20, True), True) == ["中国神话", "研究"],
      "중국어는 글자 단위 그대로")
for name, cut_at in (("高等数学（B）", "高等数学（"), ("体育（匹克球）", "体育（匹克")):
    got = app.wrap2(name, 20, app.measure(cut_at, 20, True), True)
    check(len(got) == 2 and got[1].startswith("（") and not got[0].endswith("（"),
          "괄호는 통째로 다음 줄로: %r" % got)
app.destroy()

# ------------------------------------------------------------------
section("날짜 · 시간 알아듣기")
for s, want in (("2026-11-02", dt.date(2026, 11, 2)), ("2026.11.02", dt.date(2026, 11, 2)),
                ("20261102", dt.date(2026, 11, 2)), ("헛소리", None)):
    check(deskcal.parse_date(s) == want, "날짜 %r -> %s" % (s, want))
for s, want in (("14:00", "14:00"), ("1400", "14:00"), ("930", "09:30"), ("9", "09:00"),
                ("14시 30분", "14:30"), ("오후 2시", "14:00"), ("2시반", "02:30"),
                ("2pm", "14:00"), ("2:30 PM", "14:30"), ("下午2点半", "14:30"),
                ("오전 12시", "00:00"), ("", ""), ("25:00", None), ("아무거나", None)):
    check(deskcal.parse_time(s) == want, "시간 %r -> %r" % (s, want))

# ------------------------------------------------------------------
section("일정 고치기 · 설명 풍선")
app, d = fresh({"events.json": REAL})
app.selected = TODAY
app.render()
app.update()
check(app.entry_w.get() == "" and app.entry_w.winfo_children()[0].winfo_ismapped(),
      "입력칸에 예시 '%s' (값에는 안 섞임)" % app.t("event_hint"))
title_lbl = [w for w in walk(app.panel, []) if w.winfo_class() == "Label"
             and w.cget("text") == "지켜져야 할 일정"][0]
title_lbl.event_generate("<Button-1>", x=3, y=3)
app.update()
eds = [w for w in walk(app.panel, []) if w.winfo_class() == "Entry"
       and w.get() == "지켜져야 할 일정"]
check(len(eds) == 1 and eds[0].winfo_ismapped(), "제목을 한 번 누르면 바로 고치는 칸이 열림")
eds[0].delete(0, "end")
eds[0].insert(0, "고친 제목")
# 테스트 창은 활성 창이 아니라 Tk 가 Enter 키를 이 칸에 보내지 않는다.
# 같은 저장 함수가 걸린 '포커스가 빠질 때'(= 다른 곳을 누를 때) 경로로 확인한다.
eds[0].event_generate("<FocusOut>")
app.update()
check(app.events[T][0]["title"] == "고친 제목", "고친 뒤 다른 곳을 누르면 저장")
x_lbl = [w for w in walk(app.panel, []) if w.winfo_class() == "Label" and w.cget("text") == "×"][0]
x_lbl.event_generate("<Enter>", x=2, y=2)
t0 = time.time()
while time.time() - t0 < 1.0:
    app.update()
    time.sleep(0.02)
tip_ok = app._tip is not None and app._tip.winfo_exists()
check(tip_ok and app._tip.winfo_children()[0].cget("text") == app.t("tip_delete"),
      "× 에 마우스를 올리면 '%s'" % app.t("tip_delete"))
x_lbl.event_generate("<Leave>", x=2, y=2)
app.update()
check(app._tip is None, "마우스를 떼면 설명이 사라짐")
app.destroy()

# ------------------------------------------------------------------
section("지금 수업 · 오늘로 돌아가기 · 유리 배경")
app, d = fresh(conf={"view": "tt", "size": 2})
WED = dt.date(2026, 10, 14)                       # 수요일로 고정
at = lambda h, m, day=WED: dt.datetime(day.year, day.month, day.day, h, m)
st = app.period_state(at(10, 35))
check(st[0] == "now" and st[1] == 3 and 0.4 < st[2] < 0.6, "수 10:35 → 3교시 진행 중 %s" % (st,))
check(app.period_state(at(8, 0))[:2] == ("now", 1), "08:00 정각 → 1교시 시작")
check(app.period_state(at(11, 5))[:2] == ("next", 4), "11:05 쉬는 시간 → 다음은 4교시")
check(app.period_state(at(12, 30))[:2] == ("next", 5), "12:30 → 30분 뒤 5교시 '다음'")
check(app.period_state(at(12, 20)) is None, "12:20 → 40분 남아 표시 안 함")
check(app.period_state(at(21, 45)) is None, "수업 끝난 밤엔 표시 없음")
check(app.period_state(at(10, 35, dt.date(2026, 10, 17))) is None, "토요일엔 표시 없음")
check(app.period_text(3) == "10:10–11:00" and app.period_text(10) == "18:40–19:30",
      "교시 시간: 3교시 %s · 10교시 %s" % (app.period_text(3), app.period_text(10)))

app.today = WED
app.tt = {"2-3": {"title": "数据治理", "room": "二教302", "color": deskcal.PALETTE[0],
                  "week": "all"},
          "2-4": {"title": "数据治理", "room": "二教302", "color": deskcal.PALETTE[0],
                  "week": "all"}}
app.period_state = lambda now=None: ("now", 3, 0.5)
app.render()
app.update()
c = app.cal
items_text = [c.itemcget(i, "text") for i in c.find_all() if c.type(i) == "text"]
rings = [i for i in c.find_all() if c.type(i) == "polygon"
         and c.itemcget(i, "outline") == deskcal.ACCENT and c.itemcget(i, "width") == "3.0"]
lines = [i for i in c.find_all() if c.type(i) == "line" and c.itemcget(i, "fill") == deskcal.ACCENT]
check(app.t("now") in items_text, "지금 수업에 '%s' 표시" % app.t("now"))
check(len(rings) == 1, "지금 수업 블록에 강조 테두리 1개")
bx = c.bbox(rings[0])
check(bx[3] - bx[1] > app.tch * 1.6, "3~4교시 연강이면 블록 전체를 감쌈 (높이 %d)" % (bx[3] - bx[1]))
check(len(lines) == 1, "오늘 칸에 지금 시각 가로선")
app.period_state = lambda now=None: ("next", 3, 0.0)
app.draw_tt()
items_text = [c.itemcget(i, "text") for i in c.find_all() if c.type(i) == "text"]
check(app.t("next") in items_text and app.t("now") not in items_text, "쉬는 시간엔 '%s'" % app.t("next"))
del app.period_state
app.destroy()

app, d = fresh(conf={"view": "cal"})
app.shown = dt.date(2027, 3, 1)
app.selected = dt.date(2027, 3, 9)
app.render()
app._last_input = time.time() - 30
app.clock_tick()
check(app.shown == dt.date(2027, 3, 1), "손대는 중(30초 전 입력)이면 그대로 둠")
app._last_input = time.time() - deskcal.IDLE_RETURN - 5
app.entry_w.insert(0, "적는 중")
app.clock_tick()
check(app.selected == dt.date(2027, 3, 9), "새 일정을 적다 둔 글이 있으면 안 돌아감")
app.entry_w.delete(0, "end")
app.clock_tick()
check(app.selected == app.today and app.shown == app.today.replace(day=1)
      and app.title_text() == app.month_title(app.today),
      "%d초 손대지 않으면 오늘로 돌아옴 (%s)" % (deskcal.IDLE_RETURN, app.title_text()))
yesterday = app.today - dt.timedelta(days=1)
app.today = app.selected = yesterday
app.shown = yesterday.replace(day=1)
app._last_input = time.time()
app.clock_tick()
check(app.today == dt.date.today() and app.selected == dt.date.today(),
      "자정이 지나면 날짜와 선택이 오늘로 넘어감")
app.destroy()

app, d = fresh(conf={"glass": "soft"})
if app.glass_img:
    check(app.glass_img.width() == app.w() and app.glass_img.height() == app.h(),
          "유리 배경이 창 크기와 같음 (%dx%d)" % (app.glass_img.width(), app.glass_img.height()))
else:
    check(False, "유리 배경을 만들지 못함 (바탕화면 캡처 실패)")
app._desk = None                        # 드래그용 바탕화면 유리를 만드는 중에
app.prepare_desk()
app.update()
app.set_view("tt")                       # 화면을 다시 그려도
end = time.time() + 4
while time.time() < end and not app.desk_ready():
    app.update()
    time.sleep(0.02)
check(app.desk_ready() and not app._desk_busy,
      "유리를 만드는 중에 화면을 다시 그려도 드래그용 유리가 만들어짐 (예전엔 영영 멈춤)")
app.set_view("cal")
real_sig = deskcal.wallpaper_sig
deskcal.wallpaper_sig = lambda: ("새 바탕화면",)        # Windows 추천이 그림을 바꿨다
old_img = app.glass_img
app.wall_tick()
check(not app.desk_ready(), "바탕화면이 바뀌면 드래그용 사진을 바로 버림")
check(app.glass_img is old_img, "바뀌는 애니메이션 동안(2초)은 아직 다시 만들지 않음")
app._wall_changed = time.time() - 3
app.wall_tick()
check(app.glass_img is not old_img and app._wall_changed is None, "2초 뒤 유리를 새 그림으로 다시 만듦")
deskcal.wallpaper_sig = real_sig
real_dirs = deskcal.desktop_dirs
fake_desk = tempfile.mkdtemp(prefix="deskcal_desktop_")
deskcal.desktop_dirs = lambda: [fake_desk]
before = deskcal.wallpaper_sig()
time.sleep(0.05)
open(os.path.join(fake_desk, "새 폴더.txt"), "w").close()
check(deskcal.wallpaper_sig() != before, "바탕화면에 파일·폴더가 생기면 바뀐 것으로 알아챔")
deskcal.desktop_dirs = real_dirs
app.set_glass("off")
check(app.glass_img is None and json.load(open(deskcal.CONF_FILE))["glass"] == "off",
      "'단색'으로 바꾸면 유리 없이 저장됨")
b = app.base.find_withtag("b_menu")
check(len(b) >= 2, "머리줄 ≡ 버튼은 캔버스에 그려짐")
x0, y0, x1, y1 = app.base.bbox("b_menu")
app.base.event_generate("<Motion>", x=(x0 + x1) // 2, y=(y0 + y1) // 2)
app.update()
app.drag_start(E(x=(x0 + x1) // 2, y=(y0 + y1) // 2))
check(app._drag is None, "버튼 위에서 누르면 창이 끌리지 않음")
app.destroy()

# ------------------------------------------------------------------
section("복사 · 붙여넣기")
app, d = fresh()
e = app.entry_w
e.insert(0, "복사할내용")
e.select_range(0, "end")
app.on_ctrl_key(E(w=e, kc=67))
check(app.clipboard_get() == "복사할내용", "Ctrl+C")
e.delete(0, "end")
app.on_ctrl_key(E(w=e, kc=86))
check(e.get() == "복사할내용", "Ctrl+V")
e.select_range(0, "end")
app.on_ctrl_key(E(w=e, kc=88))
check(e.get() == "", "Ctrl+X")
e.insert(0, "abc")
app.on_ctrl_key(E(w=e, kc=65))
check(e.selection_present(), "Ctrl+A")
app.destroy()

# ------------------------------------------------------------------
section("화면 밖 복구")
app, d = fresh()
l, t, r, b = app.work_area()
app.geometry("+%d+%d" % (r - 60, 40))
app.update()
app.ensure_on_screen()
app.update()
check(app.winfo_x() + app.w() <= r, "오른쪽 밖으로 나간 창을 안으로")
good = max(l, r - app.w() - 100)
app.geometry("+%d+%d" % (good, t + 20))
app.update()
app.ensure_on_screen()
check(app.winfo_x() == good, "화면 안이면 위치를 건드리지 않음")
app.destroy()

# ------------------------------------------------------------------
section("시험 · 달력 · 시간표")

# 가져오기(ISOP) 기능은 공개 소스에서 빠졌다. 아래 기능 테스트는 시간표·과목을 직접 넣고 확인한다.
app, d = fresh(files={
    "timetable.json": {
        "0-1": {"title": "高等数学（B）", "room": "理教107", "color": deskcal.PALETTE[5], "week": "all"},
        "0-2": {"title": "高等数学（B）", "room": "理教107", "color": deskcal.PALETTE[5], "week": "all"},
        "1-3": {"title": "体育", "room": "五四网球场", "color": deskcal.PALETTE[2], "week": "all"},
        "4-2": {"title": "程序设计", "room": "理教215", "color": deskcal.PALETTE[1], "week": "odd"}},
    "courses.json": {
        "高等数学（B）": {"fin_date": "2027-01-05", "fin_time": "上午"},
        "程序设计": {"fin_date": "2027-01-12", "fin_time": "09:00"}}})

app.courses["옛 과목"] = {"mid_date": "%02d-%02d" % (app.today.month, app.today.day)}
check(app.exams_on(app.today) == [("mid", "옛 과목", "")], "예전 형식 날짜(연도 없음)도 달력에 나옴")
del app.courses["옛 과목"]

# 시간표의 시험이 달력에도 보인다
exam_day = dt.date(2027, 1, 5)
check(app.exams_on(exam_day) == [("fin", "高等数学（B）", "上午")], "그 날의 시험 찾기")
app.set_view("cal")
app.shown, app.selected = exam_day.replace(day=1), exam_day
app.render()
app.update()
check(any(app.cal.type(i) == "rectangle" for i in app.cal.find_all()), "달력 칸에 시험 표시(네모)")
labels = [w.cget("text") for w in walk(app.panel, []) if w.winfo_class() == "Label"]
check(any("期末" in t or "Final" in t or "高等数学（B）" in t for t in labels),
      "그 날 패널에 시험이 보임: %r" % [t for t in labels if "高等" in t])
row = next(w for w in walk(app.panel, []) if w.winfo_class() == "Label"
           and "高等数学（B）" in w.cget("text"))
row.event_generate("<Button-1>")
app.update()
check(app.view == "tt" and app.tt_sel == (0, 1), "누르면 시간표의 그 과목 칸으로 (%s %s)"
      % (app.view, app.tt_sel))
app.set_view("tt")

# 같은 색 일정이 여러 개여도 일정마다 점, 넘치면 +N
many_day = dt.date(2027, 1, 12)
app.events[deskcal.key_of(many_day)] = [{"title": "일%d" % i, "color": deskcal.PALETTE[6], "done": False}
                                        for i in range(3)]
app.set_view("cal")
app.shown, app.selected = many_day.replace(day=1), app.today
app.render()
app.update()


def cell_items(day):
    ri = next(r for r, w in enumerate(app.weeks) if day in w)
    ci = app.weeks[ri].index(day)
    x0, y0 = app.gut + ci * app.cw, app.hh + ri * app.ch
    return [i for i in app.cal.find_overlapping(x0 + 1, y0 + 1, x0 + app.cw - 1, y0 + app.ch - 1)]


dots = [i for i in cell_items(many_day) if app.cal.type(i) == "oval"]
check(len(dots) == 3, "같은 색 일정 3개면 점 3개 (%d개)" % len(dots))
app.events[deskcal.key_of(many_day)] *= 4                  # 12개
app.render()
app.update()
texts = [app.cal.itemcget(i, "text") for i in cell_items(many_day) if app.cal.type(i) == "text"]
check(any(t.startswith("+") for t in texts), "칸에 다 못 그리면 +N 표시: %r" % texts)
del app.events[deskcal.key_of(many_day)]
app.set_view("tt")

# 시험이 있는 날에도 일정을 다 끝내면 빈 동그라미
ring_day = dt.date(2027, 1, 5)
app.events[deskcal.key_of(ring_day)] = [{"title": "끝낸 일", "color": deskcal.PALETTE[0], "done": True}]
app.set_view("cal")
app.shown, app.selected = ring_day.replace(day=1), ring_day
app.render()
app.update()
rings = [i for i in app.cal.find_all() if app.cal.type(i) == "oval"
         and app.cal.itemcget(i, "fill") == "" and app.cal.itemcget(i, "outline") == deskcal.DIM]
check(rings, "시험과 같은 날이어도 일정을 다 끝내면 빈 동그라미가 뜸")
del app.events[deskcal.key_of(ring_day)]
app.set_view("tt")

# 합쳐 보이는 수업은 블록 전체를 고친다
app.set_view("tt")
app.tt_sel = (0, 2)                       # 高等数学（B）월 1–2교시 중 2교시를 골라도
app.render_panel()
app.tt_room.delete(0, "end")
app.tt_room.insert(0, "三教999")
app.tt_commit()
tt = json.load(open(deskcal.TT_FILE, encoding="utf-8"))
check(tt["0-1"]["room"] == tt["0-2"]["room"] == "三教999", "강의실을 고치면 1–2교시 둘 다 바뀜")
app.tt_set_color(deskcal.PALETTE[6])
tt = json.load(open(deskcal.TT_FILE, encoding="utf-8"))
check(tt["0-1"]["color"] == tt["0-2"]["color"] == deskcal.PALETTE[6], "색도 블록 전체")
app.undo()
app.undo()

# 여러 칸 선택: 드래그 · Ctrl+클릭
app.set_view("tt")
app.update()


def at(di, p):
    return (int(app.tgut + (di + 0.5) * app.tcw), int(app.thh + (p - 0.5) * app.tch))


x, y = at(2, 9)
app.cal.event_generate("<ButtonPress-1>", x=x, y=y)
x, y = at(3, 10)
app.cal.event_generate("<B1-Motion>", x=x, y=y, state=0x100)
app.cal.event_generate("<ButtonRelease-1>", x=x, y=y)
app.update()
check(app.tt_multi == {(2, 9), (2, 10), (3, 9), (3, 10)}, "드래그로 사각형 범위 선택: %r" % app.tt_multi)
x, y = at(4, 12)
app.cal.event_generate("<Control-Button-1>", x=x, y=y, state=0x4)
app.update()
check((4, 12) in app.tt_multi and len(app.tt_multi) == 5, "Ctrl+클릭으로 칸 더하기")
app.tt_title.insert(0, "세미나")
app.tt_room.insert(0, "二教101")
app.tt_commit()
tt = json.load(open(deskcal.TT_FILE, encoding="utf-8"))
check(all(tt.get(k, {}).get("title") == "세미나" for k in ("2-9", "2-10", "3-9", "3-10", "4-12")),
      "입력한 과목이 고른 칸 모두에 들어감")
app.cal.event_generate("<Control-Button-1>", x=x, y=y, state=0x4)
app.update()
check((4, 12) not in app.tt_multi, "Ctrl+클릭을 다시 하면 그 칸이 빠짐")
app.tt_delete()
tt = json.load(open(deskcal.TT_FILE, encoding="utf-8"))
check(not any(k in tt for k in ("2-9", "2-10", "3-9", "3-10")) and "4-12" in tt,
      "지우기는 고른 칸만")
app.undo()
app.undo()
x, y = at(0, 1)
app.cal.event_generate("<ButtonPress-1>", x=x, y=y)
app.cal.event_generate("<ButtonRelease-1>", x=x, y=y)
app.update()
check(app.tt_multi is None and app.tt_sel == (0, 1), "그냥 클릭하면 여러 칸 선택이 풀림")

# 버그 재현: 수업이 섞인 범위를 드래그했다가, 아무것도 안 고치고 다른 곳을 드래그
before = json.load(open(deskcal.TT_FILE, encoding="utf-8"))
for a, b in ((at(0, 1), at(1, 3)), (at(3, 9), at(4, 10))):
    app.cal.event_generate("<ButtonPress-1>", x=a[0], y=a[1])
    app.cal.event_generate("<B1-Motion>", x=b[0], y=b[1], state=0x100)
    app.cal.event_generate("<ButtonRelease-1>", x=b[0], y=b[1])
    app.update()
check(json.load(open(deskcal.TT_FILE, encoding="utf-8")) == before,
      "여러 칸을 골랐다가 다른 곳을 골라도 수업이 지워지거나 바뀌지 않음")
check(app.tt_title.get() == "", "수업이 섞인 범위면 입력칸을 비워 둠")
app.tt_room.insert(0, "三教777")
app.tt_commit()
tt = json.load(open(deskcal.TT_FILE, encoding="utf-8"))
check(all(tt[k]["room"] == "三教777" for k in ("3-9", "3-10") if k in tt)
      and all(k not in tt for k in ("4-9", "4-10") if k not in before),
      "강의실만 고치면 수업이 있는 칸의 강의실만 바뀜 (빈칸에 수업을 만들지 않음)")
app.undo()

# 시험 완료 표시
app.toggle_exam("高等数学（B）", "fin")
check(app.exam_done("高等数学（B）", "fin"), "시험 네모를 누르면 완료")
app.today = app.selected = dt.date(2027, 1, 1)     # 시험 날이 아닌 날을 골라야 패널과 안 섞임
app.set_view("cal")
labels = [w.cget("text") for w in walk(app.panel, []) if w.winfo_class() == "Label"]
up = "%s · 高等数学（B）" % app.t("exam_fin_s")
check(not any(t.startswith(up) for t in labels), "완료한 시험은 다가오는 일정에서 빠짐")
app.today = dt.date.today()
app.set_view("tt")
app.tt_sel = (0, 1)
app.render_panel()
app.tt_room.insert("end", "x")
app.tt_commit()
check(app.exam_done("高等数学（B）", "fin"), "시간표에서 고쳐 저장해도 완료 표시가 남음")
app.destroy()

# ------------------------------------------------------------------
app, d = fresh(files={"courses.json": {"과목": {"mid_date": "11-09", "asg_date": "实践"}}})
saved = json.load(open(deskcal.COURSE_FILE, encoding="utf-8"))["과목"]
check(saved["mid_date"].endswith("-11-09") and len(saved["mid_date"]) == 10
      and saved["asg_date"] == "实践", "켤 때 연도 없는 날짜를 정리 (날짜가 아닌 글은 그대로)")
app.destroy()

# ------------------------------------------------------------------
section("시간표 수정 시 시험 정보 동기화 · 달력 잔여 데이터 방지")
tt_bug = {"0-1": {"title": "수학", "room": "101", "color": "#e0555f", "week": "all"},
          "0-2": {"title": "수학", "room": "101", "color": "#e0555f", "week": "all"}}
courses_bug = {"수학": {"mid_date": "2026-11-10", "mid_time": "10:00"}}
app, d = fresh(files={"timetable.json": tt_bug, "courses.json": courses_bug})
exam_d = dt.date(2026, 11, 10)
check(len(app.exams_on(exam_d)) == 1 and app.exams_on(exam_d)[0][1] == "수학",
      "시간표 과목의 시험이 달력에 정상 표시됨")

# 1. 수업 삭제 시 달력 및 courses.json 에서 시험 정보 동기화 삭제
app.set_view("tt")
app.tt_sel = (0, 1)
app.render_panel()
app.tt_delete()
check("수학" not in app.courses and len(app.exams_on(exam_d)) == 0,
      "시간표에서 수업 삭제 시 달력과 courses.json 에서 시험 정보도 함께 삭제됨")
app.undo()
check("수학" in app.courses and len(app.exams_on(exam_d)) == 1,
      "Ctrl+Z 실행 취소 시 삭제되었던 시험 정보도 함께 복구됨")

# 2. 과목명 수정(Rename) 시 시험 정보가 새 과목명으로 이전됨
app.tt_title.delete(0, "end")
app.tt_title.insert(0, "고급수학")
app.tt_title_changed()
app.tt_commit()
check("고급수학" in app.courses and "수학" not in app.courses
      and app.exams_on(exam_d)[0][1] == "고급수학",
      "과목명을 변경하면 시험 정보도 새 과목명으로 수정되고 달력에 이전 과목이 남지 않음")
app.destroy()

# 3. 시간표 정리 시 시간표에 없는 이전 유령 과목 정리
dirty = {"물리": {"fin_date": "2026-12-20", "fin_time": ""},
         "지워진과목": {"mid_date": "2026-11-10", "mid_time": "14:00"}}
app, d = fresh(files={"timetable.json": {"0-1": {"title": "물리", "room": "102", "color": "#4d9df5", "week": "all"}},
                      "courses.json": dirty})
app.cleanup_orphan_courses()
check("지워진과목" not in app.courses and len(app.exams_on(exam_d)) == 0,
      "시간표 정리 시 시간표에 없는 유령 과목이 정리되어 달력에 남지 않음")
app.destroy()

# ------------------------------------------------------------------
section("exe · 윈도우 시작 시 실행")
deskcal.RUN_NAME = "DeskCal_test_%d" % os.getpid()      # 진짜 'DeskCal' 값은 건드리지 않는다
cmd = deskcal.launch_command()
check("deskcal.py" in cmd and cmd.endswith("--autostart") and "pythonw" in cmd.lower(),
      "스크립트 실행 명령: %s" % cmd)
deskcal.set_autostart(True)
check(deskcal.autostart_enabled(), "켜면 레지스트리에 등록됨")
deskcal.set_autostart(False)
check(not deskcal.autostart_enabled(), "끄면 지워짐")
app, d = fresh()
app.init_autostart()
check(deskcal.autostart_enabled() and json.load(open(deskcal.CONF_FILE))["autostart"] is True,
      "처음 켜면 자동 실행이 켜짐")
app.set_autostart_pref(False)
app.init_autostart()
check(not deskcal.autostart_enabled(), "메뉴에서 끄면 다음에 켜도 다시 켜지지 않음")
app.destroy()
deskcal.FROZEN = True
check(deskcal.default_data_dir() == os.path.join(os.environ["LOCALAPPDATA"], "DeskCal"),
      "exe 는 %LOCALAPPDATA%\\DeskCal 에 저장")
deskcal.FROZEN = False
check(deskcal.default_data_dir() == os.path.join(deskcal.HERE, "data"), "스크립트는 옆 data 폴더")

# ------------------------------------------------------------------
n_fail = RESULTS.count(False)
print("\n%d개 중 %d개 통과%s" % (len(RESULTS), len(RESULTS) - n_fail,
                             "" if not n_fail else " — 실패 %d개" % n_fail))
sys.exit(1 if n_fail else 0)
