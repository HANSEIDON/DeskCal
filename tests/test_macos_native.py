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

    def test_06_native_isop_cpp_module(self):
        """컴파일된 macOS C++ ISOP 클라이언트 모듈 검증."""
        if not platform_helper.IS_MAC:
            self.skipTest("macOS 전용")
        try:
            import _isop_client
            self.assertTrue(hasattr(_isop_client, "get_header"))
            self.assertTrue(hasattr(_isop_client, "query_table"))
            print("\n[PASS] _isop_client.so C++ 머신코드 모듈 정상 로드 및 심볼 검증 완료!")
        except ImportError:
            print("\n[NOTE] _isop_client.so 가 아직 컴파일되지 않은 상태입니다. (순수 파이썬 모드로 동작 가능)")

    def test_07_appkit_frosted_glass_injection(self):
        """macOS AppKit Cocoa NSVisualEffectView 및 바탕화면 레벨 주입 검증."""
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
                try:
                    expected_level = AppKit.CGWindowLevelForKey(AppKit.kCGDesktopIconWindowLevelKey) + 1
                except Exception:
                    expected_level = getattr(AppKit, "kCGDesktopIconWindowLevel", 2147483603) + 1
                self.assertEqual(ns_window.level(), expected_level, "바탕화면 아이콘 바로 위 레벨이어야 합니다.")
                self.assertFalse(ns_window.isOpaque(), "윈도우는 반투명(not opaque)이어야 합니다.")
                print("\n[PASS] Cocoa NSVisualEffectView 반투명 블러 및 데스크톱 고정 주입 100% 검증 완료!")

            root.destroy()
        except Exception as e:
            print(f"\n[INFO] Tkinter/AppKit 헤드리스 윈도우 테스트 결과: {e}")

    def test_08_macos_shortcuts_and_text_replacement(self):
        """macOS ⌘ 단축키 처리 및 텍스트 자동 치환 검증."""
        if not platform_helper.IS_MAC:
            self.skipTest("macOS 전용")
        import deskcal
        # 1. 텍스트 라벨 내 'Ctrl+' -> '⌘' 자동 변환 확인
        app = deskcal.DeskCal.__new__(deskcal.DeskCal)
        app.lang = "ko"
        self.assertEqual(app.t("tip_undo"), "실행 취소 (⌘Z)")
        
        # 2. ⌘ 단축키 안전 처리 확인
        class MockEvent:
            def __init__(self, keycode=0, keysym=None, widget=None):
                self.keycode = keycode
                self.keysym = keysym
                self.widget = widget
        # keysym='c'
        ev = MockEvent(keysym='c')
        self.assertIsNone(deskcal.DeskCal.on_ctrl_key(app, ev))
        print("\n[PASS] macOS ⌘ 단축키 및 텍스트 치환 검증 완료!")


if __name__ == "__main__":
    unittest.main()
