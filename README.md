# RegAcc - Hệ thống tự động hóa đăng ký đa luồng

Ứng dụng desktop tự động hóa quy trình đăng ký tài khoản hàng loạt sử dụng **GPM Login** làm trình duyệt antidetect.

## Tính năng chính

- **Đa luồng**: Chạy nhiều profile cùng lúc với ThreadPoolExecutor
- **GPM Login Integration**: Tích hợp API local (`http://localhost:9495`) để quản lý profiles
- **Window Grid Layout**: Tự động sắp xếp cửa sổ browser dạng lưới trên màn hình
- **Proxy Management**: Hỗ trợ HTTP/SOCKS5 proxy (có/không authentication)
- **Human-like Interaction**: Mô phỏng hành vi người dùng (typing delay, random pause)
- **Xóa Profile sau quy trình**: Tùy chọn tự động xóa profile để tiết kiệm bộ nhớ
- **Xác nhận thành công**: Chờ popup `Đăng ký Thành công!` xuất hiện rồi tự động
  chuyển sang trang `/home/mine`
- **Export Results**: Xuất kết quả ra Excel (success/failed)

## Cài đặt

### Yêu cầu

- Python 3.10+
- [GPM Login](https://gpmloginapp.com/) đã cài đặt và đang chạy

### Setup

```bash
# Clone repo
git clone https://github.com/vzetiZero/RegAccBank.git
cd RegAccBank

# Tạo virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Cài dependencies
pip install -r requirements.txt

# Chạy ứng dụng
python main.py
```

## Cấu trúc dự án

```
RegAcc/
├── main.py                 # Entry point
├── requirements.txt        # Dependencies
├── README.md               # File này
├── PLAN.md                 # Kế hoạch chi tiết
├── config/
│   └── settings.json       # Cấu hình (URL, cửa sổ, dọn dẹp)
├── core/
│   ├── gpm_manager.py      # GPM Login API client
│   ├── grid.py             # Grid calculator
│   ├── dispatcher.py       # ThreadPoolExecutor dispatcher
│   ├── human.py            # Human-like delays
│   └── reporter.py         # Export results
├── ui/
│   └── dashboard.py        # GUI chính
├── data/                   # Dữ liệu tài khoản, proxy
├── results/                # Kết quả export
└── profiles/               # GPM Login profiles (auto)
```

## Chạy thử 1 profile (giữ browser mở)

Trong tab **Bảng điều khiển** → thẻ **CHẠY THỬ 1 PROFILE**:

1. **Mở test 1 profile** — tạo 1 profile, mở browser, điền form đăng ký, bấm
   *Đăng ký*, đóng popup quảng cáo. Browser được **giữ mở**.
2. **Quét trang (bắt xpath)** — kết nối lại CDP và quét trang hiện tại: liệt kê
   popup/overlay, nút bấm, nút close, iframe → giúp bắt xpath cho bước tiếp theo.
3. **Đóng browser test** — đóng browser và xoá profile test (mode=hard).

### Ánh xạ dữ liệu CSV → form

| Cột CSV | Trường trong app | Selector form (cố định trong code) |
|---|---|---|
| `taikhoan` | `account` | `input[data-input-name='account']` |
| `matkhau` | `password` | `input[data-input-name='userpass']` + `confirmPassword` |
| `Tên tài khoản` | `name` | `input[data-input-name='realName']` |
| `stk` | (dành cho bước sau) | — |

> Selectors được cố định trong `core/automation.py` (`DEFAULT_SELECTORS`), không còn file cấu hình riêng.

## Hướng dẫn sử dụng

1. **Khởi động GPM Login** và đảm bảo API đang chạy tại `http://localhost:9495`
2. **Chạy ứng dụng**: `python main.py`
3. **Màn "Chạy quy trình"**:
   - Nhập URL đích (mặc định: `https://d3kwdbhwc3ma6l.cloudfront.net/home/register?dl=5amu0u`)
   - Load file dữ liệu tài khoản (CSV/Excel)
   - Nhập danh sách proxy
   - Chọn số luồng và bố cục lưới
   - Nhấn "BẮT ĐẦU"
4. **Màn "Cài đặt"**:
   - Đặt URL sau khi đăng ký thành công, số lần retry, kích thước cửa sổ
   - **Tick "Xóa profile sau quy trình"** để tự động xóa profile sau khi hoàn thành

## API Endpoints (GPM Login)

| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/api/v3/profiles` | Liệt kê profiles |
| `POST` | `/api/v3/profiles/create` | Tạo profile mới |
| `GET` | `/api/v3/profiles/{id}` | Chi tiết profile |
| `PUT` | `/api/v3/profiles/{id}` | Cập nhật profile |
| `DELETE` | `/api/v3/profiles/{id}` | **Xóa profile** |
| `POST` | `/api/v3/profiles/start` | Khởi động browser |
| `POST` | `/api/v3/browser/{id}/stop` | Dừng browser |

## Lưu ý

- Đảm bảo tuân thủ ToS của trang web đích
- Sử dụng proxy chất lượng để tránh bị chặn
- Giới hạn số luồng để tránh nhận diện bởi hệ thống anti-bot

## License

MIT
