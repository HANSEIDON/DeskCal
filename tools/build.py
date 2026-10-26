"""Builds the Windows release: dist/DeskCal-<version>-windows-x64.zip

    python tools/build.py

Steps:
  1. Create an isolated build environment (.build-venv) with Nuitka
  2. Draw the icon
  3. Compile deskcal.py → C → machine code with Nuitka (no bytecode in output)
  4. Bundle fonts + icon, copy docs, zip it and print the SHA-256
"""
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
DATA = os.path.join(ROOT, "data")


def run(*cmd):
    print(">", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


def version():
    src = open(os.path.join(ROOT, "deskcal.py"), encoding="utf-8").read()
    return re.search(r'^__version__ = "([\d.]+)"', src, re.M).group(1)


def main():
    ver = version()

    # --- Step 1: Build environment ---
    print("\n[1/4] Setting up build environment ...")
    if not os.path.exists(VPY):
        run(sys.executable, "-m", "venv", VENV)
    run(VPY, "-m", "pip", "install", "--disable-pip-version-check", "-q",
        "nuitka", "ordered-set", "zstandard")
    # Install build requirements if present (e.g. Pillow for icon generation)
    reqs = os.path.join(ROOT, "tools", "requirements-build.txt")
    if os.path.exists(reqs):
        run(VPY, "-m", "pip", "install", "--disable-pip-version-check", "-q",
            "-r", reqs)

    # --- Step 2: Icon ---
    if os.path.exists(BUILD):
        shutil.rmtree(BUILD)
    os.makedirs(BUILD)
    icon = os.path.join(BUILD, "deskcal.ico")
    run(VPY, os.path.join(ROOT, "tools", "make_icon.py"), icon)

    # --- Step 3: Nuitka build ---
    print("\n[2/4] Compiling with Nuitka (Python → C → machine code) ...")
    out = os.path.join(BUILD, "dist")
    nuitka_cmd = [
        VPY, "-m", "nuitka",
        "--standalone",
        "--output-filename=DeskCal.exe",
        "--windows-console-mode=disable",
        "--include-package=tkinter",
        # Fonts + icon
        "--include-data-dir=" + os.path.join(ROOT, "fonts") + "=fonts",
        "--include-data-file=" + os.path.join(ROOT, "docs", "icon.png") + "=icon.png",
        # Output
        "--output-dir=" + out,
        "--remove-output",
        "--assume-yes-for-downloads",
        os.path.join(ROOT, "deskcal.py"),
    ]
    run(*nuitka_cmd)

    # Nuitka --standalone output: out/deskcal.dist/deskcal.exe + dependencies
    app = os.path.join(out, "deskcal.dist")
    if not os.path.exists(app):
        # Try alternate names
        for alt in ("deskcal", "DeskCal", "deskcal.dist"):
            candidate = os.path.join(out, alt)
            if os.path.exists(candidate):
                app = candidate
                break
    if not os.path.exists(app):
        contents = os.listdir(out) if os.path.exists(out) else []
        print("ERROR: Nuitka output folder not found. Contents of %s: %s" % (out, contents))
        sys.exit(1)

    # --- Step 4: Package ---
    print("\n[3/4] Copying docs + licenses ...")
    for name in ("README.md", "CHANGELOG.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        src = os.path.join(ROOT, name)
        if os.path.exists(src):
            shutil.copy(src, app)
    # License texts
    lic = os.path.join(app, "licenses")
    os.makedirs(lic, exist_ok=True)
    base = subprocess.run([VPY, "-c", "import sys; print(sys.base_prefix)"], check=True,
                          capture_output=True, text=True).stdout.strip()
    for src, name in ((os.path.join(base, "LICENSE.txt"), "Python-LICENSE.txt"),
                      (os.path.join(ROOT, "fonts", "OFL-LICENSE.txt"),
                       "NotoSansCJK-OFL-LICENSE.txt")):
        if os.path.exists(src):
            shutil.copy(src, os.path.join(lic, name))
    # Nuitka license
    with open(os.path.join(lic, "Nuitka-LICENSE.txt"), "w", encoding="utf-8") as f:
        f.write("DeskCal.exe is compiled with Nuitka (https://nuitka.net),\n"
                "licensed under the European Union Public Licence 1.2 (EUPL-1.2).\n")

    print("\n[4/4] Zipping ...")
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
