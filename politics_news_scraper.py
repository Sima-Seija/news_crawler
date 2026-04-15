import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("PYTHONUTF8", "1")

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
}

SESSION = requests.Session()
SESSION.headers.update(BASE_HEADERS)


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[\r\t]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_url(url: str) -> str:
    url = url.strip()
    parsed = urlparse(url)
    if not parsed.scheme:
        return url
    cleaned = parsed._replace(query="", fragment="")
    return cleaned.geturl()


def get_html(url: str, allow_statuses=None) -> str:
    allow_statuses = allow_statuses or {200}
    resp = SESSION.get(url, timeout=20)
    if resp.status_code not in allow_statuses:
        raise RuntimeError(f"{url} returned {resp.status_code}")
    return resp.text


def page_text(node) -> str:
    for bad in node.select("script, style, noscript, iframe, aside, header, footer, .shareBox, .advertiseBox, .ads, .related, .relatedNews, .newsArticle-block, .news-flash-list, .owl-carousel, .page-link, .comment"):  # noqa: E501
        bad.decompose()
    lines = []
    for raw in node.get_text(separator="\n", strip=True).splitlines():
        text = clean_text(raw)
        if not text:
            continue
        if any(skip in text for skip in [
            "請繼續往下閱讀",
            "pic.twitter.com",
            "保證天天中獎",
            "點我下載",
            "下載APP",
            "APP看新聞",
            "活動辦法",
            "更多新聞",
            "延伸閱讀",
            "你可能會喜歡",
            "人氣點閱榜",
            "分享",
            "廣告",
        ]):
            continue
        lines.append(text)
    return clean_text(" ".join(lines))


def parse_datetime(value: str) -> str:
    if not value:
        return ""
    value = clean_text(value)
    value = value.replace("\u3000", " ")
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    patterns = [
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
    ]
    for pattern in patterns:
        try:
            dt = datetime.strptime(value, pattern)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            continue

    regexes = [
        r"(\d{4}/\d{2}/\d{2})[ T](\d{2}:\d{2}:\d{2})",
        r"(\d{4}/\d{2}/\d{2})[ T](\d{2}:\d{2})",
        r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})",
        r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})",
    ]
    for regex in regexes:
        m = re.search(regex, value)
        if m:
            date_part, time_part = m.group(1), m.group(2)
            if len(time_part) == 5:
                time_part += ":00"
            try:
                dt = datetime.fromisoformat(f"{date_part} {time_part}")
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                continue

    return value


