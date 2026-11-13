# Changelog

## Unreleased

### Added

- **Several classes in one slot.** A period can now hold more than one class, for example
  one on odd weeks and another on even weeks. Select the class, click **+ Another class
  here**, and type the other course. The classes are stacked like cards: the one that
  meets this week is in front, and clicking the card peeking out behind it brings that class
  forward. Classes that don't meet this week are dashed (issue #2).
- **Week ranges.** Each class has a weeks box: `1-8` for a half-semester course, `1,3,5-7`
  for any set of weeks, blank for the whole semester (issue #2).
- **Week numbers.** **⚙ → This week** sets which week of the semester it is. Odd / even
  follows the number, the timetable title shows it, and the calendar shows week numbers
  down the left side.

### Changed

- **PKU timetable import** keeps every class when two share a time slot (it used to keep
  only the first), and reads each class's first and last week, so half-semester courses
  come in with their range (issue #2).
- `.ics` export follows week ranges.

### Fixed

- The class panel on the Timetable tab scrolls when its content is taller than the widget
  (it used to be cut off at the bottom).
- **Start with Windows** repairs itself. If the startup entry went missing (for example
  after uninstalling another copy) or the app folder was moved, DeskCal registers it again
  the next time it starts.

## 1.3.0 — 2026-11-11

### Added

- **Event times.** Type the time with the title ("Dentist 3pm", "회의 오후 3시", "下午3点开会") and
  DeskCal reads the time from it and sorts the day's events by time. The title stays as typed.
- **Repeating events.** Click **↻** next to the color chips to make a new event weekly,
  every 2 weeks or monthly. Deleting asks whether to remove just that day or all following.
- **Multi-day events.** Click the first day, Shift+click the last day, then type. The event
  shows as a thin bar across those days.
- **All upcoming items.** Click the **Upcoming** title to see the whole list, grouped into
  this week, next week and later.
- **Compact mode** (**⚙ → Size → Compact**): a small window with today's classes, events and
  upcoming items, without the calendar grid.
- **Event titles on the calendar** at the two largest sizes, instead of dots.
- **Export.** **⚙ → Export .ics** writes a file that Google Calendar, Outlook and Apple
  Calendar can import (events, exams and weekly classes). **Export / Import backup** moves
  everything to another computer in one file.
- **Update notice.** Once a day DeskCal asks GitHub for the latest version number. When
  there is a newer one, a dot appears on **⚙** with a download button in settings. Nothing
  is sent, and you can turn it off in settings.
- Scroll the mouse wheel over the calendar to change month.

### Changed

- **Settings open inside the widget** (click **⚙** or right-click) instead of a pop-up menu.
  The **≡** button is now a **⚙** that stays lit while settings are open.
- Click an item in **Upcoming** to jump to its date.

### Fixed

- Right-clicking the desktop no longer sends the widget under the desktop.
- Dragging the widget is smoother.
- Switching between Calendar and Timetable no longer stutters or flickers. The widget used
  to rebuild itself and re-read the desktop on every switch.
- Changing theme, size or language no longer flashes a blank widget.
- The circle around today's date, event dots and checkboxes now have smooth edges.
- Dropping the widget after a drag no longer flashes while its colors adjust to the new spot.
- Text typed into the new-event box is kept when you tick, delete or recolor another event.
- The ISOP import now tells you which courses could not be placed on the timetable.

## 1.2.1 — 2026-10-28

### Added

- **Weekend timetable.** Turn on **≡ → Show Weekend (Sat/Sun)** for a 7-day (Mon–Sun) timetable. Importing
  a PKU timetable with weekend classes switches it on automatically.

### Fixed

- The widget stays visible when *Show desktop* is clicked on the taskbar.
- Changing a course in the timetable keeps its exam dates on the calendar in sync.

## 1.2.0 — 2026-10-26

### Added

- **Import your PKU timetable.** The app can pull your official 课表 from the university
  through the ISOP platform: enter your student ID and the code sent to your PKU email, then
  review and tick which changes to apply. Nothing is overwritten until you confirm.
- **Tick classes and exams off** on the calendar and timetable. Finished items show as hollow
  markers and drop out of Upcoming.
- **Edit several timetable cells at once** by dragging or Ctrl+clicking them.

### Changed

- New liquid-glass app icon.
- The release is now compiled with Nuitka instead of PyInstaller.
- The calendar shows a mark per event with a "+N" overflow, and dialogs open centered on the
  widget.

### Fixed

- Crash logging and a redraw flicker when the view returned to today.

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
