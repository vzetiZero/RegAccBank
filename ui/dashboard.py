"""
Dashboard - Giao diện chính (tối ưu cho người nhập liệu).

Bố cục: Sidebar điều hướng + 3 màn hình
    • Chạy quy trình – nhập liệu + điều khiển + log trực tiếp (1 màn hình)
    • Kết quả        – tiến độ, bảng trạng thái, xuất Excel
    • Cài đặt        – cửa sổ, quy trình, dọn dẹp

Mọi cập nhật UI từ luồng nền đều đẩy qua hàng đợi `_ui_queue` và được
xử lý trên luồng chính (thread-safe) để tránh treo/lỗi Tkinter.
"""

import json
import logging
import queue
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import pandas as pd

from core.dispatcher import (
    DEFAULT_SUCCESS_URL,
    DEFAULT_URL,
    DEFAULT_WITHDRAW_PIN,
    DEFAULT_WITHDRAW_URL,
    Dispatcher,
)
from core.gpm_manager import GPMManager, parse_proxy
from core.reporter import export_results
from ui import styles as S

logger = logging.getLogger(__name__)

SETTINGS_PATH = Path("config/settings.json")

# Giá trị cột status khi tài khoản đã được tạo
STATUS_DONE = "đã tạo"

# Tên cột (chuẩn hoá chữ thường) -> ý nghĩa
COLUMN_ALIASES = {
    "account": ["taikhoan", "tài khoản", "tai khoan", "email", "mail"],
    "password": ["matkhau", "mật khẩu", "mat khau", "password", "pass"],
    "name": ["tên tài khoản", "ten tai khoan", "ten tài khoản",
             "ho ten", "hoten", "fullname", "name"],
    "stk": ["stk", "số tài khoản", "so tai khoan"],
    "bank": ["bank", "ngân hàng", "ngan hang"],
    "pin": ["pin"],
    "status": ["status", "trạng thái", "trang thai"],
}


