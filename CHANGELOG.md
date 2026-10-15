# Changelog

## 1.1.1 — 2026-10-15

### Fixes

- The frosted glass could stop following the desktop while dragging the widget. This
  happened when the screen was redrawn (switching tabs, importing a timetable, changing
  theme or size) at the moment the glass was being prepared.

## 1.1.0 — 2026-10-15

### New

- **Import your timetable from PKU portal.** Sign in once in the window that opens and
  DeskCal fills in course names, rooms, periods, odd/even weeks (单周 / 双周) and final exam
  dates. Find it in **Timetable** (button at the bottom of the side panel) or the **≡** menu.
  - Courses you already have keep their colors.
  - Exam dates you entered yourself are never overwritten.
  - Classes you added by hand are kept.
  - Ctrl+Z undoes the whole import.
- **Exams on the calendar.** Midterm, final and project dates from the timetable now show on
  the calendar as small squares in the course's color, and in that day's panel. Click one to
  jump to the course in the timetable. Editing the date in either place updates both.
- **Start with Windows is on by default.** Turn it off in the **≡** menu. DeskCal remembers
  your choice.

### Improvements

- Chinese course names with brackets wrap more naturally: 高等数学 / （B） instead of
  高等数学（ / B）.
- Long English course names wrap at spaces, or with a hyphen if a single word is too long.
- Exam dots in **Upcoming** use the course's color.
- Smaller usability and wording improvements.

### Fixes

- Exam dates saved by very early versions without a year (for example `11-09`) are now
  recognized and stored with the year.

## 1.0.0 — 2026-10-15

First release.
