import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import random
from datetime import datetime
import json
import re

# Danh sách User-Agents để mô phỏng nhiều trình duyệt khác nhau
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0',
]

def get_random_user_agent():
    """Lấy một User-Agent ngẫu nhiên từ danh sách"""
    return random.choice(USER_AGENTS)

def human_like_sleep(min_seconds=2, max_seconds=7):
    """
    Tạo delay ngẫu nhiên giống người dùng thật
    - Thêm biến động để không có pattern cố định
    - Thêm micro delays để tự nhiên hơn
    """
    base_delay = random.uniform(min_seconds, max_seconds)
    # Thêm một chút biến động nhỏ (micro delays)
    micro_variation = random.uniform(-0.5, 0.5)
    total_delay = max(1, base_delay + micro_variation)  # Đảm bảo tối thiểu 1 giây
    
    print(f"    ⏳ Đợi {total_delay:.2f} giây...")
    time.sleep(total_delay)

def long_break_sleep():
    """
    Tạo break dài hơn thỉnh thoảng (mô phỏng người dùng nghỉ giữa chừng)
    """
    break_time = random.uniform(10, 20)
    print(f"    ☕ Nghỉ giải lao {break_time:.1f} giây...")
    time.sleep(break_time)

def crawl_vnexpress_content(url):
    """
    Crawl nội dung bài viết từ VnExpress
    """
    try:
        # Sử dụng User-Agent ngẫu nhiên
        headers = {
            'User-Agent': get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        # Thêm delay nhỏ trước khi gửi request (mô phỏng thời gian click/navigate)
        time.sleep(random.uniform(0.5, 1.5))
        
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
    Crawl nội dung từ các trang web khác (Genk, ICTNews, VTV, Dân Trí, v.v.)
    """
    try:
        # Sử dụng User-Agent ngẫu nhiên
        headers = {
            'User-Agent': get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'DNT': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
        }
        
        # Thêm delay nhỏ trước khi gửi request (mô phỏng thời gian click/navigate)
        time.sleep(random.uniform(0.5, 1.5))
        
        response = requests.get(url, headers=headers, timeout=100)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Thử nhiều selector phổ biến cho các site Việt Nam
        content = None
        
        # Thử tìm article hoặc content chính với nhiều pattern hơn
        selectors = [
            ('article', {}),
            ('article', {'class': 'fck_detail'}),
            ('div', {'class': 'article-content'}),
            ('div', {'class': 'content-detail'}),
            ('div', {'class': 'article-body'}),
            ('div', {'class': 'detail-content'}),
            ('div', {'class': 'content_detail'}),
            ('div', {'class': 'baiviet-tomtat'}),
            ('div', {'class': 'singular-content'}),
            ('div', {'id': 'article-content'}),
            ('div', {'id': 'content-detail'}),
            ('div', {'class': 'maincontent'}),
        ]
        
        for tag, attrs in selectors:
            content_div = soup.find(tag, attrs)
            if content_div:
                paragraphs = content_div.find_all('p')
                if paragraphs:
                    content = ' '.join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
                    if len(content) > 100:  # Chỉ chấp nhận nếu đủ dài
                        return content
        
        # Nếu không tìm thấy bằng selector, thử lấy tất cả thẻ p trong body
        if not content:
            all_paragraphs = soup.find_all('p')
            if all_paragraphs:
                content = ' '.join([p.get_text(strip=True) for p in all_paragraphs if p.get_text(strip=True)])
                if len(content) > 200:  # Threshold cao hơn vì lấy toàn bộ
                    return content
        
        return "Không thể trích xuất nội dung"
        
    except requests.exceptions.Timeout:
        return "Lỗi: Timeout khi truy cập"
    except requests.exceptions.RequestException as e:
        return f"Lỗi request: {str(e)}"
    except Exception as e:
        return f"Lỗi: {str(e)}"


def resolve_google_news_url(google_news_url):
    """
    Resolve Google News RSS URL để lấy URL bài viết gốc
    Sử dụng Google's internal API endpoint (method từ StackOverflow)
    """
    try:
        # Bước 1: Fetch trang Google News để lấy data-p
        resp = requests.get(google_news_url, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Tìm thẻ c-wiz có attribute data-p
        c_wiz = soup.select_one('c-wiz[data-p]')
        if not c_wiz:
            print(f"    ⚠️  Không tìm thấy c-wiz element")
            return None
        
        data_p = c_wiz.get('data-p')
        if not data_p:
            print(f"    ⚠️  Không tìm thấy data-p attribute")
            return None
        
        # Bước 2: Parse JSON từ data-p
        obj = json.loads(data_p.replace('%.@.', '["garturlreq",'))
        
        # Bước 3: Tạo payload cho API request
        payload = {
            'f.req': json.dumps([[['Fbv4je', json.dumps(obj[:-6] + obj[-2:]), 'null', 'generic']]])
        }
        
        headers = {
            'content-type': 'application/x-www-form-urlencoded;charset=UTF-8',
            'user-agent': get_random_user_agent(),
        }
        
        # Bước 4: POST đến Google's internal API
        api_url = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
        response = requests.post(api_url, headers=headers, data=payload, timeout=15)
        
        # Bước 5: Parse response để lấy article URL
        array_string = json.loads(response.text.replace(")]}'", ""))[0][2]
        article_url = json.loads(array_string)[1]
        
        if article_url and 'http' in article_url:
            print(f"    🔓 Decoded: {article_url[:80]}...")
            time.sleep(random.uniform(0.5, 1.5))  # Delay nhỏ sau khi decode
            return article_url
        else:
            print(f"    ⚠️  Không lấy được URL hợp lệ")
            return None
            
    except requests.exceptions.Timeout:
        print(f"    ⚠️  Timeout khi resolve Google News URL")
        return None
    except json.JSONDecodeError as e:
        print(f"    ⚠️  Lỗi parse JSON: {str(e)}")
        return None
    except IndexError as e:
        print(f"    ⚠️  Lỗi parse response structure: {str(e)}")
        return None
    except Exception as e:
        print(f"    ⚠️  Lỗi resolve: {str(e)}")
        return None


def crawl_article_content(url):
    """
    Hàm chính để crawl nội dung dựa trên domain
    """
    # Nếu là Google News URL, resolve trước
    if 'news.google.com' in url:
        print("    📰 Phát hiện Google News URL, đang resolve...")
        resolved_url = resolve_google_news_url(url)
        
        # Nếu không resolve được, return lỗi
        if not resolved_url or resolved_url is None:
            return "❌ Không thể decode/resolve Google News URL"
        
        if 'news.google.com' in resolved_url:
            return "❌ Google News chặn bot - Không thể truy cập"
        
        url = resolved_url
    
    # Crawl theo domain
    if 'vnexpress.net' in url:
        return crawl_vnexpress_content(url)
    else:
        return crawl_generic_content(url)


def main():
    # Đọc file CSV hiện có
    input_file = "ai_deep_dive_20260307.csv"
    output_file = "Data/data_deep_dive_2026_03_07_full.csv"
    backup_file = "backup_data_deepdive.csv"
    
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
            print(f"\n[{idx+1}/{len(df)}] Đã có content, bỏ qua: {row['Title'][:50]}...")
            continue
        
        link = row['Link']
        print(f"\n[{idx+1}/{len(df)}] Đang crawl: {row['Title'][:50]}...")
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
        
        # Delay ngẫu nhiên giữa các request để giống người dùng thật
        human_like_sleep(min_seconds=2, max_seconds=7)
        
        # Thỉnh thoảng nghỉ dài hơn (mỗi 8-12 bài)
        if (idx + 1) % random.randint(8, 12) == 0:
            long_break_sleep()
    
    # Lưu kết quả cuối cùng
    df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n✓ Hoàn thành! Đã lưu vào file: {output_file}")
    print(f"Tổng số bài viết: {len(df)}")
    
    # Thống kê
    success_count = len(df[df['content'].str.len() > 100])
    print(f"Crawl thành công: {success_count}/{len(df)} bài")


if __name__ == "__main__":
    main()
    