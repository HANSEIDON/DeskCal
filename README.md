<div align="center">

<img src="docs/icon.png" width="96" alt="DeskCal icon">

# DeskCal

**Desktop calendar & timetable for PKU students**

[![Release](https://img.shields.io/github/v/release/HANSEIDON/DeskCal)](https://github.com/HANSEIDON/DeskCal/releases/latest)
![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D6)
[![License](https://img.shields.io/github/license/HANSEIDON/DeskCal)](LICENSE)

<br>

[![PKU ISOP](https://img.shields.io/badge/PKU%20ISOP-Powered%20%E2%80%A2%20Timetable%20Import-1a1a1a?style=for-the-badge&labelColor=8A0011)](#-import-your-pku-timetable)

<br><br>

<a href="https://github.com/HANSEIDON/DeskCal/releases/latest">
  <img src="https://img.shields.io/badge/Download%20for%20Windows-v1.2.0%20Setup.exe-0078D4?style=for-the-badge&logo=windows&logoColor=white" height="38" alt="Download DeskCal">
</a>
<br>
<sub>⚡ <b>1-Click Installer</b> • No Admin Rights Needed • Desktop Shortcut Included</sub>

</div>

DeskCal sits on your Windows desktop, just above the wallpaper. Deadlines, exams,
选课 dates and your weekly timetable are always one glance away. It runs fully offline
and needs no account.

> **New in 1.2.0 — [import your official 课表](#-import-your-pku-timetable).** DeskCal is powered by Peking University's official data platform (ISOP), so it can load your real
> timetable and exam dates straight from the university instead of you typing them in.

![Calendar view, dark theme](docs/calendar-dark.png)

## ✨ Features

- 🎓 **Import your PKU timetable** straight from the university through the official ISOP
  platform — review what changed, then apply ([details](#-import-your-pku-timetable)).
- 📅 **Calendar with notes**: click a day and type. Color it, tick it off, edit in place.
- ⏰ **Upcoming deadlines** with D-day badges. Orange within a week, red for today and tomorrow.
- 🗓️ **Timetable**: Mon–Fri, 12 periods on PKU's schedule. The current class is highlighted.
- 🔁 **Odd / even weeks** (单周 / 双周). Classes not meeting this week are shown dashed.
- 📝 **Exams on the calendar**: midterm, final and project deadlines per course appear on the
  calendar and in Upcoming.
- 🪟 **Always on the desktop**, even after Win+D. Frosted-glass look, dark and light themes.
- 🌐 **English / 한국어 / 中文**, with a bundled font so CJK text renders cleanly.
- 💾 **Autosave and Ctrl+Z.** Light on resources: about 75 MB of memory and under 1% of one CPU core when idle ([details](#-performance)).

![Timetable view, dark theme](docs/timetable-dark.png)


## 🚀 Install

> **Windows 10 / 11 only.** DeskCal uses Windows APIs and won't run on macOS or Linux.

### Option 1: Download the app (recommended)

1. Download **`DeskCal-<version>-Setup.exe`** (recommended) from [**Releases**](https://github.com/HANSEIDON/DeskCal/releases/latest) and run the installer.
   * Creates Desktop and Start Menu shortcuts automatically. No administrator rights required.
2. Run **`DeskCal`** from your desktop or start menu. No Python needed.

> [!NOTE]
> The exe isn't code-signed, so Windows may show **"Windows protected your PC"** on first
> launch. Click **More info → Run anyway**. Some antivirus tools also flag unsigned apps
> by mistake. If you prefer, run from source or [build the exe yourself](#building-the-exe).

<details>
<summary>Verify the download (optional)</summary>

Each release lists the installer's SHA-256 checksum. In PowerShell:

```powershell
Get-FileHash .\DeskCal-*-Setup.exe
```

The hash should match the one on the release page.
</details>

### Option 2: Run from source

1. Install [Python 3](https://www.python.org/downloads/windows/) with the default options.
2. Download this repo (**Code → Download ZIP**) or `git clone https://github.com/HANSEIDON/DeskCal.git`.
3. Double-click **`DeskCal.bat`**. No packages to install.

### Start with Windows

DeskCal starts with Windows by default, quietly behind your windows. To stop that, turn off
**≡ → Start with Windows**. The setting is an entry in your user's `Run` registry key (no
admin rights needed), and turning it off removes the entry.

## 🎓 Import your PKU timetable

![Registered PKU ISOP app](https://img.shields.io/badge/PKU%20ISOP-registered%20app-A51C30?style=flat-square)

A fresh install starts with an empty timetable — but you don't have to type in every class.
DeskCal is a **registered app on Peking University's data-sharing platform
(数据共享开放服务平台, ISOP)**, so it loads your official 课表 straight from the university,
verified by your PKU email. Open **Timetable → Import school timetable** and follow along:

| 1 · Enter your student ID | 2 · Enter the code from your PKU email |
| :---: | :---: |
| ![Student ID prompt over the app](docs/import-ask-dark.png) | ![PKU email code prompt over the app](docs/import-code-dark.png) |
| **3 · Review what will change, tick to apply** | **4 · Your timetable is filled in** |
| ![Review changes before applying](docs/import-review-dark.png) | ![Timetable filled in after importing](docs/import-filled-dark.png) |

Nothing is overwritten until you confirm. Everything goes through the official ISOP platform,
which needs the PKU network (use the campus VPN off campus); only your own timetable is read,
and nothing is uploaded.

> [!NOTE]
> DeskCal communicates directly and securely with Peking University over encrypted HTTPS. There are no intermediate servers or analytics, and all credentials remain solely on your local computer.
> Under confidentiality agreements with the university, the integration component is included only in the official release package rather than the open-source repository.

## 🖱️ How to use

| To | Do |
| --- | --- |
| Move the widget | Drag the title bar or the empty margin |
| Open settings | Click **≡**, or right-click the title bar or calendar |
| Add an event | Pick a day, type, press Enter |
| Complete / recolor | Click the dot / right-click the dot |
| Edit / delete | Click the title / click **×** |
| Undo | Ctrl+Z |
| Add a class | **Timetable** → click a cell → type the course name (saves automatically) |
| Odd / even-week class | **Every / Odd / Even** in the side panel |
| Exam dates | Select a class → **Exams · Deadlines**. They show on the calendar as squares |
| Set which week is odd | **≡ → Odd / even week** |

The settings menu also has language, theme, background and size. After two
idle minutes, the calendar jumps back to today.

## 💾 Your data

All data stays on your computer. Open the folder with **≡ → Open data folder**.

| Running | Data folder |
| --- | --- |
| `DeskCal.exe` | `%LOCALAPPDATA%\DeskCal` |
| From source | `data\` next to `deskcal.py` |

Every save keeps a `.bak` copy. Set `DESKCAL_DIR` to use a different folder.

<details>
<summary>Change the class period times</summary>

The default is PKU's 校本部 / 医学部 schedule (08:00–08:50 … 20:40–21:30). Quit DeskCal and
add 12 entries to `config.json`:

```json
{
  "periods": ["08:00-08:50", "09:00-09:50", "10:10-11:00", "11:10-12:00",
              "13:00-13:50", "14:00-14:50", "15:10-16:00", "16:10-17:00",
              "17:10-18:00", "18:40-19:30", "19:40-20:30", "20:40-21:30"]
}
```
</details>

<details>
<summary>Update or uninstall</summary>

- **Update:** quit DeskCal and replace the `DeskCal` folder with the new one. Your data is
  kept, because it's stored in `%LOCALAPPDATA%\DeskCal`.
- **Uninstall:** turn off **Start with Windows**, quit, and delete the `DeskCal` folder. To
  remove your data too, delete `%LOCALAPPDATA%\DeskCal`. DeskCal changes nothing else on
  your system.
</details>

## ⚡ Performance

DeskCal is built to sit on your desktop all day without you noticing it.

| | DeskCal 1.2.0 (exe) |
| --- | --- |
| Startup | about 1 second |
| Memory | about 73 MB |
| CPU while idle | 0.4 % of one core |
| Network | none by default (only connects to official PKU ISOP server when importing 课表) |
| Download / on disk | 40.0 MB zip / 65 MB folder, of which 32 MB is the CJK font |

Measured on Windows 11 with an Intel Core Ultra 7 258V and 32 GB RAM, using a fresh copy
with no data and the default glass background. Choosing **Background → Solid** uses a
little less memory and CPU.

While idle, DeskCal only checks whether *Show desktop* (Win+D) was pressed and whether the
wallpaper changed. Both checks take well under a millisecond, and the glass is only redrawn
when something actually changes, so the effect on battery life is negligible.

To measure on your own machine, quit DeskCal and run:

``powershell
powershell -ExecutionPolicy Bypass -File tools\benchmark.ps1
``

## 🛠️ Development

A single file, `deskcal.py`, using tkinter and Win32 calls via `ctypes`. Only the standard
library is used.

```bash
python tests/test_deskcal.py        # unit tests (temporary folders, never your data)
python tests/real_input_check.py    # drives the real mouse and keyboard briefly
python tests/make_screenshots.py    # regenerates docs/ images from demo data
```

### Building the exe

```bash
python tools/build.py
```

This builds `dist/DeskCal-<version>-windows-x64.zip` and its `.sha256` file, compiling
`deskcal.py` to machine code with [Nuitka](https://nuitka.net) in an isolated `.build-venv`.
The open-source build has no 课表 import (see the note above).

## 📝 Changelog

See [CHANGELOG.md](CHANGELOG.md).

## 📄 License

[MIT](LICENSE). Bundled third-party components (Noto Sans CJK SC font, Python runtime,
Tcl/Tk) are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

DeskCal is an independent project and is not affiliated with Peking University.
