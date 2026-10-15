# DeskCal — Desktop Calendar & Timetable for PKU Students

A calendar and class timetable that lives on your Windows desktop. It sits just above the
wallpaper, stays visible through *Show desktop* (Win+D), and keeps everything on your own
machine. No account, no sync, no internet.

Made for student life at Peking University (PKU): assignment deadlines, exams,
course registration (选课) dates, to-dos, and a weekly timetable that follows PKU's class
periods and understands odd/even-week classes (单周 / 双周). Students at other schools can
use it too, since the period times are configurable.

*DeskCal is an independent project and is not affiliated with Peking University.*

![Calendar view, dark theme](docs/calendar-dark.png)

## Features

- **Calendar with notes.** Click a day and type. Each event gets a color, can be ticked off
  (it gets crossed out), and can be edited or deleted in place.
- **Upcoming list.** Shows the next events, exams and deadlines with D-day badges. Badges
  turn orange within a week and red for today and tomorrow.
- **Timetable.** Monday to Friday, 12 periods. Consecutive periods of the same class merge
  into one tile. The class happening right now is outlined and tagged **Now** (or **Next**
  during a break).
- **Odd / even weeks.** Mark a class as every week, odd weeks or even weeks. Classes that
  don't meet this week are drawn as dashed outlines.
- **Exams and deadlines per course.** Midterm, final exam and final project dates, picked
  from a calendar, with a time or a short note. They show up in the Upcoming list.
- **Frosted-glass look.** The widget blurs the wallpaper behind it, including while you
  drag it around. Text colors are adjusted to the wallpaper, so they stay readable on
  bright or dark backgrounds.
- **Dark and light themes, English / 한국어 / 中文.** The CJK font is bundled, so Chinese,
  Korean and Latin text all render in one consistent typeface.
- **Autosave and undo.** Every change is saved immediately. Ctrl+Z undoes, and Ctrl+C / V / X / A
  work in all text boxes (also with a Korean or Chinese IME active).
- **Stays out of the way.** It lives behind your other windows. Win+D shows it. Launching
  it again brings the running widget to the front instead of starting a second copy.
- **Light on resources.** Uses about 100 MB of memory and almost no CPU when idle.

![Timetable view, dark theme](docs/timetable-dark.png)

| Light theme | 中文 |
| --- | --- |
| ![Calendar view, light theme](docs/calendar-light.png) | ![Timetable in Chinese, light theme](docs/timetable-light-zh.png) |

## Requirements

**Windows only.** DeskCal relies on Win32 APIs for the desktop layering and the glass
effect, so it won't run on macOS or Linux. It was developed on Windows 11 (64-bit).
Windows 10 should work, but it hasn't been tested.

## Install

There are two ways to run DeskCal. Both have the same features.

### Option 1: Download the app (no Python needed)

1. Go to [**Releases**](../../releases/latest) and download `DeskCal-<version>-windows-x64.zip`.
2. Extract the zip anywhere you like, for example into your Documents folder.
3. Open the extracted `DeskCal` folder and double-click **`DeskCal.exe`**.

There is no installer. The folder contains the app and everything it needs (Python
runtime, UI toolkit, font). Keep the files in the folder together.

