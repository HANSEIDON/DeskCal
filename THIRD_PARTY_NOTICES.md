# Third-party notices

DeskCal's own code has no dependencies beyond the Python standard library. The
Windows release (`DeskCal-*-windows-x64.zip`) bundles the following third-party
components so it can run without a Python installation.

| Component | Used for | License |
| --- | --- | --- |
| [Noto Sans CJK SC](https://github.com/notofonts/noto-cjk) | UI font (Chinese, Korean, Latin) | SIL Open Font License 1.1 |
| [Python](https://www.python.org/) 3.12 runtime and standard library | Runs the app | [Python Software Foundation License](https://docs.python.org/3/license.html) |
| [Tcl/Tk](https://www.tcl-lang.org/) 8.6 | Window and drawing toolkit (tkinter) | [Tcl/Tk license](https://www.tcl-lang.org/software/tcltk/license.html) (BSD-style) |
| [Nuitka](https://nuitka.net/) | Compiles `deskcal.py` to the bundled app (`DeskCal.exe`) | [Apache License 2.0](https://github.com/Nuitka/Nuitka/blob/main/LICENSE.txt) |

The full license texts are in the `licenses` folder of the release. In this
repository, the font license is `fonts/OFL-LICENSE.txt`.

The font is loaded privately by DeskCal while it runs. It is not installed on
your system.
