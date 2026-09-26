"""
Dashboard - Giao diện chính với CustomTkinter
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

logger = logging.getLogger(__name__)


class Dashboard(ctk.CTk):
    """Giao diện chính của ứng dụng."""
    
    def __init__(self):
        super().__init__()
        
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        self.title("RegAcc - Hệ thống tự động hóa đăng ký đa luồng")
        self.geometry("1200x800")
        self.minsize(1000, 700)
        
        # State
        self.gpm = GPMManager()
        self.dispatcher: Dispatcher | None = None
        self.accounts: list[dict] = []
        self.proxies: list[str] = []
        self.results: list[dict] = []
        self.selectors: dict = {}
        self.delete_after = tk.BooleanVar(value=False)
        
        # Load selectors
        self._load_selectors()
        
        # Build UI
        self._build_tabview()
        self._build_dashboard_tab()
        self._build_monitor_tab()
        self._build_advanced_tab()
        
        logging.info("Dashboard khởi tạo thành công")
    
    def _load_selectors(self):
        """Load selectors từ config."""
        config_path = Path("config/selectors.json")
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                self.selectors = json.load(f).get("default", {})
    
    def _build_tabview(self):
        """Tạo tabview chính."""
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.tab_dashboard = self.tabview.add("Bảng điều khiển")
        self.tab_monitor = self.tabview.add("Trực quan hóa & Giám sát")
        self.tab_advanced = self.tabview.add("Cấu hình nâng cao")
    
    def _build_dashboard_tab(self):
        """Tab 1: Bảng điều khiển."""
        frame = self.tab_dashboard
        frame.grid_columnconfigure(1, weight=1)
        
        # URL Input
        ctk.CTkLabel(frame, text="URL đích:", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, padx=10, pady=10, sticky="w"
        )
        self.url_entry = ctk.CTkEntry(
            frame, placeholder_text="https://...", width=500
        )
        self.url_entry.insert(0, DEFAULT_URL)
        self.url_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        
        # Data Source
        ctk.CTkLabel(frame, text="Nguồn dữ liệu:", font=("Segoe UI", 12, "bold")).grid(
            row=1, column=0, padx=10, pady=10, sticky="w"
        )
        self.btn_load_data = ctk.CTkButton(
            frame, text="Chọn file (CSV/Excel/TXT)", command=self._load_data_file
        )
        self.btn_load_data.grid(row=1, column=1, padx=10, pady=10, sticky="w")
        self.lbl_data_info = ctk.CTkLabel(frame, text="Chưa có dữ liệu", text_color="gray")
        self.lbl_data_info.grid(row=1, column=2, padx=10, pady=10, sticky="w")
        
        # Proxy Manager
        ctk.CTkLabel(frame, text="Proxy (mỗi dòng 1 proxy):", font=("Segoe UI", 12, "bold")).grid(
            row=2, column=0, padx=10, pady=10, sticky="nw"
        )
        self.txt_proxies = ctk.CTkTextbox(frame, height=150, width=400)
        self.txt_proxies.grid(row=2, column=1, padx=10, pady=10, sticky="nsew")
        self.btn_test_proxy = ctk.CTkButton(
            frame, text="Kiểm tra Proxy", command=self._test_proxies
        )
        self.btn_test_proxy.grid(row=2, column=2, padx=10, pady=10, sticky="n")
        
        # Threading Controls
        ctk.CTkLabel(frame, text="Số luồng đồng thời:", font=("Segoe UI", 12, "bold")).grid(
            row=3, column=0, padx=10, pady=10, sticky="w"
        )
        self.slider_threads = ctk.CTkSlider(
            frame, from_=1, to=10, number_of_steps=9, command=self._update_thread_label
        )
        self.slider_threads.set(3)
        self.slider_threads.grid(row=3, column=1, padx=10, pady=10, sticky="ew")
        self.lbl_thread_count = ctk.CTkLabel(frame, text="3 luồng", text_color="white")
        self.lbl_thread_count.grid(row=3, column=2, padx=10, pady=10, sticky="w")
        
        # Grid Layout Selector
        ctk.CTkLabel(frame, text="Bố cục lưới:", font=("Segoe UI", 12, "bold")).grid(
            row=4, column=0, padx=10, pady=10, sticky="w"
        )
        self.combo_grid = ctk.CTkOptionMenu(
            frame, values=["Tự động", "1x1", "2x2", "2x3", "3x3", "Headless (ẩn)"]
        )
        self.combo_grid.set("Tự động")
        self.combo_grid.grid(row=4, column=1, padx=10, pady=10, sticky="w")
        
        # Control Buttons
        btn_frame = ctk.CTkFrame(frame)
        btn_frame.grid(row=5, column=0, columnspan=3, padx=10, pady=20, sticky="ew")
        
        self.btn_start = ctk.CTkButton(
            btn_frame, text="BẮT ĐẦU", command=self._start, color="green",
            font=("Segoe UI", 14, "bold"), height=50
        )
        self.btn_start.pack(side="left", padx=10, expand=True, fill="x")
        
        self.btn_pause = ctk.CTkButton(
            btn_frame, text="TẠM DỪNG", command=self._pause, color="orange",
            font=("Segoe UI", 14, "bold"), height=50, state="disabled"
        )
        self.btn_pause.pack(side="left", padx=10, expand=True, fill="x")
        
        self.btn_stop = ctk.CTkButton(
            btn_frame, text="DỪNG HẲN", command=self._stop, color="red",
            font=("Segoe UI", 14, "bold"), height=50, state="disabled"
        )
        self.btn_stop.pack(side="left", padx=10, expand=True, fill="x")
        
        # Export Button
        self.btn_export = ctk.CTkButton(
            frame, text="Xuất kết quả (Excel)", command=self._export_results
        )
        self.btn_export.grid(row=6, column=0, columnspan=3, padx=10, pady=10, sticky="e")
    
    def _build_monitor_tab(self):
        """Tab 2: Trực quan hóa & Giám sát."""
        frame = self.tab_monitor
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        
        # Status Table
        ctk.CTkLabel(frame, text="Bảng trạng thái:", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, padx=10, pady=10, sticky="w"
        )
        
        # Header
        headers = ["STT", "Email", "Trạng thái", "Thời gian", "Chi tiết"]
        header_frame = ctk.CTkFrame(frame)
        header_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        
        for i, h in enumerate(headers):
            ctk.CTkLabel(header_frame, text=h, font=("Segoe UI", 11, "bold")).grid(
                row=0, column=i, padx=10, pady=5, sticky="w"
            )
        
        # Scrollable table
        self.table_frame = ctk.CTkScrollableFrame(frame, height=200)
        self.table_frame.grid(row=2, column=0, padx=10, pady=5, sticky="nsew")
        self.table_frame.grid_columnconfigure(4, weight=1)
        
        # Live Console Log
        ctk.CTkLabel(frame, text="Log trực tiếp:", font=("Segoe UI", 14, "bold")).grid(
            row=3, column=0, padx=10, pady=10, sticky="w"
        )
        self.txt_log = ctk.CTkTextbox(frame, height=200, state="disabled")
        self.txt_log.grid(row=4, column=0, padx=10, pady=5, sticky="nsew")
    
    def _build_advanced_tab(self):
        """Tab 3: Cấu hình nâng cao."""
        frame = self.tab_advanced
        frame.grid_columnconfigure(1, weight=1)
        
        row = 0
        
        # === Selectors ===
        ctk.CTkLabel(frame, text="CSS Selectors", font=("Segoe UI", 14, "bold")).grid(
            row=row, column=0, padx=10, pady=10, sticky="nw"
        )
        row += 1
        
        selector_fields = [
            ("Họ tên", "name"),
            ("Email", "email"),
            ("Mật khẩu", "password"),
            ("Nút Submit", "submit"),
            ("Chỉ báo thành công", "success_indicator"),
            ("Chỉ báo lỗi", "error_indicator"),
        ]
        
        for label, key in selector_fields:
            ctk.CTkLabel(frame, text=f"{label}:").grid(
                row=row, column=0, padx=10, pady=5, sticky="w"
            )
            entry = ctk.CTkEntry(frame, width=400)
            entry.insert(0, self.selectors.get(key, ""))
            entry.grid(row=row, column=1, padx=10, pady=5, sticky="w")
            setattr(self, f"sel_{key}", entry)
            row += 1
        
        # === Captcha ===
        row += 1
        ctk.CTkLabel(frame, text="Captcha Solver", font=("Segoe UI", 14, "bold")).grid(
            row=row, column=0, padx=10, pady=10, sticky="nw"
        )
        row += 1
        
        ctk.CTkLabel(frame, text="Provider:").grid(row=row, column=0, padx=10, pady=5, sticky="w")
        self.combo_captcha = ctk.CTkOptionMenu(frame, values=["Không dùng", "2Captcha", "CapSolver", "Anti-Captcha"])
        self.combo_captcha.set("Không dùng")
        self.combo_captcha.grid(row=row, column=1, padx=10, pady=5, sticky="w")
        row += 1
        
        ctk.CTkLabel(frame, text="API Key:").grid(row=row, column=0, padx=10, pady=5, sticky="w")
        self.entry_captcha_key = ctk.CTkEntry(frame, width=400, show="*")
        self.entry_captcha_key.grid(row=row, column=1, padx=10, pady=5, sticky="w")
        row += 1
        
        # === OTP/Email ===
        row += 1
        ctk.CTkLabel(frame, text="Email OTP", font=("Segoe UI", 14, "bold")).grid(
            row=row, column=0, padx=10, pady=10, sticky="nw"
        )
        row += 1
        
        ctk.CTkLabel(frame, text="IMAP Host:").grid(row=row, column=0, padx=10, pady=5, sticky="w")
        self.entry_imap_host = ctk.CTkEntry(frame, width=300)
        self.entry_imap_host.insert(0, "imap.gmail.com")
        self.entry_imap_host.grid(row=row, column=1, padx=10, pady=5, sticky="w")
        row += 1
        
        # === Retry Policy ===
        row += 1
        ctk.CTkLabel(frame, text="Retry Policy", font=("Segoe UI", 14, "bold")).grid(
            row=row, column=0, padx=10, pady=10, sticky="nw"
        )
        row += 1
        
        ctk.CTkLabel(frame, text="Số lần retry tối đa:").grid(row=row, column=0, padx=10, pady=5, sticky="w")
        self.slider_retry = ctk.CTkSlider(frame, from_=0, to=5, number_of_steps=5)
        self.slider_retry.set(2)
        self.slider_retry.grid(row=row, column=1, padx=10, pady=5, sticky="w")
        row += 1
        
        # === Xóa Profile (QUAN TRỌNG) ===
        row += 1
        ctk.CTkLabel(frame, text="Dọn dẹp", font=("Segoe UI", 14, "bold")).grid(
            row=row, column=0, padx=10, pady=10, sticky="nw"
        )
        row += 1
        
        # Checkbox xóa profile
        self.chk_delete_profile = ctk.CTkCheckBox(
            frame,
            text="Xóa profile sau quy trình (tiết kiệm bộ nhớ, dọn dẹp GPM Login)",
            variable=self.delete_after,
            font=("Segoe UI", 12),
            text_color="white",
            hover_color="green",
        )
        self.chk_delete_profile.grid(row=row, column=0, columnspan=2, padx=10, pady=10, sticky="w")
        row += 1
        
        # Label giải thích
        ctk.CTkLabel(
            frame,
            text="Khi tick vào: Mỗi profile sẽ được xóa hoàn toàn khỏi GPM Login và ổ cứng\nsau khi hoàn thành quy trình đăng ký (thông qua API DELETE /api/v3/profiles/{id})",
            text_color="gray",
            font=("Segoe UI", 10),
            justify="left"
        ).grid(row=row, column=0, columnspan=2, padx=30, pady=0, sticky="w")
        row += 1
        
        # Save Config Button
        row += 1
        self.btn_save_config = ctk.CTkButton(
            frame, text="Lưu cấu hình", command=self._save_config
        )
        self.btn_save_config.grid(row=row, column=0, columnspan=2, padx=10, pady=20, sticky="w")
    
    def _update_thread_label(self, value):
        """Cập nhật label số luồng."""
        self.lbl_thread_count.configure(text=f"{int(value)} luồng")
    
    def _load_data_file(self):
        """Load file dữ liệu tài khoản."""
        file_path = filedialog.askopenfilename(
            filetypes=[("Data files", "*.csv *.xlsx *.xls *.txt"), ("All files", "*.*")]
        )
        if not file_path:
            return
        
        try:
            if file_path.endswith(".csv"):
                df = pd.read_csv(file_path)
            elif file_path.endswith((".xlsx", ".xls")):
                df = pd.read_excel(file_path)
            else:
                df = pd.read_csv(file_path, sep="\t")
            
            self.accounts = df.to_dict("records")
            self.lbl_data_info.configure(
                text=f"Đã load {len(self.accounts)} tài khoản từ {Path(file_path).name}",
                text_color="green"
            )
            self._log(f"Đã load {len(self.accounts)} tài khoản từ {file_path}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể đọc file: {e}")
    
    def _test_proxies(self):
        """Kiểm tra proxy sống/chết."""
        proxy_text = self.txt_proxies.get("1.0", "end-1c").strip()
        if not proxy_text:
            messagebox.showwarning("Cảnh báo", "Vui lòng nhập proxy trước")
            return
        
        self.proxies = [p.strip() for p in proxy_text.split("\n") if p.strip()]
        self._log(f"Kiểm tra {len(self.proxies)} proxies...")
        
        # TODO: Implement actual proxy testing
        # For now, just validate format
        valid = 0
        for proxy in self.proxies:
            try:
                parse_proxy(proxy)
                valid += 1
            except ValueError as e:
                self._log(f"Proxy không hợp lệ: {proxy}", "error")
        
        self._log(f"Kết quả: {valid}/{len(self.proxies)} proxies hợp lệ")
    
    def _start(self):
        """Bắt đầu chạy."""
        if not self.accounts:
            messagebox.showwarning("Cảnh báo", "Vui lòng load dữ liệu tài khoản trước")
            return
        
        proxy_text = self.txt_proxies.get("1.0", "end-1c").strip()
        self.proxies = [p.strip() for p in proxy_text.split("\n") if p.strip()]
        
        url = self.url_entry.get().strip()
        threads = int(self.slider_threads.get())
        delete_after = self.delete_after.get()
        
        self._log(f"Bắt đầu: {len(self.accounts)} accounts, {threads} luồng, xóa profile: {delete_after}")
        
        # Tạo selectors từ UI
        selectors = {}
        for key in ["name", "email", "password", "submit", "success_indicator", "error_indicator"]:
            entry = getattr(self, f"sel_{key}", None)
            if entry:
                selectors[key] = entry.get().strip()
        
        self.dispatcher = Dispatcher(
            gpm=self.gpm,
            max_workers=threads,
            delete_after=delete_after,
            url=url,
            selectors=selectors,
            log_callback=self._log,
        )
        
        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="normal")
        self.btn_stop.configure(state="normal")
        
        # Chạy trong thread riêng
        import threading
        threading.Thread(target=self._run_dispatcher, daemon=True).start()
    
    def _run_dispatcher(self):
        """Chạy dispatcher trong background thread."""
        try:
            self.results = self.dispatcher.run_batch(self.accounts, self.proxies)
            self._update_table()
            self._log("Hoàn thành!")
        except Exception as e:
            self._log(f"Lỗi: {e}", "error")
        finally:
            self.btn_start.configure(state="normal")
            self.btn_pause.configure(state="disabled")
            self.btn_stop.configure(state="disabled")
    
    def _pause(self):
        """Tạm dừng."""
        self._log("Tạm dừng...")
        # TODO: Implement pause
    
    def _stop(self):
        """Dừng hoàn toàn."""
        if self.dispatcher:
            self.dispatcher.stop()
        self._log("Đã dừng!")
    
    def _update_table(self):
        """Cập nhật bảng trạng thái."""
        # Clear old rows
        for widget in self.table_frame.winfo_children():
            widget.destroy()
        
        for i, result in enumerate(self.results):
            acc = result.get("account", {})
            status = result.get("status", "unknown")
            timestamp = result.get("timestamp", "")
            error = result.get("error", "")
            
            status_color = "green" if status == "success" else "red"
            
            ctk.CTkLabel(self.table_frame, text=str(i + 1)).grid(row=i, column=0, padx=5, pady=2)
            ctk.CTkLabel(self.table_frame, text=acc.get("email", "")).grid(row=i, column=1, padx=5, pady=2)
            ctk.CTkLabel(self.table_frame, text=status, text_color=status_color).grid(row=i, column=2, padx=5, pady=2)
            ctk.CTkLabel(self.table_frame, text=timestamp).grid(row=i, column=3, padx=5, pady=2)
            ctk.CTkLabel(self.table_frame, text=error).grid(row=i, column=4, padx=5, pady=2)
    
    def _log(self, message: str, level: str = "info"):
        """Thêm log vào console."""
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        
        self.txt_log.configure(state="normal")
        
        color = {
            "info": "white",
            "warning": "orange",
            "error": "red",
            "success": "green",
        }.get(level, "white")
        
        self.txt_log.insert("end", f"[{timestamp}] ", "timestamp")
        self.txt_log.insert("end", f"{message}\n", level)
        
        self.txt_log.tag_config("timestamp", foreground="gray")
        self.txt_log.tag_config("info", foreground="white")
        self.txt_log.tag_config("warning", foreground="orange")
        self.txt_log.tag_config("error", foreground="red")
        self.txt_log.tag_config("success", foreground="green")
        
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")
    
    def _export_results(self):
        """Xuất kết quả ra Excel."""
        if not self.results:
            messagebox.showwarning("Cảnh báo", "Chưa có kết quả để xuất")
            return
        
        try:
            success_path, failed_path = export_results(self.results)
            self._log(f"Đã xuất: {success_path}, {failed_path}", "success")
            messagebox.showinfo("Thành công", f"Đã xuất kết quả!")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể xuất: {e}")
    
    def _save_config(self):
        """Lưu cấu hình."""
        # Save selectors
        selectors = {}
        for key in ["name", "email", "password", "submit", "success_indicator", "error_indicator"]:
            entry = getattr(self, f"sel_{key}", None)
            if entry:
                selectors[key] = entry.get().strip()
        
        config_path = Path("config/selectors.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({"default": selectors}, f, indent=2, ensure_ascii=False)
        
        self._log("Đã lưu cấu hình", "success")
