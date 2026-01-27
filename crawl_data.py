import feedparser
import pandas as pd
import csv
from datetime import datetime

# 1. Danh sách nguồn tin (RSS Feeds)
rss_urls = [
    "https://vnexpress.net/rss/so-hoa.rss",
    "https://genk.vn/trang-chu.rss",
    "https://ictnews.vietnamnet.vn/rss/cong-nghe.rss",
    # Link đặc biệt từ Google News (như Cách 1)
    "https://news.google.com/rss/search?q=Trí+tuệ+nhân+tạo+OR+AI+OR+LLM&hl=vi-VN&gl=VN&ceid=VN:vi"
]

# 2. Bộ từ khóa để "bắt" bài viết AI (Case insensitive)
ai_keywords = [
    "ai ", "trí tuệ nhân tạo", "machine learning", "học máy", 
    "chatgpt", "gemini", "openai", "bard", "llm", "deep learning",
    "robot", "tự động hóa", "nvidia", "algorithm", "thuật toán"
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

max_articles = 10  # Giới hạn số bài viết

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