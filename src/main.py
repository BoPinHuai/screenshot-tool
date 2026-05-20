# main.py — Stage 4 入口
# 运行：python src/main.py
#
# 启动流程：
#   1. 设置 DPI awareness
#   2. 加载 config
#   3. 创建隐藏 CTk 根窗口（customtkinter 主题初始化）
#   4. 创建 SettingsPanel（初始隐藏）
#   5. 创建 FloatingBall（常驻桌面）
#   6. mainloop()

import sys
import os
import ctypes

sys.path.insert(0, os.path.dirname(__file__))

import config
import customtkinter as ctk
from ui.settings import SettingsPanel
from ui.floating_ball import FloatingBall


def _set_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main() -> None:
    _set_dpi_awareness()
    cfg = config.load()
    os.makedirs(cfg["save_dir"], exist_ok=True)

    # 隐藏根窗口（仅用于托管子窗口，不显示）
    root = ctk.CTk()
    root.withdraw()

    # 设置面板（初始隐藏，单击悬浮球后弹出）
    panel = SettingsPanel(root, cfg)

    # 退出回调：注销快捷键 → 销毁根窗口（同时关闭所有子窗口）
    def on_quit() -> None:
        panel.quit_cleanup()
        root.destroy()

    # 悬浮球（常驻桌面）
    FloatingBall(root, panel, cfg, on_quit)

    root.mainloop()


if __name__ == "__main__":
    main()
