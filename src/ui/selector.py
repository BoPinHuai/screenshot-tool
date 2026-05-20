# ui/selector.py — 全屏框选遮罩
# Stage 3 的"标定"功能（坐标自动回填）也复用这个类

import tkinter as tk


class RegionSelector:
    """半透明全屏遮罩，用户拖拽画框后记录坐标。

    用法：
        sel = RegionSelector(root)
        root.wait_window(sel.toplevel)
        region = sel.region   # dict 或 None（ESC 取消）
    """

    def __init__(self, root: tk.Tk) -> None:
        self.region: dict | None = None

        self.toplevel = tk.Toplevel(root)
        self.toplevel.attributes("-fullscreen", True)
        self.toplevel.attributes("-alpha", 0.25)
        self.toplevel.attributes("-topmost", True)
        self.toplevel.overrideredirect(True)
        self.toplevel.configure(bg="black")

        self._canvas = tk.Canvas(
            self.toplevel, cursor="cross", bg="gray10", highlightthickness=0
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)

        self._sx = self._sy = 0
        self._rect = None

        self._canvas.bind("<ButtonPress-1>",  self._on_press)
        self._canvas.bind("<B1-Motion>",      self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self.toplevel.bind("<Escape>",         lambda _: self._cancel())

    def _on_press(self, event: tk.Event) -> None:
        self._sx, self._sy = event.x, event.y
        if self._rect:
            self._canvas.delete(self._rect)
        self._rect = self._canvas.create_rectangle(
            self._sx, self._sy, self._sx, self._sy,
            outline="#FF4444", width=2, fill="",
        )

    def _on_drag(self, event: tk.Event) -> None:
        if self._rect:
            self._canvas.coords(self._rect, self._sx, self._sy, event.x, event.y)

    def _on_release(self, event: tk.Event) -> None:
        x1 = min(self._sx, event.x)
        y1 = min(self._sy, event.y)
        x2 = max(self._sx, event.x)
        y2 = max(self._sy, event.y)
        if x2 - x1 > 5 and y2 - y1 > 5:
            self.region = {"left": x1, "top": y1, "width": x2 - x1, "height": y2 - y1}
        self.toplevel.destroy()

    def _cancel(self) -> None:
        self.toplevel.destroy()


def run_selector(root: tk.Tk) -> dict | None:
    """便捷函数：弹出框选遮罩，阻塞至用户完成或取消，返回 region dict 或 None。"""
    sel = RegionSelector(root)
    root.wait_window(sel.toplevel)
    return sel.region
