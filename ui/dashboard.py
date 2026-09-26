"""
Dashboard - Giao diện chính hiện đại (đen trắng)
Sidebar navigation + card layout với spacing nhất quán.
"""

import json
import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import pandas as pd

from core.gpm_manager import GPMManager, parse_proxy
from core.dispatcher import Dispatcher, DEFAULT_URL
from core.reporter import export_results
from ui import styles as S

logger = logging.getLogger(__name__)

SETTINGS_PATH = Path("config/settings.json")


class Dashboard(ctk.CTk):
    """Giao diện chính của ứng dụng."""

    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("RegAcc — Hệ thống đăng ký đa luồng")
        self.geometry("1360x860")
        self.minsize(1180, 760)
        self.configure(fg_color=S.BG_ROOT)

        # ===== State =====
        self.gpm = GPMManager()
        self.dispatcher: Dispatcher | None = None
        self.accounts: list[dict] = []
        self.proxies: list[str] = []
        self.results: list[dict] = []
        self.selectors: dict = {}
        self.delete_after = tk.BooleanVar(value=False)

        self._load_selectors()
        self.settings = self._load_settings()
        self._apply_settings()

        # ===== Layout =====
        self.grid_columnconfigure(0, weight=0)   # sidebar
        self.grid_columnconfigure(1, weight=1)   # content
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_content()

        # Views
        self._build_dashboard_view()
        self._build_monitor_view()
        self._build_advanced_view()

        # Show default view
        self._switch_view("dashboard")

        # Auto-load last session
        self._auto_load_last_file()

        logging.info("Dashboard khởi tạo thành công")

    # ============================================================
    # SETTINGS
    # ============================================================

    def _load_selectors(self):
        config_path = Path("config/selectors.json")
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    self.selectors = json.load(f).get("default", {})
            except (json.JSONDecodeError, IOError):
                self.selectors = {}

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
            "delete_profile_after": False,
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
        sidebar = ctk.CTkFrame(
            self, width=232, corner_radius=0,
            fg_color=S.BG_SIDEBAR, border_width=0
        )
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(2, weight=1)

        # Logo
        logo_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        logo_frame.grid(row=0, column=0, sticky="ew", padx=S.SPACE_LG, pady=(S.SPACE_XL, S.SPACE_XL))
        ctk.CTkLabel(
            logo_frame, text="◈  RegAcc",
            font=(S.FONT_FAMILY, 20, "bold"), text_color=S.TEXT_PRIMARY
        ).pack(anchor="w")
        ctk.CTkLabel(
            logo_frame, text="Automation Platform",
            font=S.FONT_TINY, text_color=S.TEXT_MUTED
        ).pack(anchor="w", pady=(2, 0))

        # Divider
        ctk.CTkFrame(sidebar, height=1, fg_color=S.BORDER).grid(
            row=1, column=0, sticky="ew", padx=S.SPACE_LG
        )

        # Nav
        nav_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        nav_frame.grid(row=2, column=0, sticky="new", padx=S.SPACE_MD, pady=S.SPACE_LG)

        self.nav_buttons = {}
        nav_items = [
            ("dashboard", "▣   Bảng điều khiển"),
            ("monitor", "◉   Giám sát"),
            ("advanced", "⚙   Cấu hình"),
        ]
        for key, label in nav_items:
            btn = ctk.CTkButton(
                nav_frame, text=label, anchor="w",
                fg_color="transparent", hover_color=S.BG_HOVER,
                text_color=S.TEXT_SECONDARY, font=S.FONT_BODY,
                height=44, corner_radius=S.RADIUS_MD,
                command=lambda k=key: self._switch_view(k),
            )
            btn.pack(fill="x", pady=S.SPACE_XS)
            self.nav_buttons[key] = btn

        # Status footer
        footer = ctk.CTkFrame(sidebar, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=S.SPACE_LG, pady=S.SPACE_LG)

        ctk.CTkFrame(footer, height=1, fg_color=S.BORDER).pack(fill="x", pady=(0, S.SPACE_MD))

        self.status_dot = ctk.CTkLabel(
            footer, text="●  Sẵn sàng", font=S.FONT_SMALL, text_color=S.TEXT_MUTED
        )
        self.status_dot.pack(anchor="w")

    def _switch_view(self, view: str):
        """Chuyển đổi giữa các view."""
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

        # Cập nhật header theo view
        headers = {
            "dashboard": ("Bảng điều khiển", "Cấu hình và chạy quy trình đăng ký đa luồng"),
            "monitor": ("Giám sát", "Theo dõi trạng thái tài khoản và log trực tiếp"),
            "advanced": ("Cấu hình nâng cao", "Selectors, captcha, OTP và tùy chọn dọn dẹp"),
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

        # Header
        header = ctk.CTkFrame(container, fg_color=S.BG_ROOT, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew", padx=S.SPACE_XL, pady=(S.SPACE_XL, S.SPACE_MD))
        header.grid_columnconfigure(0, weight=1)

        self.header_title = ctk.CTkLabel(
            header, text="Bảng điều khiển", font=S.FONT_TITLE, text_color=S.TEXT_PRIMARY
        )
        self.header_title.grid(row=0, column=0, sticky="w")

        self.header_sub = ctk.CTkLabel(
            header, text="Cấu hình và chạy quy trình đăng ký đa luồng",
            font=S.FONT_SMALL, text_color=S.TEXT_MUTED
        )
        self.header_sub.grid(row=1, column=0, sticky="w", pady=(2, 0))

        # View stack
        self.view_stack = ctk.CTkFrame(container, fg_color="transparent", corner_radius=0)
        self.view_stack.grid(row=1, column=0, sticky="nsew", padx=S.SPACE_XL, pady=(0, S.SPACE_XL))
        self.view_stack.grid_columnconfigure(0, weight=1)
        self.view_stack.grid_rowconfigure(0, weight=1)

        self.views = {}

    # ============================================================
    # VIEW: DASHBOARD
    # ============================================================

    def _build_dashboard_view(self):
        frame = ctk.CTkScrollableFrame(self.view_stack, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        self.views["dashboard"] = frame

        # --- Card: Cấu hình cơ bản ---
        card1 = ctk.CTkFrame(frame, **S.card_style())
        card1.grid(row=0, column=0, sticky="ew", pady=(0, S.SPACE_LG))
        card1.grid_columnconfigure(1, weight=1)
        pad = S.SPACE_LG

        ctk.CTkLabel(card1, text="CẤU HÌNH CƠ BẢN", font=S.FONT_HEADING,
                     text_color=S.TEXT_SECONDARY).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=pad, pady=(pad, S.SPACE_MD))

        # URL
        ctk.CTkLabel(card1, text="URL đích", font=S.FONT_BODY,
                     text_color=S.TEXT_PRIMARY).grid(row=1, column=0, sticky="w", padx=pad, pady=S.SPACE_SM)
        self.url_entry = ctk.CTkEntry(card1, placeholder_text="https://...", **S.input_style())
        self.url_entry.insert(0, self.settings.get("default_url", DEFAULT_URL))
        self.url_entry.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(0, pad), pady=S.SPACE_SM)

        # Data source
        ctk.CTkLabel(card1, text="Dữ liệu", font=S.FONT_BODY,
                     text_color=S.TEXT_PRIMARY).grid(row=2, column=0, sticky="w", padx=pad, pady=S.SPACE_SM)
        ds_frame = ctk.CTkFrame(card1, fg_color="transparent")
        ds_frame.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(0, pad), pady=S.SPACE_SM)
        self.btn_load_data = ctk.CTkButton(
            ds_frame, text="＋  Chọn file CSV / Excel", command=self._load_data_file,
            **S.secondary_button_style()
        )
        self.btn_load_data.pack(side="left")
        self.lbl_data_info = ctk.CTkLabel(
            ds_frame, text="Chưa có dữ liệu", font=S.FONT_SMALL, text_color=S.TEXT_MUTED
        )
        self.lbl_data_info.pack(side="left", padx=S.SPACE_MD)

        # --- Card: Proxy ---
        card2 = ctk.CTkFrame(frame, **S.card_style())
        card2.grid(row=1, column=0, sticky="ew", pady=(0, S.SPACE_LG))
        card2.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(card2, text="PROXY MANAGER", font=S.FONT_HEADING,
                     text_color=S.TEXT_SECONDARY).grid(
            row=0, column=0, sticky="w", padx=pad, pady=(pad, S.SPACE_MD))
        ctk.CTkLabel(card2, text="Mỗi dòng một proxy — hỗ trợ ip:port và ip:port:user:pass",
                     font=S.FONT_TINY, text_color=S.TEXT_MUTED).grid(
            row=1, column=0, sticky="w", padx=pad, pady=(0, S.SPACE_SM))

        self.txt_proxies = ctk.CTkTextbox(
            card2, height=140, fg_color=S.BG_ELEVATED, border_width=1,
            border_color=S.BORDER_LIGHT, corner_radius=S.RADIUS_MD,
            text_color=S.TEXT_PRIMARY, font=S.FONT_MONO
        )
        self.txt_proxies.grid(row=2, column=0, sticky="ew", padx=pad, pady=(0, S.SPACE_SM))

        self.btn_test_proxy = ctk.CTkButton(
            card2, text="Kiểm tra proxy", command=self._test_proxies,
            **S.secondary_button_style()
        )
        self.btn_test_proxy.grid(row=3, column=0, sticky="w", padx=pad, pady=(0, pad))

        # --- Card: Điều khiển ---
        card3 = ctk.CTkFrame(frame, **S.card_style())
        card3.grid(row=2, column=0, sticky="ew", pady=(0, S.SPACE_LG))
        card3.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card3, text="ĐIỀU KHIỂN", font=S.FONT_HEADING,
                     text_color=S.TEXT_SECONDARY).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=pad, pady=(pad, S.SPACE_MD))

        # Threads slider
        ctk.CTkLabel(card3, text="Số luồng", font=S.FONT_BODY,
                     text_color=S.TEXT_PRIMARY).grid(row=1, column=0, sticky="w", padx=pad, pady=S.SPACE_SM)
        self.slider_threads = ctk.CTkSlider(
            card3, from_=1, to=10, number_of_steps=9,
            button_color=S.ACCENT_WHITE, button_hover_color=S.ACCENT_HOVER,
            progress_color=S.ACCENT_WHITE, fg_color=S.BG_ELEVATED,
            command=self._update_thread_label
        )
        self.slider_threads.set(3)
        self.slider_threads.grid(row=1, column=1, sticky="ew", padx=S.SPACE_MD, pady=S.SPACE_SM)
        self.lbl_thread_count = ctk.CTkLabel(
            card3, text="3 luồng", font=S.FONT_BODY, text_color=S.TEXT_PRIMARY, width=70
        )
        self.lbl_thread_count.grid(row=1, column=2, sticky="e", padx=(0, pad), pady=S.SPACE_SM)

        # Grid layout
        ctk.CTkLabel(card3, text="Bố cục lưới", font=S.FONT_BODY,
                     text_color=S.TEXT_PRIMARY).grid(row=2, column=0, sticky="w", padx=pad, pady=S.SPACE_SM)
        self.combo_grid = ctk.CTkOptionMenu(
            card3, values=["Tự động", "1 cột", "2 cột", "3 cột", "4 cột"],
            fg_color=S.BG_ELEVATED, button_color=S.BG_ELEVATED,
            button_hover_color=S.BG_HOVER, text_color=S.TEXT_PRIMARY,
            dropdown_fg_color=S.BG_CARD, dropdown_hover_color=S.BG_HOVER,
            dropdown_text_color=S.TEXT_PRIMARY, font=S.FONT_BODY,
            corner_radius=S.RADIUS_MD
        )
        self.combo_grid.set(self.settings.get("grid_mode", "Tự động"))
        self.combo_grid.grid(row=2, column=1, sticky="w", padx=S.SPACE_MD, pady=S.SPACE_SM)

        # Kích thước cửa sổ
        ctk.CTkLabel(card3, text="Kích thước cửa sổ", font=S.FONT_BODY,
                     text_color=S.TEXT_PRIMARY).grid(row=3, column=0, sticky="w", padx=pad, pady=S.SPACE_SM)
        size_frame = ctk.CTkFrame(card3, fg_color="transparent")
        size_frame.grid(row=3, column=1, columnspan=2, sticky="w", padx=S.SPACE_MD, pady=S.SPACE_SM)

        self.entry_win_w = ctk.CTkEntry(size_frame, width=70, **S.input_style())
        self.entry_win_w.insert(0, str(self.settings.get("window_width", 900)))
        self.entry_win_w.pack(side="left")
        ctk.CTkLabel(size_frame, text="×", font=S.FONT_BODY,
                     text_color=S.TEXT_SECONDARY).pack(side="left", padx=S.SPACE_SM)

        self.entry_win_h = ctk.CTkEntry(size_frame, width=70, **S.input_style())
        self.entry_win_h.insert(0, str(self.settings.get("window_height", 1200)))
        self.entry_win_h.pack(side="left")

        ctk.CTkLabel(size_frame, text="Scale", font=S.FONT_BODY,
                     text_color=S.TEXT_SECONDARY).pack(side="left", padx=(S.SPACE_LG, S.SPACE_SM))
        self.entry_win_scale = ctk.CTkEntry(size_frame, width=60, **S.input_style())
        self.entry_win_scale.insert(0, str(self.settings.get("window_scale", 0.8)))
        self.entry_win_scale.pack(side="left")

        # Buttons
        btn_row = ctk.CTkFrame(card3, fg_color="transparent")
        btn_row.grid(row=4, column=0, columnspan=3, sticky="ew", padx=pad, pady=(S.SPACE_MD, pad))
        btn_row.grid_columnconfigure((0, 1, 2), weight=1)

        self.btn_start = ctk.CTkButton(
            btn_row, text="▶  BẮT ĐẦU", command=self._start, **S.success_button_style()
        )
        self.btn_start.grid(row=0, column=0, sticky="ew", padx=(0, S.SPACE_SM))

        self.btn_pause = ctk.CTkButton(
            btn_row, text="❚❚  TẠM DỪNG", command=self._pause, state="disabled",
            **S.warning_button_style()
        )
        self.btn_pause.grid(row=0, column=1, sticky="ew", padx=S.SPACE_SM)

        self.btn_stop = ctk.CTkButton(
            btn_row, text="■  DỪNG HẲN", command=self._stop, state="disabled",
            **S.danger_button_style()
        )
        self.btn_stop.grid(row=0, column=2, sticky="ew", padx=(S.SPACE_SM, 0))

        # Export
        ctk.CTkButton(
            card3, text="⭳  Xuất kết quả Excel", command=self._export_results,
            **S.secondary_button_style()
        ).grid(row=5, column=0, columnspan=3, sticky="e", padx=pad, pady=(0, pad))

    # ============================================================
    # VIEW: MONITOR
    # ============================================================

    def _build_monitor_view(self):
        frame = ctk.CTkFrame(self.view_stack, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        self.views["monitor"] = frame

        # --- Status table card ---
        card = ctk.CTkFrame(frame, **S.card_style())
        card.grid(row=0, column=0, sticky="nsew", pady=(0, S.SPACE_LG))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(2, weight=1)
        pad = S.SPACE_LG

        ctk.CTkLabel(card, text="BẢNG TRẠNG THÁI", font=S.FONT_HEADING,
                     text_color=S.TEXT_SECONDARY).grid(
            row=0, column=0, sticky="w", padx=pad, pady=(pad, S.SPACE_MD))

        # Header row
        headers = ["STT", "Email", "Trạng thái", "Thời gian", "Chi tiết"]
        widths = [50, 260, 110, 170, 300]
        header = ctk.CTkFrame(card, fg_color=S.BG_ELEVATED, corner_radius=S.RADIUS_SM)
        header.grid(row=1, column=0, sticky="ew", padx=pad, pady=(0, S.SPACE_SM))
        for i, (h, w) in enumerate(zip(headers, widths)):
            header.grid_columnconfigure(i, weight=(1 if i == 4 else 0))
            ctk.CTkLabel(header, text=h, font=S.FONT_SMALL,
                         text_color=S.TEXT_SECONDARY, width=w, anchor="w").grid(
                row=0, column=i, padx=S.SPACE_MD, pady=S.SPACE_SM, sticky="w")

        self.table_frame = ctk.CTkScrollableFrame(card, fg_color=S.BG_SURFACE, corner_radius=S.RADIUS_MD)
        self.table_frame.grid(row=2, column=0, sticky="nsew", padx=pad, pady=(0, pad))
        self.table_frame.grid_columnconfigure(4, weight=1)

        # --- Log card ---
        log_card = ctk.CTkFrame(frame, **S.card_style())
        log_card.grid(row=1, column=0, sticky="nsew")
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(log_card, text="LOG TRỰC TIẾP", font=S.FONT_HEADING,
                     text_color=S.TEXT_SECONDARY).grid(
            row=0, column=0, sticky="w", padx=pad, pady=(pad, S.SPACE_SM))

        self.txt_log = ctk.CTkTextbox(
            log_card, height=220, fg_color=S.BG_ELEVATED, border_width=1,
            border_color=S.BORDER, corner_radius=S.RADIUS_MD,
            text_color=S.TEXT_PRIMARY, font=S.FONT_MONO, state="disabled"
        )
        self.txt_log.grid(row=1, column=0, sticky="nsew", padx=pad, pady=(0, pad))

    # ============================================================
    # VIEW: ADVANCED
    # ============================================================

    def _build_advanced_view(self):
        frame = ctk.CTkScrollableFrame(self.view_stack, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        self.views["advanced"] = frame
        pad = S.SPACE_LG

        # --- Card: Selectors ---
        card = ctk.CTkFrame(frame, **S.card_style())
        card.grid(row=0, column=0, sticky="ew", pady=(0, S.SPACE_LG))
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card, text="CSS SELECTORS", font=S.FONT_HEADING,
                     text_color=S.TEXT_SECONDARY).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=pad, pady=(pad, S.SPACE_MD))

        selector_fields = [
            ("Họ tên", "name"), ("Email", "email"), ("Mật khẩu", "password"),
            ("Nút Submit", "submit"), ("Chỉ báo thành công", "success_indicator"),
            ("Chỉ báo lỗi", "error_indicator"),
        ]
        r = 1
        for label, key in selector_fields:
            ctk.CTkLabel(card, text=label, font=S.FONT_BODY,
                         text_color=S.TEXT_PRIMARY).grid(row=r, column=0, sticky="w", padx=pad, pady=S.SPACE_SM)
            entry = ctk.CTkEntry(card, **S.input_style())
            entry.insert(0, self.selectors.get(key, ""))
            entry.grid(row=r, column=1, sticky="ew", padx=(0, pad), pady=S.SPACE_SM)
            setattr(self, f"sel_{key}", entry)
            r += 1

        # --- Card: Captcha ---
        card2 = ctk.CTkFrame(frame, **S.card_style())
        card2.grid(row=1, column=0, sticky="ew", pady=(0, S.SPACE_LG))
        card2.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card2, text="CAPTCHA SOLVER", font=S.FONT_HEADING,
                     text_color=S.TEXT_SECONDARY).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=pad, pady=(pad, S.SPACE_MD))

        ctk.CTkLabel(card2, text="Provider", font=S.FONT_BODY,
                     text_color=S.TEXT_PRIMARY).grid(row=1, column=0, sticky="w", padx=pad, pady=S.SPACE_SM)
        self.combo_captcha = ctk.CTkOptionMenu(
            card2, values=["Không dùng", "2Captcha", "CapSolver", "Anti-Captcha"],
            fg_color=S.BG_ELEVATED, button_color=S.BG_ELEVATED, button_hover_color=S.BG_HOVER,
            text_color=S.TEXT_PRIMARY, dropdown_fg_color=S.BG_CARD,
            dropdown_hover_color=S.BG_HOVER, dropdown_text_color=S.TEXT_PRIMARY,
            font=S.FONT_BODY, corner_radius=S.RADIUS_MD
        )
        self.combo_captcha.set("Không dùng")
        self.combo_captcha.grid(row=1, column=1, sticky="w", padx=(0, pad), pady=S.SPACE_SM)

        ctk.CTkLabel(card2, text="API Key", font=S.FONT_BODY,
                     text_color=S.TEXT_PRIMARY).grid(row=2, column=0, sticky="w", padx=pad, pady=S.SPACE_SM)
        self.entry_captcha_key = ctk.CTkEntry(card2, show="*", **S.input_style())
        self.entry_captcha_key.grid(row=2, column=1, sticky="ew", padx=(0, pad), pady=S.SPACE_SM)

        # --- Card: OTP / Retry ---
        card3 = ctk.CTkFrame(frame, **S.card_style())
        card3.grid(row=2, column=0, sticky="ew", pady=(0, S.SPACE_LG))
        card3.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card3, text="EMAIL OTP & RETRY", font=S.FONT_HEADING,
                     text_color=S.TEXT_SECONDARY).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=pad, pady=(pad, S.SPACE_MD))

        ctk.CTkLabel(card3, text="IMAP Host", font=S.FONT_BODY,
                     text_color=S.TEXT_PRIMARY).grid(row=1, column=0, sticky="w", padx=pad, pady=S.SPACE_SM)
        self.entry_imap_host = ctk.CTkEntry(card3, **S.input_style())
        self.entry_imap_host.insert(0, "imap.gmail.com")
        self.entry_imap_host.grid(row=1, column=1, sticky="ew", padx=(0, pad), pady=S.SPACE_SM)

        ctk.CTkLabel(card3, text="Số lần retry tối đa", font=S.FONT_BODY,
                     text_color=S.TEXT_PRIMARY).grid(row=2, column=0, sticky="w", padx=pad, pady=S.SPACE_SM)
        retry_frame = ctk.CTkFrame(card3, fg_color="transparent")
        retry_frame.grid(row=2, column=1, sticky="ew", padx=(0, pad), pady=S.SPACE_SM)
        self.slider_retry = ctk.CTkSlider(
            retry_frame, from_=0, to=5, number_of_steps=5,
            button_color=S.ACCENT_WHITE, button_hover_color=S.ACCENT_HOVER,
            progress_color=S.ACCENT_WHITE, fg_color=S.BG_ELEVATED, width=260
        )
        self.slider_retry.set(2)
        self.slider_retry.pack(side="left")
        self.lbl_retry = ctk.CTkLabel(retry_frame, text="2", font=S.FONT_BODY,
                                      text_color=S.TEXT_PRIMARY, width=40)
        self.lbl_retry.pack(side="left", padx=S.SPACE_MD)
        self.slider_retry.configure(command=lambda v: self.lbl_retry.configure(text=str(int(v))))

        # --- Card: Cleanup ---
        card4 = ctk.CTkFrame(frame, **S.card_style())
        card4.grid(row=3, column=0, sticky="ew", pady=(0, S.SPACE_LG))
        card4.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(card4, text="DỌN DẸP", font=S.FONT_HEADING,
                     text_color=S.TEXT_SECONDARY).grid(
            row=0, column=0, sticky="w", padx=pad, pady=(pad, S.SPACE_MD))

        self.chk_delete_profile = ctk.CTkCheckBox(
            card4, text="Xóa profile sau quy trình",
            variable=self.delete_after, font=S.FONT_BODY, text_color=S.TEXT_PRIMARY,
            fg_color=S.ACCENT_WHITE, hover_color=S.ACCENT_HOVER,
            checkmark_color=S.TEXT_INVERT, border_color=S.BORDER_LIGHT,
            corner_radius=S.RADIUS_SM
        )
        self.chk_delete_profile.grid(row=1, column=0, sticky="w", padx=pad, pady=(0, S.SPACE_XS))

        ctk.CTkLabel(
            card4,
            text="Profile sẽ bị xóa hoàn toàn khỏi GPM Login và ổ cứng sau khi hoàn thành\n"
                 "(API: DELETE /api/v3/profiles/{id}) — giúp tiết kiệm dung lượng.",
            font=S.FONT_TINY, text_color=S.TEXT_MUTED, justify="left"
        ).grid(row=2, column=0, sticky="w", padx=pad, pady=(0, pad))

        # --- Save button ---
        ctk.CTkButton(
            frame, text="Lưu cấu hình", command=self._save_config, **S.primary_button_style()
        ).grid(row=4, column=0, sticky="e", pady=(0, S.SPACE_LG))

    # ============================================================
    # LOGIC
    # ============================================================

    def _update_thread_label(self, value):
        self.lbl_thread_count.configure(text=f"{int(value)} luồng")

    def _get_grid_cols(self):
        """Đọc số cột từ dropdown bố cục lưới. None = tự động."""
        value = self.combo_grid.get()
        if value.startswith("Tự động"):
            return None
        try:
            return int(value.split()[0])
        except (ValueError, IndexError):
            return None

    def _load_data_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Data files", "*.csv *.xlsx *.xls *.txt"), ("All files", "*.*")]
        )
        if not file_path:
            return

        proxy_text = self.txt_proxies.get("1.0", "end-1c").strip()
        self.settings["last_proxy_list"] = proxy_text
        self.settings["default_url"] = self.url_entry.get().strip()
        self.settings["delete_profile_after"] = self.delete_after.get()
        self._save_settings()

        self._load_csv_file(file_path)

    def _load_csv_file(self, file_path: str):
        """Load CSV format: taikhoan|matkhau|Tên tài khoản|stk"""
        try:
            df = None
            if file_path.endswith((".xlsx", ".xls")):
                df = pd.read_excel(file_path)
            else:
                for sep in ['|', ',', ';', '\t']:
                    try:
                        df = pd.read_csv(file_path, sep=sep)
                        if len(df.columns) >= 3:
                            break
                    except Exception:
                        continue
                if df is None:
                    df = pd.read_csv(file_path)

            df.columns = [c.strip().lower() for c in df.columns]

            column_map = {
                'tên tài khoản': 'name', 'ten tai khoan': 'name',
                'ten tài khoản': 'name', 'ho ten': 'name', 'hoten': 'name',
                'fullname': 'name', 'taikhoan': 'email', 'email': 'email', 'mail': 'email',
                'matkhau': 'password', 'mat khau': 'password',
                'password': 'password', 'pass': 'password',
            }
            mapped = set()
            for old_col, new_col in column_map.items():
                if old_col in df.columns and new_col not in mapped:
                    df.rename(columns={old_col: new_col}, inplace=True)
                    mapped.add(new_col)

            required = ['email', 'password']
            missing = [c for c in required if c not in df.columns]
            if missing:
                messagebox.showerror(
                    "Lỗi",
                    f"CSV thiếu cột bắt buộc: {missing}\n"
                    f"Cột hiện có: {df.columns.tolist()}\n"
                    f"Định dạng mong đợi: taikhoan|matkhau|Tên tài khoản|stk"
                )
                return

            if 'name' not in df.columns:
                df['name'] = df['email'].apply(lambda x: str(x).split('@')[0])

            self.accounts = df.to_dict("records")
            self.settings["last_csv_path"] = file_path
            self._save_settings()

            self.lbl_data_info.configure(
                text=f"✓ {len(self.accounts)} tài khoản · {Path(file_path).name}",
                text_color=S.SUCCESS
            )
            self._log(f"Đã load {len(self.accounts)} tài khoản từ {Path(file_path).name}", "success")

        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể đọc file: {e}")

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

    def _start(self):
        if not self.accounts:
            messagebox.showwarning("Cảnh báo", "Vui lòng load dữ liệu tài khoản trước")
            return

        proxy_text = self.txt_proxies.get("1.0", "end-1c").strip()
        self.settings["last_proxy_list"] = proxy_text
        self.settings["default_url"] = self.url_entry.get().strip()
        self.settings["delete_profile_after"] = self.delete_after.get()
        self._save_settings()

        self.proxies = [p.strip() for p in proxy_text.split("\n") if p.strip()]

        url = self.url_entry.get().strip()
        threads = int(self.slider_threads.get())
        delete_after = self.delete_after.get()

        # Kích thước cửa sổ
        try:
            win_w = int(self.entry_win_w.get().strip())
            win_h = int(self.entry_win_h.get().strip())
            win_scale = float(self.entry_win_scale.get().strip())
        except ValueError:
            messagebox.showerror("Lỗi", "Kích thước cửa sổ / scale không hợp lệ")
            return

        grid_cols = self._get_grid_cols()

        # Lưu settings
        self.settings["window_width"] = win_w
        self.settings["window_height"] = win_h
        self.settings["window_scale"] = win_scale
        self.settings["grid_mode"] = self.combo_grid.get()
        self._save_settings()

        self._log(
            f"▶ Bắt đầu: {len(self.accounts)} tài khoản · {threads} luồng · "
            f"cửa sổ {win_w}×{win_h} scale {win_scale} · xóa profile: {delete_after}", "info"
        )
        self._set_status("Đang chạy", S.SUCCESS)

        selectors = {}
        for key in ["name", "email", "password", "submit", "success_indicator", "error_indicator"]:
            entry = getattr(self, f"sel_{key}", None)
            if entry:
                selectors[key] = entry.get().strip()

        self.dispatcher = Dispatcher(
            gpm=self.gpm, max_workers=threads, delete_after=delete_after,
            url=url, selectors=selectors, log_callback=self._log,
            window_width=win_w, window_height=win_h, window_scale=win_scale,
            grid_cols=grid_cols,
        )

        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="normal")
        self.btn_stop.configure(state="normal")

        import threading
        threading.Thread(target=self._run_dispatcher, daemon=True).start()

        self._switch_view("monitor")

    def _run_dispatcher(self):
        try:
            self.results = self.dispatcher.run_batch(self.accounts, self.proxies)
            self._update_table()
            self._log("Hoàn thành quy trình", "success")
            self._set_status("Hoàn thành", S.SUCCESS)
        except Exception as e:
            self._log(f"Lỗi: {e}", "error")
            self._set_status("Lỗi", S.DANGER)
        finally:
            self.btn_start.configure(state="normal")
            self.btn_pause.configure(state="disabled")
            self.btn_stop.configure(state="disabled")

    def _pause(self):
        self._log("Tạm dừng...", "warning")
        self._set_status("Tạm dừng", S.WARNING)

    def _stop(self):
        if self.dispatcher:
            self.dispatcher.stop()
        self._log("Đã dừng!", "error")
        self._set_status("Đã dừng", S.DANGER)

    def _set_status(self, text: str, color: str = S.TEXT_MUTED):
        self.status_dot.configure(text=f"●  {text}", text_color=color)

    def _update_table(self):
        for widget in self.table_frame.winfo_children():
            widget.destroy()

        for i, result in enumerate(self.results):
            acc = result.get("account", {})
            status = result.get("status", "unknown")
            timestamp = result.get("timestamp", "")
            error = result.get("error", "")

            status_map = {
                "success": (S.SUCCESS, "Thành công"),
                "failed": (S.DANGER, "Thất bại"),
                "error": (S.DANGER, "Lỗi"),
            }
            color, label = status_map.get(status, (S.TEXT_MUTED, status))

            ctk.CTkLabel(self.table_frame, text=str(i + 1), font=S.FONT_SMALL,
                         text_color=S.TEXT_SECONDARY, width=50, anchor="w").grid(
                row=i, column=0, padx=S.SPACE_MD, pady=S.SPACE_XS, sticky="w")
            ctk.CTkLabel(self.table_frame, text=acc.get("email", ""), font=S.FONT_SMALL,
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

    def _log(self, message: str, level: str = "info"):
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", f"{timestamp}  ", "ts")
        self.txt_log.insert("end", f"{message}\n", level)

        self.txt_log.tag_config("ts", foreground=S.TEXT_MUTED)
        self.txt_log.tag_config("info", foreground=S.TEXT_PRIMARY)
        self.txt_log.tag_config("success", foreground=S.SUCCESS)
        self.txt_log.tag_config("warning", foreground=S.WARNING)
        self.txt_log.tag_config("error", foreground=S.DANGER)

        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

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
        selectors = {}
        for key in ["name", "email", "password", "submit", "success_indicator", "error_indicator"]:
            entry = getattr(self, f"sel_{key}", None)
            if entry:
                selectors[key] = entry.get().strip()

        config_path = Path("config/selectors.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({"default": selectors}, f, indent=2, ensure_ascii=False)

        self.settings["default_url"] = self.url_entry.get().strip()
        self.settings["delete_profile_after"] = self.delete_after.get()
        self._save_settings()

        self._log("Đã lưu cấu hình", "success")
