# ui/settings.py — 设置面板（Stage 4：CTkToplevel，由悬浮球控制显示）
#
# 布局：
#   左栏  — 预设列表 + 添加/删除按钮
#   右栏  — 预设编辑表单（名称、区域坐标、标定、快捷键、测试）
#   底栏  — 全局设置（保存目录、框选快捷键、保存按钮）

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

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

_PAD = 10


class SettingsPanel(ctk.CTkToplevel):
    """设置面板（Stage 4 形态：悬浮球旁弹出的 Toplevel）。
    关闭按钮只隐藏面板，不退出程序。
    退出由 FloatingBall 右键菜单触发，调用 quit_cleanup()。
    """

    def __init__(self, master, cfg: dict) -> None:
        super().__init__(master)
        self._cfg     = cfg
        self._sel_idx = -1
        self._aq: queue.Queue = queue.Queue()
        self._hk_mgr  = HotkeyManager()
        self._ball    = None   # FloatingBall 引用，由 set_ball() 注入

        self.title("Kang — 设置")
        self.geometry("740x590")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.withdraw)  # 关闭 = 隐藏

        self._build_ui()
        self._register_hotkeys()
        self._poll_queue()

        if self._cfg["presets"]:
            self._select_preset(0)

        self.withdraw()   # 初始隐藏，等悬浮球单击后再显示

    def set_ball(self, ball) -> None:
        """由 main.py 在 FloatingBall 创建后调用，注入悬浮球引用以发送通知。"""
        self._ball = ball

    # ══════════════ 快捷键管理 ══════════════

    def _make_fixed_cb(self, region: dict):
        q, r = self._aq, dict(region)
        return lambda: q.put(("fixed", r))

    def _register_hotkeys(self) -> None:
        self._hk_mgr.unregister_all()
        for p in self._cfg["presets"]:
            hk = p.get("hotkey", "").strip()
            if hk:
                self._hk_mgr.register(hk, self._make_fixed_cb(p["region"]))
        sel_hk = self._cfg.get("hotkey_select", "").strip()
        if sel_hk:
            self._hk_mgr.register(sel_hk, lambda: self._aq.put(("select",)))

    def quit_cleanup(self) -> None:
        """程序退出前调用：注销所有快捷键。"""
        self._hk_mgr.unregister_all()

    # ══════════════ 队列轮询 ══════════════

    def _poll_queue(self) -> None:
        """每 20ms 检查一次快捷键事件队列（面板隐藏时照样运行）。"""
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
        self.grid_columnconfigure(0, weight=0, minsize=200)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        lf = ctk.CTkFrame(self, width=200, corner_radius=8)
        lf.grid(row=0, column=0, padx=(_PAD, 4), pady=_PAD, sticky="nsew")
        lf.grid_propagate(False)
        self._build_left(lf)

        rf = ctk.CTkFrame(self, corner_radius=8)
        rf.grid(row=0, column=1, padx=(4, _PAD), pady=_PAD, sticky="nsew")
        self._build_right(rf)

        bf = ctk.CTkFrame(self, corner_radius=8)
        bf.grid(row=1, column=0, columnspan=2, padx=_PAD, pady=(0, _PAD), sticky="ew")
        self._build_bottom(bf)

    # ── 左栏 ──

    def _build_left(self, parent: ctk.CTkFrame) -> None:
        ctk.CTkLabel(
            parent, text="预设列表", font=ctk.CTkFont(size=13, weight="bold")
        ).pack(padx=_PAD, pady=(_PAD, 4), anchor="w")

        self._preset_scroll = ctk.CTkScrollableFrame(parent, corner_radius=6)
        self._preset_scroll.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(fill=tk.X, padx=6, pady=(4, _PAD))
        ctk.CTkButton(btn_row, text="＋ 添加", width=82,
                      command=self._add_preset).pack(side=tk.LEFT)
        ctk.CTkButton(btn_row, text="－ 删除", width=82,
                      fg_color="#c0392b", hover_color="#922b21",
                      command=self._delete_preset).pack(side=tk.RIGHT)

        self._preset_btns: list[ctk.CTkButton] = []
        self._refresh_preset_list()

    # ── 右栏 ──

    def _build_right(self, parent: ctk.CTkFrame) -> None:
        parent.grid_columnconfigure(1, weight=1)
        r = 0

        ctk.CTkLabel(parent, text="预设名称").grid(
            row=r, column=0, padx=_PAD, pady=(_PAD + 4, 4), sticky="w")
        self._name_var = tk.StringVar()
        ctk.CTkEntry(parent, textvariable=self._name_var).grid(
            row=r, column=1, padx=(0, _PAD), pady=(_PAD + 4, 4), sticky="ew")

        r += 1
        ctk.CTkLabel(parent, text="截图区域",
                     font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=r, column=0, columnspan=2, padx=_PAD, pady=(10, 2), sticky="w")

        r += 1
        cf = ctk.CTkFrame(parent, fg_color="transparent")
        cf.grid(row=r, column=0, columnspan=2, padx=_PAD, pady=2, sticky="w")
        self._lvar = tk.StringVar()
        self._tvar = tk.StringVar()
        self._wvar = tk.StringVar()
        self._hvar = tk.StringVar()
        for ci, (lbl, var) in enumerate([
            ("Left", self._lvar), ("Top",  self._tvar),
            ("宽 W",  self._wvar), ("高 H", self._hvar),
        ]):
            ctk.CTkLabel(cf, text=lbl, width=38, anchor="e").grid(
                row=0, column=ci * 2, padx=(0, 2))
            ctk.CTkEntry(cf, textvariable=var, width=72).grid(
                row=0, column=ci * 2 + 1, padx=(0, 10))

        r += 1
        ctk.CTkButton(
            parent, text="📐  标定区域（拖框自动填入坐标）",
            command=self._calibrate,
        ).grid(row=r, column=0, columnspan=2, padx=_PAD, pady=(6, 2), sticky="ew")

        r += 1
        ctk.CTkLabel(parent, text="快捷键").grid(
            row=r, column=0, padx=_PAD, pady=(10, 4), sticky="w")
        self._hotkey_var = tk.StringVar()
        ctk.CTkEntry(parent, textvariable=self._hotkey_var,
                     placeholder_text="例如  ctrl+alt+s").grid(
            row=r, column=1, padx=(0, _PAD), pady=(10, 4), sticky="ew")

        r += 1
        ctk.CTkButton(
            parent, text="📷  测试截图",
            command=self._test_capture,
        ).grid(row=r, column=0, columnspan=2, padx=_PAD, pady=(4, _PAD), sticky="ew")

    # ── 底栏 ──

    def _build_bottom(self, parent: ctk.CTkFrame) -> None:
        parent.grid_columnconfigure(1, weight=1)

        # 保存目录
        ctk.CTkLabel(parent, text="保存目录").grid(
            row=0, column=0, padx=_PAD, pady=(_PAD, 4), sticky="w")
        self._savedir_var = tk.StringVar(value=self._cfg.get("save_dir", ""))
        ctk.CTkEntry(parent, textvariable=self._savedir_var).grid(
            row=0, column=1, padx=4, pady=(_PAD, 4), sticky="ew")
        ctk.CTkButton(parent, text="浏览", width=60,
                      command=self._browse_dir).grid(
            row=0, column=2, padx=(0, _PAD), pady=(_PAD, 4))

        # 框选快捷键
        ctk.CTkLabel(parent, text="框选快捷键").grid(
            row=1, column=0, padx=_PAD, pady=(0, 4), sticky="w")
        self._sel_hk_var = tk.StringVar(value=self._cfg.get("hotkey_select", ""))
        ctk.CTkEntry(parent, textvariable=self._sel_hk_var,
                     placeholder_text="例如  ctrl+alt+d").grid(
            row=1, column=1, padx=4, pady=(0, 4), sticky="w")

        # 悬浮球显隐热键
        ctk.CTkLabel(parent, text="悬浮球热键").grid(
            row=2, column=0, padx=_PAD, pady=(0, 4), sticky="w")
        self._toggle_hk_var = tk.StringVar(
            value=self._cfg.get("hotkey_toggle_ball", "ctrl+alt+b"))
        ctk.CTkEntry(parent, textvariable=self._toggle_hk_var,
                     placeholder_text="例如  ctrl+alt+b").grid(
            row=2, column=1, padx=4, pady=(0, 4), sticky="w")

        # 悬浮球自定义图片
        ctk.CTkLabel(parent, text="悬浮球图片").grid(
            row=3, column=0, padx=_PAD, pady=(0, 4), sticky="w")
        self._ball_img_var = tk.StringVar(
            value=self._cfg.get("ball_image_path", ""))
        ctk.CTkEntry(parent, textvariable=self._ball_img_var,
                     placeholder_text="留空则显示默认蓝色圆形").grid(
            row=3, column=1, padx=4, pady=(0, 4), sticky="ew")
        btn_img_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_img_row.grid(row=3, column=2, padx=(0, _PAD), pady=(0, 4))
        ctk.CTkButton(btn_img_row, text="浏览", width=54,
                      command=self._browse_ball_img).pack(side=tk.LEFT, padx=(0, 4))
        ctk.CTkButton(btn_img_row, text="清除", width=54,
                      fg_color="#7f8c8d", hover_color="#636e72",
                      command=lambda: self._ball_img_var.set("")).pack(side=tk.LEFT)

        # 开机自启（仅打包后的 exe 有效，开发模式灰显）
        self._autostart_var = tk.BooleanVar(value=utils.get_autostart())
        autostart_cb = ctk.CTkCheckBox(
            parent, text="开机自动启动",
            variable=self._autostart_var,
            state="normal" if utils.is_packaged() else "disabled",
        )
        autostart_cb.grid(row=4, column=0, columnspan=2,
                          padx=_PAD, pady=(0, _PAD), sticky="w")

        # 保存按钮
        ctk.CTkButton(parent, text="💾  保存配置", width=110,
                      command=self._save_config).grid(
            row=4, column=2, padx=(0, _PAD), pady=(0, _PAD))

    # ══════════════ 预设列表操作 ══════════════

    def _refresh_preset_list(self) -> None:
        for b in self._preset_btns:
            b.destroy()
        self._preset_btns.clear()
        for i, p in enumerate(self._cfg["presets"]):
            selected = (i == self._sel_idx)
            b = ctk.CTkButton(
                self._preset_scroll,
                text=p.get("name", f"预设{i + 1}"),
                anchor="w",
                fg_color=("gray70", "gray30") if selected else "transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray65", "gray35"),
                command=lambda idx=i: self._select_preset(idx),
            )
            b.pack(fill=tk.X, pady=2)
            self._preset_btns.append(b)

    def _select_preset(self, idx: int) -> None:
        if self._sel_idx >= 0:
            self._flush_form()
        self._sel_idx = idx
        self._refresh_preset_list()
        p = self._cfg["presets"][idx]
        self._name_var.set(p.get("name", ""))
        reg = p.get("region", {})
        self._lvar.set(str(reg.get("left",   0)))
        self._tvar.set(str(reg.get("top",    0)))
        self._wvar.set(str(reg.get("width",  0)))
        self._hvar.set(str(reg.get("height", 0)))
        self._hotkey_var.set(p.get("hotkey", ""))

    def _flush_form(self) -> None:
        if self._sel_idx < 0 or self._sel_idx >= len(self._cfg["presets"]):
            return
        try:
            region = {
                "left":   int(self._lvar.get()),
                "top":    int(self._tvar.get()),
                "width":  int(self._wvar.get()),
                "height": int(self._hvar.get()),
            }
        except ValueError:
            region = self._cfg["presets"][self._sel_idx].get("region", {})
        self._cfg["presets"][self._sel_idx] = {
            "name":   self._name_var.get().strip(),
            "region": region,
            "hotkey": self._hotkey_var.get().strip(),
        }

    def _add_preset(self) -> None:
        self._flush_form()
        self._cfg["presets"].append({
            "name":   f"预设{len(self._cfg['presets']) + 1}",
            "region": {"left": 0, "top": 0, "width": 400, "height": 300},
            "hotkey": "",
        })
        self._sel_idx = -1
        self._select_preset(len(self._cfg["presets"]) - 1)

    def _delete_preset(self) -> None:
        if self._sel_idx < 0 or not self._cfg["presets"]:
            return
        self._cfg["presets"].pop(self._sel_idx)
        self._sel_idx = -1
        if self._cfg["presets"]:
            self._select_preset(0)
        else:
            self._refresh_preset_list()
            for v in (self._name_var, self._lvar, self._tvar,
                      self._wvar, self._hvar, self._hotkey_var):
                v.set("")

    # ══════════════ 按钮动作 ══════════════

    def _calibrate(self) -> None:
        """隐藏面板 → 用户拖框标定 → 坐标自动回填。"""
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

    def _browse_dir(self) -> None:
        path = filedialog.askdirectory(title="选择截图保存目录", parent=self)
        if path:
            self._savedir_var.set(path)

    def _browse_ball_img(self) -> None:
        path = filedialog.askopenfilename(
            title="选择悬浮球图片",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.webp *.bmp"), ("所有文件", "*.*")],
            parent=self,
        )
        if path:
            self._ball_img_var.set(path)

    def _save_config(self) -> None:
        self._flush_form()
        self._cfg["save_dir"]           = self._savedir_var.get().strip()
        self._cfg["hotkey_select"]      = self._sel_hk_var.get().strip()
        self._cfg["hotkey_toggle_ball"] = self._toggle_hk_var.get().strip()
        self._cfg["ball_image_path"]    = self._ball_img_var.get().strip()
        os.makedirs(self._cfg["save_dir"], exist_ok=True)
        cfg_module.save(self._cfg)
        self._register_hotkeys()
        self._refresh_preset_list()
        utils.set_autostart(self._autostart_var.get())
        if self._ball:
            self._ball.reload_hotkey()
            self._ball.reload_appearance()
        messagebox.showinfo("已保存", "配置已保存，快捷键已重新注册。", parent=self)
