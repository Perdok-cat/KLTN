# 🚀 Hướng dẫn nhanh

## Bước 1: Cài đặt thư viện
```bash
pip install pandas google-generativeai
```

## Bước 2: Cấu hình API Key

### Lấy API Key
1. Truy cập: https://makersuite.google.com/app/apikey
2. Đăng nhập Google
3. Click "Create API Key"
4. Copy API key

### Đặt API Key (Windows PowerShell)
```powershell
$env:GEMINI_API_KEY="paste_your_api_key_here"
```

### Đặt API Key (Windows CMD)
```cmd
set GEMINI_API_KEY=paste_your_api_key_here
```

## Bước 3: Test kết nối
```bash
python test_gemini_connection.py
```

Nếu thấy "✅ KẾT NỐI THÀNH CÔNG!" thì bạn đã sẵn sàng!

## Bước 4: Chạy gán nhãn
```bash
python Gemini_label.py
```

Chương trình sẽ:
- Tự động đọc file `Data/du_lieu_ai_day_du.csv`
- Gán nhãn cho từng bài viết
- Lưu kết quả vào `Data/du_lieu_ai_gan_nhan.csv`
- Hiển thị tiến độ real-time

## Bước 5: Phân tích kết quả
```bash
python analyze_results.py
```

## Các nhãn được gán

| Nhãn | Mô tả |
|------|-------|
| **MARKET SIGNALS** | Tin chiến lược, Big Tech, sáp nhập, chính sách |
| **SOLUTIONS & USE CASES** | Case study, công cụ AI, ứng dụng thực tế |
| **DEEP DIVE** | Kỹ thuật sâu, benchmark, research papers |
| **NOISE** | Quảng cáo, spam, nội dung không liên quan |

## Ước tính thời gian

- ~500 bài viết: **20-25 phút**
- ~1000 bài viết: **40-50 phút**

## Xử lý lỗi thường gặp

### Lỗi: "API key not configured"
```powershell
# Set lại API key
$env:GEMINI_API_KEY="your_key_here"
```

### Lỗi: "Rate limit exceeded"
- Đợi 1 phút rồi chạy lại
- Hoặc sửa `time.sleep(1)` thành `time.sleep(2)` trong code

### Lỗi: "File not found"
```bash
# Kiểm tra cấu trúc thư mục
cd Labeling_Tools
ls ../Data/du_lieu_ai_day_du.csv
```

## Tips

1. **Checkpoint tự động**: Chương trình tự động lưu sau mỗi 5 bài viết
2. **Resume**: Nếu bị dừng giữa chừng, chạy lại sẽ tiếp tục từ chỗ dừng
3. **Review**: Sau khi xong, nên xem qua các bài có confidence "low"

## Cấu trúc thư mục

```
Labeling_Tools/
├── Gemini_label.py          # Script chính
├── test_gemini_connection.py # Test API
├── analyze_results.py        # Phân tích kết quả
├── requirements.txt          # Thư viện
├── README.md                 # Hướng dẫn chi tiết
└── QUICKSTART.md            # File này

Data/
├── du_lieu_ai_day_du.csv           # Input (file gốc)
└── du_lieu_ai_gan_nhan.csv         # Output (có nhãn)
```

## Hỗ trợ

Nếu gặp vấn đề, xem hướng dẫn chi tiết trong `README.md`
