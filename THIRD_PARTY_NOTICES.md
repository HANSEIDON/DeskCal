# Third-party notices

DeskCal's own code uses only the Python standard library, plus
[pywebview](https://pywebview.flowrl.com/) for the optional PKU portal sign-in window.
The Windows release (`DeskCal-*-windows-x64.zip`) bundles the following third-party
components so it can run without a Python installation.

| Component | Used for | License |
| --- | --- | --- |
| [Noto Sans CJK SC](https://github.com/notofonts/noto-cjk) | UI font (Chinese, Korean, Latin) | SIL Open Font License 1.1 |
| [Python](https://www.python.org/) 3.12 runtime and standard library | Runs the app | [Python Software Foundation License](https://docs.python.org/3/license.html) |
| [Tcl/Tk](https://www.tcl-lang.org/) 8.6 | Window and drawing toolkit (tkinter) | [Tcl/Tk license](https://www.tcl-lang.org/software/tcltk/license.html) (BSD-style) |
| [pywebview](https://github.com/r0x0r/pywebview) | PKU portal sign-in window | BSD 3-Clause |
| [Python.NET](https://github.com/pythonnet/pythonnet) and clr_loader | Used by pywebview to talk to WebView2 | MIT |
| bottle, cffi, pycparser, proxy_tools, typing_extensions | pywebview dependencies | MIT / MIT-0 / BSD 3-Clause / MIT / PSF |
| [Microsoft WebView2 SDK](https://www.nuget.org/packages/Microsoft.Web.WebView2/) | Shipped inside pywebview; uses the WebView2 Runtime built into Windows | Microsoft WebView2 SDK license |
| [PyInstaller](https://pyinstaller.org/) bootloader | Starts the bundled app (`DeskCal.exe`) | GPL 2.0 with an exception that allows distributing bundled apps under any license ([details](https://pyinstaller.org/en/stable/license.html)) |

The full license texts are in the `licenses` folder of the release. In this
repository, the font license is `fonts/OFL-LICENSE.txt`.

The font is loaded privately by DeskCal while it runs. It is not installed on
your system.
