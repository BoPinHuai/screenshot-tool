# main.py — Stage 6 入口
# 运行（开发）：python src/main.py
# 运行（打包）：直接双击 ScreenshotTool.exe
#
# 启动流程：
#   1. 单实例检查（已有实例则退出）
#   2. 设置 DPI awareness
#   3. 加载 config
#   4. 创建隐藏 CTk 根窗口
#   5. 创建 SettingsPanel（初始隐藏）
#   6. 创建 FloatingBall（常驻桌面）
#   7. 创建 PinManager，注入 SettingsPanel 和 FloatingBall
#   8. mainloop()

import sys
import os
import ctypes

# ── 路径修复：兼容开发模式和 PyInstaller 打包模式 ──────────────────────────────
if getattr(sys, "frozen", False):
    _BASE = sys._MEIPASS
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, _BASE)
# ──────────────────────────────────────────────────────────────────────────────

import config
import customtkinter as ctk
from utils import ensure_single_instance
from ui.settings import SettingsPanel
from ui.floating_ball import FloatingBall
from ui.pin_manager import PinManager


def _set_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main() -> None:
    ensure_single_instance()
    _set_dpi_awareness()

    cfg = config.load()
    os.makedirs(cfg["save_dir"], exist_ok=True)

    root = ctk.CTk()
    root.withdraw()

    panel = SettingsPanel(root, cfg)

    def on_quit() -> None:
        panel.quit_cleanup()
        ball.quit_cleanup()
        pin_mgr.close_all()
        root.destroy()

    ball    = FloatingBall(root, panel, cfg, on_quit)
    pin_mgr = PinManager(root)

    # 各模块互相注入引用
    panel.set_ball(ball)
    panel.set_pin_mgr(pin_mgr)
    ball.set_pin_mgr(pin_mgr)

    root.mainloop()


if __name__ == "__main__":
    main()
