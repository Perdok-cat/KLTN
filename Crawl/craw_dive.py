import feedparser
import pandas as pd
from datetime import datetime
import time

# 1. DANH SÁCH NGUỒN TIN CHUYÊN SÂU (DEEP DIVE & RESEARCH) - CHỈ TIẾNG VIỆT
rss_urls = [
    "https://vinbigdata.com/cong-nghe-giong-noi",
    "https://vinbigdata.com/cong-nghe-hinh-anh",
    "https://vinbigdata.com/category/genai",
    "https://vinbigdata.com/camera-ai",
    "https://vinbigdata.com/chatbot",
    "https://vinbigdata.com/ocr",
    "https://vinbigdata.com/xu-ly-anh-y-te",
    "https://vinbigdata.com/tin-tuc-callbot",
    "https://vinbigdata.com/tro-ly-ao",
    "https://fpt.ai/vi/tai-nguyen/bai-viet/",
    "https://hblab.vn/blog/",
    "https://google.cmctelecom.vn/blogs/", 
    "https://vnptai.io/vi/blog",

    







]

# 2. BỘ LỌC DEEP DIVE (TECHNICAL KEYWORDS)
# Kết hợp cả tiếng Anh và tiếng Việt vì tài liệu kỹ thuật dùng thuật ngữ hỗn hợp
tech_focus_keywords = [
    "architecture", "kiến trúc", "model", "mô hình", "benchmark", "tham số", "parameter",
    "fine-tune", "training", "huấn luyện", "inference", "suy luận", "latencies", "độ trễ",
    "transformer", "attention mechanism", "rhlf", "quantization", "lượng tử hóa",
    "datasets", "tập dữ liệu", "loss function", "vram", "gpu", "token", "embedding",
    "research paper", "bài báo khoa học", "thư viện", "library", "framework",
    "pytorch", "tensorflow", "langchain", "llama index", "state-of-the-art", "sota"
]

# Từ khóa về các dòng model cụ thể để bắt bài Deep Dive
model_names = [
    # LLMs & SLMs
    "llama 3.1", "llama 3.2", "mistral", "mixtral", "gemma 2", "phi-3", "phi-4", 
    "qwen 2.5", "deepseek-v3", "grok-1", "gpt-4o", "claude 3.5", "gemini 1.5",
    "o1-preview", "smollm", "tinyllama", "gpt-5.2", "claude-4.6-opus", "gemini-3.1-pro", "deepseek-v3.2", "llama-4-scout", "kimi-k2.5", "ling-1t", "mimo-v2-flash", 
    "o1",
    "o1-preview",
    "o1-mini",
    "o3-mini",

    # --- Dòng GPT-4o (Đa phương thức, tốc độ cao, tối ưu chi phí) ---
    "gpt-4o",
    "gpt-4o-2024-08-06", # Các phiên bản snapshot cụ thể
    "gpt-4o-mini",
    "gpt-4o-mini-2024-07-18",
    
    # --- Dòng GPT-4 & GPT-4 Turbo ---
    "gpt-4-turbo",
    "gpt-4-turbo-preview",
    "gpt-4-vision-preview",
    "gpt-4",
    "gpt-4-32k",
    "gpt-4-0613",
    
    # --- Dòng GPT-3.5 (Tối ưu cho các tác vụ cơ bản) ---
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-16k",
    "gpt-3.5-turbo-instruct",
    "gpt-3.5-turbo-0125",
    
    # --- Dòng Base Models (Chủ yếu dùng để Fine-tuning) ---
    "babbage-002",
    "davinci-002",
    
    # --- Dòng Legacy/Deprecated (Các mô hình cũ đã hoặc sắp ngừng hỗ trợ) ---
    "text-davinci-003",
    "text-davinci-002",
    "text-curie-001",
    "text-babbage-001",
    "text-ada-001",

    "gemini-3.1-pro-preview",         # Flagship mới nhất (khả năng lập luận, đa phương thức và coding xuất sắc)
    "gemini-3-flash-preview",         # Hiệu suất tiệm cận Pro nhưng tối ưu chi phí và tốc độ
    "gemini-3.1-flash-lite-preview",  # Cực kỳ tiết kiệm, thiết kế cho các tác vụ khối lượng lớn (high-volume)
    
    # --- Dòng Gemini 2.5 Series (Thế hệ ổn định, hỗ trợ Tư duy thích ứng - Adaptive Thinking) ---
    "gemini-2.5-pro",                 # Mô hình Pro bản ổn định mạnh mẽ
    "gemini-2.5-flash",               # Mô hình đa năng, cân bằng giữa tốc độ và chi phí
    
    # --- Dòng Live API & Audio (Tương tác thời gian thực & Giọng nói) ---
    "gemini-2.5-flash-live-preview",  # Hỗ trợ Live API cho agent âm thanh/video 2 chiều độ trễ cực thấp
    "gemini-2.5-pro-tts-preview",     # Text-to-Speech (TTS) chất lượng cao cho podcast/sách nói
    "gemini-2.5-flash-tts-preview",   # Text-to-Speech (TTS) tốc độ cao cho trợ lý ảo thời gian thực
    
    # --- Dòng Media & Generative (Hình ảnh, Video, Âm nhạc) ---
    "nano-banana",                    # Mô hình tạo và chỉnh sửa hình ảnh tốc độ cao (Nano Banana model)
    "nano-banana-pro",                # Mô hình ảnh chuyên nghiệp (render text chính xác, layout phức tạp)
    "veo",                            # Mô hình tạo video điện ảnh với âm thanh gốc đồng bộ
    "lyria-3",                        # Mô hình tạo âm nhạc chất lượng cao (điều khiển được nhạc cụ, BPM, vocal)
    
    # --- Dòng Embedding (Dùng để tạo vector nhúng cho RAG, Semantic Search) ---
    "gemini-embedding-001",           # Mô hình nhúng văn bản tiêu chuẩn của Gemini
    
    # --- Dòng Legacy/Deprecated (Các mô hình cũ đã hoặc sắp ngừng hỗ trợ) ---
    "gemini-3-pro",                   # Bản 3.0 Pro (đang được thay thế bởi 3.1 Pro)
    "gemini-2.0-flash",               # Dòng 2.0 (ngừng hỗ trợ)
    "gemini-1.5-pro",                 # Dòng 1.5 thế hệ trước (ngừng hỗ trợ)
    "gemini-1.5-flash",
    "llama-3.3-70b-instruct",
    
    # --- Dòng Llama 3.2 (Hỗ trợ Vision đa phương thức và các mô hình nhỏ cho Edge/Mobile) ---
    "llama-3.2-90b-vision-instruct",  # Mô hình lớn hỗ trợ xử lý ảnh
    "llama-3.2-11b-vision-instruct",  # Mô hình tầm trung hỗ trợ xử lý ảnh
    "llama-3.2-3b-instruct",          # Chạy cục bộ trên thiết bị di động/laptop yếu
    "llama-3.2-1b-instruct",          # Cực nhẹ, tốc độ cực nhanh cho edge devices

    # --- Dòng Llama 3.1 (Hỗ trợ context length 128k, đa ngôn ngữ tốt) ---
    "llama-3.1-405b-instruct",        # Mô hình lớn nhất, mạnh nhất của Meta
    "llama-3.1-70b-instruct",         # Mô hình lý tưởng cho máy chủ tầm trung
    "llama-3.1-8b-instruct",          # Mô hình siêu phổ biến cho các máy chủ nhỏ

    # --- Dòng Llama 3 (Thế hệ 3 đời đầu) ---
    "llama-3-70b-instruct",
    "llama-3-8b-instruct",

    # --- Dòng Code Llama (Được Fine-tune chuyên biệt cho lập trình & Code) ---
    "code-llama-70b-instruct",
    "code-llama-34b-instruct",
    "code-llama-13b-instruct",
    "code-llama-7b-instruct",
    
    # --- Dòng Llama Guard & Safety (Dùng để kiểm duyệt nội dung, bảo mật) ---
    "llama-guard-3-11b-vision",       # Kiểm duyệt cả văn bản và hình ảnh
    "llama-guard-3-8b",               # Kiểm duyệt văn bản
    "prompt-guard-86m",               # Chống Prompt Injection / Jailbreak

    # --- Dòng Llama 2 Series (Legacy - Dần bị thay thế bởi Llama 3/3.1) ---
    "llama-2-70b-chat",
    "llama-2-13b-chat",
    "llama-2-7b-chat",
    
    # --- Dòng Llama 1 (Bản gốc, hiện tại chủ yếu dùng để tham khảo nghiên cứu) ---
    "llama-65b",
    "llama-33b",
    "llama-13b",
    "llama-7b",

    # Vision & Multimodal
    "vit", "vision transformer", "yolov11", "sam 2", "dinov2", "llava", "paligemma",
    
    # Generative AI
    "stable diffusion", "sd3", "flux.1", "sora", "kling ai", "luma dream machine",
    
    # Architectures & Research
    "mixture of experts", "moe", "mamba", "state space model", "ssm", 
    "flashattention", "rag", "long context", "quantization", "gguf", "lora"
]

