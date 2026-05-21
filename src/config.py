# config.py — 配置加载与保存
# 配置文件位置：%APPDATA%\ScreenshotTool\config.json
# Stage 3+ 可在设置面板里直接编辑；Stage 2 手动改 JSON 文件

import os
import json
from pathlib import Path

APP_NAME = "ScreenshotTool"   # 工具正式名确定后统一替换

# 默认配置；新版本新增字段时在此处补充，旧配置文件自动继承
DEFAULT_CONFIG: dict = {
    "save_dir": str(Path.home() / "Pictures" / "Screenshots"),
    "hotkey_select": "ctrl+alt+d",
    "hotkey_toggle_ball": "ctrl+alt+b",   # 显示/隐藏悬浮球
    "ball_x": 100,   # 悬浮球上次位置（物理像素）
    "ball_y": 100,
    "ball_image_path": "",   # 自定义悬浮球图片（留空则用默认圆形）
    # ── 贴图高级设置 ──
    "long_press_ms":   500,    # 长按触发贴图的时长（ms）
    "hide_pins_on_capture": True,   # 截图前自动隐藏贴图
    "presets": [
        {
            "name": "预设1",
            "region": {"left": 100, "top": 100, "width": 800, "height": 600},
            "hotkey": "ctrl+alt+s",
        }
    ],
}


def get_config_path() -> Path:
    appdata = os.environ.get("APPDATA", str(Path.home()))
    return Path(appdata) / APP_NAME / "config.json"


def load() -> dict:
    """读取配置文件；不存在则写入默认值并返回。向后兼容：旧文件缺少的顶层字段用默认值补全。"""
    path = get_config_path()

    if not path.exists():
        save(DEFAULT_CONFIG)
        print(f"[配置] 已生成默认配置：{path}")
        return DEFAULT_CONFIG.copy()

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 顶层字段向后兼容合并（新字段用默认值填充）
        merged = DEFAULT_CONFIG.copy()
        merged.update(data)
        return merged
    except Exception as e:
        print(f"[配置] 读取失败，使用默认值：{e}")
        return DEFAULT_CONFIG.copy()


def save(config: dict) -> None:
    """将配置写入磁盘。"""
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"[配置] 已保存：{path}")
