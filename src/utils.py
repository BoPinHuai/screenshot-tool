# utils.py — 工程工具函数
#
# 单实例运行：命名 Mutex，防止多开互抢快捷键
# 开机自启：读写 HKCU 注册表 Run 键

import sys
import ctypes
import winreg

from config import APP_NAME

# Mutex 句柄必须在进程生命周期内保持引用，防止被 GC 释放
_MUTEX_HANDLE = None
_MUTEX_NAME   = f"{APP_NAME}SingleInstance"

# 注册表路径
_REG_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"


# ── 单实例 ────────────────────────────────────────────────────────────────────

def ensure_single_instance() -> None:
    """若已有实例在运行则立即退出，否则持有 Mutex 直到进程结束。"""
    global _MUTEX_HANDLE
    _MUTEX_HANDLE = ctypes.windll.kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    if ctypes.windll.kernel32.GetLastError() == 183:   # ERROR_ALREADY_EXISTS
        print("[单实例] 已有实例在运行，退出")
        sys.exit(0)


# ── 开机自启 ──────────────────────────────────────────────────────────────────

def is_packaged() -> bool:
    """判断当前是否以 PyInstaller 打包后的 exe 运行。"""
    return getattr(sys, "frozen", False)


def get_autostart() -> bool:
    """读取注册表，返回是否已开启开机自启。"""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_RUN, 0, winreg.KEY_READ
        )
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except OSError:
        return False


def set_autostart(enable: bool) -> None:
    """开启或关闭开机自启（仅在打包后的 exe 中有效）。"""
    if not is_packaged():
        return   # 开发模式下无意义

    exe_path = sys.executable
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_RUN, 0, winreg.KEY_SET_VALUE
        )
        if enable:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe_path}"')
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except OSError:
                pass
        winreg.CloseKey(key)
    except OSError as e:
        print(f"[自启] 注册表写入失败：{e}")
