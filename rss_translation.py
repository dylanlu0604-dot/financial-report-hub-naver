"""Translate Korean RSS titles to Traditional Chinese via Google's free web endpoint."""

import json
import os
import re
import tempfile
import time
from pathlib import Path

import requests


CACHE_PATH = Path(__file__).with_name("rss_title_translations.json")
PIPELINE_VERSION = "google-translate-ko-zh-tw-no-key-v1"
TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"
REQUEST_DELAY_SECONDS = 0.4
KOREAN_RE = re.compile(r"[\uac00-\ud7a3]")
HAN_RE = re.compile(r"[\u3400-\u9fff]")
REPEATED_CHAR_RE = re.compile(r"(.)\1{4,}")
REPEATED_PHRASE_RE = re.compile(r"(.{2,8})\1{4,}")
BAD_TRANSLATION_RE = re.compile(
    r"all rights reserved|copyright|所有權利|版权所有|版權所有",
    re.IGNORECASE,
)

CATEGORY_TRANSLATIONS = {
    "회사": "公司",
    "산업": "產業",
    "투자": "投資",
    "경제": "經濟",
    "채권": "債券",
}

# Keep publisher names out of machine translation. These are the publisher
# suffixes present in the current Naver feed; unknown Korean publishers are
# also kept in their original form.
PUBLISHER_TRANSLATIONS = {
    "하나증권": "韓亞證券",
    "키움증권": "Kiwoom 證券",
    "유진투자증권": "優進投資證券",
    "iM증권": "iM 證券",
    "대신증권": "大信證券",
    "한화투자증권": "韓華投資證券",
    "신한투자증권": "新韓投資證券",
    "IBK투자증권": "IBK 投資證券",
    "유안타증권": "元大證券",
    "교보증권": "教保證券",
    "SK증권": "SK 證券",
    "DS투자증권": "DS 投資證券",
    "다올투자증권": "DAOL 投資證券",
    "미래에셋증권": "未來資產證券",
    "현대차증권": "現代汽車證券",
    "메리츠증권": "Meritz 證券",
    "한국IR협의회": "韓國 IR 協議會",
}


def _read_cache():
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if payload.get("pipeline") != PIPELINE_VERSION:
            return {}
        items = payload.get("items", {})
        return items if isinstance(items, dict) else {}
    except (OSError, json.JSONDecodeError, AttributeError):
        return {}


def _write_cache(items):
    payload = {"pipeline": PIPELINE_VERSION, "items": items}
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=CACHE_PATH.parent, delete=False
        ) as temporary_file:
            json.dump(payload, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
            temporary_path = temporary_file.name
        os.replace(temporary_path, CACHE_PATH)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)


def _split_title(title):
    """Return preserved category, translatable title text, and publisher."""
    category = ""
    match = re.match(r"^(\[[^\]]+\])\s*", title)
    if match:
        category_name = match.group(1)[1:-1]
        category = f"[{CATEGORY_TRANSLATIONS.get(category_name, category_name)}]"
        title = title[match.end() :]

    publisher = ""
    if " - " in title:
        body, suffix = title.rsplit(" - ", 1)
        if suffix in PUBLISHER_TRANSLATIONS or suffix.endswith(("증권", "협의회")):
            title = body
            publisher = PUBLISHER_TRANSLATIONS.get(suffix, suffix)

    return category, title.strip(), publisher


def _translate_text(text, session):
    response = session.get(
        TRANSLATE_URL,
        params={
            "client": "gtx",
            "sl": "ko",
            "tl": "zh-TW",
            "dt": "t",
            "q": text,
        },
        timeout=(10, 30),
    )
    response.raise_for_status()
    payload = response.json()
    translated_parts = payload[0]
    return "".join(part[0] for part in translated_parts if part and part[0]).strip()


def _is_plausible_translation(source, translated):
    if not translated or not HAN_RE.search(translated):
        return False
    if KOREAN_RE.search(translated):
        return False
    if len(translated) > max(180, len(source) * 4):
        return False
    if REPEATED_CHAR_RE.search(translated) or REPEATED_PHRASE_RE.search(translated):
        return False
    if BAD_TRANSLATION_RE.search(translated):
        return False
    return True


def _format_title(category, translated, publisher):
    title = f"{category} {translated}".strip() if category else translated
    return f"{title} - {publisher}" if publisher else title


def translate_report_titles(reports):
    """Return URL-to-title translations; invalid or failed titles stay Korean."""
    cached_items = _read_cache()
    result = {}
    pending = []

    for report in reports:
        url = str(report.get("Link") or "")
        title = str(report.get("Name") or "")
        if not url or not title or not KOREAN_RE.search(title):
            continue

        cached = cached_items.get(url)
        if isinstance(cached, dict) and cached.get("source") == title:
            translated = cached.get("translated")
            if isinstance(translated, str) and translated.strip():
                result[url] = translated
            continue
        pending.append((url, title))

    if not pending:
        return result

    print(
        f"🌐 RSS 有 {len(pending)} 個新或變更的韓文標題待翻譯 "
        "（Google Translate 免費網頁端點，無需金鑰）"
    )
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; NaverRSSBot/1.0)",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        }
    )
    consecutive_errors = 0
    completed = 0

    for index, (url, title) in enumerate(pending, 1):
        category, translatable_text, publisher = _split_title(title)
        translated = ""
        last_error = None

        for attempt in range(3):
            try:
                translated = _translate_text(translatable_text, session)
                last_error = None
                break
            except (requests.RequestException, ValueError, IndexError, TypeError) as error:
                last_error = error
                if attempt < 2:
                    time.sleep(2 ** (attempt + 1))

        if last_error is not None:
            consecutive_errors += 1
            print(f"⚠️ Google 翻譯請求失敗，保留韓文原題：{last_error}")
            if consecutive_errors >= 3:
                print("⚠️ 連續 3 篇翻譯請求失敗；本輪剩餘標題保留韓文並於下次重試。")
                break
            continue

        consecutive_errors = 0
        translated = re.sub(r"\s+", " ", translated).strip()
        translated = re.sub(r"(?<=\])(?=[\u3400-\u9fff])", " ", translated)
        if _is_plausible_translation(translatable_text, translated):
            translated_title = _format_title(category, translated, publisher)
            cached_items[url] = {"source": title, "translated": translated_title}
            result[url] = translated_title
        else:
            print(f"⚠️ 翻譯結果未通過格式檢查，保留韓文原題：{title}")
            cached_items[url] = {"source": title, "translated": ""}

        completed += 1
        if completed % 25 == 0:
            _write_cache(cached_items)
            print(f"🌐 已處理 {completed}/{len(pending)} 個待翻譯標題")
        if index < len(pending):
            time.sleep(REQUEST_DELAY_SECONDS)

    _write_cache(cached_items)
    return result
