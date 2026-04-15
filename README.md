# news_crawler

這是一個爬取台灣政治新聞的專案，包含：

- `politics_news_scraper.py`：抓取 LTN、SETN、TVBS、CNA 政治新聞並儲存成 JSON
- `dashboard.py`：本機管理頁面，可檢視、編輯、刪除新聞，並控制爬蟲啟動/停止
- `web/`：前端介面 HTML/CSS/JS

## 上傳到 GitHub 的建議檔案

- `.gitignore`
- `requirements.txt`
- `README.md`
- `politics_news_scraper.py`
- `dashboard.py`
- `web/`

不要上傳：

- `.venv/`
- `__pycache__/`
- `politics_news.json`
- `.crawl_state.json`

## 在其他電腦上執行

1. 下載專案後，進入資料夾：
   ```powershell
   cd news_crawler
   ```

2. 建立虛擬環境：
   ```powershell
   py -3 -m venv .venv
   ```

3. 啟用虛擬環境：
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

4. 安裝所需套件：
   ```powershell
   pip install -r requirements.txt
   ```

5. 單次執行爬蟲：
   ```powershell
   py -3 politics_news_scraper.py --once --max 5 --output politics_news.json --state .crawl_state.json
   ```

6. 啟動管理網站：
   ```powershell
   py -3 dashboard.py
   ```

   然後開啟瀏覽器：
   ```text
   http://127.0.0.1:8000
   ```

## 注意

- `.gitignore` 已排除 `politics_news.json` 和 `.crawl_state.json`，這兩個檔案屬於執行後產生的資料，不需要上傳
- 若要保留專案資料，可以把原始碼、設定檔、`web/` 資料夾推上 GitHub
