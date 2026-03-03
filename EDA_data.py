import pandas as pd


if __name__ == "__main__":
    df = pd.read_csv("data_2_3_2026.csv")
    
    count = df.content.astype(str).str.contains("Không thể trích xuất nội dung", na=False).sum()

    print(count)