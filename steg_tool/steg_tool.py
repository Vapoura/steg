# -*- coding: utf-8 -*-
"""
图片藏东西 —— 把任意文件嵌进 PNG / JPG 的尾部
载体图片照常打开，藏进去的文件可以用「提取」页签拿回来。
"""
import os
import struct
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from PIL import Image, ImageTk

APP_NAME = "图片藏东西"

# 尾部索引：payload + name + <Q payload_len><H name_len> + MAGIC
MAGIC = b"STEGv1\x00\x00"
FIXED = 18          # 8(magic) + 2(name_len) + 8(payload_len)

# ---------------- 配色 ----------------
BG       = "#0f1117"
CARD     = "#161922"
CARD_HI  = "#1d2130"
CARD_HOV = "#242a3a"
BORDER   = "#2a3040"
FG       = "#e7eaf3"
FG_DIM   = "#8b93a7"
FG_MUTE  = "#5d6577"
ACCENT   = "#4c8dff"
ACCENT_D = "#3a76e0"
ACCENT_H = "#5f9bff"
OK       = "#3ddc97"
WARN     = "#f0b23c"
ERR      = "#ff6b6b"

F_TITLE = ("Microsoft YaHei UI", 15, "bold")
F_H2    = ("Microsoft YaHei UI", 10, "bold")
F_BODY  = ("Microsoft YaHei UI", 9)
F_SMALL = ("Microsoft YaHei UI", 8)
F_MONO  = ("Consolas", 9)
F_BTN   = ("Microsoft YaHei UI", 10, "bold")


# ---------------- 核心逻辑 ----------------

def human_size(n):
    if n < 1024:
        return "%d B" % n
    v = float(n)
    for u in ("KB", "MB", "GB", "TB"):
        v /= 1024.0
        if v < 1024 or u == "TB":
            return "%.1f %s" % (v, u)


def sniff_image(path):
    """只看文件头判断真实格式，不信扩展名"""
    try:
        with open(path, "rb") as f:
            head = f.read(8)
    except OSError:
        return None
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if head.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    return None


def embed_file(carrier, payload, out_path):
    """把 payload 追加到载体图片末尾，返回 (载体字节, 载荷字节, 输出字节)"""
    with open(carrier, "rb") as f:
        img = f.read()
    with open(payload, "rb") as f:
        pay = f.read()
    name = os.path.basename(payload).encode("utf-8")
    blob = img + pay + name + struct.pack("<QH", len(pay), len(name)) + MAGIC
    with open(out_path, "wb") as f:
        f.write(blob)
    return len(img), len(pay), len(blob)


def parse_file(path):
    """从图片尾部还原出载荷，没有索引则返回 None"""
    with open(path, "rb") as f:
        d = f.read()
    if len(d) < FIXED or d[-8:] != MAGIC:
        return None
    name_len = struct.unpack("<H", d[-10:-8])[0]
    pay_len = struct.unpack("<Q", d[-18:-10])[0]
    start = len(d) - FIXED - name_len - pay_len
    if start < 0 or pay_len > len(d):
        return None
    name = d[start + pay_len:start + pay_len + name_len].decode("utf-8", "replace")
    return {
        "name": name or "unnamed.bin",
        "payload": d[start:start + pay_len],
        "image_len": start,
        "total": len(d),
    }


def verify_image(path, expect_size):
    """完整解码一遍，确认图片没被破坏"""
    im = Image.open(path)
    im.load()
    return im.size == expect_size, im.size


# ---------------- 界面 ----------------

