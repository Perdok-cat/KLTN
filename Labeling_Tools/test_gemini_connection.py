"""
Script test kết nối Gemini API
Chạy script này trước để đảm bảo API key hoạt động
"""

import google.generativeai as genai
import os

def test_gemini_api():
    """Test kết nối với Gemini API"""
    
    print("="*60)
    print("🧪 TEST KẾT NỐI GEMINI API")
    print("="*60)
    
    # Lấy API key
    api_key = os.getenv("GEMINI_API_KEY", "YOUR_API_KEY_HERE")
    
    if api_key == "YOUR_API_KEY_HERE" or not api_key:
        print("\n❌ LỖI: Chưa cấu hình GEMINI_API_KEY!")
        print("\nHướng dẫn:")
        print("1. Lấy API key từ: https://makersuite.google.com/app/apikey")
        print("2. Windows PowerShell: $env:GEMINI_API_KEY='your_key'")
        print("3. Windows CMD: set GEMINI_API_KEY=your_key")
        print("4. Linux/Mac: export GEMINI_API_KEY=your_key")
        return False
    
    print(f"\n✓ Đã tìm thấy API key: {api_key[:10]}...{api_key[-5:]}")
    
    try:
        # Cấu hình API
        genai.configure(api_key=api_key)
        print("✓ Đã cấu hình Gemini API")
        
        # Khởi tạo model
        model = genai.GenerativeModel('gemini-1.5-flash')
        print("✓ Đã khởi tạo model: gemini-1.5-flash")
        
        # Test request đơn giản
        print("\n📤 Đang gửi test request...")
        response = model.generate_content("Hãy trả lời bằng một từ: AI là gì?")
        
        print(f"📥 Nhận được response: {response.text}")
        
        print("\n" + "="*60)
        print("✅ KẾT NỐI THÀNH CÔNG!")
        print("="*60)
        print("\nBạn có thể chạy Gemini_label.py để bắt đầu gán nhãn.")
        return True
        
    except Exception as e:
        print("\n" + "="*60)
        print("❌ KẾT NỐI THẤT BẠI!")
        print("="*60)
        print(f"\nLỗi: {str(e)}")
        print("\nKiểm tra lại:")
        print("1. API key có đúng không?")
        print("2. Đã bật Gemini API trên Google Cloud Console chưa?")
        print("3. Có kết nối internet không?")
        return False

if __name__ == "__main__":
    test_gemini_api()
