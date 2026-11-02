# -*- coding: utf-8 -*-
"""DeskCal 플랫폼 추상화 계층 (Windows & macOS 네이티브 지원)."""
import os
import plistlib
import subprocess
import sys
import traceback

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# ---------- 1. 데이터 디렉토리 ----------

def get_default_data_dir(app_name="DeskCal"):
    """OS 규격에 맞는 기본 사용자 데이터 디렉토리 반환."""
    if IS_WIN:
        local_app = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(local_app, app_name)
    elif IS_MAC:
        return os.path.expanduser(f"~/Library/Application Support/{app_name}")
    else:
        return os.path.expanduser(f"~/.{app_name.lower()}")


# ---------- 2. DPI 및 고해상도(Retina) 설정 ----------

def setup_dpi():
    """고해상도 디스플레이 처리 (Windows: Per-Monitor DPI, macOS: Retina 자동)."""
    if IS_WIN:
        import ctypes
        user32 = ctypes.windll.user32
        _H = ctypes.c_void_p
        try:
            user32.SetProcessDpiAwarenessContext.argtypes = [_H]
            user32.SetProcessDpiAwarenessContext.restype = ctypes.c_bool
            if user32.SetProcessDpiAwarenessContext(_H(-4)):
                return "per-monitor-v2"
        except Exception:
            pass
        try:
            if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:
                return "per-monitor"
            if ctypes.windll.shcore.SetProcessDpiAwareness(1) == 0:
                return "system"
        except Exception:
            pass
        try:
            if user32.SetProcessDPIAware():
                return "system(legacy)"
        except Exception:
            pass
        return "none"
    elif IS_MAC:
        # macOS는 Cocoa/Tkinter 레이어에서 Retina 스케일링이 논리 포인트(Logical Points)로 자동 처리됨
        return "retina-native"
    return "default"


# ---------- 3. 자동 실행 (Autostart) ----------

LAUNCH_AGENT_LABEL = "com.hanseidon.deskcal"

def get_launch_command(frozen=False):
    """실행 파일 또는 파이썬 스크립트 실행 경로 반환."""
    if frozen:
        return [sys.executable, "--autostart"]
    py = sys.executable
    if IS_WIN:
        pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
        if os.path.exists(pyw):
            py = pyw
    entry = os.path.abspath(sys.argv[0])
    return [py, entry, "--autostart"]


def is_autostart_enabled():
    """로그온 시 자동 실행 여부 확인."""
    if IS_WIN:
        import winreg
        run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key) as k:
                winreg.QueryValueEx(k, "DeskCal")
            return True
        except OSError:
            return False
    elif IS_MAC:
        plist_path = os.path.expanduser(f"~/Library/LaunchAgents/{LAUNCH_AGENT_LABEL}.plist")
        return os.path.exists(plist_path)
    return False


def set_autostart(on, frozen=False, log_func=None):
    """로그온 시 자동 실행 켜기/끄기."""
    def _log(msg):
        if log_func:
            log_func(msg)

    if IS_WIN:
        import winreg
        run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            cmd_str = '"%s" --autostart' % sys.executable if frozen else '"%s" "%s" --autostart' % (
                get_launch_command(frozen)[0], get_launch_command(frozen)[1]
            )
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_SET_VALUE) as k:
                if on:
                    winreg.SetValueEx(k, "DeskCal", 0, winreg.REG_SZ, cmd_str)
                else:
                    try:
                        winreg.DeleteValue(k, "DeskCal")
                    except FileNotFoundError:
                        pass
            _log("윈도우 시작 시 실행: %s" % ("켬" if on else "끔"))
        except OSError:
            _log("윈도우 시작 시 실행 설정 실패:\n" + traceback.format_exc())

    elif IS_MAC:
        launch_dir = os.path.expanduser("~/Library/LaunchAgents")
        plist_path = os.path.join(launch_dir, f"{LAUNCH_AGENT_LABEL}.plist")
        try:
            if on:
                os.makedirs(launch_dir, exist_ok=True)
                args = get_launch_command(frozen)
                plist_data = {
                    "Label": LAUNCH_AGENT_LABEL,
                    "ProgramArguments": args,
                    "RunAtLoad": True,
                    "KeepAlive": False,
                    "ProcessType": "Interactive",
                }
                with open(plist_path, "wb") as f:
                    plistlib.dump(plist_data, f)
                _log("macOS 로그인 시 실행 등록 완료 (LaunchAgent)")
            else:
                if os.path.exists(plist_path):
                    os.remove(plist_path)
                _log("macOS 로그인 시 실행 등록 해제")
        except Exception:
            _log("macOS 자동 실행 설정 실패:\n" + traceback.format_exc())