def is_deep_dive_article(title, summary):
    """Lọc bài viết chuyên sâu dựa trên thuật ngữ kỹ thuật"""
    text = f"{title} {summary}".lower()
    
    # Kiểm tra xem có chứa từ khóa kỹ thuật hoặc tên model không
    has_tech = any(kw in text for kw in tech_focus_keywords)
    has_model = any(m in text for m in model_names)
    
    # Ưu tiên các bài có chứa số liệu hoặc các thuật ngữ đặc thù của Research
    is_research = any(kw in text for kw in ["arxiv", "paper", "methodology", "experiment"])
    
    return (has_tech or has_model) or is_research

# 3. QUÁ TRÌNH THU THẬP
articles = []
print("🚀 Đang khởi động trình quét dữ liệu DEEP DIVE AI...")

for url in rss_urls:
    try:
        feed = feedparser.parse(url)
        source_domain = url.split('/')[2]
        print(f"-> Đang phân tích: {source_domain}...")
        
        count = 0
        for entry in feed.entries:
            title = entry.get('title', '')
            summary = entry.get('summary', '')
            link = entry.get('link', '')
            
            if is_deep_dive_article(title, summary):
                articles.append({
                    "Source": source_domain,
                    "Title": title,
                    "Link": link,
                    "Date": entry.get('published', datetime.now().strftime("%Y-%m-%d"))
                })
                count += 1
        print(f"   ✅ Tìm thấy {count} bài kỹ thuật chuyên sâu.")
    except Exception as e:
        print(f"   [Lỗi] Bỏ qua {url[:30]}: {e}")

# 4. XỬ LÝ & LƯU TRỮ
df = pd.DataFrame(articles)
if not df.empty:
    df.drop_duplicates(subset=['Link'], inplace=True)
    filename = f"ai_deep_dive_VN_{datetime.now().strftime('%Y%m%d')}.csv"
    df.to_csv(filename, index=False, encoding='utf-8-sig')
    print(f"\n✨ THÀNH CÔNG! Đã thu thập {len(df)} bài viết kỹ thuật.")
    print(f"📂 File: {filename}")
else:
    print("\n⚠️ Không tìm thấy bài viết kỹ thuật nào mới.")