"""
RegAcc - Hệ thống tự động hóa đăng ký đa luồng
Sử dụng GPM Login làm trình duyệt antidetect
"""

import sys
from pathlib import Path

# Thêm project root vào path
sys.path.insert(0, str(Path(__file__).parent))

from ui.dashboard import Dashboard


def main():
    app = Dashboard()
    app.mainloop()


if __name__ == "__main__":
    main()
