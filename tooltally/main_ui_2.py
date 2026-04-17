#!/usr/bin/env python3
# ── main_ui_2.py ─────────────────────────────────────────────────────
# Tool Cabinet Touchscreen UI — ToolTally
#
# TAKE flow:
#     Login → Select Tool → flap opens (auto-closes after 5s) → Done
#
# DEPOSIT flow:
#     Login → place tool at camera → model detects → user confirms →
#     flap opens → slide (ch 8) runs → flap closes → Done
#
# Compared to the original main_ui_2.py, the ONLY behavioural changes are:
#   * TAKE and DEPOSIT now route through WorkflowController, so DEPOSIT
#     runs the full flap→slide→flap sequence on a background thread.
#   * The ResultPage shows a "Working…" state while the workflow runs.
#   * A small stable-frames check smooths out detection flicker before
#     the Confirm button enables.
#   * The admin dashboard gained a "Test Slide (ch 8)" button.
# Visual layout is untouched.
# ─────────────────────────────────────────────────────────────────────

import tkinter as tk
import cv2
from PIL import Image, ImageTk

import database as db
from servo_controller import ServoController
from camera_detector   import CameraDetector
from workflow_controller import WorkflowController
from config import (SCREEN_W, SCREEN_H,
                    CLASS_NAMES, EMPTY_CLASS, CONFIDENCE,
                    STABLE_FRAMES)

# ── Colours (unchanged) ─────────────────────────────────────────────
BG      = "#0f0f1a"
CARD    = "#1a1a2e"
ACCENT  = "#4f8ef7"
ACCENT2 = "#7c3aed"
SUCCESS = "#22c55e"
DANGER  = "#ef4444"
WARNING = "#f59e0b"
TEXT    = "#f1f5f9"
SUBTEXT = "#94a3b8"
BORDER  = "#2d2d44"

TOOL_COLORS = {
    "pliers":      "#ef4444",
    "screwdriver": "#f59e0b",
    "wrench":      "#3b82f6",
}
TOOL_ICONS = {
    "pliers":      "🔧",
    "screwdriver": "🪛",
    "wrench":      "🔩",
}
REAL_TOOLS = [t for t in CLASS_NAMES if t != EMPTY_CLASS]


# ── Base page ───────────────────────────────────────────────────────
class BasePage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=BG)
        self.controller = controller

    def on_show(self):
        pass


# ════════════════════════════════════════════════════════════════════
#  LOGIN PAGE
# ════════════════════════════════════════════════════════════════════
class LoginPage(BasePage):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)

        tk.Label(self, text="🔧 Tool Cabinet", bg=BG, fg=ACCENT,
                 font=("Helvetica", 26, "bold")).pack(pady=(32, 4))
        tk.Label(self, text="Enter your User ID", bg=BG, fg=SUBTEXT,
                 font=("Helvetica", 13)).pack(pady=(0, 16))

        self.id_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.id_var, bg=CARD, fg=TEXT,
                 font=("Courier", 26, "bold"),
                 width=14, anchor="center",
                 padx=10, pady=10).pack(pady=(0, 6))

        self.status_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.status_var, bg=BG, fg=DANGER,
                 font=("Helvetica", 12)).pack(pady=(0, 10))

        self._alpha_mode = True
        self._kb_frame = tk.Frame(self, bg=BG)
        self._kb_frame.pack()
        self._build_keyboard()

    def _build_keyboard(self):
        for w in self._kb_frame.winfo_children():
            w.destroy()

        if self._alpha_mode:
            rows = [
                list("QWERTYUIOP"),
                list("ASDFGHJKL"),
                list("ZXCVBNM") + ["⌫"],
                ["123", "SPACE", "✓"],
            ]
        else:
            rows = [
                ["1","2","3"],
                ["4","5","6"],
                ["7","8","9"],
                ["ABC", "0", "✓"],
            ]

        for row in rows:
            rf = tk.Frame(self._kb_frame, bg=BG)
            rf.pack(pady=3)
            for k in row:
                if k == "✓":
                    bg, fg, w = SUCCESS, "white", 6
                elif k == "⌫":
                    bg, fg, w = DANGER, "white", 5
                elif k in ("123", "ABC"):
                    bg, fg, w = WARNING, "white", 6
                elif k == "SPACE":
                    bg, fg, w = CARD, TEXT, 12
                else:
                    bg, fg, w = CARD, TEXT, 4
                tk.Button(rf, text=k, width=w, height=2,
                          bg=bg, fg=fg, activebackground=ACCENT,
                          font=("Helvetica", 14, "bold"),
                          relief="flat", bd=0,
                          command=lambda x=k: self._key(x)).pack(side="left", padx=3)

    def _key(self, k):
        self.status_var.set("")
        cur = self.id_var.get()
        if k == "⌫":
            self.id_var.set(cur[:-1])
        elif k == "✓":
            self._login()
        elif k == "SPACE":
            if len(cur) < 16:
                self.id_var.set(cur + " ")
        elif k == "123":
            self._alpha_mode = False
            self._build_keyboard()
        elif k == "ABC":
            self._alpha_mode = True
            self._build_keyboard()
        else:
            if len(cur) < 16:
                self.id_var.set(cur + k)

    def _login(self):
        code = self.id_var.get().strip()
        if not code:
            self.status_var.set("Please enter your User ID")
            return
        user = db.lookup_user(code)
        if not user:
            self.status_var.set("User ID not found. Try again.")
            self.id_var.set("")
            return
        self.id_var.set("")
        self.controller.set_user(user)
        if user["role"] == "admin":
            self.controller.show("AdminDashboard")
        else:
            self.controller.show("ActionPage")

    def on_show(self):
        self.id_var.set("")
        self.status_var.set("")


