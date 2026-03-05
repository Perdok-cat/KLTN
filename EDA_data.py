import pandas as pd

# Đọc file CSV
df = pd.read_csv("data.csv")

# Hiển thị số lượng bản ghi trước khi xóa
print(f"Số bản ghi trước khi xóa: {len(df)}")

# Đếm số hàng có content null
count_null = df['content'].isnull().sum()
print(f"Số hàng có content null: {count_null}")

# Xóa các hàng có content null
df_cleaned = df[df['content'].notna()]
# Hoặc dùng: df_cleaned = df.dropna(subset=['content'])

# Reset index sau khi xóa
df_cleaned = df_cleaned.reset_index(drop=True)

# Thêm cột label trống ở cuối
df_cleaned['label'] = ""

# Hiển thị số lượng sau khi xóa
print(f"Số bản ghi sau khi xóa: {len(df_cleaned)}")

# Lưu file mới
df_cleaned.to_csv("data_clean.csv", index=False, encoding='utf-8-sig')
print("✓ Đã lưu vào file: du_lieu_ai_day_du_cleaned.csv")