class App:
    def __init__(self, root):
        self.root = root
        self.carrier = None
        self.carrier_size = None
        self.payload = None
        self.extract_src = None
        self.extract_info = None
        self._thumb = None
        self.tab = "embed"

        root.title(APP_NAME)
        root.configure(bg=BG)
        root.geometry("960x646")
        root.minsize(900, 620)

        self._build_header()

        self.body = tk.Frame(root, bg=BG)
        self.body.pack(fill="both", expand=True, padx=26, pady=(14, 0))

        self.panel_embed = self._build_embed(self.body)
        self.panel_extract = self._build_extract(self.body)

        self.bar = tk.Frame(root, bg=BG, height=42)
        self.bar.pack(fill="x", side="bottom")
        self.lbl_status = tk.Label(self.bar, text="", font=F_BODY, bg=BG, fg=FG_DIM, anchor="w")
        self.lbl_status.pack(side="left", padx=28, pady=(0, 12))

        self.switch("embed")

    # -------- 通用小部件 --------

    def _btn(self, parent, text, cmd, kind="ghost", width=None, font=None):
        if kind == "primary":
            bg, fg, hov = ACCENT, "#ffffff", ACCENT_H
        elif kind == "ghost":
            bg, fg, hov = CARD_HI, FG, CARD_HOV
        else:
            bg, fg, hov = CARD, FG_DIM, CARD_HI
        b = tk.Button(
            parent, text=text, command=cmd, bg=bg, fg=fg,
            activebackground=hov, activeforeground=fg,
            relief="flat", bd=0, highlightthickness=0,
            font=font or F_BODY, cursor="hand2",
            padx=14, pady=6, disabledforeground=FG_MUTE,
        )
        b.bind("<Enter>", lambda e: b.configure(bg=hov) if str(b["state"]) != "disabled" else None)
        b.bind("<Leave>", lambda e: b.configure(bg=bg) if str(b["state"]) != "disabled" else None)
        if width:
            b.configure(width=width)
        return b

    def _card(self, parent):
        outer = tk.Frame(parent, bg=BORDER)
        inner = tk.Frame(outer, bg=CARD, padx=16, pady=14)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        self._card_bg = CARD
        return outer, inner

    def _status(self, text, color=FG_DIM):
        self.lbl_status.configure(text=text, fg=color)

    # -------- 顶栏 --------

    def _build_header(self):
        head = tk.Frame(self.root, bg=BG)
        head.pack(fill="x", padx=26, pady=(20, 0))

        left = tk.Frame(head, bg=BG)
        left.pack(side="left")
        tk.Label(left, text=APP_NAME, font=F_TITLE, bg=BG, fg=FG).pack(anchor="w")
        tk.Label(
            left, text="把任意文件塞进图片尾部 · 图片照常打开 · 可原样取回",
            font=F_SMALL, bg=BG, fg=FG_MUTE,
        ).pack(anchor="w", pady=(2, 0))

        tabs = tk.Frame(head, bg=CARD, padx=3, pady=3)
        tabs.pack(side="right")
        self.tab_btn = {}
        for key, label in (("embed", "嵌入"), ("extract", "提取")):
            b = tk.Button(
                tabs, text=label, command=lambda k=key: self.switch(k),
                bg=CARD, fg=FG_MUTE, activebackground=CARD_HI, activeforeground=FG,
                relief="flat", bd=0, highlightthickness=0,
                font=F_BODY, cursor="hand2", padx=18, pady=4,
            )
            b.pack(side="left")
            self.tab_btn[key] = b

        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x", padx=26, pady=(16, 0))

    def switch(self, key):
        self.tab = key
        for k, b in self.tab_btn.items():
            if k == key:
                b.configure(bg="#25365e", fg="#a9c8ff")
            else:
                b.configure(bg=CARD, fg=FG_MUTE)
        self.panel_embed.pack_forget()
        self.panel_extract.pack_forget()
        (self.panel_embed if key == "embed" else self.panel_extract).pack(fill="both", expand=True)
        self._status("")

    # -------- 嵌入页 --------

    def _build_embed(self, parent):
        p = tk.Frame(parent, bg=BG)

        # ① 载体图片
        o, c = self._card(p)
        o.pack(fill="x")
        c.columnconfigure(1, weight=1)

        holder = tk.Frame(c, bg="#0a0c11", width=154, height=106)
        holder.grid(row=0, column=0, sticky="nw")
        holder.pack_propagate(False)
        self.thumb = tk.Label(holder, bg="#0a0c11", fg=FG_MUTE, text="未选择图片", font=F_SMALL)
        self.thumb.pack(fill="both", expand=True)

        right = tk.Frame(c, bg=CARD)
        right.grid(row=0, column=1, sticky="new", padx=(18, 0))

        top = tk.Frame(right, bg=CARD)
        top.pack(fill="x")
        tk.Label(top, text="① 载体图片", font=F_H2, bg=CARD, fg=FG_DIM).pack(side="left")
        self._btn(top, "选择图片…", self.pick_carrier, kind="ghost").pack(side="right")

        self.lbl_carrier = tk.Label(
            right, text="PNG / JPG，图片本身会被完整保留，不会重新压缩",
            font=F_BODY, bg=CARD, fg=FG_MUTE, anchor="w",
        )
        self.lbl_carrier.pack(fill="x", pady=(10, 0))

        # ② 要藏的文件
        o2, c2 = self._card(p)
        o2.pack(fill="x", pady=12)
        c2.columnconfigure(1, weight=1)

        top2 = tk.Frame(c2, bg=CARD)
        top2.grid(row=0, column=0, columnspan=2, sticky="ew")
        tk.Label(top2, text="② 要藏的文件", font=F_H2, bg=CARD, fg=FG_DIM).pack(side="left")
        self._btn(top2, "选择文件…", self.pick_payload, kind="ghost").pack(side="right")

        self.lbl_payload = tk.Label(
            c2, text="任意类型，不限大小（压进图片后就是一个普通图片文件）",
            font=F_BODY, bg=CARD, fg=FG_MUTE, anchor="w",
        )
        self.lbl_payload.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        # ③ 输出
        o3, c3 = self._card(p)
        o3.pack(fill="x")
        c3.columnconfigure(1, weight=1)

        tk.Label(c3, text="③ 输出到", font=F_H2, bg=CARD, fg=FG_DIM).grid(row=0, column=0, sticky="w")
        self.out_var = tk.StringVar()
        ent = tk.Entry(
            c3, textvariable=self.out_var, bg="#0a0c11", fg=FG,
            insertbackground=ACCENT, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT,
            font=F_MONO, disabledbackground="#0a0c11",
        )
        ent.grid(row=0, column=1, sticky="ew", padx=(14, 12), ipady=5)
        self._btn(c3, "另存为…", self.pick_out, kind="ghost").grid(row=0, column=2)

        # 主按钮
        self.btn_run = tk.Button(
            p, text="嵌 入 并 验 证", command=self.do_embed,
            bg=ACCENT, fg="#ffffff", activebackground=ACCENT_H, activeforeground="#ffffff",
            relief="flat", bd=0, highlightthickness=0,
            font=F_BTN, cursor="hand2", pady=11,
            disabledforeground="#b9c9e8",
        )
        self.btn_run.pack(fill="x", pady=(18, 0))
        self.btn_run.bind("<Enter>", lambda e: self.btn_run.configure(bg=ACCENT_H)
                          if str(self.btn_run["state"]) != "disabled" else None)
        self.btn_run.bind("<Leave>", lambda e: self.btn_run.configure(bg=ACCENT)
                          if str(self.btn_run["state"]) != "disabled" else None)

        return p

    # -------- 提取页 --------

    def _build_extract(self, parent):
        p = tk.Frame(parent, bg=BG)

        o, c = self._card(p)
        o.pack(fill="x")
        c.columnconfigure(1, weight=1)

        holder = tk.Frame(c, bg="#0a0c11", width=154, height=106)
        holder.grid(row=0, column=0, sticky="nw")
        holder.pack_propagate(False)
        self.thumb2 = tk.Label(holder, bg="#0a0c11", fg=FG_MUTE, text="未选择图片", font=F_SMALL)
        self.thumb2.pack(fill="both", expand=True)

        right = tk.Frame(c, bg=CARD)
        right.grid(row=0, column=1, sticky="new", padx=(18, 0))

        top = tk.Frame(right, bg=CARD)
        top.pack(fill="x")
        tk.Label(top, text="选择一张由本工具处理过的图片", font=F_H2, bg=CARD, fg=FG_DIM).pack(side="left")
        self._btn(top, "打开图片…", self.pick_extract, kind="ghost").pack(side="right")

        self.lbl_extract = tk.Label(
            right, text="会自动检查图片尾部有没有索引，没有就提示",
            font=F_BODY, bg=CARD, fg=FG_MUTE, anchor="w", justify="left",
        )
        self.lbl_extract.pack(fill="x", pady=(10, 0))

        # 载荷详情
        o2, c2 = self._card(p)
        o2.pack(fill="both", expand=True, pady=(12, 0))
        c2.columnconfigure(1, weight=1)

        tk.Label(c2, text="载荷详情", font=F_H2, bg=CARD, fg=FG_DIM).grid(
            row=0, column=0, columnspan=2, sticky="w")

        self.info_val = {}
        for i, (key, label) in enumerate((
            ("name", "文件名"), ("size", "大小"),
            ("body", "图片本体"), ("check", "索引校验"),
        )):
            tk.Label(c2, text=label, font=F_BODY, bg=CARD, fg=FG_MUTE).grid(
                row=i + 1, column=0, sticky="w", pady=(10 if i == 0 else 4, 0))
            v = tk.Label(c2, text="—", font=F_MONO, bg=CARD, fg=FG_MUTE, anchor="w")
            v.grid(row=i + 1, column=1, sticky="ew", padx=(24, 0),
                   pady=(10 if i == 0 else 4, 0))
            self.info_val[key] = v

        self.hex_lbl = tk.Label(
            c2, text="选择图片后，这里会显示取出文件的开头几个字节",
            font=F_MONO, bg="#0a0c11", fg=FG_MUTE, anchor="w", justify="left",
            padx=12, pady=9,
        )
        self.hex_lbl.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(16, 0))

        self.btn_save = tk.Button(
            p, text="保存取出的文件…", command=self.do_save_payload,
            bg=CARD_HI, fg=FG_MUTE, activebackground=CARD_HOV, activeforeground=FG,
            relief="flat", bd=0, highlightthickness=0,
            font=F_BTN, cursor="hand2", pady=11, state="disabled",
        )
        self.btn_save.pack(fill="x", side="bottom", pady=(18, 0))

        return p

    def _set_info(self, info, size):
        if not info:
            for v in self.info_val.values():
                v.configure(text="—", fg=FG_MUTE)
            self.hex_lbl.configure(
                text="选择图片后，这里会显示取出文件的开头几个字节", fg=FG_MUTE)
            return
        pay = info["payload"]
        head = pay[:40]
        hexs = " ".join("%02X" % b for b in head) + (" …" if len(pay) > 40 else "")
        self.info_val["name"].configure(text=info["name"], fg=FG)
        self.info_val["size"].configure(text=human_size(len(pay)), fg=FG)
        self.info_val["body"].configure(
            text="%s · %d×%d" % (human_size(info["image_len"]), size[0], size[1]), fg=FG)
        self.info_val["check"].configure(text="通过 · STEGv1 标记 + 长度自洽", fg=OK)
        self.hex_lbl.configure(text=hexs, fg="#7f8ba3")

    # -------- 选取动作 --------

    def pick_carrier(self):
        path = filedialog.askopenfilename(
            title="选择载体图片",
            filetypes=[("图片", "*.png *.jpg *.jpeg"), ("所有文件", "*.*")],
        )
        if path:
            self.set_carrier(path)

    def set_carrier(self, path):
        kind = sniff_image(path)
        if not kind:
            return self._status("这个文件的真实格式不是 PNG / JPG（不看扩展名，看文件头）", ERR)
        try:
            im = Image.open(path)
            im.load()
        except Exception as e:
            return self._status("图片打不开：%s" % e, ERR)

        self.carrier = path
        self.carrier_size = im.size
        th = im.copy()
        th.thumbnail((154, 106), Image.LANCZOS)
        self._thumb = ImageTk.PhotoImage(th)
        self.thumb.configure(image=self._thumb, text="")

        self.lbl_carrier.configure(
            text="%s    %d×%d    %s    %s" % (
                os.path.basename(path), im.size[0], im.size[1], kind,
                human_size(os.path.getsize(path)),
            ),
            fg=FG,
        )
        stem, ext = os.path.splitext(path)
        self.out_var.set("%s_hidden%s" % (stem, ext))
        self._status("已选择载体图片", FG_DIM)

    def pick_payload(self):
        path = filedialog.askopenfilename(title="选择要藏的文件", filetypes=[("所有文件", "*.*")])
        if path:
            self.set_payload(path)

    def set_payload(self, path):
        self.payload = path
        try:
            sz = human_size(os.path.getsize(path))
        except OSError:
            sz = "?"
        self.lbl_payload.configure(text="%s    %s" % (os.path.basename(path), sz), fg=FG)
        self._status("已选择待藏文件", FG_DIM)

    def pick_out(self):
        cur = self.out_var.get().strip()
        ext = os.path.splitext(cur)[1] or ".png"
        path = filedialog.asksaveasfilename(
            title="输出为", defaultextension=ext,
            initialfile=os.path.basename(cur) if cur else "output" + ext,
            filetypes=[("图片", "*.png *.jpg")],
        )
        if path:
            self.out_var.set(path)

    # -------- 嵌入执行 --------

    def do_embed(self):
        if not self.carrier:
            return self._status("先选一张载体图片", ERR)
        if not self.payload:
            return self._status("先选要藏的文件", ERR)
        out = self.out_var.get().strip()
        if not out:
            return self._status("填一个输出路径", ERR)
        if os.path.abspath(out) == os.path.abspath(self.carrier):
            return self._status("输出路径不能和原图相同，会毁掉原图", ERR)

        self.btn_run.configure(state="disabled", text="处理中…", bg=CARD_HI)
        self._status("写入中…", FG_DIM)

        def work():
            try:
                a, b, total = embed_file(self.carrier, self.payload, out)
                same_size, size = verify_image(out, self.carrier_size)
                info = parse_file(out)
                ok_round = bool(info) and len(info["payload"]) == b
                self.root.after(0, lambda: self._embed_done(a, b, total, same_size, size, ok_round, info))
            except Exception as e:
                msg = repr(e)
                self.root.after(0, lambda: self._embed_fail(msg))

        threading.Thread(target=work, daemon=True).start()

    def _embed_done(self, a, b, total, same_size, size, ok_round, info):
        self.btn_run.configure(state="normal", text="嵌 入 并 验 证", bg=ACCENT)
        lines = []
        if not same_size:
            self._status("写入完成，但图片尺寸变了：%s —— 别用这个结果" % (size,), ERR)
            return
        if not ok_round:
            self._status("写入完成，但尾部索引校验失败，文件可能不完整", ERR)
            return

        self._status(
            "完成 · 图片 %s + 载荷 %s = %s · 已解码验证 · 末尾可直接取回" % (
                human_size(a), human_size(b), human_size(total),
            ),
            OK,
        )
        messagebox.showinfo(
            "完成",
            "已写入：\n%s\n\n图片本体 %s（%d×%d，解码验证通过）\n尾部载荷 %s（%s）\n输出 %s\n\n"
            "取回方式：打开本工具的「提取」页签选这个文件即可。" % (
                os.path.basename(self.out_var.get().strip()),
                human_size(a), size[0], size[1],
                human_size(b), info["name"] if info else "?",
                human_size(total),
            ),
        )

    def _embed_fail(self, msg):
        self.btn_run.configure(state="normal", text="嵌 入 并 验 证", bg=ACCENT)
        self._status("失败：%s" % msg, ERR)

    # -------- 提取执行 --------

    def pick_extract(self):
        path = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[("图片", "*.png *.jpg *.jpeg"), ("所有文件", "*.*")],
        )
        if path:
            self.set_extract(path)

    def set_extract(self, path):
        self.extract_src = path
        try:
            im = Image.open(path)
            im.load()
        except Exception as e:
            self.extract_info = None
            self.btn_save.configure(state="disabled", bg=CARD_HI, fg=FG_MUTE)
            self._set_info(None, None)
            return self._status("图片打不开：%s" % e, ERR)

        th = im.copy()
        th.thumbnail((154, 106), Image.LANCZOS)
        self._thumb2 = ImageTk.PhotoImage(th)
        self.thumb2.configure(image=self._thumb2, text="")

        info = parse_file(path)
        self.extract_info = info
        if not info:
            self.btn_save.configure(state="disabled", bg=CARD_HI, fg=FG_MUTE)
            self._set_info(None, None)
            self.lbl_extract.configure(
                text="%s    %d×%d\n这张图里没有找到索引，可能没被本工具处理过" % (
                    os.path.basename(path), im.size[0], im.size[1],
                ),
                fg=WARN,
            )
            return self._status("没有检测到载荷", WARN)

        self._set_info(info, im.size)
        self.btn_save.configure(state="normal", bg=ACCENT, fg="#ffffff", cursor="hand2")
        self.btn_save.bind("<Enter>", lambda e: self.btn_save.configure(bg=ACCENT_H))
        self.btn_save.bind("<Leave>", lambda e: self.btn_save.configure(bg=ACCENT))
        self.lbl_extract.configure(
            text="%s    %d×%d" % (os.path.basename(path), im.size[0], im.size[1]),
            fg=OK,
        )
        self._status("检测到载荷，可以保存", OK)

    def do_save_payload(self):
        if not self.extract_info:
            return
        info = self.extract_info
        path = filedialog.asksaveasfilename(
            title="保存取出的文件", initialfile=info["name"],
        )
        if not path:
            return
        try:
            with open(path, "wb") as f:
                f.write(info["payload"])
        except Exception as e:
            return self._status("保存失败：%s" % e, ERR)
        self._status("已保存到 %s（%s）" % (path, human_size(len(info["payload"]))), OK)


def res_path(name):
    """打包成 exe 后资源在临时解包目录里"""
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", ""), name)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)


def main():
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", root.winfo_fpixels("1i") / 72.0)
    except Exception:
        pass
    ico = res_path("app.ico")
    if os.path.exists(ico):
        try:
            root.iconbitmap(ico)
        except Exception:
            pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
