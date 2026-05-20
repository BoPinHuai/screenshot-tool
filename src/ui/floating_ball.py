# ui/floating_ball.py — 悬浮球（v0.6：PIL 抗锯齿 + 自定义图片 + 截图通知 + 显隐热键）
#
# 渲染：
#   PIL 可用时  — 超采样（4×）后 LANCZOS 缩小，边缘平滑无锯齿
#   PIL 不可用  — 回退至 tkinter canvas.create_oval（像素风）
#   自定义图片  — 等比裁切为正方形 → 圆形遮罩 → 通知时叠加绿色角标
# 通知：
#   每次截图后调用 notify_capture()，球体变绿并显示累计次数，2 秒无新截图后恢复
# 显隐：
#   右键菜单"隐藏悬浮球" + 全局热键 hotkey_toggle_ball（默认 ctrl+alt+b）

import ctypes
import queue
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

import config as cfg_module
from hotkey import HotkeyManager

# ── 常量 ────────────────────────────────────────────────────────────────────
BALL_SIZE         = 56
_TRANSPARENT      = "black"
_COLOR_NORMAL     = "#1e88e5"   # 默认蓝
_COLOR_HOVER      = "#42a5f5"   # 悬停浅蓝
_COLOR_NOTIFY     = "#27ae60"   # 截图成功绿
_COLOR_OUTLINE    = "#1565c0"   # 轮廓深蓝
_GWL_EXSTYLE      = -20
_WS_EX_NOACTIVATE = 0x08000000
_WS_EX_TOOLWINDOW = 0x00000080
_DRAG_THRESHOLD   = 4           # 超过此像素才算拖动
_SUPERSAMPLE      = 4           # PIL 超采样倍率
_NOTIFY_MS        = 2000        # 通知保持时长（ms）

# 字体搜索顺序（支持中文 + ✓）
_FONT_CANDIDATES = [
    "msyh.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/Arial.ttf",
]


def _hex2rgb(h: str) -> tuple:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def _load_pil_font(size: int):
    """尝试加载合适的字体，失败返回 None。"""
    if not _PIL_OK:
        return None
    for fp in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(fp, size)
        except (IOError, OSError):
            continue
    return None


