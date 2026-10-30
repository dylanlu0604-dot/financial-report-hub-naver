"""Fetch recent Naver Securities research reports and new PDF files."""

import csv
import hashlib
import json
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from scrapers import naver

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DOWNLOAD_DIR = ROOT / "downloads"
STATE_PATH = DATA_DIR / "reports.json"
CSV_PATH = DATA_DIR / "reports.csv"
WINDOW_DAYS = max(1, int(os.environ.get("NAVER_REPORT_WINDOW_DAYS", "10")))
CSV_FIELDS = (
    "Date",
    "Category",
    "Ticker",
    "Broker",
    "Name",
    "OriginalLink",
    "Link",
    "Downloaded",
    "DownloadedAt",
)

DOWNLOAD_SESSION = requests.Session()
DOWNLOAD_SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/129.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,application/octet-stream,*/*",
    }
)


def load_previous_reports():
    if not STATE_PATH.exists():
        return {}
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"無法讀取報告狀態檔 {STATE_PATH}: {exc}") from exc

    reports = payload.get("reports", []) if isinstance(payload, dict) else []
    return {
        report["OriginalLink"]: report
        for report in reports
        if isinstance(report, dict) and report.get("OriginalLink")
    }


def safe_pdf_name(report):
    identity = report.get("Link") or report.get("OriginalLink") or report.get("Name", "")
    suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10]
    label = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "_", report.get("Name", "report"))
    label = label.strip("._-")[:100] or "report"
    ticker = re.sub(r"[^A-Za-z0-9_-]", "", str(report.get("Ticker", "")))
    parts = [report.get("Date", ""), ticker, label, suffix]
    return "_".join(part for part in parts if part) + ".pdf"


def download_pdf(report):
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = DOWNLOAD_DIR / safe_pdf_name(report)
    temporary = destination.with_suffix(".pdf.part")
    headers = {"Referer": report.get("OriginalLink", "https://stock.naver.com/")}
    last_error = None

    for attempt in range(1, 4):
        time.sleep(random.uniform(0.8, 1.5))
        try:
            with DOWNLOAD_SESSION.get(
                report["Link"], headers=headers, timeout=(20, 90), stream=True
            ) as response:
                response.raise_for_status()
                with temporary.open("wb") as output:
                    for chunk in response.iter_content(chunk_size=1024 * 128):
                        if chunk:
                            output.write(chunk)
            with temporary.open("rb") as downloaded_file:
                signature = downloaded_file.read(5)
            if temporary.stat().st_size < 5 or signature != b"%PDF-":
                raise ValueError("回應內容不是有效的 PDF 檔案")
            temporary.replace(destination)
            return destination
        except (requests.RequestException, OSError, ValueError) as exc:
            last_error = exc
            temporary.unlink(missing_ok=True)
            if attempt < 3:
                time.sleep(2 ** (attempt - 1))

    raise RuntimeError(f"PDF 下載失敗：{last_error}") from last_error


def save_outputs(reports):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {
        "updated_at": now,
        "window_days": WINDOW_DAYS,
        "reports": reports,
    }
    STATE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(reports)


def main():
    os.environ["NAVER_REPORT_WINDOW_DAYS"] = str(WINDOW_DAYS)
    previous = load_previous_reports()
    reports = naver.scrape(cached_reports=previous)
    if not reports:
        raise RuntimeError("Naver 沒有回傳可用報告；保留舊狀態，請檢查連線或 API。")

    successful = 0
    downloaded_now = 0
    failed = 0
    current_reports = []
    for report in reports:
        existing = previous.get(report.get("OriginalLink"), {})
        record = dict(report)
        if existing.get("Downloaded"):
            record["Downloaded"] = True
            record["DownloadedAt"] = existing.get("DownloadedAt", "")
            record.pop("DownloadError", None)
            print(f"⏭️ 已成功下載，略過：{report['Name']}")
        else:
            try:
                path = download_pdf(report)
                record["Downloaded"] = True
                record["DownloadedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                record["Filename"] = path.name
                record.pop("DownloadError", None)
                successful += 1
                downloaded_now += 1
                print(f"⬇️ 已下載：{path.name}")
            except Exception as exc:
                record["Downloaded"] = False
                record["DownloadedAt"] = ""
                record["DownloadError"] = str(exc)
                failed += 1
                print(f"⚠️ {report['Name']}：{exc}")
        if record.get("Downloaded"):
            successful += 1 if existing.get("Downloaded") else 0
        current_reports.append(record)

    save_outputs(current_reports)
    print(
        f"\n✅ Naver 報告 {len(current_reports)} 篇；"
        f"成功下載 {successful} 篇、此次新下載 {downloaded_now} 篇、失敗 {failed} 篇。"
    )


if __name__ == "__main__":
    main()
