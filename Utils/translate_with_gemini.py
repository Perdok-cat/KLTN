import pandas as pd
import google.generativeai as genai
import time
import os
from tqdm import tqdm

# Cấu hình Gemini API
GOOGLE_API_KEY = ""
if not GOOGLE_API_KEY:
    raise ValueError("Vui lòng set biến môi trường GOOGLE_API_KEY")

genai.configure(api_key=GOOGLE_API_KEY)

# Khởi tạo model Gemini Flash 2.5
model = genai.GenerativeModel('gemini-2.5-flash')

def translate_to_vietnamese(text, max_retries=3):
    """
    Dịch text sang tiếng Việt sử dụng Gemini Flash 2.5
    """
    if pd.isna(text) or text.strip() == "":
        return ""
    
    # Giới hạn độ dài text để tránh vượt quá token limit
    if len(text) > 10000:
        text = text[:10000] + "..."
    
    prompt = f"""Dịch đoạn văn bản sau sang tiếng Việt. Giữ nguyên các thuật ngữ kỹ thuật về AI/ML và tên riêng.
Chỉ trả về bản dịch, không thêm giải thích:

{text}"""
    
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            print(f"  Lỗi khi dịch (lần thử {attempt + 1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                return f"[LỖI DỊCH] {str(e)}"
    
    return "[LỖI DỊCH]"

def main():
    # Đọc file CSV
    input_file = "Data/data_deep_dive_2026_03_07_full_cleaned.csv"
    output_file = "Data/data_deep_dive_2026_03_07_full_vietnamese.csv"
    checkpoint_file = "Data/translation_checkpoint.csv"
    
    print(f"Đang đọc file: {input_file}")
    df = pd.read_csv(input_file)
    
    print(f"Tổng số bản ghi: {len(df)}")
    
    # Kiểm tra xem có checkpoint không
    start_idx = 0
    if os.path.exists(checkpoint_file):
        print(f"Tìm thấy checkpoint, tiếp tục từ nơi đã dừng...")
        df_checkpoint = pd.read_csv(checkpoint_file)
        df = df_checkpoint
        # Tìm hàng đầu tiên chưa dịch
        for idx in range(len(df)):
            if 'Title_VN' not in df.columns or pd.isna(df.at[idx, 'Title_VN']) or df.at[idx, 'Title_VN'] == "":
                start_idx = idx
                break
        print(f"Bắt đầu từ bản ghi {start_idx + 1}")
    else:
        # Thêm các cột tiếng Việt
        df['Title_VN'] = ""
        df['content_VN'] = ""
    
    # Dịch từng bản ghi
    print("\nBắt đầu dịch...")
    for idx in tqdm(range(start_idx, len(df)), desc="Dịch bài viết"):
        row = df.iloc[idx]
        
        print(f"\n[{idx + 1}/{len(df)}] Đang dịch: {row['Title'][:60]}...")
        
        # Dịch Title
        if pd.isna(df.at[idx, 'Title_VN']) or df.at[idx, 'Title_VN'] == "":
            print("  - Dịch Title...")
            title_vn = translate_to_vietnamese(row['Title'])
            df.at[idx, 'Title_VN'] = title_vn
            print(f"time to sleeep 10s") 
            time.sleep(10)
             # Tránh rate limit
        
        # Dịch Content
        if pd.isna(df.at[idx, 'content_VN']) or df.at[idx, 'content_VN'] == "":
            print("  - Dịch Content...")
            content_vn = translate_to_vietnamese(row['content'])
            df.at[idx, 'content_VN'] = content_vn
            time.sleep(1)  # Tránh rate limit
        
        # LƯU NGAY SAU KHI DỊCH XONG MỖI BÀI
        df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"  ✓ Đã lưu bài {idx + 1} vào {output_file}")
        
        # Lưu backup mỗi 10 bài
        if (idx + 1) % 10 == 0:
            df.to_csv(checkpoint_file, index=False, encoding='utf-8-sig')
            print(f"  ✓ Đã lưu backup tại bài {idx + 1}")
    
    # Lưu kết quả cuối cùng
    df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n✓ Hoàn thành! Đã lưu vào file: {output_file}")
    
    # Xóa checkpoint
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)
        print("✓ Đã xóa checkpoint file")
    
    # Thống kê
    success_count = len(df[~df['Title_VN'].str.contains('[LỖI DỊCH]', na=False)])
    print(f"\nThống kê:")
    print(f"- Tổng số bài: {len(df)}")
    print(f"- Dịch thành công: {success_count}/{len(df)} bài")

if __name__ == "__main__":
    main()
