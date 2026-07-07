"""
news_collector.py — 新聞與重大事件蒐集

資料來源：
  - MOPS 公開資訊觀測站（重大訊息、財報公告）
  - RSS feeds（Yahoo Finance、MoneyDJ）

每個交易日自動更新。
"""

import logging
import re
from datetime import date, datetime
from typing import List, Optional

import feedparser
import pandas as pd
import requests

from src.core.result import CollectResult

from config import HTTP_HEADERS, HTTP_TIMEOUT, NEWS_RSS_FEEDS

logger = logging.getLogger(__name__)


# ── MOPS 重大訊息 API ─────────────────────────────────────────
MOPS_SIGNIFICANT_URL = "https://mops.twse.com.tw/mops/web/ajax_t38s000"

MOPS_HEADERS = {
    **HTTP_HEADERS,
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": "https://mops.twse.com.tw/",
}


def fetch_rss_news(max_per_feed: int = 50) -> List[dict]:
    """抓取 RSS 財經新聞。"""
    articles = []
    for feed_url in NEWS_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:max_per_feed]:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                pub_date = entry.get("published", "")
                link = entry.get("link", "")

                # 嘗試解析日期
                parsed_date = _parse_feed_date(pub_date)

                articles.append(
                    {
                        "title": title,
                        "summary": _clean_html(summary),
                        "date": parsed_date,
                        "source": _extract_domain(feed_url),
                        "link": link,
                        "category": "market",
                        "stock_ids": _extract_stock_ids(title + " " + summary),
                    }
                )
        except Exception as e:
            logger.warning(f"RSS feed failed ({feed_url}): {e}")

    logger.info(f"RSS news: {len(articles)} articles fetched.")
    return articles


def fetch_mops_announcements(trade_date: Optional[date] = None) -> List[dict]:
    """
    抓取 MOPS 重大訊息（最近一天）。
    使用 MOPS 的開放 API。
    """
    target = (trade_date or date.today()).isoformat().replace("-", "")
    # 台灣民國年
    roc_year = int(target[:4]) - 1911
    roc_date = f"{roc_year}{target[4:8]}"

    articles = []
    try:
        payload = {
            "step": "1",
            "firstin": "1",
            "off": "1",
            "queryName": "date",
            "inpuType": "date",
            "TYPEK": "all",
            "action": "1",
            "startdate": roc_date,
            "enddate": roc_date,
        }
        resp = requests.post(
            "https://mops.twse.com.tw/mops/web/ajax_t38s000",
            data=payload,
            headers=MOPS_HEADERS,
            timeout=HTTP_TIMEOUT,
        )
        if resp.status_code == 200:
            # MOPS 回傳 HTML，簡單解析
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(resp.text, "lxml")
            rows = soup.select("table tr")
            for row in rows[1:]:
                cols = row.select("td")
                if len(cols) < 4:
                    continue
                stock_id = cols[0].get_text(strip=True)
                subject = cols[3].get_text(strip=True) if len(cols) > 3 else ""
                articles.append(
                    {
                        "title": subject,
                        "summary": subject,
                        "date": trade_date or date.today(),
                        "source": "MOPS",
                        "link": "",
                        "category": "announcement",
                        "stock_ids": [stock_id] if stock_id else [],
                    }
                )
    except Exception as e:
        logger.warning(f"MOPS announcements failed: {e}")

    logger.info(f"MOPS announcements: {len(articles)} records.")
    return articles


