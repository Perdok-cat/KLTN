import pandas as pd
import google.generativeai as genai
import os
import time
from typing import Dict, List
import json

# Cấu hình Gemini API
# Lấy API key từ biến môi trường hoặc thay trực tiếp
API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_API_KEY_HERE")
genai.configure(api_key=API_KEY)

# Khởi tạo model
model = genai.GenerativeModel('gemini-1.5-flash')

# Định nghĩa các nhãn và tiêu chí
LABELS = {
    "MARKET SIGNALS": {
        "description": "Tầm nhìn & Chiến lược - Trả lời câu hỏi 'Thế giới AI đang thay đổi thế nào và nó ảnh hưởng gì đến túi tiền của tôi?'",
        "criteria": [
            "Big Tech ra model mới",
            "Sáp nhập/đầu tư lớn",
            "Thay đổi chính sách/luật pháp AI toàn cầu",
            "Breaking News quan trọng về AI",
            "Chiến lược doanh nghiệp lớn",
            "Định giá công ty, vòng gọi vốn lớn"
        ]
    },
    "SOLUTIONS & USE CASES": {
        "description": "Thực thi & Ứng dụng - Trả lời câu hỏi 'Tôi có thể dùng cái này để tiết kiệm tiền hoặc tăng năng suất ở đâu?'",
        "criteria": [
            "Case study thực tế",
            "Hướng dẫn triển khai AI trong ngành cụ thể",
            "Công cụ AI vừa ra mắt",
            "Ứng dụng AI cho Tài chính, Marketing, HR",
            "Giải pháp tiết kiệm chi phí",
            "Tăng năng suất thực tế"
        ]
    },
    "DEEP DIVE": {
        "description": "Bối cảnh & Kỹ thuật - Dành cho đội ngũ R&D hoặc chuyên gia muốn hiểu sâu",
        "criteria": [
            "Giải thích kiến trúc model",
            "Benchmark và đánh giá kỹ thuật",
            "Bài báo nghiên cứu (Research Papers)",
            "Cập nhật thư viện mã nguồn",
            "Chi tiết kỹ thuật sâu",
            "Tin nhỏ về công nghệ"
        ]
    },
    "NOISE": {
        "description": "Loại bỏ - Nội dung rác, quảng cáo, tin tuyển dụng",
        "criteria": [
            "Quảng cáo",
            "Tin tuyển dụng",
            "Listicles sáo rỗng",
            "Nội dung không liên quan AI",
            "Spam hoặc nội dung chất lượng thấp"
        ]
    }
}

def create_labeling_prompt(title: str, content: str) -> str:
    """Tạo prompt cho Gemini để gán nhãn"""
    
    prompt = f"""Bạn là một chuyên gia phân loại nội dung AI. Nhiệm vụ của bạn là phân tích bài viết và gán một trong 4 nhãn sau:

1. MARKET SIGNALS (Tầm nhìn & Chiến lược)
   - Big Tech ra model mới, sáp nhập/đầu tư lớn
   - Thay đổi chính sách/luật pháp AI toàn cầu
   - Breaking News quan trọng về AI
   - Mục tiêu: Trả lời "Thế giới AI đang thay đổi thế nào?"

2. SOLUTIONS & USE CASES (Thực thi & Ứng dụng)
   - Case study thực tế, hướng dẫn triển khai AI
   - Công cụ AI mới ra mắt
   - Ứng dụng AI trong ngành cụ thể (Tài chính, Marketing, HR...)
   - Mục tiêu: Trả lời "Tôi có thể dùng cái này để tiết kiệm tiền/tăng năng suất?"

3. DEEP DIVE (Bối cảnh & Kỹ thuật)
   - Giải thích kiến trúc model, Benchmark
   - Bài báo nghiên cứu (Research Papers)
   - Cập nhật thư viện mã nguồn
   - Chi tiết kỹ thuật sâu

4. NOISE (Loại bỏ)
   - Quảng cáo, tin tuyển dụng
   - Listicles sáo rỗng
   - Nội dung không liên quan AI hoặc chất lượng thấp

---
TIÊU ĐỀ: {title}

NỘI DUNG:
{content[:3000]}  # Giới hạn 3000 ký tự để tiết kiệm token

---
Hãy phân tích và trả về ĐÚNG MỘT trong các nhãn sau: MARKET SIGNALS, SOLUTIONS & USE CASES, DEEP DIVE, NOISE

Định dạng trả về JSON:
{{
    "label": "TÊN_NHÃN",
    "confidence": "high/medium/low",
    "reasoning": "Lý do ngắn gọn (1-2 câu)"
}}
"""
    return prompt

