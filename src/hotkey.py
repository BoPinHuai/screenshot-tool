# hotkey.py — 全局快捷键管理（Windows RegisterHotKey API）
#
# 使用 OS 原生 RegisterHotKey，而非 keyboard 库的 WH_KEYBOARD_LL 钩子。
# 好处：Ctrl/Alt 等修饰键单独按下时完全不经过本程序，建模/游戏等软件不受影响；
# 只有完整组合键匹配时 OS 才通知我们，零延迟、零干扰。
#
# 架构：
#   后台线程持有 Windows 消息循环，所有热键注册/注销在该线程完成（RegisterHotKey
#   要求注册与接收 WM_HOTKEY 的线程相同）。主线程通过 PostThreadMessageW 发送命令。

import ctypes
import ctypes.wintypes
import threading
from ctypes import wintypes

# ── Windows API 常量 ─────────────────────────────────────────────────────────
MOD_ALT      = 0x0001
MOD_CONTROL  = 0x0002
MOD_SHIFT    = 0x0004
MOD_WIN      = 0x0008
MOD_NOREPEAT = 0x4000   # 按住时不重复触发

WM_HOTKEY          = 0x0312
_WM_APP_REGISTER   = 0x8001   # 自定义线程消息：注册热键
_WM_APP_UNREG_ALL  = 0x8002   # 自定义线程消息：注销全部热键

# ── 按键名 → 虚拟键码（VK code） ─────────────────────────────────────────────
_VK: dict[str, int] = {c: ord(c.upper()) for c in 'abcdefghijklmnopqrstuvwxyz'}
_VK.update({str(i): 0x30 + i for i in range(10)})
_VK.update({
    'f1': 0x70,  'f2': 0x71,  'f3': 0x72,  'f4': 0x73,
    'f5': 0x74,  'f6': 0x75,  'f7': 0x76,  'f8': 0x77,
    'f9': 0x78,  'f10': 0x79, 'f11': 0x7A, 'f12': 0x7B,
    'space': 0x20, 'enter': 0x0D, 'tab': 0x09,
    'esc': 0x1B, 'escape': 0x1B,
    'delete': 0x2E, 'del': 0x2E, 'insert': 0x2D,
    'home': 0x24, 'end': 0x23, 'pageup': 0x21, 'pagedown': 0x22,
    'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27,
    'backspace': 0x08,
})

_MOD_MAP: dict[str, int] = {
    'ctrl': MOD_CONTROL, 'control': MOD_CONTROL,
    'alt':  MOD_ALT,
    'shift': MOD_SHIFT,
    'win':  MOD_WIN,
}


def _parse_hotkey(hotkey_str: str) -> tuple[int, int]:
    """'ctrl+alt+s' → (mod_flags | MOD_NOREPEAT, vk_code)。解析失败抛 ValueError。"""
    mods = MOD_NOREPEAT
    vk   = 0
    for part in (p.strip().lower() for p in hotkey_str.split('+')):
        if part in _MOD_MAP:
            mods |= _MOD_MAP[part]
        elif part in _VK:
            vk = _VK[part]
        else:
            raise ValueError(f"未知按键名: {part!r}")
    if not vk:
        raise ValueError(f"热键缺少触发键: {hotkey_str!r}")
    return mods, vk


class HotkeyManager:
    """使用 Windows RegisterHotKey API 注册全局快捷键。

    - 不安装任何键盘钩子，建模/游戏软件的 Ctrl/Alt 完全不受影响。
    - register() / unregister_all() 可从任意线程调用。
    - callback 在后台线程触发，应用 queue.put 传回主线程（线程安全）。
    """

    def __init__(self) -> None:
        self._callbacks: dict[int, object] = {}   # hotkey_id → callback
        self._cmds:      dict[int, tuple]  = {}   # hotkey_id → (mods, vk, callback)
        self._next_id = 1
        self._lock    = threading.Lock()
        self._thread_id: int | None = None
        self._ready   = threading.Event()

        t = threading.Thread(target=self._run, daemon=True)
        t.start()
        if not self._ready.wait(timeout=3):
            print("[热键] 警告：后台线程初始化超时")

    # ══════════════ 后台消息循环（在独立线程中运行）══════════════

    def _run(self) -> None:
        user32   = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        self._thread_id = kernel32.GetCurrentThreadId()

        # 触发线程消息队列初始化（首次 PeekMessage 会创建队列）
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)

        self._ready.set()

        while True:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0 or ret == -1:   # WM_QUIT 或错误
                break

            mid = msg.message

            if mid == WM_HOTKEY:
                cb = self._callbacks.get(msg.wParam)
                if cb:
                    try:
                        cb()
                    except Exception as e:
                        print(f"[热键] 回调异常: {e}")

            elif mid == _WM_APP_REGISTER:
                hid = msg.wParam
                with self._lock:
                    data = self._cmds.pop(hid, None)
                if data:
                    mods, vk, cb = data
                    ok = user32.RegisterHotKey(None, hid, mods, vk)
                    if ok:
                        self._callbacks[hid] = cb
                        print(f"[热键] 已注册 id={hid} mods=0x{mods:04X} vk=0x{vk:02X}")
                    else:
                        err = kernel32.GetLastError()
                        print(f"[热键] 注册失败 id={hid} (错误码={err}，可能被其他程序占用)")

            elif mid == _WM_APP_UNREG_ALL:
                for hid in list(self._callbacks):
                    user32.UnregisterHotKey(None, hid)
                self._callbacks.clear()
                print("[热键] 已注销所有快捷键")

    # ══════════════ 公开接口 ══════════════

    def register(self, hotkey: str, callback) -> bool:
        """注册全局快捷键。返回 True 表示命令已投递（注册在后台线程异步完成）。"""
        try:
            mods, vk = _parse_hotkey(hotkey)
        except ValueError as e:
            print(f"[热键] 解析失败 '{hotkey}'：{e}")
            return False

        if not self._thread_id:
            print(f"[热键] 后台线程未就绪，跳过: {hotkey!r}")
            return False

        with self._lock:
            hid = self._next_id
            self._next_id += 1
            self._cmds[hid] = (mods, vk, callback)

        ctypes.windll.user32.PostThreadMessageW(
            self._thread_id, _WM_APP_REGISTER, hid, 0
        )
        return True

    def unregister_all(self) -> None:
        """注销所有已注册的快捷键（程序退出时调用）。"""
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(
                self._thread_id, _WM_APP_UNREG_ALL, 0, 0
            )
