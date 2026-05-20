# ui/floating_ball.py — 悬浮球
#
# 形态：圆形无边框置顶窗口，黑色背景 + -transparentcolor 实现透明角
# 交互：
#   左键拖动  — 移动位置，松手后记忆
#   左键单击  — 展开 / 收起设置面板
#   右键      — 上下文菜单（设置 / 关于 / 退出）
# 样式：
#   WS_EX_NOACTIVATE  — 不抢键盘焦点
#   WS_EX_TOOLWINDOW  — 不出现在任务栏

import ctypes
import tkinter as tk
from tkinter import messagebox

import config as cfg_module

# ── 常量 ──────────────────────────────────────────────────────────────────────
BALL_SIZE        = 56            # 悬浮球直径（像素）
_TRANSPARENT     = "black"       # 透明背景色
_COLOR_NORMAL    = "#1e88e5"     # 默认球色（蓝）
_COLOR_HOVER     = "#42a5f5"     # 悬停球色
_COLOR_OUTLINE   = "#1565c0"     # 轮廓色
_GWL_EXSTYLE     = -20
_WS_EX_NOACTIVATE = 0x08000000
_WS_EX_TOOLWINDOW = 0x00000080
# 拖动判定阈值（像素）：超过此值才算拖动，否则视为单击
_DRAG_THRESHOLD  = 4


class FloatingBall(tk.Toplevel):
    """常驻桌面的圆形悬浮球。"""

    def __init__(self, root: tk.Tk, panel, cfg: dict, on_quit) -> None:
        super().__init__(root)
        self._panel     = panel
        self._cfg       = cfg
        self._on_quit   = on_quit
        self._size      = BALL_SIZE
        self._dragging  = False
        self._drag_sx   = 0
        self._drag_sy   = 0

        self._setup_window()
        self._build_canvas()
        self.update_idletasks()
        self._apply_win_style()

    # ══════════════ 窗口初始化 ══════════════

    def _setup_window(self) -> None:
        s = self._size
        x = self._cfg.get("ball_x", 100)
        y = self._cfg.get("ball_y", 100)

        self.overrideredirect(True)                          # 无标题栏
        self.attributes("-topmost", True)                    # 置顶
        self.attributes("-transparentcolor", _TRANSPARENT)   # 黑色区域透明
        self.configure(bg=_TRANSPARENT)
        self.geometry(f"{s}x{s}+{x}+{y}")

    def _build_canvas(self) -> None:
        s = self._size
        self._canvas = tk.Canvas(
            self, width=s, height=s,
            bg=_TRANSPARENT, highlightthickness=0,
        )
        self._canvas.place(x=0, y=0)

        # 圆形球体
        self._oval = self._canvas.create_oval(
            2, 2, s - 2, s - 2,
            fill=_COLOR_NORMAL, outline=_COLOR_OUTLINE, width=2,
        )
        # 中心文字（CJK 字符，渲染稳定）
        self._canvas.create_text(
            s // 2, s // 2,
            text="截", font=("Microsoft YaHei", 16, "bold"), fill="white",
        )

        # 事件绑定
        self._canvas.bind("<ButtonPress-1>",  self._on_press)
        self._canvas.bind("<B1-Motion>",       self._on_motion)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<Button-3>",        self._on_right_click)
        self._canvas.bind("<Enter>",           self._on_hover_in)
        self._canvas.bind("<Leave>",           self._on_hover_out)

    def _apply_win_style(self) -> None:
        """设 WS_EX_NOACTIVATE（不抢焦点）+ WS_EX_TOOLWINDOW（不出现在任务栏）。"""
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
            print(f"[悬浮球] 窗口样式设置失败：{e}")

    # ══════════════ 鼠标事件 ══════════════

    def _on_press(self, event: tk.Event) -> None:
        self._drag_sx  = event.x
        self._drag_sy  = event.y
        self._dragging = False

    def _on_motion(self, event: tk.Event) -> None:
        dx = event.x - self._drag_sx
        dy = event.y - self._drag_sy
        if not self._dragging:
            if abs(dx) > _DRAG_THRESHOLD or abs(dy) > _DRAG_THRESHOLD:
                self._dragging = True
        if self._dragging:
            nx = self.winfo_x() + dx
            ny = self.winfo_y() + dy
            self.geometry(f"+{nx}+{ny}")
            # 面板跟随悬浮球移动
            if self._panel.winfo_viewable():
                self._position_panel()

    def _on_release(self, event: tk.Event) -> None:
        if self._dragging:
            self._save_position()
        else:
            self._toggle_panel()
        self._dragging = False

    def _on_hover_in(self, _: tk.Event) -> None:
        self._canvas.itemconfigure(self._oval, fill=_COLOR_HOVER)

    def _on_hover_out(self, _: tk.Event) -> None:
        self._canvas.itemconfigure(self._oval, fill=_COLOR_NORMAL)

    # ══════════════ 面板开关 ══════════════

    def _toggle_panel(self) -> None:
        if self._panel.winfo_viewable():
            self._panel.withdraw()
        else:
            self._position_panel()
            self._panel.deiconify()
            self._panel.lift()          # 确保面板在最前

    def _position_panel(self) -> None:
        """把设置面板放在悬浮球旁边，自动避免超出屏幕边缘。"""
        bx = self.winfo_x()
        by = self.winfo_y()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        pw, ph = 740, 530

        # 优先放右侧，放不下就放左侧
        px = bx + self._size + 10
        if px + pw > sw:
            px = bx - pw - 10

        # 顶部与悬浮球对齐，超出屏幕则上移
        py = max(0, min(by, sh - ph))
        self._panel.geometry(f"{pw}x{ph}+{px}+{py}")

    # ══════════════ 位置记忆 ══════════════

    def _save_position(self) -> None:
        self._cfg["ball_x"] = self.winfo_x()
        self._cfg["ball_y"] = self.winfo_y()
        cfg_module.save(self._cfg)

    # ══════════════ 右键菜单 ══════════════

    def _on_right_click(self, event: tk.Event) -> None:
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="⚙  设置", command=self._open_settings)
        menu.add_separator()
        menu.add_command(label="关于",    command=self._show_about)
        menu.add_command(label="退出",    command=self._on_quit)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _open_settings(self) -> None:
        if not self._panel.winfo_viewable():
            self._position_panel()
            self._panel.deiconify()
            self._panel.lift()

    def _show_about(self) -> None:
        messagebox.showinfo(
            "关于截图工具",
            "截图工具  v0.4\n\n"
            "固定区域截图 + 手动框选\n"
            "悬浮球形态，按快捷键立即截图\n\n"
            "单击悬浮球展开设置",
            parent=self,
        )
