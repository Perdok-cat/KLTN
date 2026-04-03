from __future__ import annotations

import functions_framework
import feedparser
import requests
from bs4 import BeautifulSoup
import time
import random
import json
import uuid
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Optional


from google.cloud import bigquery

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BIGQUERY_PROJECT = "your-gcp-project-id"      # TODO: replace with your GCP project ID
BIGQUERY_DATASET = "ai_news"
BIGQUERY_TABLE   = "raw_articles"

MAX_ARTICLES_PER_RUN = 500   # cap to avoid Cloud Function timeout

RSS_URLS = [
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
    "https://news.google.com/rss/search?q=Tr%C3%AD+tu%E1%BB%87+nh%C3%A2n+t%E1%BA%A1o+OR+AI+OR+LLM&hl=vi-VN&gl=VN&ceid=VN:vi",
    "https://news.google.com/rss/search?q=Nvidia+OR+Chip+OR+B%C3%A1n+d%E1%BA%ABn&hl=vi-VN&gl=VN&ceid=VN:vi",
    "https://news.google.com/rss/search?q=ChatGPT+OR+Gemini+OR+OpenAI&hl=vi-VN&gl=VN&ceid=VN:vi",
    "https://news.google.com/rss/search?q=LLM+OR+%22Large+Language+Model%22+OR+Transformer&hl=vi-VN&gl=VN&ceid=VN:vi",
    "https://news.google.com/rss/search?q=GPT-5+OR+Claude+4+OR+Gemini+2.0+OR+Llama+4+OR+Mistral&hl=vi-VN&gl=VN&ceid=VN:vi",
    "https://news.google.com/rss/search?q=OpenAI+OR+Anthropic+OR+Google+DeepMind+OR+Microsoft+AI&hl=vi-VN&gl=VN&ceid=VN:vi",
    "https://news.google.com/rss/search?q=Elon+Musk+xAI+OR+Grok+OR+Meta+AI&hl=vi-VN&gl=VN&ceid=VN:vi",
    "https://news.google.com/rss/search?q=%22AI+Viet+Nam%22+OR+VinAI+OR+Zalo+AI+OR+Viettel+AI&hl=vi-VN&gl=VN&ceid=VN:vi",
    "https://news.google.com/rss/search?q=%22AI+Agent%22+OR+%22Agentic+AI%22+OR+AutoGPT&hl=vi-VN&gl=VN&ceid=VN:vi",
    "https://news.google.com/rss/search?q=%22AI+coding%22+OR+GitHub+Copilot+OR+Cursor+AI&hl=vi-VN&gl=VN&ceid=VN:vi",
]