class Dashboard(ctk.CTk):
    """Giao diện chính của ứng dụng."""

    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("68win auto - LH @vstar_auto")
        self.geometry("1280x820")
        self.minsize(1120, 720)
        self.configure(fg_color=S.BG_ROOT)

        # ===== State =====
        self.gpm = GPMManager()
        self.dispatcher: Dispatcher | None = None
        self.accounts: list[dict] = []
        self.proxies: list[str] = []
        self.results: list[dict] = []
        self.delete_after = tk.BooleanVar(value=False)
        self._table_count = 0
        self.run_total = 0

        # Dữ liệu CSV/Excel đang dùng (để ghi PIN + status ngược lại file)
        self.data_df = None
        self.data_path = None
        self.data_sep = ","
        self.data_encoding = "utf-8"
        self.cols: dict = {}
        self.skipped_count = 0
        self._last_save = 0.0

        # Hàng đợi cập nhật UI an toàn từ luồng nền
        self._ui_queue: "queue.Queue" = queue.Queue()

        self.settings = self._load_settings()
        self._apply_settings()

        # ===== Layout =====
        self.grid_columnconfigure(0, weight=0)   # sidebar
        self.grid_columnconfigure(1, weight=1)   # content
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_content()

        self._build_run_view()
        self._build_results_view()
        self._build_settings_view()

        self._switch_view("run")

        # Auto-load phiên làm việc trước
        self._auto_load_last_file()
        self._refresh_input_stats()

        self.after(80, self._drain_ui_queue)
        logging.info("Dashboard khởi tạo thành công")

    # ============================================================
    # UI QUEUE (thread-safe updates)
    # ============================================================

    def _drain_ui_queue(self):
        try:
            while True:
                fn = self._ui_queue.get_nowait()
                try:
                    fn()
                except Exception as e:  # noqa: BLE001
                    logger.error(f"UI update lỗi: {e}")
        except queue.Empty:
            pass
        self.after(80, self._drain_ui_queue)

    def _ui(self, fn):
        """Đưa hàm cập nhật UI vào hàng đợi (gọi an toàn từ luồng nền)."""
        self._ui_queue.put(fn)

    # ============================================================
    # SETTINGS
    # ============================================================

    def _load_settings(self) -> dict:
        if SETTINGS_PATH.exists():
            try:
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {
            "last_csv_path": "",
            "last_proxy_list": "",
            "default_url": DEFAULT_URL,
            "success_url": DEFAULT_SUCCESS_URL,
            "withdraw_url": DEFAULT_WITHDRAW_URL,
            "withdraw_pin": DEFAULT_WITHDRAW_PIN,
            "delete_profile_after": False,
            "threads": 5,
            "run_count": "all",
            "bank_random": False,
            "window_width": 900,
            "window_height": 1200,
            "window_scale": 0.8,
            "grid_mode": "Tự động",
        }

    def _save_settings(self):
        try:
            SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
        except IOError as e:
            logger.error(f"Lỗi lưu settings: {e}")

    def _apply_settings(self):
        self.delete_after.set(self.settings.get("delete_profile_after", False))

    def _auto_load_last_file(self):
        last_proxy = self.settings.get("last_proxy_list", "")
        if last_proxy:
            self.txt_proxies.delete("1.0", "end")
            self.txt_proxies.insert("1.0", last_proxy)
            self.proxies = [p.strip() for p in last_proxy.split("\n") if p.strip()]
            self._log(f"Đã tải lại {len(self.proxies)} proxy từ lần chạy trước", "info")

        last_csv = self.settings.get("last_csv_path", "")
        if last_csv and Path(last_csv).exists():
            self._load_csv_file(last_csv)
            self._log(f"Đã tải lại file: {Path(last_csv).name}", "info")

    # ============================================================
    # SIDEBAR
    # ============================================================

    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self, width=224, corner_radius=0, fg_color=S.BG_SIDEBAR)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(2, weight=1)

        # Logo
        logo = ctk.CTkFrame(sidebar, fg_color="transparent")
        logo.grid(row=0, column=0, sticky="ew", padx=S.SPACE_LG, pady=(S.SPACE_XL, S.SPACE_LG))
        ctk.CTkLabel(
            logo, text="◈  68win auto",
            font=(S.FONT_FAMILY, 20, "bold"), text_color=S.TEXT_PRIMARY
        ).pack(anchor="w")
        ctk.CTkLabel(
            logo, text="LH @vstar_auto",
            font=S.FONT_TINY, text_color=S.TEXT_MUTED
        ).pack(anchor="w", pady=(2, 0))

        ctk.CTkFrame(sidebar, height=1, fg_color=S.BORDER).grid(
            row=1, column=0, sticky="ew", padx=S.SPACE_LG
        )

        # Nav
        nav = ctk.CTkFrame(sidebar, fg_color="transparent")
        nav.grid(row=2, column=0, sticky="new", padx=S.SPACE_MD, pady=S.SPACE_LG)

        self.nav_buttons = {}
        nav_items = [
            ("run", "▶   Chạy quy trình"),
            ("results", "▤   Kết quả"),
            ("settings", "⚙   Cài đặt"),
        ]
        for key, label in nav_items:
            btn = ctk.CTkButton(
                nav, text=label, anchor="w",
                fg_color="transparent", hover_color=S.BG_HOVER,
                text_color=S.TEXT_SECONDARY, font=S.FONT_BODY,
                height=44, corner_radius=S.RADIUS_MD,
                command=lambda k=key: self._switch_view(k),
            )
            btn.pack(fill="x", pady=S.SPACE_XS)
            self.nav_buttons[key] = btn

        # Footer status
        footer = ctk.CTkFrame(sidebar, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=S.SPACE_LG, pady=S.SPACE_LG)
        ctk.CTkFrame(footer, height=1, fg_color=S.BORDER).pack(fill="x", pady=(0, S.SPACE_MD))
        self.status_dot = ctk.CTkLabel(
            footer, text="●  Sẵn sàng", font=S.FONT_SMALL, text_color=S.TEXT_MUTED
        )
        self.status_dot.pack(anchor="w")

    def _switch_view(self, view: str):
        for key, btn in self.nav_buttons.items():
            if key == view:
                btn.configure(fg_color=S.ACCENT_WHITE, text_color=S.TEXT_INVERT,
                              hover_color=S.ACCENT_HOVER)
            else:
                btn.configure(fg_color="transparent", text_color=S.TEXT_SECONDARY,
                              hover_color=S.BG_HOVER)

        for key, frame in self.views.items():
            if key == view:
                frame.grid(row=0, column=0, sticky="nsew")
            else:
                frame.grid_remove()

        headers = {
            "run": ("Chạy quy trình", "Nhập dữ liệu và khởi động đăng ký hàng loạt"),
            "results": ("Kết quả", "Theo dõi tiến độ và xuất báo cáo"),
            "settings": ("Cài đặt", "Cửa sổ, quy trình và dọn dẹp"),
        }
        title, sub = headers.get(view, ("", ""))
        self.header_title.configure(text=title)
        self.header_sub.configure(text=sub)

    # ============================================================
    # CONTENT AREA
    # ============================================================

    def _build_content(self):
        container = ctk.CTkFrame(self, fg_color=S.BG_ROOT, corner_radius=0)
        container.grid(row=0, column=1, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(container, fg_color=S.BG_ROOT, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew", padx=S.SPACE_XL, pady=(S.SPACE_XL, S.SPACE_MD))
        header.grid_columnconfigure(0, weight=1)

        self.header_title = ctk.CTkLabel(
            header, text="Chạy quy trình", font=S.FONT_TITLE, text_color=S.TEXT_PRIMARY
        )
        self.header_title.grid(row=0, column=0, sticky="w")

        self.header_sub = ctk.CTkLabel(
            header, text="Nhập dữ liệu và khởi động đăng ký hàng loạt",
            font=S.FONT_SMALL, text_color=S.TEXT_MUTED
        )
        self.header_sub.grid(row=1, column=0, sticky="w", pady=(2, 0))

        self.view_stack = ctk.CTkFrame(container, fg_color="transparent", corner_radius=0)
        self.view_stack.grid(row=1, column=0, sticky="nsew", padx=S.SPACE_XL, pady=(0, S.SPACE_XL))
        self.view_stack.grid_columnconfigure(0, weight=1)
        self.view_stack.grid_rowconfigure(0, weight=1)

        self.views = {}

    # ============================================================
    # HELPERS
    # ============================================================

    def _make_chip(self, parent, label: str, value: str, color: str | None = None):
        """Tạo thẻ chỉ số nhỏ, trả về Label giá trị để cập nhật."""
        chip = ctk.CTkFrame(parent, **S.chip_style())
        chip.pack(side="left", padx=(0, S.SPACE_SM))
        ctk.CTkLabel(
            chip, text=label.upper(), font=S.FONT_TINY, text_color=S.TEXT_MUTED
        ).pack(side="left", padx=(S.SPACE_MD, S.SPACE_XS), pady=S.SPACE_SM)
        val = ctk.CTkLabel(
            chip, text=value, font=(S.FONT_FAMILY, 13, "bold"),
            text_color=color or S.TEXT_PRIMARY
        )
        val.pack(side="left", padx=(0, S.SPACE_MD), pady=S.SPACE_SM)
        return val

    # ============================================================
    # VIEW: RUN (nhập liệu + điều khiển + log)
    # ============================================================

    def _build_run_view(self):
        frame = ctk.CTkFrame(self.view_stack, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        self.views["run"] = frame

        # --- Chips chỉ số nhanh ---
        chips = ctk.CTkFrame(frame, fg_color="transparent")
        chips.grid(row=0, column=0, sticky="ew", pady=(0, S.SPACE_MD))
        self.chip_accounts = self._make_chip(chips, "Tài khoản", "0")
        self.chip_proxies = self._make_chip(chips, "Proxy", "0")
        self.chip_threads = self._make_chip(chips, "Luồng", "5")
        self.chip_progress = self._make_chip(chips, "Tiến độ", "0/0")

        # --- Main: form (trái) + log (phải) ---
        main = ctk.CTkFrame(frame, fg_color="transparent")
        main.grid(row=1, column=0, sticky="nsew")
        main.grid_columnconfigure(0, weight=4, minsize=430)
        main.grid_columnconfigure(1, weight=5)
        main.grid_rowconfigure(0, weight=1)

        self._build_form_panel(main)
        self._build_log_panel(main)

        # --- Action bar cố định ---
        self._build_action_bar(frame)

    def _build_form_panel(self, parent):
        card = ctk.CTkFrame(parent, **S.card_style())
        card.grid(row=0, column=0, sticky="nsew", padx=(0, S.SPACE_MD))
        card.grid_columnconfigure(0, weight=1)
        pad = S.SPACE_LG

        ctk.CTkLabel(card, text="NHẬP LIỆU", font=S.FONT_HEADING,
                     text_color=S.TEXT_SECONDARY).grid(
            row=0, column=0, sticky="w", padx=pad, pady=(pad, S.SPACE_SM))

        # URL
        ctk.CTkLabel(card, text="URL đích", font=S.FONT_SMALL,
                     text_color=S.TEXT_SECONDARY).grid(row=1, column=0, sticky="w", padx=pad)
        self.url_entry = ctk.CTkEntry(card, placeholder_text="https://...", **S.input_style())
        self.url_entry.insert(0, self.settings.get("default_url", DEFAULT_URL))
        self.url_entry.grid(row=2, column=0, sticky="ew", padx=pad, pady=(S.SPACE_XS, S.SPACE_MD))

        # Data source
        ctk.CTkLabel(card, text="Dữ liệu tài khoản (CSV / Excel)", font=S.FONT_SMALL,
                     text_color=S.TEXT_SECONDARY).grid(row=3, column=0, sticky="w", padx=pad)
        ds = ctk.CTkFrame(card, fg_color="transparent")
        ds.grid(row=4, column=0, sticky="ew", padx=pad, pady=(S.SPACE_XS, S.SPACE_MD))
        ctk.CTkButton(ds, text="＋  Chọn file", command=self._load_data_file,
                      **S.secondary_button_style()).pack(side="left")
        self.lbl_data_info = ctk.CTkLabel(
            ds, text="Chưa có dữ liệu", font=S.FONT_SMALL, text_color=S.TEXT_MUTED
        )
        self.lbl_data_info.pack(side="left", padx=S.SPACE_MD)

        # PIN rút tiền (dùng khi chạy và ghi vào CSV)
        ctk.CTkLabel(card, text="PIN rút tiền (6 số) — dùng & ghi vào CSV", font=S.FONT_SMALL,
                     text_color=S.TEXT_SECONDARY).grid(row=5, column=0, sticky="w", padx=pad)
        pin_row = ctk.CTkFrame(card, fg_color="transparent")
        pin_row.grid(row=6, column=0, sticky="ew", padx=pad, pady=(S.SPACE_XS, S.SPACE_MD))
        self.entry_withdraw_pin = ctk.CTkEntry(pin_row, width=120, placeholder_text="201198",
                                               **S.input_style())
        self.entry_withdraw_pin.insert(
            0, str(self.settings.get("withdraw_pin", DEFAULT_WITHDRAW_PIN))
        )
        self.entry_withdraw_pin.pack(side="left")
        ctk.CTkButton(pin_row, text="💾  Ghi PIN vào CSV", command=self._apply_pin_to_csv,
                      **S.ghost_button_style()).pack(side="left", padx=S.SPACE_MD)

        # Ngân hàng
        ctk.CTkLabel(card, text="Ngân hàng — nguồn chọn", font=S.FONT_SMALL,
                     text_color=S.TEXT_SECONDARY).grid(row=7, column=0, sticky="w", padx=pad)
        bank_row = ctk.CTkFrame(card, fg_color="transparent")
        bank_row.grid(row=8, column=0, sticky="ew", padx=pad, pady=(S.SPACE_XS, S.SPACE_MD))

        self.chk_bank_random = ctk.CTkCheckBox(
            bank_row, text="Ngân hàng ngẫu nhiên",
            command=lambda: self._on_bank_mode_change("random"),
            font=S.FONT_SMALL, text_color=S.TEXT_PRIMARY, fg_color=S.ACCENT_WHITE,
            hover_color=S.ACCENT_HOVER, checkmark_color=S.TEXT_INVERT,
            border_color=S.BORDER_LIGHT, corner_radius=S.RADIUS_SM,
        )
        self.chk_bank_random.pack(side="left")

        self.chk_bank_csv = ctk.CTkCheckBox(
            bank_row, text="Theo cột bank trong CSV",
            command=lambda: self._on_bank_mode_change("csv"),
            font=S.FONT_SMALL, text_color=S.TEXT_PRIMARY, fg_color=S.ACCENT_WHITE,
            hover_color=S.ACCENT_HOVER, checkmark_color=S.TEXT_INVERT,
            border_color=S.BORDER_LIGHT, corner_radius=S.RADIUS_SM,
        )
        self.chk_bank_csv.pack(side="left", padx=S.SPACE_LG)

        if self.settings.get("bank_random", False):
            self.chk_bank_random.select()
        else:
            self.chk_bank_csv.select()

        ctk.CTkLabel(card, text="CSV chưa có bank → tự lấy ngẫu nhiên và ghi lại vào CSV.",
                     font=S.FONT_TINY, text_color=S.TEXT_MUTED).grid(
            row=9, column=0, sticky="w", padx=pad, pady=(0, S.SPACE_MD))

        # Proxy
        ctk.CTkLabel(card, text="Proxy — mỗi dòng một proxy (không bắt buộc)",
                     font=S.FONT_SMALL, text_color=S.TEXT_SECONDARY).grid(
            row=10, column=0, sticky="w", padx=pad)
        self.txt_proxies = ctk.CTkTextbox(
            card, height=84, fg_color=S.BG_ELEVATED, border_width=1,
            border_color=S.BORDER_LIGHT, corner_radius=S.RADIUS_MD,
            text_color=S.TEXT_PRIMARY, font=S.FONT_MONO
        )
        self.txt_proxies.grid(row=11, column=0, sticky="ew", padx=pad, pady=(S.SPACE_XS, S.SPACE_XS))
        self.txt_proxies.bind("<KeyRelease>", lambda e: self._refresh_input_stats())

        proxy_row = ctk.CTkFrame(card, fg_color="transparent")
        proxy_row.grid(row=12, column=0, sticky="ew", padx=pad, pady=(0, S.SPACE_MD))
        ctk.CTkButton(proxy_row, text="Kiểm tra định dạng", command=self._test_proxies,
                      **S.ghost_button_style()).pack(side="left")
        ctk.CTkLabel(proxy_row, text="ip:port · ip:port:user:pass · socks5://…",
                     font=S.FONT_TINY, text_color=S.TEXT_MUTED).pack(side="left", padx=S.SPACE_SM)

        # Controls: số luồng + số tài khoản + bố cục
        ctrl = ctk.CTkFrame(card, fg_color="transparent")
        ctrl.grid(row=13, column=0, sticky="ew", padx=pad, pady=(0, S.SPACE_MD))
        ctrl.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(ctrl, text="Số luồng", font=S.FONT_SMALL,
                     text_color=S.TEXT_SECONDARY).grid(row=0, column=0, sticky="w")
        self.entry_threads = ctk.CTkEntry(ctrl, width=90, **S.input_style())
        self.entry_threads.insert(0, str(self.settings.get("threads", 5)))
        self.entry_threads.grid(row=0, column=1, sticky="w", padx=S.SPACE_MD)
        self.entry_threads.bind("<KeyRelease>", lambda e: self._refresh_input_stats())
        ctk.CTkLabel(ctrl, text="luồng (1–50)", font=S.FONT_TINY,
                     text_color=S.TEXT_MUTED).grid(row=0, column=2, sticky="w")

        ctk.CTkLabel(ctrl, text="Số tài khoản chạy", font=S.FONT_SMALL,
                     text_color=S.TEXT_SECONDARY).grid(row=1, column=0, sticky="w", pady=(S.SPACE_SM, 0))
        self.entry_run_count = ctk.CTkEntry(ctrl, width=90, placeholder_text="all", **S.input_style())
        self.entry_run_count.insert(0, str(self.settings.get("run_count", "all")))
        self.entry_run_count.grid(row=1, column=1, sticky="w", padx=S.SPACE_MD, pady=(S.SPACE_SM, 0))
        ctk.CTkLabel(ctrl, text="all = tất cả", font=S.FONT_TINY,
                     text_color=S.TEXT_MUTED).grid(row=1, column=2, sticky="w", pady=(S.SPACE_SM, 0))

        ctk.CTkLabel(ctrl, text="Bố cục lưới", font=S.FONT_SMALL,
                     text_color=S.TEXT_SECONDARY).grid(row=2, column=0, sticky="w", pady=(S.SPACE_SM, 0))
        self.combo_grid = ctk.CTkOptionMenu(
            ctrl, values=["Tự động", "1 cột", "2 cột", "3 cột", "4 cột"],
            fg_color=S.BG_ELEVATED, button_color=S.BG_ELEVATED,
            button_hover_color=S.BG_HOVER, text_color=S.TEXT_PRIMARY,
            dropdown_fg_color=S.BG_CARD, dropdown_hover_color=S.BG_HOVER,
            dropdown_text_color=S.TEXT_PRIMARY, font=S.FONT_BODY,
            corner_radius=S.RADIUS_MD,
        )
        self.combo_grid.set(self.settings.get("grid_mode", "Tự động"))
        self.combo_grid.grid(row=2, column=1, sticky="w", padx=S.SPACE_MD, pady=(S.SPACE_SM, 0))

    def _build_log_panel(self, parent):
        card = ctk.CTkFrame(parent, **S.card_style())
        card.grid(row=0, column=1, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        pad = S.SPACE_LG

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=pad, pady=(pad, S.SPACE_SM))
        ctk.CTkLabel(head, text="LOG TRỰC TIẾP", font=S.FONT_HEADING,
                     text_color=S.TEXT_SECONDARY).pack(side="left")
        ctk.CTkButton(head, text="Xóa log", width=64, command=self._clear_log,
                      **S.ghost_button_style()).pack(side="right")

        self.txt_log = ctk.CTkTextbox(
            card, fg_color=S.BG_ELEVATED, border_width=1, border_color=S.BORDER,
            corner_radius=S.RADIUS_MD, text_color=S.TEXT_PRIMARY,
            font=S.FONT_MONO, state="disabled", wrap="word"
        )
        self.txt_log.grid(row=1, column=0, sticky="nsew", padx=pad, pady=(0, pad))
        self._setup_log_tags()

    def _setup_log_tags(self):
        self.txt_log.tag_config("ts", foreground=S.TEXT_MUTED)
        self.txt_log.tag_config("info", foreground=S.TEXT_PRIMARY)
        self.txt_log.tag_config("success", foreground=S.SUCCESS)
        self.txt_log.tag_config("warning", foreground=S.WARNING)
        self.txt_log.tag_config("error", foreground=S.DANGER)

    def _build_action_bar(self, parent):
        bar = ctk.CTkFrame(
            parent, fg_color=S.BG_CARD, corner_radius=S.RADIUS_LG,
            border_width=1, border_color=S.BORDER
        )
        bar.grid(row=2, column=0, sticky="ew", pady=(S.SPACE_MD, 0))

        self.btn_start = ctk.CTkButton(
            bar, text="▶  BẮT ĐẦU", command=self._start, **S.success_button_style()
        )
        self.btn_start.grid(row=0, column=0, padx=(S.SPACE_LG, S.SPACE_SM), pady=S.SPACE_MD)

        self.btn_pause = ctk.CTkButton(
            bar, text="❚❚  TẠM DỪNG", command=self._pause, state="disabled",
            **S.warning_button_style()
        )
        self.btn_pause.grid(row=0, column=1, padx=S.SPACE_SM, pady=S.SPACE_MD)

        self.btn_stop = ctk.CTkButton(
            bar, text="■  DỪNG", command=self._stop, state="disabled",
            **S.danger_button_style()
        )
        self.btn_stop.grid(row=0, column=2, padx=(S.SPACE_SM, S.SPACE_LG), pady=S.SPACE_MD)

        bar.grid_columnconfigure(3, weight=1)

        ctk.CTkButton(
            bar, text="⭳  Xuất Excel", command=self._export_results,
            **S.secondary_button_style()
        ).grid(row=0, column=4, padx=(0, S.SPACE_LG), pady=S.SPACE_MD)

    # ============================================================
    # VIEW: RESULTS
    # ============================================================

    def _build_results_view(self):
        frame = ctk.CTkFrame(self.view_stack, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)
        self.views["results"] = frame
        pad = S.SPACE_LG

        top = ctk.CTkFrame(frame, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", pady=(0, S.SPACE_MD))
        self.chip_total = self._make_chip(top, "Tổng", "0")
        self.chip_ok = self._make_chip(top, "Thành công", "0", color=S.SUCCESS)
        self.chip_exists = self._make_chip(top, "Đã có", "0", color=S.INFO)
        self.chip_fail = self._make_chip(top, "Thất bại", "0", color=S.DANGER)
        self.chip_err = self._make_chip(top, "Lỗi", "0", color=S.DANGER)

        self.progress = ctk.CTkProgressBar(
            frame, height=8, corner_radius=4,
            progress_color=S.ACCENT_WHITE, fg_color=S.BG_ELEVATED
        )
        self.progress.grid(row=1, column=0, sticky="ew", pady=(0, S.SPACE_MD))
        self.progress.set(0)

        card = ctk.CTkFrame(frame, **S.card_style())
        card.grid(row=2, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        headers = ["STT", "Tài khoản", "Trạng thái", "Thời gian", "Chi tiết"]
        widths = [50, 260, 110, 170, 300]
        header = ctk.CTkFrame(card, fg_color=S.BG_ELEVATED, corner_radius=S.RADIUS_SM)
        header.grid(row=0, column=0, sticky="ew", padx=pad, pady=(pad, S.SPACE_SM))
        for i, (h, w) in enumerate(zip(headers, widths)):
            header.grid_columnconfigure(i, weight=(1 if i == 4 else 0))
            ctk.CTkLabel(header, text=h, font=S.FONT_SMALL,
                         text_color=S.TEXT_SECONDARY, width=w, anchor="w").grid(
                row=0, column=i, padx=S.SPACE_MD, pady=S.SPACE_SM, sticky="w")

        self.table_frame = ctk.CTkScrollableFrame(card, fg_color=S.BG_SURFACE,
                                                  corner_radius=S.RADIUS_MD)
        self.table_frame.grid(row=1, column=0, sticky="nsew", padx=pad, pady=(0, pad))
        self.table_frame.grid_columnconfigure(4, weight=1)

    # ============================================================
    # VIEW: SETTINGS
    # ============================================================

    def _build_settings_view(self):
        frame = ctk.CTkScrollableFrame(self.view_stack, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        self.views["settings"] = frame
        pad = S.SPACE_LG

        # --- Cửa sổ ---
        card_win = ctk.CTkFrame(frame, **S.card_style())
        card_win.grid(row=0, column=0, sticky="ew", pady=(0, S.SPACE_LG))
        card_win.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card_win, text="KÍCH THƯỚC CỬA SỔ", font=S.FONT_HEADING,
                     text_color=S.TEXT_SECONDARY).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=pad, pady=(pad, S.SPACE_MD))

        size = ctk.CTkFrame(card_win, fg_color="transparent")
        size.grid(row=1, column=1, sticky="w", padx=(0, pad), pady=(0, pad))

        self.entry_win_w = ctk.CTkEntry(size, width=80, **S.input_style())
        self.entry_win_w.insert(0, str(self.settings.get("window_width", 900)))
        self.entry_win_w.pack(side="left")
        ctk.CTkLabel(size, text="×", font=S.FONT_BODY,
                     text_color=S.TEXT_SECONDARY).pack(side="left", padx=S.SPACE_SM)

        self.entry_win_h = ctk.CTkEntry(size, width=80, **S.input_style())
        self.entry_win_h.insert(0, str(self.settings.get("window_height", 1200)))
        self.entry_win_h.pack(side="left")

        ctk.CTkLabel(card_win, text="Kích thước cửa sổ tối đa", font=S.FONT_BODY,
                     text_color=S.TEXT_PRIMARY).grid(row=1, column=0, sticky="w", padx=pad)
        ctk.CTkLabel(card_win,
                     text="Tự động thu nhỏ và xếp lưới để các cửa sổ không đè lên nhau.",
                     font=S.FONT_TINY, text_color=S.TEXT_MUTED).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=pad, pady=(S.SPACE_XS, 0))

        # --- Quy trình ---
        card3 = ctk.CTkFrame(frame, **S.card_style())
        card3.grid(row=1, column=0, sticky="ew", pady=(0, S.SPACE_LG))
        card3.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card3, text="QUY TRÌNH", font=S.FONT_HEADING,
                     text_color=S.TEXT_SECONDARY).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=pad, pady=(pad, S.SPACE_MD))

        ctk.CTkLabel(card3, text="URL sau khi đăng ký thành công", font=S.FONT_BODY,
                     text_color=S.TEXT_PRIMARY).grid(row=1, column=0, sticky="w", padx=pad, pady=S.SPACE_SM)
        self.entry_success_url = ctk.CTkEntry(card3, placeholder_text="https://...", **S.input_style())
        self.entry_success_url.insert(0, self.settings.get("success_url", DEFAULT_SUCCESS_URL))
        self.entry_success_url.grid(row=1, column=1, sticky="ew", padx=(0, pad), pady=S.SPACE_SM)

        ctk.CTkLabel(card3, text="URL trang rút tiền", font=S.FONT_BODY,
                     text_color=S.TEXT_PRIMARY).grid(row=2, column=0, sticky="w", padx=pad, pady=S.SPACE_SM)
        self.entry_withdraw_url = ctk.CTkEntry(card3, placeholder_text="https://...", **S.input_style())
        self.entry_withdraw_url.insert(0, self.settings.get("withdraw_url", DEFAULT_WITHDRAW_URL))
        self.entry_withdraw_url.grid(row=2, column=1, sticky="ew", padx=(0, pad), pady=S.SPACE_SM)

        ctk.CTkLabel(card3, text="Số lần retry tối đa", font=S.FONT_BODY,
                     text_color=S.TEXT_PRIMARY).grid(row=3, column=0, sticky="w", padx=pad, pady=S.SPACE_SM)
        retry = ctk.CTkFrame(card3, fg_color="transparent")
        retry.grid(row=3, column=1, sticky="ew", padx=(0, pad), pady=S.SPACE_SM)
        self.slider_retry = ctk.CTkSlider(
            retry, from_=0, to=5, number_of_steps=5,
            button_color=S.ACCENT_WHITE, button_hover_color=S.ACCENT_HOVER,
            progress_color=S.ACCENT_WHITE, fg_color=S.BG_ELEVATED, width=260,
        )
        self.slider_retry.set(2)
        self.slider_retry.pack(side="left")
        self.lbl_retry = ctk.CTkLabel(retry, text="2", font=S.FONT_BODY,
                                      text_color=S.TEXT_PRIMARY, width=40)
        self.lbl_retry.pack(side="left", padx=S.SPACE_MD)
        self.slider_retry.configure(command=lambda v: self.lbl_retry.configure(text=str(int(v))))

        ctk.CTkLabel(
            card3,
            text="Thành công khi popup \"Đăng ký Thành công!\" xuất hiện → vào URL trên → bấm \"Quản Lý Rút Tiền\"\n"
                 "→ thiết lập PIN bằng bàn phím số ảo → Xác Nhận → mở trang rút tiền → bấm \"Thêm Vào\".",
            font=S.FONT_TINY, text_color=S.TEXT_MUTED, justify="left"
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=pad, pady=(S.SPACE_XS, 0))

        # --- Dọn dẹp ---
        card4 = ctk.CTkFrame(frame, **S.card_style())
        card4.grid(row=2, column=0, sticky="ew", pady=(0, S.SPACE_LG))
        card4.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(card4, text="DỌN DẸP", font=S.FONT_HEADING,
                     text_color=S.TEXT_SECONDARY).grid(
            row=0, column=0, sticky="w", padx=pad, pady=(pad, S.SPACE_MD))

        self.chk_delete_profile = ctk.CTkCheckBox(
            card4, text="Xóa profile sau quy trình", variable=self.delete_after,
            font=S.FONT_BODY, text_color=S.TEXT_PRIMARY,
            fg_color=S.ACCENT_WHITE, hover_color=S.ACCENT_HOVER,
            checkmark_color=S.TEXT_INVERT, border_color=S.BORDER_LIGHT,
            corner_radius=S.RADIUS_SM,
        )
        self.chk_delete_profile.grid(row=1, column=0, sticky="w", padx=pad, pady=(0, S.SPACE_XS))

        ctk.CTkLabel(
            card4,
            text="Profile sẽ bị xóa hoàn toàn khỏi GPM Login và ổ cứng sau khi hoàn thành\n"
                 "(API: DELETE /profiles/delete/{id}?mode=hard) — giúp tiết kiệm dung lượng.",
            font=S.FONT_TINY, text_color=S.TEXT_MUTED, justify="left"
        ).grid(row=2, column=0, sticky="w", padx=pad, pady=(0, pad))

        ctk.CTkButton(
            frame, text="Lưu cấu hình", command=self._save_config, **S.primary_button_style()
        ).grid(row=3, column=0, sticky="e", pady=(0, S.SPACE_LG))

    # ============================================================
    # INPUT HELPERS
    # ============================================================

    def _on_bank_mode_change(self, source=None):
        """Giữ 2 checkbox ngân hàng loại trừ nhau (luôn chọn đúng 1)."""
        if source == "random" and self.chk_bank_random.get():
            self.chk_bank_csv.deselect()
        elif source == "csv" and self.chk_bank_csv.get():
            self.chk_bank_random.deselect()
        if not self.chk_bank_random.get() and not self.chk_bank_csv.get():
            self.chk_bank_csv.select()
        self.settings["bank_random"] = bool(self.chk_bank_random.get())

    def _refresh_input_stats(self):
        self.chip_accounts.configure(text=str(len(self.accounts)))
        proxy_text = self.txt_proxies.get("1.0", "end-1c").strip()
        n = len([p for p in proxy_text.split("\n") if p.strip()])
        self.chip_proxies.configure(text=str(n))
        try:
            val = self.entry_threads.get().strip()
            self.chip_threads.configure(text=val if val else "5")
        except Exception:
            pass

    def _get_grid_cols(self):
        value = self.combo_grid.get()
        if value.startswith("Tự động"):
            return None
        try:
            return int(value.split()[0])
        except (ValueError, IndexError):
            return None

    # ============================================================
    # DATA
    # ============================================================

    def _load_data_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Data files", "*.csv *.xlsx *.xls *.txt"), ("All files", "*.*")]
        )
        if not file_path:
            return

        self.settings["last_proxy_list"] = self.txt_proxies.get("1.0", "end-1c").strip()
        self.settings["default_url"] = self.url_entry.get().strip()
        self.settings["delete_profile_after"] = self.delete_after.get()
        self._save_settings()

        self._load_csv_file(file_path)

    @staticmethod
    def _cell(row, col) -> str:
        v = row.get(col, "")
        try:
            if pd.isna(v):
                return ""
        except (TypeError, ValueError):
            pass
        return str(v).strip()

    @staticmethod
    def _is_done(value) -> bool:
        return str(value).strip().lower() in ("đã tạo", "da tao", "created", "done")

    def _load_csv_file(self, file_path: str):
        """
        Load CSV/Excel. Giữ nguyên tên cột gốc, tự thêm cột 'pin' và 'status'.
        Bỏ qua các dòng có status = 'đã tạo'.
        """
        try:
            sep = ","
            df = None
            if file_path.endswith((".xlsx", ".xls")):
                df = pd.read_excel(file_path, dtype=str)
            else:
                for s in ["|", ",", ";", "\t"]:
                    try:
                        d = pd.read_csv(file_path, sep=s, dtype=str)
                        if len(d.columns) >= 3:
                            df, sep = d, s
                            break
                    except Exception:
                        continue
                if df is None:
                    df = pd.read_csv(file_path, dtype=str)

            df.columns = [str(c).strip() for c in df.columns]
            lower = {str(c).strip().lower(): c for c in df.columns}

            resolved = {}
            for canon, aliases in COLUMN_ALIASES.items():
                for a in aliases:
                    if a in lower:
                        resolved[canon] = lower[a]
                        break

            missing = [c for c in ("account", "password") if c not in resolved]
            if missing:
                messagebox.showerror(
                    "Lỗi",
                    f"File thiếu cột bắt buộc: {missing}\n"
                    f"Cột hiện có: {df.columns.tolist()}\n"
                    f"Định dạng mong đợi: taikhoan|matkhau|Tên tài khoản|stk|pin|status"
                )
                return

            # Thêm cột pin/status nếu file chưa có
            added_cols = False
            if "pin" not in resolved:
                df["pin"] = ""
                resolved["pin"] = "pin"
                added_cols = True
            if "status" not in resolved:
                df["status"] = ""
                resolved["status"] = "status"
                added_cols = True
            if "bank" not in resolved:
                df["bank"] = ""
                resolved["bank"] = "bank"
                # đặt cột bank ngay sau cột stk
                order = list(df.columns)
                order.remove("bank")
                if "stk" in resolved and resolved["stk"] in order:
                    order.insert(order.index(resolved["stk"]) + 1, "bank")
                else:
                    order.append("bank")
                df = df[order]
                added_cols = True
            if "name" not in resolved:
                df["name"] = df[resolved["account"]].apply(
                    lambda x: str(x).split("@")[0] if not pd.isna(x) else ""
                )
                resolved["name"] = "name"

            self.data_df = df
            self.data_path = file_path
            self.data_sep = sep
            self.cols = resolved

            # Lọc bỏ tài khoản đã tạo
            active, skipped = [], 0
            for idx, row in df.iterrows():
                if self._is_done(self._cell(row, resolved["status"])):
                    skipped += 1
                    continue
                rec = {
                    "account": self._cell(row, resolved["account"]),
                    "password": self._cell(row, resolved["password"]),
                    "name": self._cell(row, resolved["name"]),
                    "pin": self._cell(row, resolved["pin"]),
                    "_row": idx,
                }
                if "stk" in resolved:
                    rec["stk"] = self._cell(row, resolved["stk"])
                if "bank" in resolved:
                    rec["bank"] = self._cell(row, resolved["bank"])
                active.append(rec)

            self.accounts = active
            self.skipped_count = skipped

            self.settings["last_csv_path"] = file_path
            self._save_settings()

            if added_cols:
                self._save_df()  # ghi ngay để file có cột pin/status

            info = f"✓ {len(self.accounts)} tài khoản"
            if skipped:
                info += f" · bỏ qua {skipped} đã tạo"
            info += f" · {Path(file_path).name}"
            self.lbl_data_info.configure(text=info, text_color=S.SUCCESS)
            self._refresh_input_stats()
            self._log(
                f"Đã load {len(self.accounts)} tài khoản từ {Path(file_path).name}"
                + (f" — bỏ qua {skipped} tài khoản đã tạo" if skipped else ""),
                "success",
            )
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể đọc file: {e}")

    def _save_df(self):
        """Ghi DataFrame hiện tại trở lại file gốc."""
        if self.data_df is None or not self.data_path:
            return
        try:
            if str(self.data_path).lower().endswith((".xlsx", ".xls")):
                self.data_df.to_excel(self.data_path, index=False)
            else:
                self.data_df.to_csv(
                    self.data_path, sep=self.data_sep, index=False, encoding="utf-8"
                )
        except Exception as e:
            self._log(f"Lỗi ghi file dữ liệu: {e}", "error")

    def _save_df_throttled(self):
        now = time.monotonic()
        if now - self._last_save >= 3:
            self._last_save = now
            self._save_df()

    def _mark_done(self, account: dict, status: str, pin=None, bank=None):
        """Ghi status='đã tạo' (và PIN / bank) cho 1 tài khoản vào file dữ liệu."""
        if self.data_df is None or not account or not self.cols:
            return
        row = account.get("_row")
        if row is None or row not in self.data_df.index:
            return
        try:
            if status == "exists":
                current = self._cell(self.data_df.loc[row], self.cols["status"])
                if current:
                    return  # đã ghi rồi thì thôi
            self.data_df.at[row, self.cols["status"]] = STATUS_DONE
            if pin:
                self.data_df.at[row, self.cols["pin"]] = pin
                account["pin"] = pin
            if bank:
                self.data_df.at[row, self.cols["bank"]] = bank
                account["bank"] = bank
            self._save_df_throttled()
        except Exception as e:
            self._log(f"Lỗi cập nhật file dữ liệu: {e}", "error")

    def _write_pin_to_active(self) -> int:
        pin = self.entry_withdraw_pin.get().strip()
        if not pin or self.data_df is None or not self.cols:
            return 0
        n = 0
        for acc in self.accounts:
            row = acc.get("_row")
            if row is None or row not in self.data_df.index:
                continue
            try:
                self.data_df.at[row, self.cols["pin"]] = pin
                acc["pin"] = pin
                n += 1
            except Exception:
                pass
        if n:
            self._save_df()
        return n

    def _apply_pin_to_csv(self):
        pin = self.entry_withdraw_pin.get().strip()
        if not pin:
            messagebox.showwarning("Cảnh báo", "Vui lòng nhập PIN trước")
            return
        if self.data_df is None:
            messagebox.showwarning("Cảnh báo", "Chưa có dữ liệu để ghi")
            return
        n = self._write_pin_to_active()
        self.settings["withdraw_pin"] = pin
        self._save_settings()
        self._log(f"Đã ghi PIN vào {n} tài khoản trong file dữ liệu", "success")
        messagebox.showinfo("Thành công", f"Đã ghi PIN vào {n} tài khoản trong CSV.")

    # ---------- tài khoản đã tồn tại -> file riêng ----------

    def _exists_csv_path(self):
        if not self.data_path:
            return None
        return str(Path(self.data_path).with_name("tai_khoan_da_co.csv"))

    def _exists_sep(self) -> str:
        if self.data_path and str(self.data_path).lower().endswith((".xlsx", ".xls")):
            return ","
        return self.data_sep or ","

    def _rebuild_row_index(self):
        """Cập nhật lại _row cho self.accounts sau khi file chính bị xoá bớt dòng."""
        if self.data_df is None or not self.cols:
            return
        acc_col = self.cols.get("account")
        if not acc_col:
            return
        idx = {}
        for i, val in self.data_df[acc_col].items():
            idx[str(val).strip()] = i
        for acc in self.accounts:
            key = str(acc.get("account", "")).strip()
            if key in idx:
                acc["_row"] = idx[key]

    def _move_exists_accounts(self, accounts: list):
        """
        Chuyển các tài khoản 'đã tồn tại' sang file riêng (tai_khoan_da_co.csv)
        và xoá khỏi file chính, để lần chạy sau không xử lý lại.
        """
        if self.data_df is None or not accounts:
            return
        path = self._exists_csv_path()
        if not path:
            return

        rows, drop_idx = [], []
        acc_col = self.cols.get("account")
        if not acc_col or acc_col not in self.data_df.columns:
            return
        index_by_acc = {}
        for i, val in self.data_df[acc_col].items():
            index_by_acc[str(val).strip()] = i
        seen = set()
        for acc in accounts:
            key = str(acc.get("account", "")).strip()
            r = index_by_acc.get(key)
            if r is None or r not in self.data_df.index or r in seen:
                continue
            seen.add(r)
            rows.append(self.data_df.loc[r])
            drop_idx.append(r)
        if not rows:
            return

        try:
            out = pd.DataFrame(rows).reindex(columns=self.data_df.columns)
            exists = Path(path)
            if exists.exists():
                old = pd.read_csv(path, sep=self._exists_sep(), dtype=str)
                out = pd.concat(
                    [old.reindex(columns=self.data_df.columns), out], ignore_index=True
                )
                acc_col = self.cols.get("account")
                if acc_col and acc_col in out.columns:
                    out = out.drop_duplicates(subset=[acc_col], keep="last")
            out.to_csv(path, sep=self._exists_sep(), index=False, encoding="utf-8")

            # Xoá khỏi file chính
            self.data_df = self.data_df.drop(index=drop_idx).reset_index(drop=True)
            for acc in accounts:  # tránh chuyển lặp lại
                acc["_row"] = None
            self._rebuild_row_index()
            self._save_df()
            self._log(
                f"Đã chuyển {len(drop_idx)} tài khoản đã tồn tại sang {exists.name} "
                f"và xoá khỏi file chính",
                "success",
            )
        except Exception as e:
            self._log(f"Lỗi chuyển tài khoản đã tồn tại sang file riêng: {e}", "error")

    def _test_proxies(self):
        proxy_text = self.txt_proxies.get("1.0", "end-1c").strip()
        if not proxy_text:
            messagebox.showwarning("Cảnh báo", "Vui lòng nhập proxy trước")
            return

        self.proxies = [p.strip() for p in proxy_text.split("\n") if p.strip()]
        self._log(f"Kiểm tra {len(self.proxies)} proxy...")

        valid = 0
        for proxy in self.proxies:
            try:
                parse_proxy(proxy)
                valid += 1
            except ValueError:
                self._log(f"Proxy không hợp lệ: {proxy}", "error")

        level = "success" if valid == len(self.proxies) else "warning"
        self._log(f"Kết quả: {valid}/{len(self.proxies)} proxy hợp lệ", level)

        self.settings["last_proxy_list"] = proxy_text
        self._save_settings()
        self._refresh_input_stats()

    # ============================================================
    # RUN
    # ============================================================

    def _start(self):
        if not self.accounts:
            messagebox.showwarning("Cảnh báo", "Vui lòng load dữ liệu tài khoản trước")
            return

        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Cảnh báo", "Vui lòng nhập URL đích")
            return

        proxy_text = self.txt_proxies.get("1.0", "end-1c").strip()
        self.settings["last_proxy_list"] = proxy_text
        self.settings["default_url"] = url
        self.settings["delete_profile_after"] = self.delete_after.get()
        self.proxies = [p.strip() for p in proxy_text.split("\n") if p.strip()]

        success_url = self.entry_success_url.get().strip()
        self.settings["success_url"] = success_url

        withdraw_url = self.entry_withdraw_url.get().strip()
        withdraw_pin = self.entry_withdraw_pin.get().strip()
        self.settings["withdraw_url"] = withdraw_url
        self.settings["withdraw_pin"] = withdraw_pin

        bank_mode = "random" if self.chk_bank_random.get() else "csv"
        self.settings["bank_random"] = bool(self.chk_bank_random.get())

        try:
            threads = int(self.entry_threads.get().strip())
        except ValueError:
            threads = 5
        threads = max(1, min(threads, 50))

        run_raw = self.entry_run_count.get().strip().lower()
        if run_raw in ("", "all", "tất cả", "tat ca"):
            accounts_to_run = list(self.accounts)
        else:
            try:
                n = int(run_raw)
            except ValueError:
                messagebox.showerror("Lỗi", "Số tài khoản chạy không hợp lệ (nhập số hoặc 'all')")
                return
            accounts_to_run = self.accounts[:n] if n > 0 else list(self.accounts)

        delete_after = self.delete_after.get()
        max_retries = int(self.slider_retry.get())

        try:
            win_w = int(self.entry_win_w.get().strip())
            win_h = int(self.entry_win_h.get().strip())
        except ValueError:
            messagebox.showerror("Lỗi", "Kích thước cửa sổ không hợp lệ")
            return
        win_scale = 1.0

        grid_cols = self._get_grid_cols()

        self.settings["window_width"] = win_w
        self.settings["window_height"] = win_h
        self.settings["window_scale"] = win_scale
        self.settings["grid_mode"] = self.combo_grid.get()
        self.settings["withdraw_pin"] = withdraw_pin
        self.settings["threads"] = threads
        self.settings["run_count"] = run_raw
        self._save_settings()

        pin_written = self._write_pin_to_active()
        if pin_written:
            self._log(f"Đã ghi PIN vào {pin_written} tài khoản trong file dữ liệu", "info")
        if not withdraw_pin:
            self._log("Chưa nhập PIN rút tiền — sẽ bỏ qua bước thiết lập PIN", "warning")

        # Reset kết quả
        self.run_total = len(accounts_to_run)
        self.results = []
        self._clear_table()
        self._update_summary()
        self.progress.set(0)
        self.chip_progress.configure(text=f"0/{self.run_total}")

        self._log(
            f"▶ Bắt đầu: {len(accounts_to_run)}/{len(self.accounts)} tài khoản · {threads} luồng · "
            f"retry {max_retries} · bank: {'ngẫu nhiên' if bank_mode == 'random' else 'theo CSV'} · "
            f"cửa sổ tối đa {win_w}×{win_h} · xóa profile: {delete_after}", "info"
        )
        self._set_status("Đang chạy", S.SUCCESS)

        self.dispatcher = Dispatcher(
            gpm=self.gpm, max_workers=threads, max_retries=max_retries,
            delete_after=delete_after, url=url, success_url=success_url,
            withdraw_pin=withdraw_pin, withdraw_url=withdraw_url,
            bank_mode=bank_mode,
            log_callback=self._log, window_width=win_w, window_height=win_h,
            window_scale=win_scale, grid_cols=grid_cols,
            progress_callback=self._on_progress,
        )

        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="normal", text="❚❚  TẠM DỪNG")
        self.btn_stop.configure(state="normal")

        import threading
        threading.Thread(target=self._run_dispatcher, args=(accounts_to_run,), daemon=True).start()

    def _run_dispatcher(self, accounts):
        try:
            results = self.dispatcher.run_batch(accounts, self.proxies)
            self._ui(lambda: self._finish_run(results))
        except Exception as e:
            self._ui(lambda: self._finish_run_error(e))

    def _finish_run(self, results):
        self.results = results
        self._clear_table()
        for r in results:
            self._append_table_row(r)
        self._update_summary()
        # Chuyển tài khoản đã tồn tại sang file riêng
        exists_accounts = [r.get("account") or {} for r in results
                           if r.get("status") == "exists"]
        if exists_accounts:
            self._move_exists_accounts(exists_accounts)
        self._save_df()
        total = self.run_total or len(self.accounts)
        self.progress.set(1 if total and results else 0)
        self.chip_progress.configure(text=f"{len(results)}/{total}")
        self._log("Hoàn thành quy trình", "success")
        self._set_status("Hoàn thành", S.SUCCESS)
        self._reset_run_buttons()

    def _finish_run_error(self, e):
        self._log(f"Lỗi: {e}", "error")
        self._set_status("Lỗi", S.DANGER)
        self._reset_run_buttons()

    def _reset_run_buttons(self):
        self.btn_start.configure(state="normal")
        self.btn_pause.configure(state="disabled", text="❚❚  TẠM DỪNG")
        self.btn_stop.configure(state="disabled")

    def _on_progress(self, done, total, result):
        def apply():
            self.chip_progress.configure(text=f"{done}/{total}")
            if total:
                self.progress.set(done / total)
            if result is not None:
                self._append_table_row(result)
                self.results.append(result)
                self._update_summary()
                status = result.get("status")
                if status in ("success", "exists"):
                    self._mark_done(result.get("account") or {}, status,
                                    pin=self.entry_withdraw_pin.get().strip(),
                                    bank=result.get("bank"))
        self._ui(apply)

    def _pause(self):
        if not self.dispatcher:
            return
        if self.dispatcher.is_paused():
            self.dispatcher.resume()
            self.btn_pause.configure(text="❚❚  TẠM DỪNG")
            self._set_status("Đang chạy", S.SUCCESS)
        else:
            self.dispatcher.pause()
            self.btn_pause.configure(text="▶  TIẾP TỤC")
            self._set_status("Tạm dừng", S.WARNING)

    def _stop(self):
        if self.dispatcher:
            self.dispatcher.stop()
        self._log("Đã dừng!", "error")
        self._set_status("Đã dừng", S.DANGER)

    def _set_status(self, text: str, color: str = S.TEXT_MUTED):
        self.status_dot.configure(text=f"●  {text}", text_color=color)

    # ============================================================
    # TABLE
    # ============================================================

    def _clear_table(self):
        for widget in self.table_frame.winfo_children():
            widget.destroy()
        self._table_count = 0

    def _append_table_row(self, result: dict):
        i = self._table_count
        self._table_count += 1

        acc = result.get("account", {}) or {}
        status = result.get("status", "unknown")
        timestamp = result.get("timestamp", "")
        error = result.get("error", "")

        status_map = {
            "success": (S.SUCCESS, "Thành công"),
            "exists": (S.INFO, "Đã có tài khoản"),
            "failed": (S.DANGER, "Thất bại"),
            "error": (S.DANGER, "Lỗi"),
        }
        color, label = status_map.get(status, (S.TEXT_MUTED, status))

        ctk.CTkLabel(self.table_frame, text=str(i + 1), font=S.FONT_SMALL,
                     text_color=S.TEXT_SECONDARY, width=50, anchor="w").grid(
            row=i, column=0, padx=S.SPACE_MD, pady=S.SPACE_XS, sticky="w")
        ctk.CTkLabel(self.table_frame, text=acc.get("account", ""), font=S.FONT_SMALL,
                     text_color=S.TEXT_PRIMARY, width=260, anchor="w").grid(
            row=i, column=1, padx=S.SPACE_MD, pady=S.SPACE_XS, sticky="w")
        ctk.CTkLabel(self.table_frame, text=f"● {label}", font=S.FONT_SMALL,
                     text_color=color, width=110, anchor="w").grid(
            row=i, column=2, padx=S.SPACE_MD, pady=S.SPACE_XS, sticky="w")
        ctk.CTkLabel(self.table_frame, text=timestamp, font=S.FONT_SMALL,
                     text_color=S.TEXT_MUTED, width=170, anchor="w").grid(
            row=i, column=3, padx=S.SPACE_MD, pady=S.SPACE_XS, sticky="w")
        ctk.CTkLabel(self.table_frame, text=error, font=S.FONT_SMALL,
                     text_color=S.TEXT_SECONDARY, anchor="w").grid(
            row=i, column=4, padx=S.SPACE_MD, pady=S.SPACE_XS, sticky="w")

    def _update_summary(self):
        total = len(self.results)
        ok = sum(1 for r in self.results if r.get("status") == "success")
        exists = sum(1 for r in self.results if r.get("status") == "exists")
        failed = sum(1 for r in self.results if r.get("status") == "failed")
        err = sum(1 for r in self.results if r.get("status") == "error")
        self.chip_total.configure(text=str(total))
        self.chip_ok.configure(text=str(ok))
        self.chip_exists.configure(text=str(exists))
        self.chip_fail.configure(text=str(failed))
        self.chip_err.configure(text=str(err))

    # ============================================================
    # LOG
    # ============================================================

    def _log(self, message: str, level: str = "info"):
        self._ui(lambda: self._append_log(message, level))

    def _append_log(self, message: str, level: str = "info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", f"{timestamp}  ", "ts")
        self.txt_log.insert("end", f"{message}\n", level)
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def _clear_log(self):
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.configure(state="disabled")

    # ============================================================
    # EXPORT / SAVE
    # ============================================================

    def _export_results(self):
        if not self.results:
            messagebox.showwarning("Cảnh báo", "Chưa có kết quả để xuất")
            return
        try:
            success_path, failed_path = export_results(self.results)
            self._log(f"Đã xuất kết quả: {success_path}", "success")
            messagebox.showinfo("Thành công", "Đã xuất kết quả Excel!")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể xuất: {e}")

    def _save_config(self):
        self.settings["default_url"] = self.url_entry.get().strip()
        self.settings["success_url"] = self.entry_success_url.get().strip()
        self.settings["withdraw_url"] = self.entry_withdraw_url.get().strip()
        self.settings["withdraw_pin"] = self.entry_withdraw_pin.get().strip()
        self.settings["run_count"] = self.entry_run_count.get().strip()
        self.settings["bank_random"] = bool(self.chk_bank_random.get())
        self.settings["delete_profile_after"] = self.delete_after.get()

        try:
            self.settings["threads"] = int(self.entry_threads.get().strip())
        except ValueError:
            pass

        try:
            self.settings["window_width"] = int(self.entry_win_w.get().strip())
            self.settings["window_height"] = int(self.entry_win_h.get().strip())
        except ValueError:
            pass

        self._save_settings()
        self._log("Đã lưu cấu hình", "success")
