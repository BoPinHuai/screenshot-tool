# ui/pin.py — 单张贴图窗口（Stage 6）
#
# 每张贴图 = 一个独立的无边框 Toplevel，常驻置顶，不抢键盘焦点。
#
# 鼠标交互（仅悬停时响应，不需要先点击）：
#   左键拖动       — 移动（阈值 5px）
#   左键单击       — 置顶
#   左键双击       — 关闭
#   滚轮           — 缩放（20%–500%）
#   Ctrl + 滚轮    — 透明度（10%–100%）
#   右键           — 操作菜单

import ctypes
import tkinter as tk
from tkinter import messagebox
from io import BytesIO

try:
    from PIL import Image, ImageTk
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

_GWL_EXSTYLE      = -20
_WS_EX_NOACTIVATE = 0x08000000
_WS_EX_TOOLWINDOW = 0x00000080

_DRAG_THRESHOLD = 5
_SCALE_MIN      = 0.20
_SCALE_MAX      = 5.00
_ALPHA_MIN      = 0.10
_ALPHA_MAX      = 1.00
_SCALE_STEP     = 0.10   # 每格滚轮变化量
_ALPHA_STEP     = 0.05


class PinWindow(tk.Toplevel):
    """单张贴图窗口。无边框置顶，不抢焦点。"""

    def __init__(
        self,
        root:    tk.Tk,
        image:   "Image.Image",
        x:       int,
        y:       int,
        manager,
    ) -> None:
        super().__init__(root)
        self._mgr    = manager
        self._orig   = image.copy()   # 保存原图（用于缩放）
        self._scale  = 1.0
        self._alpha  = 1.0
        self._photo  = None           # 当前显示的 ImageTk.PhotoImage（防 GC）

        self._drag_sx   = 0
        self._drag_sy   = 0
        self._dragging  = False

        self._setup_window(x, y)
        self._build_label()
        self.update_idletasks()
        self._apply_win_style()
        self._display()

    # ══════════════ 窗口初始化 ══════════════

    def _setup_window(self, x: int, y: int) -> None:
        w, h = self._orig.size
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", self._alpha)
        self.configure(bg="black")
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_label(self) -> None:
        self._label = tk.Label(self, bg="black", cursor="fleur", bd=0)
        self._label.place(x=0, y=0, relwidth=1, relheight=1)
        self._label.bind("<ButtonPress-1>",   self._on_press)
        self._label.bind("<B1-Motion>",        self._on_motion)
        self._label.bind("<ButtonRelease-1>",  self._on_release)
        self._label.bind("<Double-Button-1>",  self._on_double_click)
        self._label.bind("<Button-3>",         self._on_right_click)
        self._label.bind("<MouseWheel>",       self._on_scroll)

    def _apply_win_style(self) -> None:
        """WS_EX_NOACTIVATE（不抢焦点）+ WS_EX_TOOLWINDOW（不出现在任务栏）。"""
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            if not hwnd:
                hwnd = self.winfo_id()
            cur = ctypes.windll.user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, _GWL_EXSTYLE,
                cur | _WS_EX_NOACTIVATE | _WS_EX_TOOLWINDOW,
            )
        except Exception as e:
            print(f"[贴图] 窗口样式设置失败：{e}")

    # ══════════════ 图像显示 ══════════════

    def _display(self) -> None:
        """根据当前 _scale 重新渲染并更新窗口尺寸。"""
        w = max(1, int(self._orig.width  * self._scale))
        h = max(1, int(self._orig.height * self._scale))
        if _PIL_OK:
            img = (
                self._orig.resize((w, h), Image.LANCZOS)
                if self._scale != 1.0
                else self._orig
            )
            self._photo = ImageTk.PhotoImage(img)
            self._label.configure(image=self._photo)
        else:
            # PIL 不可用：只能显示原始尺寸（不支持缩放）
            self._photo = tk.PhotoImage(data=self._orig.tobytes())
            self._label.configure(image=self._photo)
        # 调整窗口尺寸（保持左上角位置不变）
        ox, oy = self.winfo_x(), self.winfo_y()
        self.geometry(f"{w}x{h}+{ox}+{oy}")

    # ══════════════ 鼠标事件 ══════════════

    def _on_press(self, event: tk.Event) -> None:
        self._drag_sx  = event.x
        self._drag_sy  = event.y
        self._dragging = False
        self.lift()
        self._mgr.set_active(self)

    def _on_motion(self, event: tk.Event) -> None:
        dx = event.x - self._drag_sx
        dy = event.y - self._drag_sy
        if not self._dragging:
            if abs(dx) > _DRAG_THRESHOLD or abs(dy) > _DRAG_THRESHOLD:
                self._dragging = True
        if self._dragging:
            self.geometry(f"+{self.winfo_x() + dx}+{self.winfo_y() + dy}")

    def _on_release(self, event: tk.Event) -> None:
        self._dragging = False

    def _on_double_click(self, event: tk.Event) -> None:
        self.close()

    def _on_scroll(self, event: tk.Event) -> None:
        direction = 1 if event.delta > 0 else -1
        if event.state & 0x4:   # Ctrl 键按下
            self._alpha = max(_ALPHA_MIN, min(_ALPHA_MAX,
                              self._alpha + direction * _ALPHA_STEP))
            self.attributes("-alpha", self._alpha)
        else:
            new_scale = max(_SCALE_MIN, min(_SCALE_MAX,
                            self._scale + direction * _SCALE_STEP))
            if new_scale != self._scale:
                self._scale = new_scale
                self._display()

    # ══════════════ 右键菜单 ══════════════

    def _on_right_click(self, event: tk.Event) -> None:
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="复制到剪贴板",    command=self._copy_to_clipboard)
        menu.add_separator()
        menu.add_command(label="关闭              双击",  command=self.close)
        menu.add_command(label="关闭所有贴图",            command=self._mgr.close_all)
        menu.add_separator()
        # 操作提示（灰色，仅作说明）
        menu.add_command(label="透明度      Ctrl＋滚轮",  state="disabled")
        menu.add_command(label="缩放                滚轮", state="disabled")
        menu.add_command(label="移动          左键拖动",  state="disabled")
        menu.add_separator()
        menu.add_command(label=f"重置大小（当前 {int(self._scale*100)}%）",
                         command=self._reset_scale)
        menu.add_command(label=f"重置透明度（当前 {int(self._alpha*100)}%）",
                         command=self._reset_alpha)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # ══════════════ 操作 ══════════════

    def _copy_to_clipboard(self) -> None:
        """用 ctypes 把图片写入 Windows 剪贴板（CF_DIB 格式）。"""
        try:
            buf = BytesIO()
            self._orig.convert("RGB").save(buf, "BMP")
            dib = buf.getvalue()[14:]          # 去掉 14 字节 BITMAPFILEHEADER

            GMEM_MOVEABLE = 0x0002
            CF_DIB        = 8
            k32 = ctypes.windll.kernel32
            u32 = ctypes.windll.user32

            h_mem = k32.GlobalAlloc(GMEM_MOVEABLE, len(dib))
            ptr   = k32.GlobalLock(h_mem)
            ctypes.memmove(ptr, dib, len(dib))
            k32.GlobalUnlock(h_mem)

            u32.OpenClipboard(0)
            u32.EmptyClipboard()
            u32.SetClipboardData(CF_DIB, h_mem)
            u32.CloseClipboard()
            print("[贴图] 已复制到剪贴板")
        except Exception as e:
            messagebox.showerror("错误", f"复制到剪贴板失败：{e}", parent=self)

    def _reset_scale(self) -> None:
        self._scale = 1.0
        self._display()

    def _reset_alpha(self) -> None:
        self._alpha = 1.0
        self.attributes("-alpha", 1.0)

    # ══════════════ 生命周期 ══════════════

    def hide(self) -> None:
        self.withdraw()

    def show(self) -> None:
        self.deiconify()

    def close(self) -> None:
        self._mgr.remove(self)
        self.destroy()
