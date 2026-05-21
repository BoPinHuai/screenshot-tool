# ui/pin_manager.py — 多贴图全局管理（Stage 6）
#
# 职责：
#   create_pin()   — 从 PIL Image + 坐标创建新贴图，超上限时关闭最旧的
#   hide_all()     — 截图前批量隐藏（不销毁）
#   show_all()     — 截图后批量恢复
#   close_all()    — 销毁全部贴图
#   count()        — 当前贴图数量
#   set_active()   — 某张贴图被点击，记录为活跃项

import tkinter as tk

try:
    from PIL import Image
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

from ui.pin import PinWindow

MAX_PINS = 20   # 超过此数量时自动关闭最旧的贴图


class PinManager:
    """管理所有 PinWindow 实例的全局状态。"""

    def __init__(self, root: tk.Tk) -> None:
        self._root   = root
        self._pins:  list[PinWindow] = []
        self._active: PinWindow | None = None
        self._all_hidden = False   # 是否处于"全部隐藏"状态

    # ══════════════ 创建 ══════════════

    def create_pin(
        self,
        image: "Image.Image",
        x:     int,
        y:     int,
    ) -> PinWindow:
        """创建并显示一张新贴图，超出上限时自动移除最旧的。"""
        if len(self._pins) >= MAX_PINS:
            print(f"[贴图] 达到上限 {MAX_PINS}，关闭最旧的贴图")
            self._pins[0].close()   # close() 会调用 self.remove()

        pin = PinWindow(self._root, image, x, y, self)
        self._pins.append(pin)
        self._active = pin
        return pin

    def create_pin_from_file(self, path: str, x: int, y: int) -> PinWindow | None:
        """从文件路径加载图片并创建贴图。"""
        if not _PIL_OK:
            print("[贴图] Pillow 未安装，无法创建贴图")
            return None
        try:
            image = Image.open(path).convert("RGBA")
            return self.create_pin(image, x, y)
        except Exception as e:
            print(f"[贴图] 读取图片失败：{e}")
            return None

    # ══════════════ 批量操作 ══════════════

    def hide_all(self) -> None:
        """隐藏所有贴图（不销毁，截图前调用）。"""
        self._all_hidden = True
        for pin in self._pins:
            pin.hide()

    def show_all(self) -> None:
        """恢复所有贴图（截图后调用）。"""
        self._all_hidden = False
        for pin in self._pins:
            pin.show()

    def close_all(self) -> None:
        """销毁所有贴图。"""
        for pin in list(self._pins):
            pin.close()

    def toggle_visibility(self) -> bool:
        """切换全部贴图的显隐状态，返回显示后的状态（True = 现已可见）。"""
        if self._all_hidden:
            self.show_all()
            return True
        else:
            self.hide_all()
            return False

    # ══════════════ 单张操作回调 ══════════════

    def remove(self, pin: PinWindow) -> None:
        """PinWindow 销毁时调用，从列表移除。"""
        if pin in self._pins:
            self._pins.remove(pin)
        if self._active is pin:
            self._active = None

    def set_active(self, pin: PinWindow) -> None:
        self._active = pin

    # ══════════════ 状态查询 ══════════════

    def count(self) -> int:
        return len(self._pins)

    def is_hidden(self) -> bool:
        return self._all_hidden
