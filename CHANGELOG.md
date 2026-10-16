# Changelog

## 1.1.3 — 2026-10-16

### Changed

- **Importing from the PKU portal is paused.** The import signed in through the portal's
  existing sign-in registration, and the PKU Computing Center has told us other apps may
  not reuse it. The button now explains that DeskCal is waiting for the university's
  official permission. The import will return once it's approved. Versions 1.1.0–1.1.2,
  which include the old import, are no longer offered for download.
- The release no longer bundles pywebview, so the download is about 4 MB smaller.

## 1.1.2 — 2026-10-16

### Fixes

- The frosted glass now follows wallpaper changes. With Windows Spotlight or a slideshow,
  the glass (and the glass shown while dragging) kept showing the previous wallpaper until
  DeskCal was restarted. DeskCal now notices the new wallpaper within a few seconds,
  including the change Windows makes shortly after you sign in.
- Adding, removing or renaming files and folders on the desktop also refreshes the glass,
  since desktop icons show through it.

### Improvements

- Better text contrast on bright wallpapers: the glass gets just dark enough that text
  stays easy to read, measured against each user's own wallpaper.

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