# ════════════════════════════════════════════════════════════════════
#  ACTION PAGE — Take or Deposit
# ════════════════════════════════════════════════════════════════════
class ActionPage(BasePage):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)

        self.greeting = tk.StringVar(value="")
        tk.Label(self, textvariable=self.greeting, bg=BG, fg=TEXT,
                 font=("Helvetica", 20, "bold")).pack(pady=(44, 4))
        tk.Label(self, text="What would you like to do?",
                 bg=BG, fg=SUBTEXT, font=("Helvetica", 14)).pack(pady=(0, 36))

        btn_f = tk.Frame(self, bg=BG)
        btn_f.pack()

        tk.Button(btn_f,
                  text="📤  TAKE a Tool",
                  width=20, height=3,
                  bg=ACCENT, fg="white",
                  font=("Helvetica", 16, "bold"), relief="flat",
                  command=lambda: controller.show("SelectToolPage")
                  ).pack(pady=14)

        tk.Button(btn_f,
                  text="📥  DEPOSIT a Tool",
                  width=20, height=3,
                  bg=ACCENT2, fg="white",
                  font=("Helvetica", 16, "bold"), relief="flat",
                  command=lambda: controller.show("DepositPage")
                  ).pack(pady=14)

        tk.Button(self, text="Logout", bg=BG, fg=SUBTEXT,
                  font=("Helvetica", 11), relief="flat",
                  command=lambda: controller.show("LoginPage")).pack(pady=(30, 0))

    def on_show(self):
        user = self.controller.current_user
        if user:
            self.greeting.set(f"Welcome, {user['name']} 👋")


# ════════════════════════════════════════════════════════════════════
#  SELECT TOOL PAGE (TAKE flow)
# ════════════════════════════════════════════════════════════════════
class SelectToolPage(BasePage):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)

        tk.Label(self, text="📤 Which tool do you need?",
                 bg=BG, fg=TEXT,
                 font=("Helvetica", 20, "bold")).pack(pady=(44, 8))
        tk.Label(self, text="Tap the tool — its compartment will open",
                 bg=BG, fg=SUBTEXT, font=("Helvetica", 13)).pack(pady=(0, 40))

        self._btn_frame = tk.Frame(self, bg=BG)
        self._btn_frame.pack()

        for tool in REAL_TOOLS:
            col  = TOOL_COLORS.get(tool, ACCENT)
            icon = TOOL_ICONS.get(tool, "🔧")
            tk.Button(self._btn_frame,
                      text=f"{icon}  {tool.capitalize()}",
                      width=20, height=3,
                      bg=col, fg="white",
                      font=("Helvetica", 16, "bold"), relief="flat",
                      command=lambda t=tool: controller.take_tool(t)
                      ).pack(pady=10)

        tk.Button(self, text="← Back", bg=CARD, fg=TEXT,
                  font=("Helvetica", 12), relief="flat",
                  command=lambda: controller.show("ActionPage")).pack(pady=(30, 0))