**"Windows protected your PC" warning.** The exe is not code-signed (signing certificates
cost money), so on the first launch Windows SmartScreen may show this warning. Click
**More info → Run anyway**. Some antivirus products also flag apps built with PyInstaller
by mistake. If you'd rather not trust a downloaded exe, use Option 2 or build the exe
yourself from this source (see [Building the exe](#building-the-exe)).

**Check the download (optional).** Each release lists the SHA-256 checksum of the zip
(also in the `.sha256` file next to it). In PowerShell:

```powershell
Get-FileHash .\DeskCal-1.0.0-windows-x64.zip
```

The printed hash should match the one on the release page.

### Option 2: Run from source

1. Install Python 3 from [python.org](https://www.python.org/downloads/windows/). The
   default options are fine, and tkinter is included. Tested with Python 3.12.
2. Download this repository (**Code → Download ZIP**, then extract it), or clone it:

   ```bash
   git clone https://github.com/HANSEIDON/DeskCal-Desktop-Calendar-Timetable-for-PKU-Students.git
   ```

3. Double-click **`DeskCal.bat`**.

There are no third-party packages to install.

## Start with Windows

Open the menu (**≡**) and turn on **Start with Windows**. DeskCal then starts quietly behind
your windows when you sign in. This adds a `DeskCal` entry under
`HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`, which only affects your
user account and needs no admin rights. Turn the option off to remove it.

If you move the DeskCal folder later, turn the option off and on again so it points to the
new location.

## Using it

| To | Do |
| --- | --- |
| Move the widget | Drag any empty area (the title bar or around the calendar) |
| Open settings | Click **≡**, or right-click the title bar or calendar |
| Add an event | Select a day, type in the box, press Enter or click **Add** |
| Complete an event | Click the colored dot. Click again to undo |
| Recolor an event | Right-click the dot |
| Edit or delete an event | Click its title to edit. Click **×** to delete |
| Undo | Ctrl+Z |
| Add a class | In **Timetable**, click a cell and type the course name. It saves as you type |
| Make a class odd/even-week | Choose **Every / Odd / Even** in the side panel |
| Add exam dates | Select a class, then pick dates under **Exams · Deadlines** |
| Set which week is odd | **≡ → Odd / even week** |
| Quit | **≡ → Quit** |

After two minutes without input, the calendar returns to today unless you are in the
middle of typing.

The settings menu also has **Language**, **Theme**, **Background** (Glass subtle, Glass
clear or Solid), **Size** (five fixed sizes) and **Always on top / Keep on desktop**.

## Your data

Everything stays on your computer. DeskCal never connects to the internet.

| Running | Data folder |
| --- | --- |
| `DeskCal.exe` | `%LOCALAPPDATA%\DeskCal` |
| From source | `data` folder next to `deskcal.py` |

**≡ → Open data folder** opens it. To keep the data somewhere else, set the `DESKCAL_DIR`
environment variable to that folder.

| File | Contents |
| --- | --- |
| `events.json` | Calendar events |
| `timetable.json` | Timetable cells |
| `courses.json` | Exam and deadline dates per course |
| `config.json` | Window position, size, theme, language, and other settings |
| `error.log` | Diagnostic log |

Each save writes a `.bak` copy of the previous version. If a file can't be read, saving is
paused so the existing file is never overwritten with empty data.

### Class period times

The period times default to PKU's schedule for the main campus and Health Science Center
(校本部 / 医学部: period 1 is 08:00–08:50 … period 12 is 20:40–21:30). To change them, quit DeskCal and add a `periods` list with 12
`"HH:MM-HH:MM"` entries to `config.json`:

```json
{
  "periods": ["08:00-08:50", "09:00-09:50", "10:10-11:00", "11:10-12:00",
              "13:00-13:50", "14:00-14:50", "15:10-16:00", "16:10-17:00",
              "17:10-18:00", "18:40-19:30", "19:40-20:30", "20:40-21:30"]
}
```

## Updating and uninstalling

**Update:** quit DeskCal, then replace the `DeskCal` folder with the one from the new
release. Your data is kept because it lives in `%LOCALAPPDATA%\DeskCal`, not in the app
folder.

**Uninstall:**

1. Turn off **≡ → Start with Windows** if you turned it on.
2. Quit DeskCal and delete the `DeskCal` folder.
3. To remove your data as well, delete `%LOCALAPPDATA%\DeskCal`.

DeskCal makes no other changes to your system.

## Development

The app is a single file, `deskcal.py`. It uses tkinter plus Win32 calls through `ctypes`,
and nothing outside the Python standard library.

```bash
python tests/test_deskcal.py        # unit tests (uses temporary folders, never your data)
python tests/real_input_check.py    # drives the real mouse and keyboard for a few seconds
python tests/make_screenshots.py    # regenerates the images in docs/ from demo data
```

### Building the exe

```bash
python tools/build.py
```

This creates an isolated build environment in `.build-venv`, installs the pinned
PyInstaller version from `tools/requirements-build.txt`, draws the icon
(`tools/make_icon.py`) and writes `dist/DeskCal-<version>-windows-x64.zip` plus its
`.sha256` file. The version number comes from `__version__` in `deskcal.py`.

## License

DeskCal is released under the [MIT License](LICENSE).

## Third-party components

DeskCal bundles [Noto Sans CJK SC](https://github.com/notofonts/noto-cjk) (SIL Open Font
License) in `fonts/`. It is loaded privately while the app runs and is not installed on
your system. The exe additionally bundles the Python runtime, Tcl/Tk and the PyInstaller
bootloader. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for their licenses.