def load_json_file(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json_file(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_state(path: str) -> set:
    state = load_json_file(path, {})
    urls = state.get("seen_urls") if isinstance(state, dict) else None
    return set(urls) if isinstance(urls, list) else set()


def save_state(path: str, seen_urls: set) -> None:
    save_json_file(path, {"seen_urls": sorted(seen_urls)})


def load_existing_articles(path: str) -> list:
    return load_json_file(path, []) if os.path.exists(path) else []


def write_articles(path: str, articles: list) -> None:
    save_json_file(path, articles)


def crawl_once(output_path: str, state_path: str, max_per_source: int) -> list[dict]:
    seen_urls = load_state(state_path)
    existing_articles = load_existing_articles(output_path)
    if not seen_urls and existing_articles:
        seen_urls = {article.get("url") for article in existing_articles if article.get("url")}
    new_articles = collect_articles(max_per_source=max_per_source, skip_urls=seen_urls)
    if new_articles:
        all_articles = existing_articles + new_articles
        write_articles(output_path, all_articles)
        save_state(state_path, seen_urls | {article["url"] for article in new_articles})
    return new_articles


def list_ltn() -> list[dict]:
    html = get_html("https://news.ltn.com.tw/list/breakingnews/politics")
    soup = BeautifulSoup(html, "lxml")
    result = []
    seen = set()
    for a in soup.select("a[href*='/news/politics/breakingnews/']"):
        href = a.get("href")
        if not href:
            continue
        url = urljoin("https://news.ltn.com.tw", href)
        if url in seen:
            continue
        seen.add(url)
        title = a.get("title") or a.get_text(separator=" ", strip=True)
        if title:
            result.append({"url": url, "title": clean_text(title)})
    return result[:20]


def parse_ltn_article(url: str) -> dict:
    html = get_html(url, allow_statuses={200})
    soup = BeautifulSoup(html, "lxml")
    title_node = soup.select_one("h1")
    title = clean_text(title_node.get_text(strip=True)) if title_node else ""
    time_node = soup.select_one("span.article_time") or soup.select_one("span.time")
    published_at = clean_text(time_node.get_text(strip=True)) if time_node else ""
    published_at = parse_datetime(published_at)
    content_node = soup.select_one("div[itemprop='articleBody']") or soup.select_one("article")
    content = page_text(content_node) if content_node else clean_text(soup.get_text(separator=" ", strip=True))
    return {
        "source": "LTN",
        "title": title,
        "published_at": published_at,
        "content": content,
        "url": url,
    }


def list_setn() -> list[dict]:
    html = get_html("https://www.setn.com/News.aspx?Category=1", allow_statuses={200, 404})
    soup = BeautifulSoup(html, "lxml")
    result = []
    seen = set()
    for a in soup.select("a[href*='News.aspx?NewsID=']"):
        href = a.get("href")
        if not href or "Category=" in href or href.startswith("/News.aspx?NewsID=") is False:
            continue
        url = urljoin("https://www.setn.com", href)
        if url in seen:
            continue
        seen.add(url)
        title = a.get_text(separator=" ", strip=True)
        if title and not title.isdigit():
            result.append({"url": url, "title": clean_text(title)})
    return result[:20]


def parse_setn_article(url: str) -> dict:
    html = get_html(url, allow_statuses={200})
    soup = BeautifulSoup(html, "lxml")
    title_node = soup.select_one("h1")
    title = clean_text(title_node.get_text(strip=True)) if title_node else ""
    published_at = ""
    if soup.select_one('meta[property="article:published_time"]'):
        published_at = soup.select_one('meta[property="article:published_time"]')['content']
    if not published_at and soup.select_one('meta[name="pubdate"]'):
        published_at = soup.select_one('meta[name="pubdate"]')['content']
    if not published_at:
        datetext = " ".join(x.get_text(separator=" ", strip=True) for x in soup.select("time, span.news-time, div.infobar, .author_box"))
        m = re.search(r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}", datetext)
        if m:
            published_at = m.group(0)
    published_at = parse_datetime(published_at)
    content_node = soup.select_one("#Content1") or soup.select_one("article")
    content = page_text(content_node) if content_node else clean_text(soup.get_text(separator=" ", strip=True))
    return {
        "source": "SETN",
        "title": title,
        "published_at": published_at,
        "content": content,
        "url": url,
    }


def list_tvbs() -> list[dict]:
    html = get_html("https://news.tvbs.com.tw/politics")
    soup = BeautifulSoup(html, "lxml")
    result = []
    seen = set()
    for a in soup.select("a[href*='/politics/']"):
        href = a.get("href")
        if not href:
            continue
        if "/politics/" not in href:
            continue
        if not re.search(r"/politics/\d+", href):
            continue
        url = urljoin("https://news.tvbs.com.tw", href)
        if url in seen:
            continue
        seen.add(url)
        title = a.get("title") or a.get_text(separator=" ", strip=True)
        if title:
            title = clean_text(title)
            if len(title) > 0 and not title.startswith("https://"):
                result.append({"url": url, "title": title})
    return result[:20]


def parse_tvbs_article(url: str) -> dict:
    html = get_html(url, allow_statuses={200})
    soup = BeautifulSoup(html, "lxml")
    title_node = soup.select_one("article h1.title") or soup.select_one("article h1") or soup.select_one("h1")
    title = clean_text(title_node.get_text(strip=True)) if title_node else ""
    published_at = ""
    date_text = " ".join(x.get_text(separator=" ", strip=True) for x in soup.select("article .author_box, article .author_box .author, time, span.date, span.publish-time"))
    if not published_at:
        m = re.search(r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}", date_text)
        if m:
            published_at = m.group(0)
    published_at = parse_datetime(published_at)

    content_node = soup.select_one("article")
    content = ""
    if content_node:
        for bad in content_node.select(".title_box, .bread, .share, .shareBox, .advertiseBox, .recommend, .related, .articleList, .ad, .social_bar, .article-btn, .promo"):  # noqa: E501
            bad.decompose()
        paragraphs = [clean_text(p.get_text(separator=" ", strip=True)) for p in content_node.select("p")]
        content_lines = []
        for line in paragraphs:
            if not line:
                continue
            if len(line) < 15:
                continue
            if any(skip in line for skip in ["首頁", "分享", "延伸閱讀", "你可能會喜歡", "人氣點閱榜", "APP", "廣告", "點我", "Google 新聞", "👉", "▶"]):
                continue
            content_lines.append(line)
        content = " ".join(content_lines)
    if not content:
        content = page_text(content_node) if content_node else clean_text(soup.get_text(separator=" ", strip=True))
    return {
        "source": "TVBS",
        "title": title,
        "published_at": published_at,
        "content": content,
        "url": url,
    }


def list_cna() -> list[dict]:
    html = get_html("https://www.cna.com.tw")
    soup = BeautifulSoup(html, "lxml")
    result = []
    seen = set()
    for a in soup.select("a[href*='/news/aipl/']"):
        href = a.get("href")
        if not href or not href.startswith("/news/aipl/"):
            continue
        if not re.search(r"/news/aipl/\d+\.aspx", href):
            continue
        url = urljoin("https://www.cna.com.tw", href)
        if url in seen:
            continue
        seen.add(url)
        title = a.get("title") or a.get_text(separator=" ", strip=True)
        if title:
            result.append({"url": url, "title": clean_text(title)})
    return result[:20]


def parse_cna_article(url: str) -> dict:
    html = get_html(url, allow_statuses={200})
    soup = BeautifulSoup(html, "lxml")
    title_node = soup.select_one("h1")
    title = clean_text(title_node.get_text(strip=True)) if title_node else ""
    published_at = ""
    if soup.select_one('meta[property="article:published_time"]'):
        published_at = soup.select_one('meta[property="article:published_time"]')['content']
    elif soup.select_one('meta[name="pubdate"]'):
        published_at = soup.select_one('meta[name="pubdate"]')['content']
    published_at = parse_datetime(published_at)
    content = ""
    for script in soup.select('script[type="application/ld+json"]'):
        text = script.get_text(strip=True)
        try:
            value = json.loads(text)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and item.get("@type") == "NewsArticle":
                        content = item.get("articleBody", "")
                        if content:
                            break
            elif isinstance(value, dict) and value.get("@type") == "NewsArticle":
                content = value.get("articleBody", "")
            if content:
                break
        except Exception:
            continue
    if not content:
        content_node = soup.select_one("article") or soup.select_one("section")
        content = page_text(content_node) if content_node else clean_text(soup.get_text(separator=" ", strip=True))
    published_at = parse_datetime(published_at)
    return {
        "source": "CNA",
        "title": title,
        "published_at": published_at,
        "content": clean_text(content),
        "url": url,
    }


def collect_articles(max_per_source: int = 10, skip_urls: set | None = None) -> list[dict]:
    skip_urls = skip_urls or set()
    all_articles = []
    seen_titles = set()
    seen_urls = set()
    sources = [
        (list_ltn, parse_ltn_article),
        (list_setn, parse_setn_article),
        (list_tvbs, parse_tvbs_article),
        (list_cna, parse_cna_article),
    ]

    for list_fn, parse_fn in sources:
        try:
            candidates = list_fn()
        except Exception as exc:
            print(f"跳過來源 {parse_fn.__name__}: {exc}")
            continue
        count = 0
        for item in candidates:
            if count >= max_per_source:
                break
            url = item["url"]
            if url in seen_urls or url in skip_urls:
                continue
            try:
                article = parse_fn(url)
            except Exception as exc:
                print(f"解析文章失敗 {url}: {exc}")
                continue
            normalized_title = clean_text(article.get("title", "")).lower()
            if not normalized_title:
                continue
            if normalized_title in seen_titles:
                continue
            seen_titles.add(normalized_title)
            seen_urls.add(url)
            all_articles.append(article)
            count += 1
    return all_articles


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取 LTN、SETN、TVBS、CNA 的政治新聞，輸出 JSON 結構化資料。")
    parser.add_argument("--output", "-o", default="politics_news.json", help="將結果寫入 JSON 檔案。")
    parser.add_argument("--state", default=".crawl_state.json", help="將抓取歷史紀錄儲存到狀態檔。")
    parser.add_argument("--max", type=int, default=5, help="每個來源最多抓取幾篇新的新聞。")
    parser.add_argument("--interval-hours", type=float, default=1.5, help="定時抓取間隔（小時）。")
    parser.add_argument("--once", action="store_true", help="只執行一次並退出。")
    args = parser.parse_args()

    if args.once:
        new_articles = crawl_once(args.output, args.state, args.max)
        print(f"本次抓到 {len(new_articles)} 篇新文章（每個來源最多 {args.max} 篇）。")
        return

    print(f"啟動定時抓取，每 {args.interval_hours} 小時抓一次，輸出到 {args.output}，狀態檔 {args.state}。每個來源最多 {args.max} 篇。")
    while True:
        new_articles = crawl_once(args.output, args.state, args.max)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 本次新增 {len(new_articles)} 篇文章（每個來源最多 {args.max} 篇）。")
        next_run = datetime.now() + timedelta(hours=args.interval_hours)
        print(f"下次執行：{next_run.strftime('%Y-%m-%d %H:%M:%S')}。")
        sleep_seconds = int(args.interval_hours * 3600)
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
