# ui/settings.py — 设置面板（单固定区域 + 全局设置，失焦自动保存）

import os
import time
import queue
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

import config as cfg_module
import capture
import utils
from ui.selector import run_selector
from hotkey import HotkeyManager

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

_PAD     = 14
_PANEL_W = 600
_PANEL_H = 390


class SettingsPanel(ctk.CTkToplevel):
    """设置面板。关闭按钮只隐藏，不退出程序。
    字段失焦或浏览/清除/标定后自动保存，无需手动点击保存按钮。
    """

    def __init__(self, master, cfg: dict) -> None:
        super().__init__(master)
        self._cfg    = cfg
        self._aq     = queue.Queue()
        self._hk_mgr = HotkeyManager()
        self._ball   = None

        self.title("Kang — 设置")
        self.geometry(f"{_PANEL_W}x{_PANEL_H}")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.withdraw)

        self._build_ui()
        self._register_hotkeys()
        self._poll_queue()
        self.withdraw()

    def set_ball(self, ball) -> None:
        self._ball = ball

    # ══════════════ 快捷键管理 ══════════════

    def _register_hotkeys(self) -> None:
        self._hk_mgr.unregister_all()
        sel_hk = self._cfg.get("hotkey_select", "").strip()
        if sel_hk:
            self._hk_mgr.register(sel_hk, lambda: self._aq.put(("select",)))
        fix_hk = self._cfg.get("hotkey_fixed", "").strip()
        if fix_hk:
            region = dict(self._cfg.get("fixed_region", {}))
            self._hk_mgr.register(fix_hk, lambda r=region: self._aq.put(("fixed", r)))

    def quit_cleanup(self) -> None:
        self._hk_mgr.unregister_all()

    # ══════════════ 队列轮询 ══════════════

    def _poll_queue(self) -> None:
        try:
            while True:
                act = self._aq.get_nowait()
                if act[0] == "fixed":
                    capture.capture_region(act[1], self._cfg["save_dir"])
                    if self._ball:
                        self._ball.notify_capture()
                elif act[0] == "select":
                    ok = capture.capture_select(self, self._cfg["save_dir"])
                    if ok and self._ball:
                        self._ball.notify_capture()
        except queue.Empty:
            pass
        self.after(20, self._poll_queue)

    # ══════════════ 构建 UI ══════════════

    def _build_ui(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        r = 0

        # ─── 固定截图区域 ───
        ctk.CTkLabel(
            self, text="固定截图区域",
            font=ctk.CTkFont(size=13, weight="bold"), anchor="w",
        ).grid(row=r, column=0, columnspan=3, padx=_PAD, pady=(_PAD, 2), sticky="w")
        r += 1

        # 快捷键
        ctk.CTkLabel(self, text="快捷键", anchor="w").grid(
            row=r, column=0, padx=(_PAD, 8), pady=5, sticky="w")
        self._fixed_hk_var = tk.StringVar(
            value=self._cfg.get("hotkey_fixed", "ctrl+alt+s"))
        e = ctk.CTkEntry(self, textvariable=self._fixed_hk_var,
                         placeholder_text="例如  ctrl+alt+s")
        e.grid(row=r, column=1, columnspan=2, padx=(4, _PAD), pady=5, sticky="ew")
        e.bind("<FocusOut>", lambda _: self._auto_save())
        r += 1

        # 坐标
        ctk.CTkLabel(self, text="截图区域", anchor="w").grid(
            row=r, column=0, padx=(_PAD, 8), pady=5, sticky="w")
        coord_f = ctk.CTkFrame(self, fg_color="transparent")
        coord_f.grid(row=r, column=1, columnspan=2, padx=(4, _PAD), pady=5, sticky="w")
        region = self._cfg.get("fixed_region",
                               {"left": 0, "top": 0, "width": 800, "height": 600})
        self._lvar = tk.StringVar(value=str(region.get("left",   0)))
        self._tvar = tk.StringVar(value=str(region.get("top",    0)))
        self._wvar = tk.StringVar(value=str(region.get("width",  800)))
        self._hvar = tk.StringVar(value=str(region.get("height", 600)))
        for ci, (lbl, var) in enumerate([
            ("Left", self._lvar), ("Top", self._tvar),
            ("宽",   self._wvar), ("高",  self._hvar),
        ]):
            ctk.CTkLabel(coord_f, text=lbl, width=32, anchor="e").grid(
                row=0, column=ci * 2, padx=(0, 2))
            ec = ctk.CTkEntry(coord_f, textvariable=var, width=72)
            ec.grid(row=0, column=ci * 2 + 1, padx=(0, 10))
            ec.bind("<FocusOut>", lambda _: self._auto_save())
        r += 1

        # 标定 + 测试
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=r, column=0, columnspan=3, padx=_PAD, pady=(4, _PAD), sticky="w")
        ctk.CTkButton(btns, text="📐  标定区域（拖框自动填入坐标）",
                      width=220, command=self._calibrate).pack(side=tk.LEFT, padx=(0, 10))
        ctk.CTkButton(btns, text="📷  测试截图",
                      width=130, command=self._test_capture).pack(side=tk.LEFT)
        r += 1

        # ─── 分割线 ───
        ctk.CTkFrame(self, height=1, fg_color=("gray75", "gray40")).grid(
            row=r, column=0, columnspan=3, padx=_PAD, pady=4, sticky="ew")
        r += 1

        # ─── 全局设置 ───
        ctk.CTkLabel(
            self, text="全局设置",
            font=ctk.CTkFont(size=13, weight="bold"), anchor="w",
        ).grid(row=r, column=0, columnspan=3, padx=_PAD, pady=(4, 2), sticky="w")
        r += 1

        # 保存目录
        ctk.CTkLabel(self, text="保存目录", anchor="w").grid(
            row=r, column=0, padx=(_PAD, 8), pady=5, sticky="w")
        self._savedir_var = tk.StringVar(value=self._cfg.get("save_dir", ""))
        e_dir = ctk.CTkEntry(self, textvariable=self._savedir_var)
        e_dir.grid(row=r, column=1, padx=4, pady=5, sticky="ew")
        e_dir.bind("<FocusOut>", lambda _: self._auto_save())
        ctk.CTkButton(self, text="浏览", width=60,
                      command=self._browse_dir).grid(
            row=r, column=2, padx=(4, _PAD), pady=5)
        r += 1

        # 框选快捷键
        ctk.CTkLabel(self, text="框选快捷键", anchor="w").grid(
            row=r, column=0, padx=(_PAD, 8), pady=5, sticky="w")
        self._sel_hk_var = tk.StringVar(value=self._cfg.get("hotkey_select", ""))
        e2 = ctk.CTkEntry(self, textvariable=self._sel_hk_var,
                          placeholder_text="例如  ctrl+alt+d")
        e2.grid(row=r, column=1, columnspan=2, padx=(4, _PAD), pady=5, sticky="ew")
        e2.bind("<FocusOut>", lambda _: self._auto_save())
        r += 1

        # 悬浮球热键
        ctk.CTkLabel(self, text="悬浮球热键", anchor="w").grid(
            row=r, column=0, padx=(_PAD, 8), pady=5, sticky="w")
        self._toggle_hk_var = tk.StringVar(
            value=self._cfg.get("hotkey_toggle_ball", "ctrl+alt+b"))
        e3 = ctk.CTkEntry(self, textvariable=self._toggle_hk_var,
                          placeholder_text="例如  ctrl+alt+b")
        e3.grid(row=r, column=1, columnspan=2, padx=(4, _PAD), pady=5, sticky="ew")
        e3.bind("<FocusOut>", lambda _: self._auto_save())
        r += 1

        # 悬浮球图片
        ctk.CTkLabel(self, text="悬浮球图片", anchor="w").grid(
            row=r, column=0, padx=(_PAD, 8), pady=5, sticky="w")
        self._ball_img_var = tk.StringVar(
            value=self._cfg.get("ball_image_path", ""))
        e4 = ctk.CTkEntry(self, textvariable=self._ball_img_var,
                          placeholder_text="留空则显示默认蓝色圆形")
        e4.grid(row=r, column=1, padx=4, pady=5, sticky="ew")
        e4.bind("<FocusOut>", lambda _: self._auto_save())
        img_btns = ctk.CTkFrame(self, fg_color="transparent")
        img_btns.grid(row=r, column=2, padx=(4, _PAD), pady=5)
        ctk.CTkButton(img_btns, text="浏览", width=50,
                      command=self._browse_ball_img).pack(side=tk.LEFT, padx=(0, 4))
        ctk.CTkButton(img_btns, text="清除", width=50,
                      fg_color="#95a5a6", hover_color="#7f8c8d",
                      command=self._clear_ball_img).pack(side=tk.LEFT)
        r += 1

        # 开机自启
        self._autostart_var = tk.BooleanVar(value=utils.get_autostart())
        ctk.CTkCheckBox(
            self, text="开机自动启动",
            variable=self._autostart_var,
            state="normal" if utils.is_packaged() else "disabled",
            command=self._auto_save,
        ).grid(row=r, column=0, columnspan=3, padx=_PAD, pady=(4, _PAD), sticky="w")

    # ══════════════ 自动保存 ══════════════

    def _auto_save(self) -> None:
        try:
            region = {
                "left":   int(self._lvar.get()),
                "top":    int(self._tvar.get()),
                "width":  int(self._wvar.get()),
                "height": int(self._hvar.get()),
            }
        except ValueError:
            region = self._cfg.get("fixed_region",
                                   {"left": 0, "top": 0, "width": 800, "height": 600})
        self._cfg["fixed_region"]       = region
        self._cfg["hotkey_fixed"]       = self._fixed_hk_var.get().strip()
        self._cfg["save_dir"]           = self._savedir_var.get().strip()
        self._cfg["hotkey_select"]      = self._sel_hk_var.get().strip()
        self._cfg["hotkey_toggle_ball"] = self._toggle_hk_var.get().strip()
        self._cfg["ball_image_path"]    = self._ball_img_var.get().strip()
        os.makedirs(self._cfg["save_dir"], exist_ok=True)
        cfg_module.save(self._cfg)
        self._register_hotkeys()
        utils.set_autostart(self._autostart_var.get())
        if self._ball:
            self._ball.reload_hotkey()
            self._ball.reload_appearance()

    # ══════════════ 标定 / 测试 ══════════════

    def _calibrate(self) -> None:
        self.withdraw()
        self.update()
        time.sleep(0.15)
        region = run_selector(self)
        self.deiconify()
        if region:
            self._lvar.set(str(region["left"]))
            self._tvar.set(str(region["top"]))
            self._wvar.set(str(region["width"]))
            self._hvar.set(str(region["height"]))
            self._auto_save()

    def _test_capture(self) -> None:
        try:
            region = {
                "left":   int(self._lvar.get()),
                "top":    int(self._tvar.get()),
                "width":  int(self._wvar.get()),
                "height": int(self._hvar.get()),
            }
        except ValueError:
            messagebox.showerror("错误", "坐标必须是整数", parent=self)
            return
        capture.capture_region(region, self._savedir_var.get().strip())
        if self._ball:
            self._ball.notify_capture()

    # ══════════════ 浏览 / 清除 ══════════════

    def _browse_dir(self) -> None:
        path = filedialog.askdirectory(title="选择截图保存目录", parent=self)
        if path:
            self._savedir_var.set(path)
            self._auto_save()

    def _browse_ball_img(self) -> None:
        path = filedialog.askopenfilename(
            title="选择悬浮球图片",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.webp *.bmp"),
                       ("所有文件", "*.*")],
            parent=self,
        )
        if path:
            self._ball_img_var.set(path)
            self._auto_save()

    def _clear_ball_img(self) -> None:
        self._ball_img_var.set("")
        self._auto_save()
