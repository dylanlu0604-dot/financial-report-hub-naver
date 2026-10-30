# Financial Report Hub Naver

獨立抓取 Naver Securities 研究報告的專案，涵蓋公司、產業、投資、總經與債券五個分類。公司研究只保留 Naver 最新市值排行前五大公司。

## 抓取方式

- 每日台北時間 07:20 自動執行，也可從 GitHub Actions 手動啟動。
- 預設查詢近 10 天；可用 `NAVER_REPORT_WINDOW_DAYS` 調整。
- 逐篇解析 Naver 官方 PDF 連結，序列下載並檢查 PDF 檔頭。
- 以報告頁面連結記錄已成功下載的報告。每日只下載新報告或先前下載失敗的報告。
- `data/reports.json` 保存目前查詢區間的報告和下載狀態；`data/reports.csv` 與當次新下載的 PDF 由 GitHub Actions 保存為 14 天 artifact。
- PDF 不提交至 Git 倉庫，避免累積大型二進位檔案。

## 本機執行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -u main.py
```

輸出位於 `data/reports.json`、`data/reports.csv` 和 `downloads/`。

## 設定查詢天數

預設為 10 天。執行時可覆寫：

```bash
NAVER_REPORT_WINDOW_DAYS=10 python -u main.py
```
