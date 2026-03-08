import feedparser
import pandas as pd
from datetime import datetime
import time

# 1. DANH SÁCH NGUỒN TIN (Đã tích hợp toàn bộ các trang yêu cầu)
rss_urls = [
    # --- 1. Nhóm SaaS & Nền tảng quản trị (WordPress thường có hậu tố /feed) ---
    "https://resources.base.vn",
    "https://misa.vn/tin-tuc",
    "https://1office.vn/blog",
    "https://news.google.com/rss/search?q=site:cloudgo.vn+AI+OR+%22trí+tuệ+nhân+tạo%22&hl=vi-VN&gl=VN&ceid=VN:vi", # Dùng Google News để ép lấy bài từ CloudGO
    
    # --- 2. Nhóm Kinh tế & Đầu tư (ROI, Case study Doanh nghiệp) ---
    "https://vneconomy.vn/kinh-te-so.htm",
    "https://cafef.vn",
    "https://cafef.vn/doanh-nghiep.chn", # Mục ngân hàng rất hay có case study AI eKYC, AI tín dụng
    "https://news.google.com/rss/search?q=site:nhipcaudautu.vn+AI+OR+%22chuyển+đổi+số%22&hl=vi-VN&gl=VN&ceid=VN:vi",

    # --- 3. Nhóm Tech blog của Tập đoàn Công nghệ ---
    "https://techinsight.com.vn/", # Blog của FPT
    "https://news.google.com/rss/search?q=site:viettelai.vn+AI+OR+site:vnetwork.vn+AI&hl=vi-VN&gl=VN&ceid=VN:vi",

    # --- 4. Nhóm Marketing & Quảng cáo ---
    "https://www.brandsvietnam.com", # RSS của BrandsVN
    "https://news.google.com/rss/search?q=site:advertisingvietnam.com+AI&hl=vi-VN&gl=VN&ceid=VN:vi",

    # --- 5. Nhóm Báo chí Công nghệ đại chúng ---
    "https://vnexpress.net/rss/so-hoa.rss",
    "https://genk.vn/trang-chu.rss",
    "https://vietnamnet.vn/rss/cong-nghe.rss", # Cổng công nghệ của VietNamNet (bao gồm ICTNews)

    # --- 6. Nhóm TÌM KIẾM TỪ KHÓA QUÉT RỘNG TOÀN MẠNG ---
    "https://news.google.com/rss/search?q=%22Ứng+dụng+AI%22+OR+%22giải+pháp+AI%22+OR+%22triển+khai+AI%22&hl=vi-VN&gl=VN&ceid=VN:vi",
    "https://news.google.com/rss/search?q=%22Case+study+AI%22+OR+%22AI+trong+doanh+nghiệp%22&hl=vi-VN&gl=VN&ceid=VN:vi",
    "https://news.google.com/rss/search?q=%22AI+trong+Marketing%22+OR+%22AI+trong+Tài+chính%22+OR+%22AI+nhân+sự%22&hl=vi-VN&gl=VN&ceid=VN:vi",
    "https://news.google.com/rss/search?q=%22tối+ưu+chi+phí%22+OR+%22tăng+năng+suất%22+AI&hl=vi-VN&gl=VN&ceid=VN:vi"
]

# 2. BỘ LỌC KÉP (TWO-LAYER FILTER) ĐỂ BẮT ĐÚNG NHÃN "SOLUTIONS & USE CASES"
ai_keywords = [
    " ai ", "trí tuệ nhân", "trí thông minh", "học máy", 
    "chatgpt", "gemini", "claude", "copilot", "llm", "ai tạo sinh", 
    "machine learning", "trợ lý ảo", "chatbot"
]

solution_keywords = [
    "ứng dụng", "giải pháp", "case study", "triển khai", "hướng dẫn",
    "tiết kiệm", "năng suất", "tối ưu", "công cụ", "doanh nghiệp", 
    "tự động hóa", "marketing", "tài chính", "nhân sự", "hr", "roi",
    "thực tế", "thực thi", "vận hành", "quy trình"
]

def is_solution_article(title, summary):
    """Lọc bài viết phải thỏa mãn CẢ 2 điều kiện: Chứa từ khóa AI VÀ chứa từ khóa Thực thi/Giải pháp"""
    text = f"{title} {summary}".lower()
    has_ai = any(kw in text for kw in ai_keywords)
    has_solution = any(kw in text for kw in solution_keywords)
    return has_ai and has_solution

# 3. QUÁ TRÌNH THU THẬP DỮ LIỆU
articles = []
print("Bắt đầu crawl dữ liệu theo nhãn SOLUTIONS & USE CASES...")
print(f"Tổng số nguồn: {len(rss_urls)}\n")

max_articles_total = 1500  

for url in rss_urls:
    if len(articles) >= max_articles_total:
        break
        
    try:
        # Sử dụng headers giả lập trình duyệt để tránh bị chặn bởi một số trang
        feed = feedparser.parse(url)
        
        source_name = url.split('/')[2].replace('news.google.com', 'Google News (Search)')
        print(f"-> Đang quét: {source_name}... (Tìm thấy {len(feed.entries)} bài gốc)")
        
        match_count = 0
        for entry in feed.entries:
            if len(articles) >= max_articles_total:
                break
                
            title = entry.title if 'title' in entry else ""
            summary = entry.summary if 'summary' in entry else ""
            link = entry.link if 'link' in entry else ""
            pub_date = entry.published if 'published' in entry else datetime.now().strftime("%Y-%m-%d")

            # Áp dụng bộ lọc
            if is_solution_article(title, summary):
                articles.append({
                    "title": title, 
                    "link": link,
                })
                match_count += 1
                
        print(f"   => Đã lọc được {match_count} bài chuẩn Use Case.")
        time.sleep(1) # Nghỉ 1 giây để tránh spam request làm sập feed
        
    except Exception as e:
        print(f"   [Lỗi] Không thể đọc {url[:50]}: {e}")
        
# 4. LƯU DỮ LIỆU
df = pd.DataFrame(articles)

if not df.empty:
    # Xóa các bài viết bị trùng lặp link (ví dụ Google News và RSS trả về cùng 1 bài)
    df.drop_duplicates(subset=['link'], inplace=True) 
    
    filename = f"ai_use_cases_{datetime.now().strftime('%Y%m%d')}.csv"
    df.to_csv(filename, index=False, encoding='utf-8-sig')
    
    print(f"\n✅ Đã hoàn thành! Thu thập được {len(df)} bài viết đúng nhãn Thực thi & Ứng dụng.")
    print(f"📂 File đã được lưu tại: {filename}") 
else:
    print("\n❌ Không tìm thấy bài viết nào khớp với tiêu chí ngày hôm nay.")