AI_KEYWORDS = [
    # Tiếng Việt cơ bản
    "ai ", "trí tuệ nhân tạo", "trí thông minh nhân tạo", "học máy", "mạng thần kinh",
    # Công cụ / Mô hình nổi tiếng
    "chatgpt", "gemini", "openai", "bard", "claude", "copilot", "midjourney",
    "stable diffusion", "llama", "mistral", "nvidia", "hugging face", "anthropic",
    "microsoft ai", "google ai",
    # Thuật ngữ chuyên môn
    "llm", "large language model", "generative ai", "ai tạo sinh", "machine learning",
    "deep learning", "nlp", "xử lý ngôn ngữ tự nhiên", "computer vision",
    "thị giác máy tính", "neural network", "transformer model", "thuật toán", "algorithm",
    # Phần cứng & Hạ tầng
    "gpu", "h100", "a100", "chip bán dẫn", "bán dẫn", "vi xử lý ai", "cuda",
    # Ứng dụng & Xu hướng
    "xe tự hành", "robot", "tự động hóa", "big data", "dữ liệu lớn",
    "chatbot", "virtual assistant", "trợ lý ảo",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _random_ua() -> str:
    return random.choice(USER_AGENTS)


def _base_headers() -> dict:
    return {
        "User-Agent": _random_ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "DNT": "1",
    }


def _is_ai_article(text: str) -> bool:
    if not text:
        return False
    text_lower = text.lower()
    return any(kw in text_lower for kw in AI_KEYWORDS)


def _extract_source(url: str) -> str:
    """Return the netloc (e.g. 'vnexpress.net') of a URL."""
    try:
        return urlparse(url).netloc
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Step 1 – Collect links from RSS feeds
# ---------------------------------------------------------------------------

def collect_links_from_rss() -> list[dict]:
    """
    Parse every RSS feed and return a deduplicated list of AI-related articles.
    Each item: {"title": ..., "link": ..., "pub_date": ..., "source": ...}
    """
    seen_links: set[str] = set()
    articles: list[dict] = []

    for rss_url in RSS_URLS:
        if len(articles) >= MAX_ARTICLES_PER_RUN:
            break
        try:
            feed = feedparser.parse(rss_url)
            logger.info("RSS %s => %d entries", rss_url, len(feed.entries))
        except Exception as exc:
            logger.warning("Failed to parse RSS %s: %s", rss_url, exc)
            continue

        for entry in feed.entries:
            if len(articles) >= MAX_ARTICLES_PER_RUN:
                break

            title   = getattr(entry, "title",     "") or ""
            summary = getattr(entry, "summary",   "") or ""
            link    = getattr(entry, "link",      "") or ""
            pub_raw = getattr(entry, "published", "") or ""

            if not link or link in seen_links:
                continue

            if _is_ai_article(title) or _is_ai_article(summary):
                seen_links.add(link)
                articles.append({
                    "title":    title,
                    "link":     link,
                    "pub_date": pub_raw,
                    "source":   _extract_source(link),
                })

    logger.info("Total RSS articles collected: %d", len(articles))
    return articles


# ---------------------------------------------------------------------------
# Step 2 – Filter out links already in BigQuery
# ---------------------------------------------------------------------------

def filter_new_links(client: bigquery.Client, articles: list[dict]) -> list[dict]:
    """
    Query BigQuery to find which links are already stored, then return only the
    articles whose link is NOT yet in the table.
    """
    if not articles:
        return []

    table_ref = f"`{BIGQUERY_PROJECT}.{BIGQUERY_DATASET}.{BIGQUERY_TABLE}`"

    links = [a["link"] for a in articles]
    # BigQuery supports parameterized array queries via UNNEST
    formatted = ", ".join(f"'{l.replace(chr(39), chr(39)*2)}'" for l in links)

    query = f"""
        SELECT link
        FROM {table_ref}
        WHERE link IN ({formatted})
    """
    try:
        existing = {row.link for row in client.query(query).result()}
        logger.info("Links already in BigQuery: %d", len(existing))
    except Exception as exc:
        # If the table doesn't exist yet, treat all as new
        logger.warning("BigQuery dedup query failed (table may not exist yet): %s", exc)
        existing = set()

    new_articles = [a for a in articles if a["link"] not in existing]
    logger.info("New articles to crawl: %d", len(new_articles))
    return new_articles


# ---------------------------------------------------------------------------
# Step 3 – Crawl article content
# ---------------------------------------------------------------------------

def _resolve_google_news_url(google_url: str) -> str | None:
    """Decode a Google News redirect URL to the original article URL."""
    try:
        resp = requests.get(google_url, timeout=15, headers=_base_headers())
        soup = BeautifulSoup(resp.text, "html.parser")

        c_wiz = soup.select_one("c-wiz[data-p]")
        if not c_wiz:
            return None
        data_p = c_wiz.get("data-p")
        if not data_p:
            return None

        obj = json.loads(data_p.replace("%.@.", '["garturlreq",'))
        payload = {
            "f.req": json.dumps([[["Fbv4je", json.dumps(obj[:-6] + obj[-2:]), "null", "generic"]]])
        }
        api_url = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
        api_resp = requests.post(
            api_url,
            headers={"content-type": "application/x-www-form-urlencoded;charset=UTF-8",
                     "user-agent": _random_ua()},
            data=payload,
            timeout=15,
        )
        array_string = json.loads(api_resp.text.replace(")]}'", ""))[0][2]
        article_url = json.loads(array_string)[1]
        if article_url and "http" in article_url:
            return article_url
    except Exception as exc:
        logger.debug("Google News resolve failed: %s", exc)
    return None


def _crawl_vnexpress(url: str) -> str:
    """Crawl article body from VnExpress."""
    try:
        resp = requests.get(url, headers=_base_headers(), timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")

        for selector in [
            ("article", {"class": "fck_detail"}),
            ("div",     {"class": "fck_detail"}),
            ("article", {"class": "content_detail"}),
        ]:
            div = soup.find(*selector)
            if div:
                paras = div.find_all("p", class_="Normal") or div.find_all("p")
                content = " ".join(p.get_text(strip=True) for p in paras if p.get_text(strip=True))
                if content:
                    return content

        return ""
    except Exception as exc:
        logger.debug("VnExpress crawl error %s: %s", url, exc)
        return ""


def _crawl_generic(url: str) -> str:
    """Generic crawler for other Vietnamese news sites."""
    try:
        resp = requests.get(url, headers=_base_headers(), timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")

        selectors = [
            ("article", {}),
            ("article", {"class": "fck_detail"}),
            ("div",     {"class": "article-content"}),
            ("div",     {"class": "content-detail"}),
            ("div",     {"class": "article-body"}),
            ("div",     {"class": "detail-content"}),
            ("div",     {"class": "content_detail"}),
            ("div",     {"class": "baiviet-tomtat"}),
            ("div",     {"class": "singular-content"}),
            ("div",     {"id":    "article-content"}),
            ("div",     {"id":    "content-detail"}),
            ("div",     {"class": "maincontent"}),
        ]

        for tag, attrs in selectors:
            div = soup.find(tag, attrs)
            if div:
                paras = div.find_all("p")
                content = " ".join(p.get_text(strip=True) for p in paras if p.get_text(strip=True))
                if len(content) > 100:
                    return content

        # Fallback: all <p> tags in page
        all_p = soup.find_all("p")
        content = " ".join(p.get_text(strip=True) for p in all_p if p.get_text(strip=True))
        return content if len(content) > 200 else ""

    except Exception as exc:
        logger.debug("Generic crawl error %s: %s", url, exc)
        return ""


def crawl_content(url: str) -> str:
    """Dispatch to the right crawler based on the domain."""
    if "news.google.com" in url:
        logger.info("  Resolving Google News URL...")
        resolved = _resolve_google_news_url(url)
        if not resolved or "news.google.com" in resolved:
            return ""
        url = resolved

    if "vnexpress.net" in url:
        return _crawl_vnexpress(url)
    return _crawl_generic(url)


# ---------------------------------------------------------------------------
# Step 4 – Insert rows into BigQuery
# ---------------------------------------------------------------------------

def ensure_table_exists(client: bigquery.Client) -> None:
    """Create the BigQuery dataset and table if they do not exist yet."""
    dataset_ref = bigquery.DatasetReference(BIGQUERY_PROJECT, BIGQUERY_DATASET)
    try:
        client.get_dataset(dataset_ref)
    except Exception:
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = "US"
        client.create_dataset(dataset, exists_ok=True)
        logger.info("Created dataset %s.%s", BIGQUERY_PROJECT, BIGQUERY_DATASET)

    table_ref = dataset_ref.table(BIGQUERY_TABLE)
    schema = [
        bigquery.SchemaField("id",         "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("title",      "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("link",       "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("source",     "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("pub_date",   "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("content",    "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("crawl_date", "TIMESTAMP", mode="REQUIRED"),
    ]
    table = bigquery.Table(table_ref, schema=schema)
    client.create_table(table, exists_ok=True)
    logger.info("Table %s.%s.%s is ready", BIGQUERY_PROJECT, BIGQUERY_DATASET, BIGQUERY_TABLE)


def insert_rows(client: bigquery.Client, rows: list[dict]) -> int:
    """
    Stream-insert rows into BigQuery.
    Returns the number of rows successfully inserted.
    """
    if not rows:
        return 0

    table_id = f"{BIGQUERY_PROJECT}.{BIGQUERY_DATASET}.{BIGQUERY_TABLE}"
    errors = client.insert_rows_json(table_id, rows)

    if errors:
        logger.error("BigQuery insert errors: %s", errors)
        # Count successfully inserted rows (approximate via absence of errors per row)
        failed = len(errors)
        return len(rows) - failed

    return len(rows)


# ---------------------------------------------------------------------------
# Cloud Function entry point
# ---------------------------------------------------------------------------

@functions_framework.http
def collect_ai_news(request):
    """
    HTTP-triggered Cloud Function.

    Flow:
      1. Parse RSS feeds → collect AI-related links
      2. Deduplicate against existing BigQuery rows
      3. Crawl full article content for new links
      4. Insert enriched rows into BigQuery
      5. Return a JSON summary
    """
    run_start = datetime.now(timezone.utc)
    logger.info("=== collect_ai_news triggered at %s ===", run_start.isoformat())

    bq_client = bigquery.Client(project=BIGQUERY_PROJECT)

    # --- 1. RSS collection ---
    articles = collect_links_from_rss()
    if not articles:
        return {"status": "ok", "message": "No articles found in RSS feeds.", "inserted": 0}, 200

    # --- 2. Deduplication ---
    ensure_table_exists(bq_client)
    new_articles = filter_new_links(bq_client, articles)
    if not new_articles:
        return {"status": "ok", "message": "All articles already in BigQuery.", "inserted": 0}, 200

    # --- 3. Crawl content ---
    rows_to_insert: list[dict] = []
    crawl_date_str = run_start.isoformat()

    for i, article in enumerate(new_articles):
        link  = article["link"]
        title = article["title"]
        logger.info("[%d/%d] Crawling: %s", i + 1, len(new_articles), title[:60])

        content = crawl_content(link)

        rows_to_insert.append({
            "id":         str(uuid.uuid4()),
            "title":      title,
            "link":       link,
            "source":     article.get("source", ""),
            "pub_date":   article.get("pub_date", ""),
            "content":    content,
            "crawl_date": crawl_date_str,
        })

        # Polite delay to avoid hammering servers
        #time.sleep(random.uniform(1.0, 3.0))

        # Batch-insert every 50 rows to keep memory usage bounded
        if len(rows_to_insert) >= 50:
            inserted = insert_rows(bq_client, rows_to_insert)
            logger.info("Batch inserted %d rows", inserted)
            rows_to_insert = []

    # --- 4. Insert remaining rows ---
    inserted_total = 0
    if rows_to_insert:
        inserted_total += insert_rows(bq_client, rows_to_insert)

    run_end = datetime.now(timezone.utc)
    elapsed = (run_end - run_start).total_seconds()

    summary = {
        "status":           "ok",
        "rss_articles":     len(articles),
        "new_articles":     len(new_articles),
        "inserted":         inserted_total,
        "elapsed_seconds":  round(elapsed, 1),
        "run_at":           crawl_date_str,
    }
    logger.info("Run summary: %s", summary)
    return summary, 200
