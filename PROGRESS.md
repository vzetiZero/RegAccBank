# PROGRESS — Trạng thái dự án RegAcc

> Cập nhật: 2026-09-27
> Browser engine: GPM Login (antidetect), API local `http://localhost:9495/api/v1`

Tài liệu này ghi lại **những gì đã làm xong** và **những gì còn dở / cần phát triển tiếp**.

---

## 1. ĐÃ LÀM XONG ✅

### 1.1. Giao diện (UI)
- Sidebar 3 màn hình: **Chạy quy trình** · **Kết quả** · **Cài đặt**.
- Màn **Chạy quy trình** (tối ưu cho nhập liệu):
  - URL đích, chọn file dữ liệu (CSV/Excel).
  - **PIN rút tiền** (dùng khi chạy & ghi vào CSV) + nút **Ghi PIN vào CSV**.
  - **Ngân hàng**: 2 checkbox loại trừ nhau — **Ngân hàng ngẫu nhiên** / **Theo cột bank trong CSV**.
  - Proxy (mỗi dòng 1 proxy).
  - **Số luồng**: ô nhập số, mặc định **5** (giới hạn 1–50).
  - **Số tài khoản chạy**: ô nhập số hoặc `all`, mặc định **all**.
  - Bố cục lưới cửa sổ.
  - Log trực tiếp (cột phải).
  - Thanh hành động cố định: **BẮT ĐẦU / TẠM DỪNG / DỪNG / Xuất Excel**.
- Tên app (title): **68win auto - LH @vstar_auto**; logo sidebar hiển thị **68win auto / LH @vstar_auto**.
- Đã **gỡ toàn bộ phần test** khỏi giao diện (không còn nút chạy thử/quét trang).
- Màn **Kết quả**: chip Tổng / Thành công / Đã có / Thất bại / Lỗi, thanh tiến độ, bảng kết quả cập nhật theo thời gian thực.
- Màn **Cài đặt**: URL sau đăng ký, URL rút tiền, số lần retry, kích thước cửa sổ tối đa, tuỳ chọn xoá profile.
- Cập nhật UI từ luồng nền qua hàng đợi (thread-safe, không treo Tkinter).

### 1.2. Dữ liệu CSV
- Giữ nguyên tên cột gốc: `taikhoan | matkhau | Tên tài khoản | stk`.
- Tự thêm các cột mới và ghi ra file: **`bank`** (đặt ngay sau `stk`), **`pin`**, **`status`**.
- **Ngân hàng**: nếu CSV chưa có `bank` → chọn **ngẫu nhiên** rồi **ghi lại** vào CSV.
- **Bỏ qua** các dòng có `status = "đã tạo"` khi nạp (chạy lại không tạo trùng).
- Tự ghi `status = "đã tạo"` khi:
  - Đăng ký **thành công**.
  - Phát hiện tài khoản **đã tồn tại** (chỉ ghi khi cột status đang trống).
- Tài khoản **đã tồn tại** (exists) được **chuyển sang file riêng `tai_khoan_da_co.csv`**
  (cùng thư mục file dữ liệu) và **xoá khỏi file chính** → lần chạy sau không xử lý lại.
- Ghi PIN cấu hình vào cột `pin` (qua nút hoặc khi bắt đầu chạy).

### 1.3. Automation (chuỗi quy trình)
- Tạo profile GPM kèm proxy.
- **Xếp lưới cửa sổ**: tính theo **số luồng chạy đồng thời** (không phải tổng tài khoản),
  mỗi luồng giữ 1 "ô" (pool) và trả lại khi xong; kích thước tự thu nhỏ theo ô + canh giữa,
  trừ taskbar → các cửa sổ **cách đều, không đè lên nhau**.
- Mở browser, kết nối Playwright qua CDP.
- Điền form đăng ký: `account`, `password`, `confirm_password`, `real_name`.
- Bấm **Đăng ký** (`#insideRegisterSubmitClick`) — có nhiều phương án click dự phòng.
- Chờ kết quả:
  - **`Đăng ký Thành công!`** → `success`.
  - **`Tên tài khoản đã tồn tại`** → `exists` (dừng, ghi log/status).
  - Không thấy popup → `failed` (retry theo cài đặt).
