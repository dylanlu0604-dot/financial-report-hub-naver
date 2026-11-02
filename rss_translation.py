"""Translate Korean report titles for the Naver RSS feed with Argos Translate."""

import json
import os
import re
import tempfile
from pathlib import Path


CACHE_PATH = Path(__file__).with_name("rss_title_translations.json")
PIPELINE_VERSION = "argos-ko-en-1.1-en-zt-1.9-v1"
KOREAN_RE = re.compile(r"[\uac00-\ud7a3]")


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
            "w",
            encoding="utf-8",
            dir=CACHE_PATH.parent,
            delete=False,
        ) as temporary_file:
            json.dump(payload, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
            temporary_path = temporary_file.name
        os.replace(temporary_path, CACHE_PATH)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)


def _ensure_translation_pair(package, from_code, to_code):
    installed = package.get_installed_packages()
    if any(
        item.type == "translate"
        and item.from_code == from_code
        and item.to_code == to_code
        for item in installed
    ):
        return

    package.update_package_index()
    model = next(
        (
            item
            for item in package.get_available_packages()
            if item.type == "translate"
            and item.from_code == from_code
            and item.to_code == to_code
        ),
        None,
    )
    if model is None:
        raise RuntimeError(f"Argos 找不到翻譯模型：{from_code} → {to_code}")
    package.install_from_path(model.download())


def _get_translators():
    from argostranslate import package, translate

    _ensure_translation_pair(package, "ko", "en")
    _ensure_translation_pair(package, "en", "zt")
    return (
        translate.get_translation_from_codes("ko", "en"),
        translate.get_translation_from_codes("en", "zt"),
    )


def translate_report_titles(reports):
    """Return URL-to-title translations, reusing translations saved in Git."""
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

    print(f"🌐 RSS 有 {len(pending)} 個新或變更的韓文標題需要翻譯（Argos Translate）")
    try:
        korean_to_english, english_to_traditional = _get_translators()
    except Exception as error:
        print(f"⚠️ 無法載入免費翻譯模型，本輪保留原標題，之後會重試：{error}")
        return result

    for url, title in pending:
        try:
            english = korean_to_english.translate(title).strip()
            translated = english_to_traditional.translate(english).strip() if english else ""
            if not translated:
                raise ValueError("翻譯結果為空")
            cached_items[url] = {"source": title, "translated": translated}
            result[url] = translated
        except Exception as error:
            print(f"⚠️ 標題翻譯失敗，保留韓文原題：{title} ({error})")

    _write_cache(cached_items)
    return result
