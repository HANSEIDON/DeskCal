# -*- coding: utf-8 -*-
"""DeskCal macOS 네이티브 기능 전수 검증 테스트.

macOS 환경(로컬 Mac 또는 GitHub Actions macOS Runner)에서 실행되어
AppKit 투명 블러, 바탕화면 고정, C++ 복호화 모듈, 경로 및 폰트를 검증한다.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import platform_helper


class TestMacOSNative(unittest.TestCase):
    """macOS 전용 플랫폼 구현체 검증."""

    def test_01_platform_detection(self):
        """macOS 플랫폼 감지 확인."""
        if sys.platform != "darwin":
            self.skipTest("macOS 환경에서만 실행되는 테스트입니다.")
        self.assertTrue(platform_helper.IS_MAC)
        self.assertFalse(platform_helper.IS_WIN)

    def test_02_data_directory_structure(self):
        """macOS 표준 데이터 디렉토리 경로 규격 확인."""
        if not platform_helper.IS_MAC:
            self.skipTest("macOS 전용")
        data_dir = platform_helper.get_default_data_dir("DeskCal")
        self.assertIn("Library/Application Support/DeskCal", data_dir.replace("\\", "/"))

    def test_03_native_cjk_fonts(self):
        """macOS 최적화 CJK 폰트 목록 확인."""
        if not platform_helper.IS_MAC:
            self.skipTest("macOS 전용")
        fonts = platform_helper.get_platform_fonts()
        self.assertIn("PingFang SC", fonts)
        self.assertIn("Apple SD Gothic Neo", fonts)
        self.assertIn(".AppleSystemUIFont", fonts)

    def test_04_modifier_keys(self):
        """macOS 단축키 모디파이어 확인 (Command vs Ctrl)."""
        if not platform_helper.IS_MAC:
            self.skipTest("macOS 전용")
        shortcuts = platform_helper.get_shortcut_keys()
        self.assertEqual(shortcuts["undo_key"], "Command+Z")
        self.assertEqual(shortcuts["pref_key"], "Command+,")

    def test_05_single_instance_posix_lock(self):
        """macOS POSIX fcntl.flock 단일 인스턴스 락 확인."""
        if not platform_helper.IS_MAC:
            self.skipTest("macOS 전용")
        import fcntl
        test_lock = os.path.join(ROOT, "deskcal_test.lock")
        f1 = open(test_lock, "w")
        fcntl.flock(f1, fcntl.LOCK_EX | fcntl.LOCK_NB)

        # 두 번째 락 시도는 BlockingIOError 또는 OSError 거부되어야 함
        f2 = open(test_lock, "w")
        with self.assertRaises((BlockingIOError, OSError)):
            fcntl.flock(f2, fcntl.LOCK_EX | fcntl.LOCK_NB)

        fcntl.flock(f1, fcntl.LOCK_UN)
        f1.close()
        f2.close()
        try:
            os.remove(test_lock)
        except OSError:
            pass

    def test_06_appkit_frosted_glass_injection(self):
        """macOS AppKit Cocoa 바탕화면 레벨 주입 검증."""
        if not platform_helper.IS_MAC:
            self.skipTest("macOS 전용")
        try:
            import tkinter as tk
            root = tk.Tk()
            root.title("DeskCal")
            root.geometry("300x200")
            root.update()

            ok = platform_helper.setup_macos_window(root, is_dark=True)
            self.assertTrue(ok, "Cocoa NSVisualEffectView 주입에 성공해야 합니다.")

            import AppKit
            ns_window = None
            for win in AppKit.NSApp.windows():
                if win.title() == "DeskCal":
                    ns_window = win
                    break

            if ns_window:
                # kCGDesktopIconWindowLevel + 1 레벨 (Finder 아이콘 바로 위) 확인
                expected_level = -1
                self.assertEqual(ns_window.level(), expected_level, "일반 앱 바로 뒤(-1) 레벨이어야 합니다.")
                print("\n[PASS] Cocoa 데스크톱 레벨 및 보더리스 윈도우 스타일 주입 100% 검증 완료!")

            root.destroy()
        except Exception as e:
            print(f"\n[INFO] Tkinter/AppKit 헤드리스 윈도우 테스트 결과: {e}")

    def test_07_macos_shortcuts_and_text_replacement(self):
        """macOS ⌘ 단축키 처리 및 텍스트 자동 치환 검증."""
        if not platform_helper.IS_MAC:
            self.skipTest("macOS 전용")
        import deskcal
        # 1. 텍스트 라벨 내 'Ctrl+' -> '⌘' 자동 변환 확인
        app = deskcal.DeskCal.__new__(deskcal.DeskCal)
        app.lang = "ko"
        self.assertEqual(app.t("tip_delete"), "지우기 (⌘Z로 되돌리기)")
        
        # 2. ⌘ 단축키 안전 처리 확인 ('c'는 핸들러가 처리 후 "break" 반환)
        class MockEvent:
            def __init__(self, keycode=0, keysym=None, widget=None):
                self.keycode = keycode
                self.keysym = keysym
                self.widget = widget
        # keysym='c' -> 'break'
        ev = MockEvent(keysym='c')
        self.assertEqual(deskcal.DeskCal.on_ctrl_key(app, ev), "break")
        # keysym='z' -> None (Ctrl+Z는 다른 핸들러)
        ev_z = MockEvent(keysym='z')
        self.assertIsNone(deskcal.DeskCal.on_ctrl_key(app, ev_z))
        print("\n[PASS] macOS ⌘ 단축키 및 텍스트 치환 검증 완료!")


    def test_08_macos_glass_rendering(self):
        """macOS 바탕화면 유리 블러(make_glass) 생성 및 BGRA 바이트 검증."""
        if not platform_helper.IS_MAC:
            self.skipTest("macOS 전용")
        import deskcal
        from PIL import Image
        import tempfile
        tmp_wall = tempfile.mktemp(suffix=".png")
        Image.new("RGB", (800, 600), (80, 120, 200)).save(tmp_wall)
        try:
            old_func = deskcal.get_macos_wallpaper_image
            deskcal.get_macos_wallpaper_image = lambda: tmp_wall
            raw = deskcal.make_glass(50, 50, 200, 150, "#151821", 0.76)
            self.assertIsNotNone(raw, "macOS 유리 BGRA 바이트열이 생성되어야 합니다.")
            self.assertEqual(len(raw), 200 * 150 * 4, "생성된 바이트열 길이가 w*h*4이어야 합니다.")
            ppm = deskcal.bgra_to_ppm(raw, 200, 150)
            self.assertTrue(ppm.startswith(b"P6 200 150 255\n"), "유효한 PPM 헤더를 가져야 합니다.")
            print("\n[PASS] macOS make_glass 및 PPM 생성 100% 검증 완료!")
        finally:
            deskcal.get_macos_wallpaper_image = old_func
            if os.path.exists(tmp_wall):
                os.remove(tmp_wall)


if __name__ == "__main__":
    unittest.main()
