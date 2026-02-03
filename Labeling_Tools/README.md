# Công cụ Gán nhãn Tự động với Gemini AI

## Mục đích
Công cụ này sử dụng Google Gemini AI để tự động gán nhãn cho dữ liệu đã crawl từ file `du_lieu_ai_day_du.csv`.

## Các nhãn được sử dụng

### 1. MARKET SIGNALS (Tầm nhìn & Chiến lược)
- **Mục tiêu**: Trả lời câu hỏi "Thế giới AI đang thay đổi thế nào và nó ảnh hưởng gì đến túi tiền của tôi?"
- **Nội dung**: 
  - Big Tech ra model mới
  - Sáp nhập/đầu tư lớn
  - Thay đổi chính sách/luật pháp AI toàn cầu
  - Breaking News quan trọng

### 2. SOLUTIONS & USE CASES (Thực thi & Ứng dụng)
- **Mục tiêu**: Trả lời câu hỏi "Tôi có thể dùng cái này để tiết kiệm tiền hoặc tăng năng suất ở đâu?"
- **Nội dung**:
  - Case study thực tế
  - Hướng dẫn triển khai AI trong ngành cụ thể
  - Công cụ AI vừa ra mắt
  - Ứng dụng AI cho Tài chính, Marketing, HR...

### 3. DEEP DIVE (Bối cảnh & Kỹ thuật)
- **Mục tiêu**: Dành cho đội ngũ R&D hoặc chuyên gia muốn hiểu sâu
- **Nội dung**:
  - Giải thích kiến trúc model
  - Benchmark và đánh giá kỹ thuật
  - Bài báo nghiên cứu (Research Papers)
  - Cập nhật thư viện mã nguồn

### 4. NOISE (Loại bỏ)
- **Mục tiêu**: Loại bỏ nội dung không có giá trị
- **Nội dung**:
  - Quảng cáo
  - Tin tuyển dụng
  - Listicles sáo rỗng
  - Nội dung không liên quan AI

## Cài đặt

### Bước 1: Cài đặt thư viện
```bash
pip install -r requirements.txt
```

### Bước 2: Lấy API Key từ Google
1. Truy cập: https://makersuite.google.com/app/apikey
2. Tạo API key mới (hoặc sử dụng key có sẵn)
3. Copy API key

### Bước 3: Cấu hình API Key
Có 2 cách:

**Cách 1: Sử dụng biến môi trường (Khuyến nghị)**
```bash
# Windows (PowerShell)
$env:GEMINI_API_KEY="your_api_key_here"

# Windows (CMD)
set GEMINI_API_KEY=your_api_key_here

# Linux/Mac
export GEMINI_API_KEY=your_api_key_here
```

**Cách 2: Sửa trực tiếp trong code**
Mở file `Gemini_label.py` và sửa dòng:
```python
API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_API_KEY_HERE")
```
Thành:
```python
API_KEY = os.getenv("GEMINI_API_KEY", "your_actual_api_key_here")
```

## Sử dụng

### Chạy chương trình
```bash
cd Labeling_Tools
python Gemini_label.py
```

### Tính năng chính

1. **Xử lý theo batch**: 
   - Xử lý 5 bài viết rồi tự động lưu checkpoint
   - Tránh mất dữ liệu nếu có lỗi

2. **Resume từ checkpoint**:
   - Nếu chương trình bị dừng, khi chạy lại sẽ tự động bỏ qua các bài đã gán nhãn
   - Tiếp tục từ bài chưa xử lý

3. **Rate limiting**:
   - Tự động sleep 1s giữa các lần gọi API
   - Tránh bị giới hạn bởi Gemini API

4. **Retry logic**:
   - Tự động retry 3 lần nếu API call thất bại
   - Exponential backoff giữa các lần retry

5. **Thống kê real-time**:
   - Hiển thị tiến độ xử lý
   - Thống kê số lượng từng nhãn
   - Độ tin cậy của việc gán nhãn

## File đầu ra

File kết quả: `Data/du_lieu_ai_gan_nhan.csv`

Các cột được thêm vào:
- `label`: Nhãn được gán (MARKET SIGNALS, SOLUTIONS & USE CASES, DEEP DIVE, NOISE)
- `confidence`: Độ tin cậy (high/medium/low)
- `reasoning`: Lý do ngắn gọn tại sao gán nhãn này

## Tùy chỉnh

### Thay đổi batch size
Trong hàm `main()`, sửa tham số `batch_size`:
```python
df = process_csv(
    input_file=input_file,
    output_file=output_file,
    start_idx=0,
    batch_size=10  # Thay đổi số này
)
```

### Bắt đầu từ index cụ thể
Nếu muốn bắt đầu từ bài viết thứ 100:
```python
df = process_csv(
    input_file=input_file,
    output_file=output_file,
    start_idx=100,  # Bắt đầu từ index 100
    batch_size=5
)
```

### Thay đổi model Gemini
Trong code, sửa dòng:
```python
model = genai.GenerativeModel('gemini-1.5-flash')
```
Thành model khác như:
```python
model = genai.GenerativeModel('gemini-1.5-pro')  # Model mạnh hơn nhưng chậm hơn
```

## Xử lý lỗi

### Lỗi: "API key not configured"
- Kiểm tra lại API key
- Đảm bảo đã set biến môi trường hoặc sửa trong code

### Lỗi: "Rate limit exceeded"
- Tăng thời gian sleep giữa các request
- Sửa dòng `time.sleep(1)` thành `time.sleep(2)` hoặc lớn hơn

### Lỗi: "File not found"
- Kiểm tra đường dẫn file input
- Đảm bảo file `du_lieu_ai_day_du.csv` tồn tại trong thư mục `Data/`

## Ước tính thời gian

Với ~500 bài viết:
- Mỗi bài viết mất ~2-3 giây (bao gồm API call + sleep)
- Tổng thời gian: ~20-25 phút

## Chi phí API

Google Gemini API có hạn mức miễn phí:
- Gemini 1.5 Flash: 15 requests/phút, 1 triệu tokens/ngày (miễn phí)
- Nếu vượt quá, cần upgrade lên plan trả phí

## Lưu ý

1. **Backup dữ liệu**: Nên backup file gốc trước khi chạy
2. **Internet**: Cần kết nối internet ổn định
3. **API Key**: Không chia sẻ API key công khai
4. **Review kết quả**: Nên kiểm tra lại một số nhãn được gán để đảm bảo chất lượng

## Liên hệ

Nếu có vấn đề hoặc cần hỗ trợ, vui lòng tạo issue hoặc liên hệ trực tiếp.
