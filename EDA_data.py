import pandas as pd


if __name__ == "__main__":
    df = pd.read_csv("data_2_3_2026.csv")
    
    # count = df.content.astype(str).str.contains("Không thể trích xuất nội dung", na=False).sum()

    # mask = df.content.astype(str).str.contains("Không thể trích xuất nội dung", na=False) 

    # df.drop(df.index[mask], inplace=True)
    # df.reset_index(drop=True, inplace=True) 

    mask_xau = df["content"].astype(str).str.contains("Không thể trích xuất nội dung", na=False)
    mask_null = df["content"].isna()

    df = df[~(mask_xau | mask_null)].reset_index(drop=True)

    print(df.info())