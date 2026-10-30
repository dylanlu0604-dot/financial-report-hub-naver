# Financial Report Hub Naver

這是完整的 Financial Report Hub Naver 專案：保留原本報告庫的抓取、PDF 下載、HTML 總覽、RSS、CSV／JSON、NotebookLM Markdown 與 PDF 文字分卷輸出，只保留 Naver Securities 作為資料來源。

網站首頁：https://dylanlu0604-dot.github.io/financial-report-hub-naver/

## 抓取範圍

- Naver Securities 公司、產業、投資、總經、債券五個分類。
- 公司研究只收錄 Naver 最新市值排行前十大公司。
- 預設抓取近 15 天；可用 `NAVER_REPORT_WINDOW_DAYS` 調整。
- 每日台北時間 07:20 自動執行，也可從 GitHub Actions 手動啟動。
- 已下載的 PDF 會依檔名保留，不會在每次執行時重複下載。

## 完整報告庫輸出

- `index.html`：可排序的報告總覽，包含來源、日期、頁數、PDF 連結及摘要欄。
- `data/reports.json`：完整報告資料及本機 PDF 路徑。
- `data/reports.csv`：適合試算表使用的報告清單；Actions 另提供 30 天下載 artifact。
- `data/reports_for_notebooklm.md`：NotebookLM 報告與 PDF 連結清單。
- `data/rss_naver_securities.xml`：Naver Securities RSS 訂閱源。
- `all report pdf/`：下載的原始 PDF，報告連結使用本倉庫的 GitHub Raw 檔案。
- `merged_pdfs/`：依來源合併並自動分卷的 PDF。
- `merged_plain_text_html/`：抽取 PDF 文字、過濾常見免責樣板後，依報告量產生 HTML 與 TXT 分卷，適合 NotebookLM 網址匯入。
- `notebooklm-five-source-extension/`：NotebookLM Chrome 擴充套件；依分卷清單匯入 Naver 報告文字來源，並建立分析筆記。

GitHub Actions 會更新以上輸出並提交回此倉庫。Naver 原始 PDF 與合併 PDF 因而會累積在 Git 歷史中。首次完整執行已生成第一批報告、RSS 與 NotebookLM 檔案。

## 本機執行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
python -u main.py
python merge_pdfs.py
python build_merged_plain_text_html.py
python check_generated_pdf_sizes.py
```

如需從 NotebookLM Markdown 清單批次下載 PDF，可執行：

```bash
python download_pdf.py
```

## 調整查詢天數

預設為 15 天。執行時可覆寫：

```bash
NAVER_REPORT_WINDOW_DAYS=15 python -u main.py
```