# ---------- 4. 네이티브 폰트 우선순위 ----------

def get_platform_fonts():
    """OS별 한중일 및 영문 고화질 가독성 폰트 목록."""
    if IS_MAC:
        return [
            "PingFang SC",
            "Apple SD Gothic Neo",
            ".AppleSystemUIFont",
            "Helvetica Neue",
            "Hiragino Sans GB",
            "Arial",
        ]
    elif IS_WIN:
        return [
            "Microsoft YaHei",
            "Malgun Gothic",
            "Segoe UI",
            "Arial",
        ]
    return ["Noto Sans CJK SC", "Noto Sans", "DejaVu Sans", "Arial"]


# ---------- 5. macOS Cocoa/AppKit 네이티브 데스크탑 고정 & 블러 ----------

def setup_macos_window(tk_root, is_dark=True):
    """
    macOS AppKit을 통해 Tkinter 창을 데스크톱 레벨로 밀착시키고,
    순정 하드웨어 가속 NSVisualEffectView(반투명 프로스트 글래스)를 주입한다.
    """
    if not IS_MAC:
        return False
    try:
        import AppKit
        import objc
        from ctypes import c_void_p

        # Tkinter 창의 Cocoa NSWindow 인스턴스 획득
        # winfo_id()는 X11 ID 또는 NSView 포인터를 반환한다
        view_ptr = tk_root.winfo_id()
        ns_view = objc.objc_object(c_void_p=view_ptr)
        ns_window = ns_view.window() if hasattr(ns_view, "window") else None

        if not ns_window:
            # 윈도우 타이틀이나 번호로 폴백 탐색
            for win in AppKit.NSApp.windows():
                if win.title() == "DeskCal":
                    ns_window = win
                    break

        if not ns_window:
            return False

        # 1. 데스크톱 레벨로 창 고정 (kCGDesktopWindowLevel = kCGNormalWindowLevel - 1)
        # 미션 컨트롤이나 '데스크탑 보기'를 해도 항상 바탕화면 위에 유지됨
        ns_window.setLevel_(AppKit.kCGDesktopWindowLevel)

        # 2. 모든 Spaces(가상 데스크톱)에 상시 표시 + 미션컨트롤 사이클 제외
        ns_window.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces |
            AppKit.NSWindowCollectionBehaviorStationary |
            AppKit.NSWindowCollectionBehaviorIgnoresCycle
        )

        # 3. 투명 타이틀바 및 투명 배경 처리
        ns_window.setTitlebarAppearsTransparent_(True)
        ns_window.setOpaque_(False)
        ns_window.setBackgroundColor_(AppKit.NSColor.clearColor())

        # 4. 순정 NSVisualEffectView (Frosted Glass / Vibrancy) 주입
        content_view = ns_window.contentView()
        bounds = content_view.bounds()

        effect_view = AppKit.NSVisualEffectView.alloc().initWithFrame_(bounds)
        effect_view.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        effect_view.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)

        # 다크 모드 / 라이트 모드에 따른 블러 머티리얼 설정
        if is_dark:
            effect_view.setMaterial_(AppKit.NSVisualEffectMaterialHUDWindow)
            effect_view.setAppearance_(AppKit.NSAppearance.appearanceNamed_(AppKit.NSAppearanceNameVibrantDark))
        else:
            effect_view.setMaterial_(AppKit.NSVisualEffectMaterialUnderWindowBackground)
            effect_view.setAppearance_(AppKit.NSAppearance.appearanceNamed_(AppKit.NSAppearanceNameVibrantLight))

        effect_view.setState_(AppKit.NSVisualEffectStateActive)

        # 가장 뒤 레이어로 삽입 (Tkinter 컴포넌트들 바로 뒤)
        content_view.addSubview_positioned_relativeTo_(effect_view, AppKit.NSWindowBelow, None)
        return True

    except Exception as e:
        print(f"[PlatformHelper] macOS Cocoa setup error: {e}")
        return False


# ---------- 6. 단축키 매핑 (Command vs Control) ----------

def get_shortcut_keys():
    """OS에 따른 단축키 이름 및 이벤트 바인딩 반환."""
    if IS_MAC:
        return {
            "undo_key": "Command+Z",
            "undo_bind": "<Command-z>",
            "undo_bind_alt": "<Control-z>",
            "pref_key": "Command+,",
            "pref_bind": "<Command-comma>",
        }
    return {
        "undo_key": "Ctrl+Z",
        "undo_bind": "<Control-z>",
        "undo_bind_alt": "<Control-Z>",
        "pref_key": "Ctrl+,",
        "pref_bind": "<Control-comma>",
    }