# ════════════════════════════════════════════════════════════════════
#  DEPOSIT PAGE
# ════════════════════════════════════════════════════════════════════
class DepositPage(BasePage):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)
        self._active = False

        tk.Label(self, text="📥 Deposit a Tool",
                 bg=BG, fg=TEXT,
                 font=("Helvetica", 20, "bold")).pack(pady=(20, 4))
        tk.Label(self, text="Place the tool in front of the camera",
                 bg=BG, fg=SUBTEXT, font=("Helvetica", 13)).pack(pady=(0, 10))

        # Camera preview
        self.cam_label = tk.Label(self, bg=CARD,
                                  width=320, height=240,
                                  highlightthickness=4,
                                  highlightbackground=CARD)
        self.cam_label.pack(pady=6)

        # Detection readout
        self.icon_var = tk.StringVar(value="🔍")
        tk.Label(self, textvariable=self.icon_var, bg=BG,
                 font=("Helvetica", 30)).pack()

        self.det_var = tk.StringVar(value="Waiting for tool…")
        tk.Label(self, textvariable=self.det_var, bg=BG, fg=WARNING,
                 font=("Helvetica", 17, "bold")).pack(pady=2)

        self.conf_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.conf_var, bg=BG, fg=SUBTEXT,
                 font=("Helvetica", 12)).pack()

        # Confirm / cancel
        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(pady=14)

        self.confirm_btn = tk.Button(btn_row,
                                     text="✓  Confirm Deposit",
                                     state="disabled",
                                     width=16, height=2,
                                     bg=SUCCESS, fg="white",
                                     font=("Helvetica", 13, "bold"), relief="flat",
                                     command=self._confirm)
        self.confirm_btn.pack(side="left", padx=10)

        tk.Button(btn_row, text="✕  Cancel",
                  width=10, height=2,
                  bg=DANGER, fg="white",
                  font=("Helvetica", 13, "bold"), relief="flat",
                  command=self._cancel).pack(side="left", padx=10)

        self._detected_tool = None
        self._detected_conf = 0.0
        self._stable_count  = 0
        self._stable_tool   = None

    def on_show(self):
        self.det_var.set("Waiting for tool…")
        self.conf_var.set("")
        self.icon_var.set("🔍")
        self.cam_label.config(highlightbackground=CARD)
        self.confirm_btn.config(state="disabled")
        self._detected_tool = None
        self._stable_count  = 0
        self._stable_tool   = None
        self._active = True
        self._update_loop()

    def _update_loop(self):
        if not self._active:
            return

        frame, label, conf = self.controller.camera.get_latest()

        if frame is not None:
            rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img   = Image.fromarray(rgb).resize((320, 240))
            photo = ImageTk.PhotoImage(img)
            self.cam_label.config(image=photo)
            self.cam_label.image = photo

        is_real = label in REAL_TOOLS and conf >= CONFIDENCE

        # Require N consecutive stable frames before enabling Confirm.
        if is_real and label == self._stable_tool:
            self._stable_count += 1
        elif is_real:
            self._stable_tool  = label
            self._stable_count = 1
        else:
            self._stable_tool  = None
            self._stable_count = 0

        if is_real:
            self._detected_tool = label
            self._detected_conf = conf
            col = TOOL_COLORS.get(label, WARNING)
            self.icon_var.set(TOOL_ICONS.get(label, "🔧"))
            self.det_var.set(f"{label.upper()} detected")
            self.conf_var.set(f"Confidence: {conf:.0%}")
            self.cam_label.config(highlightbackground=col)
            if self._stable_count >= STABLE_FRAMES:
                self.confirm_btn.config(state="normal")
            else:
                self.confirm_btn.config(state="disabled")
        else:
            self._detected_tool = None
            self.icon_var.set("🔍")
            self.det_var.set("No tool detected — hold tool in view")
            self.conf_var.set("")
            self.cam_label.config(highlightbackground=CARD)
            self.confirm_btn.config(state="disabled")

        self.after(120, self._update_loop)

    def _confirm(self):
        if not self._detected_tool:
            return
        self._active = False
        self.controller.deposit_tool(self._detected_tool, self._detected_conf)

    def _cancel(self):
        self._active = False
        self.controller.show("ActionPage")


