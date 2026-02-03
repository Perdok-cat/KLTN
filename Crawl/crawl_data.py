import feedparser
import pandas as pd
import csv
from datetime import datetime

# 1. Danh sách nguồn tin (RSS Feeds)
rss_urls = [
    # --- NHÓM TIN CÔNG NGHỆ CHUYÊN BIỆT ---
    "https://vnexpress.net/rss/so-hoa.rss",
    "https://genk.vn/trang-chu.rss",
    "https://ictnews.vietnamnet.vn/rss/cong-nghe.rss",
    "https://tinhte.vn/rss",
    "https://sforum.vn/feed",
    "https://techrum.vn/forums/-/index.rss",
    "https://www.techz.vn/rss/cong-nghe.rss",
    "https://trangcongnghe.com.vn/rss/tin-tuc-cong-nghe/",
    "https://nghenhinvietnam.vn/rss/hi-tech.rss",
    "https://viettimes.vn/rss/cong-nghe-4.rss",

    # --- NHÓM BÁO ĐIỆN TỬ LỚN (MỤC CÔNG NGHỆ) ---
    "https://thanhnien.vn/rss/cong-nghe-game.rss",
    "https://tuoitre.vn/rss/khoa-hoc-cong-nghe.rss",
    "https://vietnamnet.vn/rss/cong-nghe.rss",
    "https://vtv.vn/cong-nghe.rss",
    "https://znews.vn/rss/cong-nghe.rss",
    "https://baomoi.com/rss/c/76.epi",
    "https://dantri.com.vn/rss/suc-manh-so.rss",
    "https://laodong.vn/rss/cong-nghe-12.rss",
    "https://nld.com.vn/rss/cong-nghe.rss",
    "https://tienphong.vn/rss/cong-nghe-khoa-hoc-201.rss",
    "https://plo.vn/rss/ky-nguyen-so-245.rss",
    "https://www.24h.com.vn/rss/cong-nghe-thong-tin-c55.rss",
    "https://vtcnews.vn/rss/cong-nghe.rss",
    "https://baochinhphu.vn/rss/khoa-hoc-cong-nghe.rss",

    # --- NHÓM KINH TẾ, TÀI CHÍNH & STARTUP ---
    "https://cafef.vn/rss/cong-nghe.rss",
    "https://cafebiz.vn/rss/cong-nghe.rss",
    "https://vneconomy.vn/rss/the-gioi-so.rss",
    "https://vietnambiz.vn/rss/cong-nghe.rss",
    "https://forbes.vn/feed/",

    # --- NHÓM TÌM KIẾM THEO TỪ KHÓA (GOOGLE NEWS) ---
    "https://news.google.com/rss/search?q=Trí+tuệ+nhân+tạo+OR+AI+OR+LLM&hl=vi-VN&gl=VN&ceid=VN:vi",
    "https://news.google.com/rss/search?q=Nvidia+OR+Chip+OR+Bán+dẫn&hl=vi-VN&gl=VN&ceid=VN:vi",
    "https://news.google.com/rss/search?q=ChatGPT+OR+Gemini+OR+OpenAI&hl=vi-VN&gl=VN&ceid=VN:vi"
]

ai_keywords = [
    # Cơ bản & Tiếng Việt
    "ai ", "trí tuệ nhân tạo", "trí thông minh nhân tạo", "học máy", "mạng thần kinh",
    
    # Các ông lớn & Công cụ phổ biến
    "chatgpt", "gemini", "openai", "bard", "claude", "copilot", "midjourney", "stable diffusion",
    "llama", "mistral", "nvidia", "hugging face", "anthropic", "microsoft ai", "google ai",
    
    # Thuật ngữ chuyên môn (Sâu hơn LLM)
    "llm", "large language model", "generative ai", "ai tạo sinh", "machine learning", 
    "deep learning", "nlp", "xử lý ngôn ngữ tự nhiên", "computer vision", "thị giác máy tính",
    "neural network", "transformer model", "thuật toán", "algorithm",
    
    # Phần cứng & Hạ tầng
    "gpu", "h100", "a100", "chip bán dẫn", "bán dẫn", "vi xử lý ai", "cuda",
    
    # Ứng dụng & Xu hướng
    "xe tự hành", "robot", "tự động hóa", "big data", "dữ liệu lớn", 
    "chatbot", "virtual assistant", "trợ lý ảo"
]

def is_ai_article(text):
    """Hàm kiểm tra xem text có chứa từ khóa AI không"""
    if not text: return False
    text_lower = text.lower()
    for kw in ai_keywords:
        if kw in text_lower:
            return True
    return False

articles = []

print("Đang bắt đầu crawl và lọc tin AI...")

max_articles = 1000  

for url in rss_urls:
    if len(articles) >= max_articles:
        break
        
    feed = feedparser.parse(url)
    print(f"-> Đang đọc nguồn: {url} ({len(feed.entries)} bài)")
    
    for entry in feed.entries:
        if len(articles) >= max_articles:
            break
            
        title = entry.title if 'title' in entry else ""
        summary = entry.summary if 'summary' in entry else ""
        link = entry.link if 'link' in entry else ""
        pub_date = entry.published if 'published' in entry else datetime.now().strftime("%Y-%m-%d")

        # KỸ THUẬT QUAN TRỌNG: Chỉ lấy bài nếu Tiêu đề hoặc Tóm tắt có từ khóa AI
        if is_ai_article(title) or is_ai_article(summary):
            articles.append({
                "title": title,
                "summary": summary, # Bạn sẽ dựa vào cái này để gán nhãn
                "link": link,
                "published": pub_date,
                "label": "" # Cột trống để bạn điền tay (0, 1, 2)
            })
        
# 3. Lưu ra file CSV
df = pd.DataFrame(articles)
# Xóa trùng lặp (nếu Google News trỏ về cùng bài với VnExpress)
df.drop_duplicates(subset=['link'], inplace=True) 

filename = "du_lieu_ai_gan_nhan.csv"
df.to_csv(filename, index=False, encoding='utf-8-sig')

print(f"\nĐã hoàn thành! Tìm thấy {len(df)} bài báo liên quan đến AI.")
print(f"File đã lưu tại: {filename}")
print("Giờ bạn hãy mở file này lên và điền cột 'label' nhé.")