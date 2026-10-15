"""Builds the Windows release: dist/DeskCal-<version>-windows-x64.zip

    python tools/build.py

Steps: create an isolated build environment (.build-venv) with the pinned PyInstaller,
draw the icon, write the exe version info, bundle deskcal.py + fonts into a folder
(DeskCal/DeskCal.exe + DeskCal/_internal), then zip it and print the SHA-256.
"""
import glob
import hashlib
import os
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
DIST = os.path.join(ROOT, "dist")
VENV = os.path.join(ROOT, ".build-venv")
VPY = os.path.join(VENV, "Scripts", "python.exe")


def run(*cmd):
    print(">", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


def version():
    src = open(os.path.join(ROOT, "deskcal.py"), encoding="utf-8").read()
    return re.search(r'^__version__ = "([\d.]+)"', src, re.M).group(1)


def version_file(ver, path):
    """Windows file properties (Details tab) for DeskCal.exe."""
    nums = tuple(int(n) for n in (ver.split(".") + ["0", "0", "0"])[:4])
    fields = {"CompanyName": "", "FileDescription": "DeskCal desktop calendar",
              "FileVersion": ver, "InternalName": "DeskCal",
              "OriginalFilename": "DeskCal.exe", "ProductName": "DeskCal",
              "ProductVersion": ver}
    strings = ",\n".join("          StringStruct(%r, %r)" % kv for kv in fields.items())
    with open(path, "w", encoding="utf-8") as f:
        f.write("""VSVersionInfo(
  ffi=FixedFileInfo(filevers=%(n)r, prodvers=%(n)r, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
%(s)s])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""" % {"n": nums, "s": strings})


def main():
    ver = version()
    if not os.path.exists(VPY):
        run(sys.executable, "-m", "venv", VENV)
    run(VPY, "-m", "pip", "install", "--disable-pip-version-check", "-q",
        "-r", os.path.join(ROOT, "tools", "requirements-build.txt"))
    if os.path.exists(BUILD):
        shutil.rmtree(BUILD)          # fails loudly if a file in it is still open
    os.makedirs(BUILD)
    icon = os.path.join(BUILD, "deskcal.ico")
    run(VPY, os.path.join(ROOT, "tools", "make_icon.py"), icon)
    vfile = os.path.join(BUILD, "version_info.txt")
    version_file(ver, vfile)
    out = os.path.join(BUILD, "dist")
    run(VPY, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir",
        "--name", "DeskCal", "--icon", icon, "--version-file", vfile,
        "--add-data", os.path.join(ROOT, "fonts") + os.pathsep + "fonts",
        "--distpath", out, "--workpath", os.path.join(BUILD, "work"),
        "--specpath", BUILD, os.path.join(ROOT, "deskcal.py"))
    app = os.path.join(out, "DeskCal")
    for name in ("README.md", "CHANGELOG.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy(os.path.join(ROOT, name), app)
    # License texts of everything bundled, in one visible folder (see THIRD_PARTY_NOTICES.md)
    lic = os.path.join(app, "licenses")
    os.makedirs(lic)
    base = subprocess.run([VPY, "-c", "import sys; print(sys.base_prefix)"], check=True,
                          capture_output=True, text=True).stdout.strip()
    for src, name in ((os.path.join(base, "LICENSE.txt"), "Python-LICENSE.txt"),
                      (os.path.join(app, "_internal", "_tk_data", "license.terms"),
                       "TclTk-LICENSE.txt"),
                      (os.path.join(ROOT, "fonts", "OFL-LICENSE.txt"),
                       "NotoSansCJK-OFL-LICENSE.txt")):
        shutil.copy(src, os.path.join(lic, name))
    site = os.path.join(VENV, "Lib", "site-packages")      # pywebview and what it needs
    for pkg in ("pywebview", "pythonnet", "clr_loader", "bottle", "cffi", "pycparser",
                "typing_extensions"):
        for info in glob.glob(os.path.join(site, pkg + "-*.dist-info")):
            for src in glob.glob(os.path.join(info, "licenses", "LICENSE*")):
                shutil.copy(src, os.path.join(lic, "%s-LICENSE.txt" % pkg))
    with open(os.path.join(lic, "WebView2-NOTICE.txt"), "w", encoding="utf-8") as f:
        f.write("The PKU portal sign-in window uses Microsoft Edge WebView2. pywebview ships the\n"
                "WebView2 SDK libraries (Microsoft.Web.WebView2.*.dll, WebView2Loader.dll),\n"
                "redistributable under the Microsoft WebView2 SDK license:\n"
                "https://www.nuget.org/packages/Microsoft.Web.WebView2/\n"
                "The WebView2 Runtime itself is part of Windows and is not bundled.\n")
    with open(os.path.join(lic, "PyInstaller-LICENSE.txt"), "w", encoding="utf-8") as f:
        f.write("DeskCal.exe starts through the PyInstaller bootloader, licensed under the\n"
                "GPL 2.0 with an exception that allows distributing bundled programs under\n"
                "any license: https://pyinstaller.org/en/stable/license.html\n")

    os.makedirs(DIST, exist_ok=True)
    zpath = os.path.join(DIST, "DeskCal-%s-windows-x64.zip" % ver)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for base, _, files in os.walk(app):
            for f in files:
                full = os.path.join(base, f)
                z.write(full, os.path.join("DeskCal", os.path.relpath(full, app)))
    digest = hashlib.sha256(open(zpath, "rb").read()).hexdigest()
    with open(zpath + ".sha256", "w") as f:
        f.write("%s  %s\n" % (digest, os.path.basename(zpath)))
    print("\n%s  (%.1f MB)\nSHA-256: %s" % (zpath, os.path.getsize(zpath) / 1e6, digest))


if __name__ == "__main__":
    main()