# ════════════════════════════════════════════════════════════════════
#  RESULT PAGE
#  Shows a "Working…" state while the deposit workflow runs, then the
#  final success/failure message.
# ════════════════════════════════════════════════════════════════════
class ResultPage(BasePage):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)

        self.icon_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.icon_var, bg=BG,
                 font=("Helvetica", 60)).pack(pady=(50, 8))

        self.msg_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.msg_var, bg=BG, fg=TEXT,
                 font=("Helvetica", 20, "bold"),
                 wraplength=520, justify="center").pack(pady=6)

        self.sub_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.sub_var, bg=BG, fg=SUBTEXT,
                 font=("Helvetica", 13),
                 wraplength=520, justify="center").pack(pady=4)

        self.cd_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.cd_var, bg=BG, fg=SUBTEXT,
                 font=("Helvetica", 12)).pack(pady=(20, 0))

        self.done_btn = tk.Button(self, text="Done", width=14, height=2,
                                  bg=ACCENT, fg="white",
                                  font=("Helvetica", 14, "bold"), relief="flat",
                                  command=self._done)
        self.done_btn.pack(pady=20)
        self._countdown_id = None

    def on_show(self):
        r = self.controller.last_result
        if not r:
            return

        status = r.get("status", "final")   # "working" | "final"
        if status == "working":
            # Sequence still running — show progress indicator, no countdown.
            self.icon_var.set("⏳")
            self.msg_var.set(f"Depositing {r.get('tool', '').capitalize()}…")
            self.sub_var.set("Flap opening · slide running · please wait")
            self.cd_var.set("")
            self.done_btn.config(state="disabled")
            return

        # Final state:
        self.done_btn.config(state="normal")
        if r.get("success"):
            self.icon_var.set("✅")
            if r["action"] == "take":
                self.msg_var.set(
                    f"{r['tool'].capitalize()} compartment is now open")
                self.sub_var.set(
                    "Please take your tool.\nCompartment will lock after 5 seconds.")
            else:
                self.msg_var.set(
                    f"{r['tool'].capitalize()} deposited successfully")
                self.sub_var.set(
                    f"Tool placed in compartment {r['tool']}.\nThank you!")
        else:
            self.icon_var.set("❌")
            self.msg_var.set("Something went wrong")
            self.sub_var.set(r.get("error", "Please contact an admin."))
        self._countdown(6)

    def _countdown(self, n):
        if self._countdown_id:
            self.after_cancel(self._countdown_id)
            self._countdown_id = None
        if n > 0:
            self.cd_var.set(f"Returning to menu in {n}s…")
            self._countdown_id = self.after(1000, lambda: self._countdown(n - 1))
        else:
            self._done()

    def _done(self):
        if self._countdown_id:
            self.after_cancel(self._countdown_id)
            self._countdown_id = None
        self.controller.show("ActionPage")