def label_with_gemini(title: str, content: str, max_retries: int = 3) -> Dict:
    """Gọi Gemini API để gán nhãn với retry logic"""
    
    if not content or len(content.strip()) < 50:
        return {
            "label": "NOISE",
            "confidence": "high",
            "reasoning": "Nội dung quá ngắn hoặc rỗng"
        }
    
    prompt = create_labeling_prompt(title, content)
    
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            
            # Parse JSON response
            response_text = response.text.strip()
            
            # Loại bỏ markdown code block nếu có
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            
            result = json.loads(response_text.strip())
            
            # Validate label
            if result.get("label") not in LABELS:
                # Fallback: tìm label trong text
                for label in LABELS:
                    if label in response_text:
                        result["label"] = label
                        break
                else:
                    result["label"] = "NOISE"
            
            return result
            
        except json.JSONDecodeError:
            # Nếu không parse được JSON, thử extract label từ text
            try:
                response_text = response.text
                for label in LABELS:
                    if label in response_text:
                        return {
                            "label": label,
                            "confidence": "medium",
                            "reasoning": "Extracted from non-JSON response"
                        }
            except:
                pass
                
        except Exception as e:
            print(f"Lỗi khi gọi Gemini API (lần {attempt + 1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                return {
                    "label": "NOISE",
                    "confidence": "low",
                    "reasoning": f"API Error: {str(e)}"
                }
    
    return {
        "label": "NOISE",
        "confidence": "low",
        "reasoning": "Failed after retries"
    }

def process_csv(input_file: str, output_file: str, start_idx: int = 0, batch_size: int = 10):
    """Xử lý file CSV và gán nhãn"""
    
    print(f"Đang đọc file: {input_file}")
    df = pd.read_csv(input_file)
    
    print(f"Tổng số bài viết: {len(df)}")
    print(f"Bắt đầu từ index: {start_idx}")
    
    # Đảm bảo có cột label và các cột metadata
    if 'label' not in df.columns:
        df['label'] = ''
    if 'confidence' not in df.columns:
        df['confidence'] = ''
    if 'reasoning' not in df.columns:
        df['reasoning'] = ''
    
    total_processed = 0
    label_counts = {label: 0 for label in LABELS}
    
    # Xử lý từng batch
    for i in range(start_idx, len(df), batch_size):
        batch_end = min(i + batch_size, len(df))
        print(f"\n{'='*60}")
        print(f"Xử lý batch {i}-{batch_end} / {len(df)}")
        print(f"{'='*60}")
        
        for idx in range(i, batch_end):
            row = df.iloc[idx]
            
            # Skip nếu đã có label
            if pd.notna(row['label']) and row['label'].strip():
                print(f"[{idx+1}] Đã có label: {row['title'][:50]}... -> {row['label']}")
                label_counts[row['label']] += 1
                total_processed += 1
                continue
            
            title = row['title']
            content = row.get('content', '')
            
            print(f"\n[{idx+1}] Đang xử lý: {title[:70]}...")
            
            # Gọi Gemini để gán nhãn
            result = label_with_gemini(title, content)
            
            # Cập nhật DataFrame
            df.at[idx, 'label'] = result['label']
            df.at[idx, 'confidence'] = result.get('confidence', '')
            df.at[idx, 'reasoning'] = result.get('reasoning', '')
            
            label_counts[result['label']] += 1
            total_processed += 1
            
            print(f"    ✓ Nhãn: {result['label']}")
            print(f"    ✓ Độ tin cậy: {result.get('confidence', 'N/A')}")
            print(f"    ✓ Lý do: {result.get('reasoning', 'N/A')[:100]}")
            
            # Lưu checkpoint sau mỗi batch
            if (idx + 1) % batch_size == 0 or idx == len(df) - 1:
                df.to_csv(output_file, index=False, encoding='utf-8-sig')
                print(f"\n💾 Đã lưu checkpoint tại index {idx+1}")
                
                # Hiển thị thống kê
                print(f"\n📊 Thống kê hiện tại:")
                print(f"   Tổng đã xử lý: {total_processed}/{len(df)}")
                for label, count in label_counts.items():
                    percentage = (count / total_processed * 100) if total_processed > 0 else 0
                    print(f"   {label}: {count} ({percentage:.1f}%)")
            
            # Rate limiting
            time.sleep(1)  # Tránh hit rate limit của Gemini API
    
    print(f"\n{'='*60}")
    print("✅ HOÀN THÀNH!")
    print(f"{'='*60}")
    print(f"\n📊 Kết quả cuối cùng:")
    print(f"   Tổng số bài viết: {len(df)}")
    for label, count in label_counts.items():
        percentage = (count / len(df) * 100) if len(df) > 0 else 0
        print(f"   {label}: {count} ({percentage:.1f}%)")
    
    # Lưu file cuối cùng
    df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n💾 Đã lưu file kết quả: {output_file}")
    
    return df

