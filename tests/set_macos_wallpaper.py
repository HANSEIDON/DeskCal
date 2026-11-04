# -*- coding: utf-8 -*-
"""macOS 가상 데스크톱 환경에 화려한 테스트용 배경화면을 설정하고 표시한다."""
import math
import os
import sys
import time

def create_wallpaper(path, w=1024, h=768):
    from PIL import Image, ImageDraw, ImageFilter
    im = Image.new("RGB", (w, h), (40, 60, 110))
    draw = ImageDraw.Draw(im)

    for y in range(h):
        t = y / (h - 1)
        r = int(30 + 60 * t)
        g = int(50 + 70 * t)
        b = int(100 + 70 * (1 - t))
        draw.line([(0, y), (w, y)], fill=(r, g, b))

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    blobs = [
        (int(w * 0.20), int(h * 0.80), 380, (40, 200, 210)),   # Bright Cyan
        (int(w * 0.80), int(h * 0.20), 400, (255, 120, 60)),   # Bright Coral/Orange
        (int(w * 0.50), int(h * 0.50), 350, (170, 90, 240)),   # Bright Purple
        (int(w * 0.85), int(h * 0.80), 320, (255, 200, 50)),   # Vivid Gold
        (int(w * 0.15), int(h * 0.25), 300, (60, 140, 255)),   # Azure Blue
    ]

    for cx, cy, radius, col in blobs:
        for r in range(radius, 0, -10):
            alpha = int(75 * (1.0 - (r / radius) ** 1.3))
            c = (col[0], col[1], col[2], alpha)
            draw_ov = ImageDraw.Draw(overlay)
            draw_ov.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c)

    im.paste(overlay, (0, 0), overlay)
    im = im.filter(ImageFilter.GaussianBlur(radius=25))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    im.save(path)
    print(f"Wallpaper generated at: {path}")

def run_desktop_server(path):
    import AppKit
    app = AppKit.NSApplication.sharedApplication()

    # 1. Cocoa NSWorkspace로 바탕화면 설정 시도
    ws = AppKit.NSWorkspace.sharedWorkspace()
    url = AppKit.NSURL.fileURLWithPath_(os.path.abspath(path))
    for s in (AppKit.NSScreen.screens() or []):
        try:
            ws.setDesktopImageURL_forScreen_options_error_(url, s, {}, None)
        except Exception:
            pass

    # 2. 러너 환경에서 바탕화면이 안 칠해질 경우를 대비해 kCGDesktopWindowLevel에 배경 창 띄우기
    windows = []
    for s in (AppKit.NSScreen.screens() or []):
        frame = s.frame()
        win = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, AppKit.NSWindowStyleMaskBorderless, AppKit.NSBackingStoreBuffered, False
        )
        try:
            import Quartz
            level = Quartz.kCGDesktopWindowLevel
        except Exception:
            level = -2147483603
        win.setLevel_(level)
        win.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces |
            AppKit.NSWindowCollectionBehaviorStationary |
            AppKit.NSWindowCollectionBehaviorIgnoresCycle
        )
        img = AppKit.NSImage.alloc().initWithContentsOfFile_(os.path.abspath(path))
        view = AppKit.NSImageView.alloc().initWithFrame_(win.contentView().bounds())
        view.setImage_(img)
        view.setImageScaling_(AppKit.NSImageScaleAxesIndependently)
        win.contentView().addSubview_(view)
        win.orderFrontRegardless()
        windows.append(win)

    print("Background desktop window active at kCGDesktopWindowLevel!")
    app.run()

if __name__ == "__main__":
    out_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/wallpaper.png"
    create_wallpaper(out_path)
    if "--serve" in sys.argv:
        run_desktop_server(out_path)