# ════════════════════════════════════════════════════════════════════
#  ADMIN DASHBOARD
# ════════════════════════════════════════════════════════════════════
class AdminDashboard(BasePage):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)

        tk.Label(self, text="⚙️  Admin Dashboard", bg=BG, fg=ACCENT,
                 font=("Helvetica", 22, "bold")).pack(pady=(30, 12))

        cfg = dict(width=22, height=2, relief="flat", bd=0,
                   font=("Helvetica", 14, "bold"))

        tk.Button(self, text="📋  View Logs", bg=CARD, fg=TEXT,
                  command=lambda: controller.show("AdminLogs"),
                  **cfg).pack(pady=5)

        tk.Button(self, text="👥  Manage Users", bg=CARD, fg=TEXT,
                  command=lambda: controller.show("AdminUsers"),
                  **cfg).pack(pady=5)

        tk.Label(self, text="Manual Compartment Control",
                 bg=BG, fg=SUBTEXT,
                 font=("Helvetica", 12)).pack(pady=(16, 4))

        for tool in REAL_TOOLS:
            col  = TOOL_COLORS.get(tool, CARD)
            icon = TOOL_ICONS.get(tool, "🔧")
            tk.Button(self, text=f"{icon}  Open {tool.capitalize()}",
                      bg=col, fg="white",
                      command=lambda t=tool: controller.admin_open(t),
                      **cfg).pack(pady=3)

        # NEW: Slide test button (channel 8)
        tk.Button(self, text="⚙  Test Slide (ch 8)",
                  bg=ACCENT2, fg="white",
                  command=controller.admin_test_slide,
                  **cfg).pack(pady=(8, 4))

        tk.Button(self, text="Logout", bg=BG, fg=SUBTEXT,
                  font=("Helvetica", 11), relief="flat",
                  command=lambda: controller.show("LoginPage")).pack(pady=(12, 0))


# ════════════════════════════════════════════════════════════════════
#  ADMIN LOGS
# ════════════════════════════════════════════════════════════════════
class AdminLogs(BasePage):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)

        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=20, pady=(20, 8))
        tk.Label(hdr, text="📋 Activity Log", bg=BG, fg=TEXT,
                 font=("Helvetica", 18, "bold")).pack(side="left")
        tk.Button(hdr, text="↻", bg=CARD, fg=TEXT,
                  font=("Helvetica", 12), relief="flat", width=3,
                  command=self.on_show).pack(side="right", padx=4)
        tk.Button(hdr, text="← Back", bg=CARD, fg=TEXT,
                  font=("Helvetica", 11), relief="flat",
                  command=lambda: controller.show("AdminDashboard")).pack(side="right", padx=4)

        self.list_frame = tk.Frame(self, bg=BG)
        self.list_frame.pack(fill="both", expand=True, padx=20, pady=4)

    def on_show(self):
        for w in self.list_frame.winfo_children():
            w.destroy()

        logs = db.get_logs(limit=40)
        if not logs:
            tk.Label(self.list_frame, text="No activity yet.",
                     bg=BG, fg=SUBTEXT,
                     font=("Helvetica", 13)).pack(pady=20)
            return

        cols   = ["Time",          "User",  "Action",  "Tool",  "Compartment"]
        widths = [16,               12,      7,         11,      13]
        hdr_row = tk.Frame(self.list_frame, bg=BORDER)
        hdr_row.pack(fill="x", pady=(0, 2))
        for h, w in zip(cols, widths):
            tk.Label(hdr_row, text=h, bg=BORDER, fg=SUBTEXT,
                     font=("Helvetica", 10, "bold"),
                     width=w).pack(side="left", padx=4)

        canvas = tk.Canvas(self.list_frame, bg=BG, highlightthickness=0)
        vsb    = tk.Scrollbar(self.list_frame, orient="vertical",
                              command=canvas.yview)
        inner  = tk.Frame(canvas, bg=BG)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        for log in logs:
            row = tk.Frame(inner, bg=CARD)
            row.pack(fill="x", pady=1)
            ts      = str(log.get("timestamp", ""))[:16]
            action  = log.get("action", "") or ""
            tool    = log.get("tool", "") or ""
            act_col = SUCCESS if action == "place" else ACCENT
            vals    = [ts,
                       log.get("user_name", "") or "",
                       action.upper(),
                       tool.capitalize(),
                       tool.capitalize()]
            for v, w in zip(vals, widths):
                fg = act_col if v.lower() in ("take", "place") else TEXT
                tk.Label(row, text=v, bg=CARD, fg=fg,
                         font=("Helvetica", 10),
                         width=w).pack(side="left", padx=4, pady=5)


