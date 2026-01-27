import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime

def crawl_vnexpress_content(url):
    """
    Crawl nội dung bài viết từ VnExpress
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=100)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Tìm nội dung chính của bài viết VnExpress
        # VnExpress thường dùng class 'fck_detail' hoặc 'Normal' cho nội dung
        content_div = soup.find('article', class_='fck_detail')
        
        if not content_div:
            # Thử tìm theo cách khác
            content_div = soup.find('div', class_='fck_detail')
        
        if not content_div:
            # Thử tìm tất cả đoạn văn trong container chính
            content_div = soup.find('article', class_='content_detail')
        
        if content_div:
            # Lấy tất cả các đoạn văn
            paragraphs = content_div.find_all('p', class_='Normal')
            
            if not paragraphs:
                # Nếu không có class Normal, lấy tất cả thẻ p
                paragraphs = content_div.find_all('p')
            
            # Ghép nội dung
            content = ' '.join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
            
            return content if content else "Không thể trích xuất nội dung"
        else:
            return "Không tìm thấy nội dung bài viết"
            
    except requests.exceptions.Timeout:
        return "Lỗi: Timeout khi truy cập"
    except requests.exceptions.RequestException as e:
        return f"Lỗi khi crawl: {str(e)}"
    except Exception as e:
        return f"Lỗi không xác định: {str(e)}"


def crawl_generic_content(url):
    """
    Crawl nội dung từ các trang web khác (Genk, ICTNews, v.v.)
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=100)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Thử nhiều selector phổ biến
        content = None
        
        # Thử tìm article hoặc content chính
        selectors = [
            ('article', {}),
            ('div', {'class': 'article-content'}),
            ('div', {'class': 'content-detail'}),
            ('div', {'class': 'article-body'}),
            ('div', {'id': 'article-content'}),
        ]
        
        for tag, attrs in selectors:
            content_div = soup.find(tag, attrs)
            if content_div:
                paragraphs = content_div.find_all('p')
                if paragraphs:
                    content = ' '.join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
                    if len(content) > 100:  # Chỉ chấp nhận nếu đủ dài
                        return content
        
        return "Không thể trích xuất nội dung"
        
    except Exception as e:
        return f"Lỗi: {str(e)}"


def crawl_article_content(url):
    """
    Hàm chính để crawl nội dung dựa trên domain
    """
    if 'vnexpress.net' in url:
        return crawl_vnexpress_content(url)
    else:
        return crawl_generic_content(url)


def main():
    # Đọc file CSV hiện có
    input_file = "du_lieu_ai_gan_nhan.csv"
    output_file = "du_lieu_ai_day_du.csv"
    backup_file = "du_lieu_ai_day_du_backup.csv"
    
    print(f"Đang đọc file: {input_file}")
    df = pd.read_csv(input_file)
    
    print(f"Tìm thấy {len(df)} bài viết cần crawl nội dung")
    
    # Kiểm tra xem đã có file output chưa để tiếp tục từ nơi dừng
    try:
        existing_df = pd.read_csv(output_file)
        print(f"Phát hiện file output đã tồn tại với {len(existing_df)} bài viết")
        
        # Nếu có cột content và đã crawl một số bài, tiếp tục từ đó
        if 'content' in existing_df.columns and len(existing_df) == len(df):
            df = existing_df
            print("Tiếp tục crawl từ file đã lưu trước đó")
        else:
            print("File output không hợp lệ, bắt đầu crawl mới")
            if 'content' not in df.columns:
                df['content'] = ""
    except FileNotFoundError:
        print("Bắt đầu crawl mới")
        # Thêm cột content nếu chưa có
        if 'content' not in df.columns:
            df['content'] = ""
    
    # Đếm số bài đã crawl (content có độ dài > 0)
    crawled_count = len(df[df['content'].str.len() > 0]) if 'content' in df.columns else 0
    print(f"Đã crawl: {crawled_count}/{len(df)} bài viết")
    
    # Crawl từng bài
    for idx, row in df.iterrows():
        # Bỏ qua nếu đã có content (độ dài > 0)
        if pd.notna(df.at[idx, 'content']) and len(str(df.at[idx, 'content'])) > 0:
            print(f"\n[{idx+1}/{len(df)}] Đã có content, bỏ qua: {row['title'][:50]}...")
            continue
        
        link = row['link']
        print(f"\n[{idx+1}/{len(df)}] Đang crawl: {row['title'][:50]}...")
        print(f"    Link: {link}")
        
        try:
            # Crawl nội dung
            content = crawl_article_content(link)
            df.at[idx, 'content'] = content
            
            # Hiển thị preview
            preview = content[:100] + "..." if len(content) > 100 else content
            print(f"    Kết quả: {preview}")
            
            # LƯU NGAY SAU KHI CRAWL THÀNH CÔNG
            df.to_csv(output_file, index=False, encoding='utf-8-sig')
            print(f"    ✓ Đã lưu vào {output_file}")
            
            # Tạo backup mỗi 10 bài
            if (idx + 1) % 10 == 0:
                df.to_csv(backup_file, index=False, encoding='utf-8-sig')
                print(f"    ✓ Đã tạo backup tại {backup_file}")
            
        except Exception as e:
            print(f"    ✗ Lỗi không mong muốn: {str(e)}")
            df.at[idx, 'content'] = f"Lỗi: {str(e)}"
            # Vẫn lưu file khi gặp lỗi
            df.to_csv(output_file, index=False, encoding='utf-8-sig')
        
        # Delay để tránh bị chặn
        time.sleep(2)  # Đợi 2 giây giữa các request
    
    # Lưu kết quả cuối cùng
    df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n✓ Hoàn thành! Đã lưu vào file: {output_file}")
    print(f"Tổng số bài viết: {len(df)}")
    
    # Thống kê
    success_count = len(df[df['content'].str.len() > 100])
    print(f"Crawl thành công: {success_count}/{len(df)} bài")


if __name__ == "__main__":
    main()