def display_statistics(df: pd.DataFrame):
    """Hiển thị thống kê chi tiết"""
    print("\n" + "="*60)
    print("📈 THỐNG KÊ CHI TIẾT")
    print("="*60)
    
    if 'label' not in df.columns:
        print("Chưa có dữ liệu label")
        return
    
    label_stats = df['label'].value_counts()
    
    for label in LABELS:
        count = label_stats.get(label, 0)
        percentage = (count / len(df) * 100) if len(df) > 0 else 0
        print(f"\n{label}:")
        print(f"  Số lượng: {count}")
        print(f"  Tỷ lệ: {percentage:.1f}%")
        print(f"  Mô tả: {LABELS[label]['description']}")
    
    # Thống kê confidence
    if 'confidence' in df.columns:
        print(f"\n📊 Độ tin cậy:")
        confidence_stats = df['confidence'].value_counts()
        for conf, count in confidence_stats.items():
            print(f"  {conf}: {count} ({count/len(df)*100:.1f}%)")

def main():
    """Hàm main"""
    print("="*60)
    print("🏷️  CÔNG CỤ GÁN NHÃN TỰ ĐỘNG VỚI GEMINI AI")
    print("="*60)
    
    # Đường dẫn file
    input_file = "Data/du_lieu_ai_day_du.csv"
    output_file = "Data/du_lieu_ai_gan_nhan.csv"
    
    # Kiểm tra API key
    if API_KEY == "YOUR_API_KEY_HERE":
        print("\n⚠️  CẢNH BÁO: Bạn chưa cấu hình GEMINI_API_KEY!")
        print("Vui lòng:")
        print("1. Lấy API key từ: https://makersuite.google.com/app/apikey")
        print("2. Đặt biến môi trường: set GEMINI_API_KEY=your_key_here")
        print("3. Hoặc sửa trực tiếp trong code: API_KEY = 'your_key_here'")
        return
    
    print(f"\n📂 File đầu vào: {input_file}")
    print(f"📂 File đầu ra: {output_file}")
    
    # Xử lý
    df = process_csv(
        input_file=input_file,
        output_file=output_file,
        start_idx=0,  # Bắt đầu từ đầu
        batch_size=5   # Xử lý 5 bài viết rồi lưu checkpoint
    )
    
    # Hiển thị thống kê
    display_statistics(df)
    
    print("\n✅ Hoàn thành! Kiểm tra file:", output_file)

if __name__ == "__main__":
    main()
