# capture.py — 截图逻辑

import os
import time
import tkinter as tk
from datetime import datetime

import mss
import mss.tools

from ui.selector import run_selector


def make_filepath(save_dir: str) -> str:
    """返回一个不冲突的时间戳文件路径，同一秒内追加三位序号。"""
    os.makedirs(save_dir, exist_ok=True)
    base = datetime.now().strftime("screenshot_%Y%m%d_%H%M%S")
    path = os.path.join(save_dir, f"{base}.png")
    if not os.path.exists(path):
        return path
    i = 1
    while True:
        path = os.path.join(save_dir, f"{base}_{i:03d}.png")
        if not os.path.exists(path):
            return path
        i += 1


def capture_region(region: dict, save_dir: str) -> str:
    """截取指定矩形区域并保存为 PNG，返回文件绝对路径。"""
    with mss.mss() as sct:
        shot = sct.grab(region)
        path = make_filepath(save_dir)
        mss.tools.to_png(shot.rgb, shot.size, output=path)
    print(f"[截图] {path}")
    return path


def capture_select(root: tk.Tk, save_dir: str) -> bool:
    """弹出框选遮罩，用户拖选后截图保存。返回 True 表示已截图，False 表示已取消。"""
    region = run_selector(root)
    if region:
        time.sleep(0.08)   # 等遮罩从屏幕上完全消失再截图
        capture_region(region, save_dir)
        return True
    print("[框选] 已取消")
    return False