def classify_news_sentiment(title: str, summary: str) -> dict:
    """
    規則式新聞情緒分類（利多/中性/利空）。
    AI 版本在 claude_analyst.py 中進行更精確分析。
    """
    text = (title + " " + summary).upper()

    # 利多關鍵字
    bullish_kws = [
        "獲利",
        "EPS創高",
        "EPS成長",
        "法人買超",
        "外資買",
        "獲大單",
        "接單滿載",
        "擴廠",
        "新產品",
        "新客戶",
        "漲停",
        "創新高",
        "業績亮眼",
        "超出預期",
        "上調目標價",
        "庫藏股",
        "股利",
    ]
    # 利空關鍵字
    bearish_kws = [
        "虧損",
        "跌停",
        "財報不如預期",
        "EPS下滑",
        "外資賣超",
        "法說下修",
        "獲利衰退",
        "減資",
        "重大訴訟",
        "內線交易",
        "退出市場",
        "停工",
        "下調目標價",
        "裁員",
    ]

    bull_count = sum(1 for kw in bullish_kws if kw in text)
    bear_count = sum(1 for kw in bearish_kws if kw in text)

    if bear_count > bull_count:
        sentiment = "bearish"
        score = max(0, 40 - bear_count * 10)
    elif bull_count > bear_count:
        sentiment = "bullish"
        score = min(90, 60 + bull_count * 5)
    else:
        sentiment = "neutral"
        score = 60

    return {
        "sentiment": sentiment,
        "news_score": float(score),
        "has_major_negative": bear_count >= 2,
    }


def classify_news_importance(title: str) -> int:
    """
    判斷新聞重要性（1-5 星）。
    """
    title_upper = title.upper()

    critical_kws = ["法說會", "財報", "重大訊息", "庫藏股", "減資", "合併"]
    high_kws = ["新產品", "新客戶", "大訂單", "擴廠", "策略合作"]
    medium_kws = ["EPS", "ROE", "法人", "外資"]

    if any(kw in title_upper for kw in critical_kws):
        return 5
    elif any(kw in title_upper for kw in high_kws):
        return 4
    elif any(kw in title_upper for kw in medium_kws):
        return 3
    elif len(title) > 20:
        return 2
    return 1


def classify_news_duration(category: str, title: str) -> str:
    """
    判斷事件影響期間：short / medium / long
    """
    title_upper = title.upper()

    long_kws = ["擴廠", "長期合作", "AI突破", "新產能", "策略合作"]
    medium_kws = ["法說會", "季報", "半年報"]

    if any(kw in title_upper for kw in long_kws):
        return "long"
    elif any(kw in title_upper for kw in medium_kws):
        return "medium"
    return "short"


def _extract_stock_ids(text: str) -> List[str]:
    """從文字中提取台股代號（4碼數字）。"""
    return list(set(re.findall(r"\b(\d{4})\b", text)))


def _parse_feed_date(date_str: str) -> date:
    """嘗試解析 RSS 日期字串。"""
    if not date_str:
        return date.today()
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str[: len(fmt)], fmt).date()
        except Exception:
            continue
    return date.today()


def _clean_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _extract_domain(url: str) -> str:
    m = re.search(r"https?://([^/]+)", url)
    return m.group(1) if m else url


# ── 統一介面 ──────────────────────────────────────────────────


class NewsCollector:
    """統一 Collector 介面（BaseCollector 協議）。"""

    name = "news"

    def collect(self, trade_date: Optional[date] = None, **kwargs) -> List[dict]:
        rss = fetch_rss_news()
        mops = fetch_mops_announcements(trade_date)
        return rss + mops

    def validate(self, data: List[dict]) -> tuple:
        if not isinstance(data, list):
            return False, "news data is not a list"
        if not data:
            return False, "no news articles collected"
        return True, "ok"

    def parse(self, data: List[dict]) -> pd.DataFrame:
        df = pd.DataFrame(data)
        for col in ("title", "summary", "source", "link"):
            if col not in df.columns:
                df[col] = ""
        if "date" not in df.columns:
            df["date"] = date.today()
        return df[["title", "summary", "date", "source", "link"]]

    def save(self, df: pd.DataFrame, session) -> int:
        # 新聞資料目前不持久化到 DB（按需使用）；保留介面相容性。
        return len(df)

    def run(
        self, trade_date: Optional[date] = None, session=None, **kwargs
    ) -> CollectResult:
        try:
            data = self.collect(trade_date)
        except Exception as e:
            return CollectResult.error(f"collect failed: {e}", source=self.name)
        ok, msg = self.validate(data)
        if not ok:
            logger.warning(f"[{self.name}] validate failed: {msg}")
            return CollectResult.warning(msg, source=self.name)
        df = self.parse(data)
        return CollectResult.success(len(df), source=self.name)
