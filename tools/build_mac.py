# -*- coding: utf-8 -*-
"""DeskCal macOS 빌드 및 DMG 패키징 스크립트.

Usage (on macOS or GitHub Actions macOS runner):
    python tools/build_mac.py

학교 课表 가져오기(ISOP)는 공개 저장소에 없는 private/ 폴더가 있을 때만 들어간다. 그 폴더가
앱에 가져오기 기능(deskcal_addon)과 서명 모듈 빌더(build_native)를 넣는다. 서명 모듈 자체는
환경 변수 ISOP_APP_KEY / ISOP_APP_SECRET 이 있을 때만 만들어진다 (private/build_native.py 참고).
private/ 가 없으면(포크·공개 빌드) 가져오기 없는 앱이 만들어진다.
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
PRIV = os.path.join(ROOT, "private")

# 가져오기 기능 빌더는 private/ 에만 있다. 없으면(공개 빌드) 가져오기 없이 간다.
build_native = None
if os.path.isdir(PRIV):
    sys.path.insert(0, PRIV)
    try:
        import build_native  # noqa: E402
    except ImportError:
        build_native = None


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

    # --- Step 0: 가져오기 기능 (private/ 가 있을 때만) ---
    print("[0/3] Timetable import add-on...")
    isop_module = None
    if build_native is not None:
        print("private/ found - building the import add-on into the app.")
        isop_module = build_native.build(require="--require-isop" in sys.argv[1:])
    else:
        print("private/ not found - building WITHOUT the school timetable import.")
        if os.environ.get("GITHUB_ACTIONS"):
            print("::warning title=Timetable import disabled::private/ was not checked out")

    # --- Step 1: Packaging Standalone macOS .app Bundle ---
    print("\n[1/3] Packaging Standalone macOS .app Bundle...")
    app_name = "DeskCal"
    icon_png = os.path.join(ROOT, "docs", "icon.png")

    pyi_cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        f"--name={app_name}",
        f"--distpath={BUILD}",
        f"--workpath={os.path.join(BUILD, 'pyi_work')}",
        "--hidden-import=AppKit",
        "--hidden-import=Foundation",
        "--hidden-import=objc",
        "--hidden-import=platform_helper",
        f"--paths={ROOT}",
        "--osx-bundle-identifier=com.hanseidon.deskcal",
    ]
    if build_native is not None:                       # 가져오기 기능을 앱 안에 넣는다
        pyi_cmd += [f"--paths={PRIV}", "--hidden-import=deskcal_addon"]
    if isop_module:
        pyi_cmd += [f"--add-binary={isop_module}:.", "--hidden-import=_isop_client"]

    if os.path.exists(icon_png):
        pyi_cmd.append(f"--icon={icon_png}")

    # 실행 중에 쓰는 그림은 아이콘뿐이다 (docs 의 설명용 스크린샷은 넣지 않는다)
    if os.path.exists(icon_png):
        pyi_cmd.append(f"--add-data={icon_png}:docs")

    pyi_cmd.append(os.path.join(ROOT, "deskcal.py"))

    run(*pyi_cmd)

    # Locate generated .app bundle
    app_bundle = os.path.join(BUILD, f"{app_name}.app")
    if not os.path.exists(app_bundle):
        # Fallback check
        alt = os.path.join(BUILD, "deskcal.app")
        if os.path.exists(alt):
            app_bundle = alt

    if not os.path.exists(app_bundle):
        raise RuntimeError(f"Build did not generate .app bundle at {app_bundle}!")

    print(f"Generated App Bundle: {app_bundle}")

    # 넣기로 한 것이 앱 안에 실제로 들어갔는지 확인한다
    def in_bundle(prefix):
        # 1. 앱 번들 파일시스템 상에 존재하는지 확인 (바이너리 모듈, 리소스 등)
        if any(name.startswith(prefix)
               for _dir, _sub, names in os.walk(app_bundle) for name in names):
            return True
        # 2. PyInstaller PYZ 아카이브 / TOC 에 포함되었는지 확인 (순수 파이썬 모듈)
        pyi_work = os.path.join(BUILD, "pyi_work")
        if os.path.exists(pyi_work):
            for _dir, _sub, names in os.walk(pyi_work):
                if "PYZ-00.toc" in names:
                    try:
                        with open(os.path.join(_dir, "PYZ-00.toc"), "r", encoding="utf-8", errors="ignore") as f:
                            toc_content = f.read()
                            if f"'{prefix}'" in toc_content or f'"{prefix}"' in toc_content:
                                return True
                    except Exception:
                        pass
        return False

    if build_native is not None:
        if not in_bundle("deskcal_addon"):
            raise RuntimeError("deskcal_addon is missing from the app bundle")
        if isop_module and not in_bundle("_isop_client"):
            raise RuntimeError("_isop_client was built but is missing from the app bundle")
        print("Timetable import: included (%s signing module)"
              % ("with" if isop_module else "WITHOUT"))
    else:
        print("Timetable import: NOT included (no private/)")

    # --- Step 2: Package into DMG ---
    print("\n[2/3] Creating DMG disk image...")
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
    print(f"\n[3/3] Creating portable ZIP: {zip_path}")
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
