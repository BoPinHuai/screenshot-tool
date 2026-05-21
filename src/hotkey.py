# hotkey.py — 全局快捷键管理
#
# register()           — 普通快捷键（suppress=True，按下即触发）
# register_long_press() — 长按检测快捷键：
#     短按（< long_ms 松开）→ short_cb
#     长按（≥ long_ms 松开）→ long_cb
#
# 实现原理：
#   add_hotkey(suppress=True) 捕获并抑制按键；
#   on_release 在松开时计算时长，分流 short / long 两条路径。

import time
import keyboard


def _parse_hotkey(hotkey_str: str) -> tuple[list[str], str]:
    """'ctrl+alt+s'  →  (['ctrl', 'alt'], 's')"""
    parts = [p.strip().lower() for p in hotkey_str.split('+')]
    return parts[:-1], parts[-1]


class HotkeyManager:
    """注册、追踪、批量注销全局快捷键。"""

    def __init__(self) -> None:
        self._hotkeys: list[str] = []   # add_hotkey 注册的热键字符串
        self._hooks:   list      = []   # on_press / on_release hook 句柄

    # ── 普通快捷键（向后兼容） ──────────────────────────────────────────────

    def register(self, hotkey: str, callback) -> bool:
        """注册一个全局快捷键（按下即触发，suppress=True）。"""
        try:
            keyboard.add_hotkey(hotkey, callback, suppress=True)
            self._hotkeys.append(hotkey)
            return True
        except Exception as e:
            print(f"[快捷键] 注册失败 '{hotkey}'：{e}  → 请检查是否与其他程序冲突")
            return False

    # ── 长按快捷键 ─────────────────────────────────────────────────────────

    def register_long_press(
        self,
        hotkey:   str,
        short_cb,
        long_cb,
        long_ms:  int = 500,
    ) -> bool:
        """注册支持长按的快捷键。
        短按（< long_ms 松开）→ short_cb()
        长按（≥ long_ms 松开）→ long_cb()
        按下事件被 add_hotkey suppress=True 吞掉，不透传给其他程序。
        """
        try:
            _, trigger = _parse_hotkey(hotkey)
            press_time: list[float | None] = [None]

            def _on_trigger():
                """add_hotkey 按下时记录时间戳（已 suppress）。"""
                press_time[0] = time.monotonic()

            def _on_release(e: keyboard.KeyboardEvent):
                if e.name.lower() != trigger:
                    return
                if press_time[0] is None:
                    return
                duration = time.monotonic() - press_time[0]
                press_time[0] = None
                if duration >= long_ms / 1000.0:
                    long_cb()
                else:
                    short_cb()

            keyboard.add_hotkey(hotkey, _on_trigger, suppress=True)
            self._hotkeys.append(hotkey)

            h = keyboard.on_release(_on_release)
            self._hooks.append(h)
            return True

        except Exception as e:
            print(f"[快捷键] 长按注册失败 '{hotkey}'：{e}")
            return False

    # ── 注销 ───────────────────────────────────────────────────────────────

    def unregister_all(self) -> None:
        """注销所有已注册的快捷键（重载配置 / 退出时调用）。"""
        for hk in self._hotkeys:
            try:
                keyboard.remove_hotkey(hk)
            except Exception:
                pass
        self._hotkeys.clear()

        for h in self._hooks:
            try:
                keyboard.unhook(h)
            except Exception:
                pass
        self._hooks.clear()
