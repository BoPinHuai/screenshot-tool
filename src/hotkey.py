# hotkey.py — 全局快捷键管理

import keyboard


class HotkeyManager:
    """注册、追踪、批量注销全局快捷键。"""

    def __init__(self) -> None:
        self._registered: list[str] = []

    def register(self, hotkey: str, callback) -> bool:
        """注册一个全局快捷键。返回 True 表示成功，False 表示失败（冲突或权限）。"""
        try:
            keyboard.add_hotkey(hotkey, callback, suppress=True)
            self._registered.append(hotkey)
            return True
        except Exception as e:
            print(f"[快捷键] 注册失败 '{hotkey}'：{e}  → 请检查是否与其他程序冲突")
            return False

    def unregister_all(self) -> None:
        """注销所有已注册的快捷键（退出时调用）。"""
        for hk in self._registered:
            try:
                keyboard.remove_hotkey(hk)
            except Exception:
                pass
        self._registered.clear()