# ════════════════════════════════════════════════════════════════════
#  ADMIN USERS
# ════════════════════════════════════════════════════════════════════
class AdminUsers(BasePage):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)

        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=20, pady=(20, 8))
        tk.Label(hdr, text="👥 Manage Users", bg=BG, fg=TEXT,
                 font=("Helvetica", 18, "bold")).pack(side="left")
        tk.Button(hdr, text="← Back", bg=CARD, fg=TEXT,
                  font=("Helvetica", 11), relief="flat",
                  command=lambda: controller.show("AdminDashboard")).pack(side="right")

        form = tk.Frame(self, bg=CARD)
        form.pack(fill="x", padx=20, pady=8)
        tk.Label(form, text="Add New User", bg=CARD, fg=TEXT,
                 font=("Helvetica", 12, "bold")).grid(
            row=0, column=0, columnspan=5, sticky="w", padx=10, pady=6)

        tk.Label(form, text="ID:", bg=CARD, fg=SUBTEXT,
                 font=("Helvetica", 11)).grid(row=1, column=0, padx=8)
        self.new_id = tk.Entry(form, font=("Helvetica", 12), width=10,
                               bg=BG, fg=TEXT, insertbackground=TEXT)
        self.new_id.grid(row=1, column=1, padx=4, pady=6)

        tk.Label(form, text="Name:", bg=CARD, fg=SUBTEXT,
                 font=("Helvetica", 11)).grid(row=1, column=2, padx=8)
        self.new_name = tk.Entry(form, font=("Helvetica", 12), width=14,
                                 bg=BG, fg=TEXT, insertbackground=TEXT)
        self.new_name.grid(row=1, column=3, padx=4, pady=6)

        self.role_var = tk.StringVar(value="user")
        tk.OptionMenu(form, self.role_var, "user", "admin").grid(
            row=1, column=4, padx=8)

        self.add_status = tk.StringVar(value="")
        tk.Label(form, textvariable=self.add_status, bg=CARD, fg=SUCCESS,
                 font=("Helvetica", 10)).grid(
            row=2, column=0, columnspan=4, sticky="w", padx=10)
        tk.Button(form, text="Add", bg=SUCCESS, fg="white",
                  font=("Helvetica", 11, "bold"), relief="flat",
                  command=self._add_user).grid(row=1, column=5, padx=10)

        self.list_frame = tk.Frame(self, bg=BG)
        self.list_frame.pack(fill="both", expand=True, padx=20, pady=8)

    def on_show(self):
        self._refresh()

    def _refresh(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        for u in db.get_all_users():
            row = tk.Frame(self.list_frame, bg=CARD)
            row.pack(fill="x", pady=2)
            role_col = DANGER if u["role"] == "admin" else TEXT
            tk.Label(row, text=u["user_id"], bg=CARD, fg=ACCENT,
                     font=("Courier", 12, "bold"), width=10).pack(
                side="left", padx=10, pady=6)
            tk.Label(row, text=u["name"], bg=CARD, fg=TEXT,
                     font=("Helvetica", 12), width=16).pack(side="left")
            tk.Label(row, text=u["role"].upper(), bg=CARD, fg=role_col,
                     font=("Helvetica", 10, "bold"), width=8).pack(side="left")
            if u["role"] != "admin":
                tk.Button(row, text="Remove", bg=DANGER, fg="white",
                          font=("Helvetica", 10), relief="flat",
                          command=lambda uid=u["user_id"]: self._remove(uid)
                          ).pack(side="right", padx=10)

    def _add_user(self):
        uid  = self.new_id.get().strip()
        name = self.new_name.get().strip()
        role = self.role_var.get()
        if not uid or not name:
            self.add_status.set("ID and Name are required.")
            return
        result = db.add_user(uid, name, role)
        if result:
            self.add_status.set(f"✓ Added {name}")
            self.new_id.delete(0, "end")
            self.new_name.delete(0, "end")
            self._refresh()
        else:
            self.add_status.set("Error — ID may already exist.")

    def _remove(self, uid):
        db.delete_user(uid)
        self._refresh()


# ════════════════════════════════════════════════════════════════════
#  APP CONTROLLER
# ════════════════════════════════════════════════════════════════════
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tool Cabinet")
        self.geometry(f"{SCREEN_W}x{SCREEN_H}")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.attributes("-fullscreen", True)
        self.bind("<Escape>", lambda e: self.attributes("-fullscreen", False))

        self.current_user = None
        self.last_result  = None

        # Hardware
        self.servo    = ServoController()
        self.camera   = CameraDetector()
        self.camera.start()

        # Workflow — routes servo sequences off the UI thread and marshals
        # callbacks back on the UI thread via .after().
        self.workflow = WorkflowController(
            self.servo,
            ui_scheduler=lambda fn: self.after(0, fn),
        )

        # Pages
        container = tk.Frame(self, bg=BG)
        container.pack(fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.pages = {}
        for PageClass in (LoginPage, ActionPage, SelectToolPage,
                          DepositPage, ResultPage,
                          AdminDashboard, AdminLogs, AdminUsers):
            name = PageClass.__name__
            page = PageClass(container, self)
            self.pages[name] = page
            page.grid(row=0, column=0, sticky="nsew")

        self.show("LoginPage")

    # ── Navigation ───────────────────────────────────────────────
    def show(self, name):
        page = self.pages[name]
        page.tkraise()
        page.on_show()

    def set_user(self, user):
        self.current_user = user

    # ── TAKE flow ────────────────────────────────────────────────
    def take_tool(self, tool):
        """User selected a tool to take. Open the flap, log it."""
        user = self.current_user

        def after_open(success, error):
            try:
                db.log_action(
                    user_db_id    = user["id"],
                    tool_name     = tool,
                    action        = "take",
                    detected_tool = tool,
                    confidence    = 1.0,
                )
            except Exception as e:
                print(f"[DB ERROR] {e}")

            self.last_result = {
                "status":  "final",
                "success": success,
                "action":  "take",
                "tool":    tool,
                "error":   error or ("" if success
                                     else "Failed to open compartment"),
            }
            self.show("ResultPage")

        self.workflow.run_take_sequence(tool, on_done=after_open)

    # ── DEPOSIT flow ─────────────────────────────────────────────
    def deposit_tool(self, tool, confidence):
        """
        Camera confirmed the tool. Kick off the full deposit choreography
        (flap open → slide → flap close) on a worker thread, and show the
        ResultPage in a 'working' state until it reports back.
        """
        user = self.current_user

        # Show the result page in "working" state immediately.
        self.last_result = {
            "status":  "working",
            "success": False,
            "action":  "place",
            "tool":    tool,
            "error":   "",
        }
        self.show("ResultPage")

        def after_sequence(success, error):
            try:
                db.log_action(
                    user_db_id    = user["id"],
                    tool_name     = tool,
                    action        = "place",
                    detected_tool = tool,
                    confidence    = confidence,
                )
            except Exception as e:
                print(f"[DB ERROR] {e}")

            self.last_result = {
                "status":  "final",
                "success": success,
                "action":  "place",
                "tool":    tool,
                "error":   error or ("" if success
                                     else "Deposit sequence failed"),
            }
            # Re-trigger on_show so the page renders the final state.
            self.show("ResultPage")

        self.workflow.run_deposit_sequence(tool, confidence,
                                           on_done=after_sequence)

    # ── Admin ────────────────────────────────────────────────────
    def admin_open(self, tool):
        self.workflow.run_take_sequence(tool)

    def admin_test_slide(self):
        """Fire the channel-8 slide servo once, for bench testing."""
        import threading
        threading.Thread(target=self.servo.run_slide, daemon=True).start()

    # ── Shutdown ─────────────────────────────────────────────────
    def on_close(self):
        try:
            self.camera.stop()
        except Exception as e:
            print(f"[CLOSE] camera stop error: {e}")
        try:
            self.servo.cleanup()
        except Exception as e:
            print(f"[CLOSE] servo cleanup error: {e}")
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