- Nhánh **success** chạy tiếp:
  1. Truy cập `/home/mine`.
  2. Bấm menu **Quản Lý Rút Tiền**.
  3. Nhập **PIN 2 ô** bằng **bàn phím số ảo** (bấm liên tiếp `PIN+PIN`, có fallback mở lại bàn phím) → bấm **Xác Nhận**.
  4. Truy cập `/home/withdraw`.
  5. Bấm **Thêm Vào** (`#addAccountClick`).
  6. Dialog nhập lại **mật khẩu rút tiền** (bàn phím ảo) → **Tiếp Theo**.
  7. **Điền số tài khoản ngân hàng** (giá trị cột `stk`) vào ô `input[placeholder="Vui lòng nhập số tài khoản ngân hàng"]`.
  8. **Chọn ngân hàng**: ô search `input[placeholder="Chọn ngân hàng phát hành"]` → chọn option trong `div.ui-options__option` (theo CSV hoặc ngẫu nhiên).
  9. Bấm **"Xác Nhận"** (`#bindWithdrawAccountNextClick`) để lưu tài khoản ngân hàng.
- Đóng browser, tuỳ chọn xoá profile (hard).

### 1.4. Hạ tầng
- `Dispatcher`: ThreadPoolExecutor, retry (thu thập đúng kết quả retry), tạm dừng/tiếp tục thật, callback tiến độ.
- `SingleTester` (dành cho dev): chạy thử 1 profile / quét trang — **đã gỡ khỏi giao diện**, chỉ giữ module để phát triển.
- `Reporter`: xuất Excel success/failed.
- Selectors **cố định trong `core/automation.py`** (không còn file `config/selectors.json`).

---

## 2. CHƯA LÀM / CẦN PHÁT TRIỂN 🚧

### 2.1. Bước rút tiền (đang dở — ưu tiên tiếp theo)
- [x] ~~Chọn ngân hàng phát hành~~ — **đã làm** (`input[placeholder="Chọn ngân hàng phát hành"]`).
- [x] ~~Bấm nút "Xác Nhận"~~ — **đã làm** (`#bindWithdrawAccountNextClick`).
- [ ] **Nhập số tiền rút** và bấm **"Xác nhận rút tiền"** (`_apply-withdraw-form-btn_16eet_184`, đang disabled) — chưa làm.

> Form ngân hàng hiện đã hoàn tất: số tài khoản + chọn ngân hàng + Xác Nhận.

### 2.2. Khác
- [ ] Kiểm tra proxy **kết nối thật** (hiện chỉ kiểm tra định dạng chuỗi).
- [ ] **Trạng thái chi tiết** cho tài khoản thất bại (hiện ghi lý do ở bảng kết quả, chưa ghi vào CSV).
- [ ] **PIN theo từng tài khoản** (hiện dùng 1 PIN chung nhập ở GUI cho tất cả).
- [ ] **Retry cho các bước sau đăng ký** (PIN, ngân hàng) — hiện chỉ retry bước đăng ký.
- [ ] **Validate `stk`** trước khi chạy (độ dài, chỉ số...).
- [ ] **Đóng gói `.exe`** (PyInstaller).
- [ ] **Log ra file** (hiện chỉ hiện trên UI).
- [ ] Xử lý khi **site đổi selector** (hiện phải sửa code).
- [ ] Cân nhắc cột `pin`: hiện ghi cho tất cả tài khoản chưa tạo (có thể chỉ ghi khi thực sự dùng).

---

## 3. Cấu hình (`config/settings.json`)
| Khoá | Ý nghĩa | Mặc định |
|---|---|---|
| `default_url` | URL đăng ký | `/home/register?dl=5amu0u` |
| `success_url` | URL sau đăng ký thành công | `/home/mine?dl=5amu0u` |
| `withdraw_url` | URL trang rút tiền | `/home/withdraw?dl=5amu0u&active=10` |
| `withdraw_pin` | PIN rút tiền (6 số) | `201198` |
| `threads` | Số luồng | `5` |
| `run_count` | Số tài khoản chạy | `all` |
| `bank_random` | `true` = bank ngẫu nhiên, `false` = theo CSV | `false` |
| `window_width/height` | Kích thước cửa sổ tối đa (tự thu nhỏ theo lưới) | `900 / 1200` |
| `grid_mode` | Bố cục lưới | `Tự động` |
| `delete_profile_after` | Xoá profile sau khi chạy | `false` |

---

## 4. Ghi chú kỹ thuật quan trọng
- **Success** được xác định **chỉ** khi thấy popup `Đăng ký Thành công!`.
- Ô PIN rút tiền **không nhận bàn phím vật lý** → bắt buộc bấm **bàn phím số ảo**;
  bấm **liên tiếp** `PIN+PIN` để ô 1 rồi ô 2; nhịp bấm ~120ms để bàn phím không tự ẩn.
- Nút **Đăng ký** phải nhắm `#insideRegisterSubmitClick` (không bấm vào `<span>` con).
- Mọi thao tác cập nhật UI từ luồng nền đi qua `_ui_queue`.

---

*Ghi chú: file `danh_sach_tai_khoan_1000.csv` hiện đã có cột `pin` và `status`.*
