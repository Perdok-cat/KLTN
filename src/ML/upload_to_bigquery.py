"""
Script đẩy dữ liệu training lên bảng BigQuery đã có sẵn.

Cách dùng:
  export GOOGLE_CLOUD_PROJECT=<your-project-id>
  python src/ML/upload_to_bigquery.py
  
  Hoặc:
  python src/ML/upload_to_bigquery.py --project <your-project-id>
"""

import argparse
import logging
import os
import sys

import pandas as pd
from sklearn.model_selection import train_test_split

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload data to existing BigQuery table")
    parser.add_argument(
        "--data-path",
        default=os.getenv("DATA_PATH", "Data/PROCESSED_DATA.csv"),
        help="Đường dẫn tới file CSV dữ liệu",
    )
    parser.add_argument(
        "--project",
        default=os.getenv("GOOGLE_CLOUD_PROJECT", ""),
        help="Google Cloud Project ID",
    )
    # Vẫn giữ default để bạn không cần gõ lại nếu đã setup đúng tên này trên GCP
    parser.add_argument(
        "--dataset",
        default=os.getenv("BQ_DATASET", "mlops_dataset"),
        help="BigQuery Dataset ID đã có sẵn",
    )
    parser.add_argument(
        "--table",
        default=os.getenv("BQ_TABLE", "training_data"),
        help="BigQuery Table ID đã có sẵn",
    )
    parser.add_argument(
        "--write-mode",
        choices=["WRITE_TRUNCATE", "WRITE_APPEND", "WRITE_EMPTY"],
        default="WRITE_APPEND", # Thường bảng có sẵn thì sẽ muốn APPEND thêm dữ liệu mới
        help="Chế độ ghi vào BigQuery",
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=0.2,
    )
    return parser.parse_args()


def load_and_prepare(data_path: str, test_size: float) -> pd.DataFrame:
    """Đọc CSV và chuẩn bị các cột khớp với bảng BigQuery."""
    logger.info(f"Đọc dữ liệu từ: {data_path}")
    df = pd.read_csv(data_path)

    # Đảm bảo xử lý null/type để tránh lỗi schema mismatch với bảng có sẵn
    df["text_tok"] = df["text_tok"].fillna("").astype(str)
    df["label"] = df["label"].astype(str)
    df["label_enc"] = df["label_enc"].astype(int)

    train_idx, test_idx = train_test_split(
        df.index,
        test_size=test_size,
        random_state=42,
        stratify=df["label_enc"],
    )
    df["split"] = "train"
    df.loc[test_idx, "split"] = "test"

    df["created_at"] = pd.Timestamp.now(tz='UTC')
    return df


def upload_to_bigquery(
    df: pd.DataFrame,
    project: str,
    dataset_id: str,
    table_id: str,
    write_mode: str,
):
    """Đẩy DataFrame lên bảng BigQuery đã tồn tại."""
    from google.cloud import bigquery

    # Chỉ khởi tạo client bằng project ID
    client = bigquery.Client(project=project)
    table_ref = f"{project}.{dataset_id}.{table_id}"

    # Cấu hình siêu tối giản: Chỉ định write_mode. BQ sẽ tự động map cột với bảng có sẵn.
    job_config = bigquery.LoadJobConfig(
        write_disposition=write_mode,
    )

    logger.info(f"Bắt đầu đẩy dữ liệu lên bảng: {table_ref} (mode={write_mode})")
    
    # Thực hiện đẩy dữ liệu
    load_job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    load_job.result()  # Chờ đến khi hoàn tất

    # Kiểm tra lại thông tin sau khi upload
    table = client.get_table(table_ref)
    logger.info("Upload thành công!")
    logger.info(f"  Tổng số hàng hiện tại trong bảng: {table.num_rows:,}")


def main():
    args = parse_args()

    if not args.project:
        logger.error("Vui lòng cung cấp Project ID qua biến môi trường hoặc tham số --project")
        sys.exit(1)

    logger.info(f"Chuẩn bị upload vào: {args.project}.{args.dataset}.{args.table}")
    
    df = load_and_prepare(args.data_path, args.test_size)

    upload_to_bigquery(
        df=df,
        project=args.project,
        dataset_id=args.dataset,
        table_id=args.table,
        write_mode=args.write_mode,
    )


if __name__ == "__main__":
    main()