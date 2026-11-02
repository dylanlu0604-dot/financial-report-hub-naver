"""Translate Korean RSS titles to Traditional Chinese with a cached open model."""

import json
import os
import re
import tempfile
from pathlib import Path


CACHE_PATH = Path(__file__).with_name("rss_title_translations.json")
PIPELINE_VERSION = "m2m100-418m-ko-zh-s2twp-v1"
MODEL_ID = "facebook/m2m100_418M"
KOREAN_RE = re.compile(r"[\uac00-\ud7a3]")
REPEATED_CHAR_RE = re.compile(r"(.)\1{4,}")
REPEATED_PHRASE_RE = re.compile(r"(.{2,8})\1{4,}")
BAD_TRANSLATION_RE = re.compile(
    r"all rights reserved|copyright|所有權利|版权所有|版權所有|保留所有權利",
    re.IGNORECASE,
)


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


def _load_translator():
    import torch
    from opencc import OpenCC
    from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

    torch.set_num_threads(min(4, os.cpu_count() or 2))
    tokenizer = M2M100Tokenizer.from_pretrained(MODEL_ID)
    tokenizer.src_lang = "ko"
    model = M2M100ForConditionalGeneration.from_pretrained(MODEL_ID)
    model.eval()
    return torch, tokenizer, model, OpenCC("s2twp")


def _translate_batch(texts, translator):
    torch, tokenizer, model, traditional_converter = translator
    encoded = tokenizer(
        texts,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=256,
    )
    with torch.inference_mode():
        generated = model.generate(
            **encoded,
            forced_bos_token_id=tokenizer.get_lang_id("zh"),
            num_beams=4,
            max_new_tokens=160,
            no_repeat_ngram_size=3,
            repetition_penalty=1.15,
        )
    simplified = tokenizer.batch_decode(generated, skip_special_tokens=True)
    return [traditional_converter.convert(text).strip() for text in simplified]


def _is_plausible_translation(source, translated):
    if not translated or not re.search(r"[\u3400-\u9fff]", translated):
        return False
    if len(translated) > max(120, len(source) * 3):
        return False
    if REPEATED_CHAR_RE.search(translated) or REPEATED_PHRASE_RE.search(translated):
        return False
    if BAD_TRANSLATION_RE.search(translated):
        return False
    return True


def translate_report_titles(reports):
    """Return URL-to-title translations; invalid outputs fall back to Korean."""
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
        f"（{MODEL_ID}，GitHub Actions CPU）"
    )
    try:
        translator = _load_translator()
    except Exception as error:
        print(f"⚠️ 無法載入翻譯模型，本輪保留韓文原題，之後會重試：{error}")
        return result

    for start in range(0, len(pending), 8):
        batch = pending[start : start + 8]
        try:
            translations = _translate_batch([title for _, title in batch], translator)
        except Exception as error:
            print(f"⚠️ 翻譯批次失敗，本批保留韓文原題：{error}")
            continue

        for (url, title), translated in zip(batch, translations):
            if _is_plausible_translation(title, translated):
                cached_items[url] = {"source": title, "translated": translated}
                result[url] = translated
            else:
                print(f"⚠️ 翻譯結果異常，保留韓文原題：{title}")
                cached_items[url] = {"source": title, "translated": ""}

    _write_cache(cached_items)
    return result
