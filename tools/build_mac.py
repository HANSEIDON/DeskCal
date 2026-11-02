# -*- coding: utf-8 -*-
"""DeskCal macOS 빌드 및 DMG 패키징 스크립트.

Usage (on macOS or GitHub Actions macOS runner):
    python tools/build_mac.py
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import sysconfig

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
DIST = os.path.join(ROOT, "dist")
TOOLS = os.path.join(ROOT, "tools")


def run(*cmd, env=None):
    print(">", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT, env=env)


def get_version():
    src = open(os.path.join(ROOT, "deskcal.py"), encoding="utf-8").read()
    m = re.search(r'^__version__ = "([\d.]+)"', src, re.M)
    return m.group(1) if m else "1.2.1"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def main():
    ver = get_version()
    print(f"=== DeskCal {ver} macOS Build Pipeline ===")

    os.makedirs(BUILD, exist_ok=True)
    os.makedirs(DIST, exist_ok=True)

    # --- Step 1: Compile Native C++ ISOP Client for macOS ---
    print("\n[1/4] Compiling macOS native C++ ISOP client (_isop_client.so)...")
    src_cpp = os.path.join(TOOLS, "_isop_client_mac.cpp")
    out_so = os.path.join(ROOT, "_isop_client.so")

    if os.path.exists(src_cpp):
        py_include = sysconfig.get_path("include")
        clang_cmd = [
            "clang++",
            "-std=c++17",
            "-O3",
            "-shared",
            "-undefined", "dynamic_lookup",
            f"-I{py_include}",
            src_cpp,
            "-lcurl",
            "-o", out_so,
        ]
        try:
            run(*clang_cmd)
            print("Successfully compiled _isop_client.so")
        except Exception as e:
            print(f"Warning: Failed to compile _isop_client_mac.cpp ({e}). Proceeding without ISOP.")

    # --- Step 2: Nuitka Machine-Code Compilation (.app Bundle) ---
    print("\n[2/4] Compiling with Nuitka (Python -> C -> Mach-O binary)...")
    app_name = "DeskCal"
    icon_png = os.path.join(ROOT, "docs", "icon.png")

    nuitka_cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--macos-create-app-bundle",
        f"--macos-app-name={app_name}",
        "--assume-yes-for-downloads",
        "--output-dir=build",
    ]

    if os.path.exists(icon_png):
        nuitka_cmd.append(f"--macos-app-icon={icon_png}")

    # Include data and docs
    if os.path.exists(os.path.join(ROOT, "data")):
        nuitka_cmd.append(f"--include-data-dir={os.path.join(ROOT, 'data')}=data")
    if os.path.exists(os.path.join(ROOT, "docs")):
        nuitka_cmd.append(f"--include-data-dir={os.path.join(ROOT, 'docs')}=docs")

    # If _isop_client.so was compiled, include it in the root of the app
    if os.path.exists(out_so):
        nuitka_cmd.append(f"--include-data-files={out_so}=_isop_client.so")

    nuitka_cmd.append(os.path.join(ROOT, "deskcal.py"))

    run(*nuitka_cmd)

    # Locate generated .app bundle
    app_bundle = os.path.join(BUILD, "deskcal.app")
    if not os.path.exists(app_bundle):
        # Alternative path depending on Nuitka output naming
        alt = os.path.join(BUILD, f"{app_name}.app")
        if os.path.exists(alt):
            app_bundle = alt

    if not os.path.exists(app_bundle):
        raise RuntimeError("Nuitka build did not generate .app bundle!")

    print(f"Generated App Bundle: {app_bundle}")

    # --- Step 3: Package into DMG ---
    print("\n[3/4] Creating DMG disk image...")
    dmg_name = f"DeskCal-{ver}-macOS.dmg"
    dmg_path = os.path.join(DIST, dmg_name)

    if os.path.exists(dmg_path):
        os.remove(dmg_path)

    # Temporary DMG staging folder with Applications shortcut symlink
    dmg_stage = os.path.join(BUILD, "dmg_stage")
    if os.path.exists(dmg_stage):
        shutil.rmtree(dmg_stage)
    os.makedirs(dmg_stage)

    # Copy .app to staging
    shutil.copytree(app_bundle, os.path.join(dmg_stage, "DeskCal.app"))

    # Create Applications symlink for drag-and-drop installation
    try:
        os.symlink("/Applications", os.path.join(dmg_stage, "Applications"))
    except OSError:
        pass

    # Use hdiutil to build compressed DMG
    hdiutil_cmd = [
        "hdiutil", "create",
        "-volname", "DeskCal",
        "-srcfolder", dmg_stage,
        "-ov",
        "-format", "UDZO",
        dmg_path,
    ]
    run(*hdiutil_cmd)

    # Also build a portable .zip release
    zip_name = f"DeskCal-{ver}-macOS.zip"
    zip_path = os.path.join(DIST, zip_name)
    print(f"\n[4/4] Creating portable ZIP: {zip_path}")
    run("ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", app_bundle, zip_path)

    # Checksums
    for target in [dmg_path, zip_path]:
        if os.path.exists(target):
            ck = sha256_file(target)
            size_mb = os.path.getsize(target) / (1024 * 1024)
            with open(f"{target}.sha256", "w", encoding="utf-8") as f:
                f.write(f"{ck}  {os.path.basename(target)}\n")
            print(f"\nCreated: {os.path.basename(target)} ({size_mb:.1f} MB)")
            print(f"SHA-256: {ck}")

    print("\n=== macOS Build Complete! ===")


if __name__ == "__main__":
    main()
