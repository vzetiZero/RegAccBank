"""
Reporter - Xuất báo cáo kết quả
"""

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def export_results(results: list[dict], output_dir: str = "results/") -> tuple[str, str]:
    """
    Xuất file success_accounts.xlsx và failed_accounts.xlsx.
    
    Args:
        results: Danh sách kết quả từ Dispatcher
        output_dir: Thư mục xuất file
    
    Returns:
        tuple[str, str]: (success_file_path, failed_file_path)
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    df = pd.DataFrame(results)
    
    if "account" in df.columns:
        df["email"] = df["account"].apply(lambda x: x.get("email", "") if isinstance(x, dict) else "")
        df["name"] = df["account"].apply(lambda x: x.get("name", "") if isinstance(x, dict) else "")
    
    success_df = df[df["status"] == "success"]
    failed_df = df[df["status"] != "success"]
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    success_path = f"{output_dir}/success_{timestamp}.xlsx"
    failed_path = f"{output_dir}/failed_{timestamp}.xlsx"
    
    if not success_df.empty:
        success_df.to_excel(success_path, index=False)
        logger.info(f"Đã xuất {len(success_df)} kết quả thành công: {success_path}")
    
    if not failed_df.empty:
        failed_df.to_excel(failed_path, index=False)
        logger.info(f"Đã xuất {len(failed_df)} kết quả thất bại: {failed_path}")
    
    return success_path, failed_path