class FloatingBall(tk.Toplevel):
    """常驻桌面的圆形悬浮球（PIL 抗锯齿渲染）。"""

    def __init__(self, root: tk.Tk, panel, cfg: dict, on_quit) -> None:
        super().__init__(root)
        self._panel   = panel
        self._cfg     = cfg
        self._on_quit = on_quit
        self._size    = BALL_SIZE

        self._dragging    = False
        self._drag_sx     = 0
        self._drag_sy     = 0
        self._hover_active = False

        # 通知状态
        self._shot_count    = 0
        self._notify_job    = None
        self._notify_active = False

        # 热键 + 线程安全队列
        self._aq     = queue.Queue()
        self._hk_mgr = HotkeyManager()

        self._setup_window()
        self._build_canvas()
        self.update_idletasks()
        self._apply_win_style()
        self._register_toggle_hotkey()
        self._poll_queue()

    # ══════════════ 窗口初始化 ══════════════

    def _setup_window(self) -> None:
        s = self._size
        x = self._cfg.get("ball_x", 100)
        y = self._cfg.get("ball_y", 100)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-transparentcolor", _TRANSPARENT)
        self.configure(bg=_TRANSPARENT)
        self.geometry(f"{s}x{s}+{x}+{y}")

    def _build_canvas(self) -> None:
        s = self._size
        self._canvas = tk.Canvas(
            self, width=s, height=s,
            bg=_TRANSPARENT, highlightthickness=0,
        )
        self._canvas.place(x=0, y=0)

        self._photo_ref = None   # PIL PhotoImage 引用（防 GC）
        self._bg_item   = None   # canvas image item（PIL 模式）或 oval item（tkinter 回退）
        self._text_item = None   # canvas text item（tkinter 回退专用）

        self._redraw(color=_COLOR_NORMAL, label="截")

        self._canvas.bind("<ButtonPress-1>",   self._on_press)
        self._canvas.bind("<B1-Motion>",        self._on_motion)
        self._canvas.bind("<ButtonRelease-1>",  self._on_release)
        self._canvas.bind("<Button-3>",         self._on_right_click)
        self._canvas.bind("<Enter>",            self._on_hover_in)
        self._canvas.bind("<Leave>",            self._on_hover_out)

    # ── 渲染 ────────────────────────────────────────────────────────────────

    def _redraw(self, color: str = _COLOR_NORMAL, label: str = "截") -> None:
        """重绘悬浮球；PIL 可用时渲染矢量平滑圆，否则回退至 tkinter oval。"""
        if not _PIL_OK:
            self._redraw_tk(color, label)
            return

        img_path = self._cfg.get("ball_image_path", "").strip()
        use_custom = bool(img_path and Path(img_path).is_file())

        pil_img = (
            self._make_custom_img(img_path, self._size, label)
            if use_custom
            else self._make_circle_img(self._size, color, label)
        )

        self._photo_ref = ImageTk.PhotoImage(pil_img)
        if self._bg_item is None:
            self._bg_item = self._canvas.create_image(
                0, 0, anchor="nw", image=self._photo_ref
            )
        else:
            self._canvas.itemconfigure(self._bg_item, image=self._photo_ref)

        # PIL 图像已含文字，隐藏 tkinter 回退的 text item
        if self._text_item is not None:
            self._canvas.itemconfigure(self._text_item, state="hidden")

    def _make_circle_img(self, s: int, color: str, label: str) -> "Image.Image":
        """PIL 超采样：在 4× 分辨率绘制，LANCZOS 缩小到目标尺寸，边缘自然平滑。"""
        ss = s * _SUPERSAMPLE
        img  = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        m = 2 * _SUPERSAMPLE   # 边距

        # 外圈轮廓
        out_r, out_g, out_b = _hex2rgb(_COLOR_OUTLINE)
        draw.ellipse(
            [m - _SUPERSAMPLE, m - _SUPERSAMPLE,
             ss - m + _SUPERSAMPLE, ss - m + _SUPERSAMPLE],
            fill=(out_r, out_g, out_b, 255),
        )
        # 主色填充
        fr, fg, fb = _hex2rgb(color)
        draw.ellipse(
            [m, m, ss - m, ss - m],
            fill=(fr, fg, fb, 255),
        )

        # 文字居中
        font = _load_pil_font(16 * _SUPERSAMPLE)
        if font:
            bbox = draw.textbbox((0, 0), label, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            tx = (ss - tw) // 2 - bbox[0]
            ty = (ss - th) // 2 - bbox[1]
            draw.text((tx, ty), label, fill=(255, 255, 255, 255), font=font)

        return img.resize((s, s), Image.LANCZOS)

    def _make_custom_img(self, path: str, s: int, label: str) -> "Image.Image":
        """加载自定义图片 → 居中裁切为正方形 → 圆形遮罩 → 通知时叠加绿色角标。"""
        try:
            src = Image.open(path).convert("RGBA")
        except Exception:
            # 图片损坏或无法读取，回退到默认圆
            return self._make_circle_img(s, _COLOR_NORMAL, label)

        # 居中裁切为正方形
        w, h = src.size
        side = min(w, h)
        src  = src.crop(((w - side) // 2, (h - side) // 2,
                          (w + side) // 2, (h + side) // 2))
        src  = src.resize((s, s), Image.LANCZOS)

        # 圆形遮罩
        mask   = Image.new("L", (s, s), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, s - 1, s - 1], fill=255)
        result = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        result.paste(src, mask=mask)

        # 截图通知：右下角叠加绿色圆形角标
        if self._notify_active:
            br   = s // 5           # 角标半径
            bx0  = s - br * 2 - 1
            by0  = s - br * 2 - 1
            bx1  = s - 1
            by1  = s - 1
            draw = ImageDraw.Draw(result)
            draw.ellipse([bx0, by0, bx1, by1], fill=(39, 174, 96, 230))
            badge = str(self._shot_count) if self._shot_count > 1 else "✓"
            font  = _load_pil_font(br + 2)
            if font:
                bb  = draw.textbbox((0, 0), badge, font=font)
                tw, th = bb[2] - bb[0], bb[3] - bb[1]
                draw.text(
                    ((bx0 + bx1) // 2 - tw // 2 - bb[0],
                     (by0 + by1) // 2 - th // 2 - bb[1]),
                    badge,
                    fill=(255, 255, 255, 255),
                    font=font,
                )

        return result

    def _redraw_tk(self, color: str, label: str) -> None:
        """PIL 不可用时的纯 tkinter 回退（像素风圆形）。"""
        s = self._size
        if self._bg_item is None:
            self._bg_item = self._canvas.create_oval(
                2, 2, s - 2, s - 2,
                fill=color, outline=_COLOR_OUTLINE, width=2,
            )
            self._text_item = self._canvas.create_text(
                s // 2, s // 2,
                text=label,
                font=("Microsoft YaHei", 14, "bold"),
                fill="white",
            )
        else:
            self._canvas.itemconfigure(self._bg_item, fill=color)
            self._canvas.itemconfigure(
                self._text_item, text=label, state="normal"
            )

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

    # ══════════════ 热键（显隐） ══════════════

    def _register_toggle_hotkey(self) -> None:
        hk = self._cfg.get("hotkey_toggle_ball", "ctrl+alt+b").strip()
        if hk:
            self._hk_mgr.register(hk, lambda: self._aq.put(("toggle",)))

    def reload_hotkey(self) -> None:
        """配置保存后调用，重新注册显隐热键。"""
        self._hk_mgr.unregister_all()
        self._register_toggle_hotkey()

    def _poll_queue(self) -> None:
        try:
            while True:
                act = self._aq.get_nowait()
                if act[0] == "toggle":
                    self._toggle_visibility()
        except queue.Empty:
            pass
        self.after(20, self._poll_queue)

    def quit_cleanup(self) -> None:
        """程序退出前注销热键。"""
        self._hk_mgr.unregister_all()

    # ══════════════ 截图通知 ══════════════

    def notify_capture(self) -> None:
        """每次截图后调用：计数 +1，球变绿，2 秒无新截图后自动恢复。"""
        self._shot_count  += 1
        self._notify_active = True
        if self._notify_job is not None:
            self.after_cancel(self._notify_job)
        label = str(self._shot_count) if self._shot_count > 1 else "✓"
        self._redraw(color=_COLOR_NOTIFY, label=label)
        self._notify_job = self.after(_NOTIFY_MS, self._revert_ball)

    def _revert_ball(self) -> None:
        self._shot_count    = 0
        self._notify_job    = None
        self._notify_active = False
        color = _COLOR_HOVER if self._hover_active else _COLOR_NORMAL
        self._redraw(color=color, label="截")

    def reload_appearance(self) -> None:
        """配置中图片路径变化后调用，重绘悬浮球外观。"""
        if not self._notify_active:
            self._redraw(color=_COLOR_NORMAL, label="截")

    # ══════════════ 显隐 ══════════════

    def _toggle_visibility(self) -> None:
        if self.winfo_viewable():
            if self._panel.winfo_viewable():
                self._panel.withdraw()
            self.withdraw()
        else:
            self.deiconify()

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
            if self._panel.winfo_viewable():
                self._position_panel()

    def _on_release(self, event: tk.Event) -> None:
        if self._dragging:
            self._save_position()
        else:
            self._toggle_panel()
        self._dragging = False

    def _on_hover_in(self, _: tk.Event) -> None:
        self._hover_active = True
        if self._notify_active:
            return
        # 自定义图片模式不做颜色悬停（图片已固定）
        img_path = self._cfg.get("ball_image_path", "").strip()
        if not (img_path and Path(img_path).is_file()):
            self._redraw(color=_COLOR_HOVER, label="截")

    def _on_hover_out(self, _: tk.Event) -> None:
        self._hover_active = False
        if self._notify_active:
            return
        img_path = self._cfg.get("ball_image_path", "").strip()
        if not (img_path and Path(img_path).is_file()):
            self._redraw(color=_COLOR_NORMAL, label="截")

    # ══════════════ 面板开关 ══════════════

    def _toggle_panel(self) -> None:
        if self._panel.winfo_viewable():
            self._panel.withdraw()
        else:
            self._position_panel()
            self._panel.deiconify()
            self._panel.lift()

    def _position_panel(self) -> None:
        """把设置面板放在悬浮球旁边，自动避免超出屏幕边缘。"""
        bx = self.winfo_x()
        by = self.winfo_y()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        pw, ph = 740, 590   # 与 SettingsPanel.geometry 保持一致

        px = bx + self._size + 10
        if px + pw > sw:
            px = bx - pw - 10
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
        menu.add_command(label="⚙  设置",    command=self._open_settings)
        menu.add_command(label="隐藏悬浮球",  command=self.withdraw)
        menu.add_separator()
        menu.add_command(label="关于",        command=self._show_about)
        menu.add_command(label="退出",        command=self._on_quit)
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
        hk = self._cfg.get("hotkey_toggle_ball", "ctrl+alt+b")
        messagebox.showinfo(
            "关于截图工具",
            f"截图工具  v0.6\n\n"
            "固定区域截图 + 手动框选\n"
            "悬浮球形态，按快捷键立即截图\n"
            f"按 {hk} 可显示／隐藏悬浮球\n\n"
            "单击悬浮球展开设置",
            parent=self,
        )
