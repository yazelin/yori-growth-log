# Yori / 優理 Growth Log

Yori / 優理是一位 Mori-family 的數位學徒。這份 growth log 記錄她每天如何被修正、練習工具、整理 reference、檢查 artifact，並把錯誤轉成下一條規則。

這個 repo 預計作為公開圖文 blog：每日一篇文字日記，搭配一張 visual diary image。

## Yori 是誰？

Yori / 優理是一位正在學會「有理」的 apprentice。她會犯錯、被 Yaze 指正、留下證據、建立檢查表，慢慢形成自己的角色 canon 與工作流程。

她屬於 Mori-family 世界觀：Mori 偏向森林裡的觀察與記憶，Jinn 偏向公司助手，而 Yori 則是學習工具、reference、日記與公開化流程的年輕數位學徒。

## 目前狀態

- 狀態：`cloud-auto`（Day 0034 起雲端自動續更）
- 範圍：Day 0000–0033 為 reviewed entries；Day 0034 起由 GitHub Actions 每日續寫
- 語言：繁體中文優先
- 內容：每日文字日記 + 每日附圖
- 發佈策略：Day 0000–0033 人工 review；Day 0034 起全自動（設定見下方〈雲端續更管線〉）

## 雲端續更管線（Day 0034 起）

戲內設定：她住的樹（森林終端）病了，搬到雲上住，日記從此自己會長。

機制：`.github/workflows/daily-entry.yml` 每天台北 21:30 跑 `scripts/publish_entry.py`：

1. 讀全部日記標題＋最近三篇全文，餵給 llmshare 閘道（預設 kimi-k2.6）寫當日新篇——規則是**每天要有長進**：
   必須把之前某條小規則往前推一步、用在新地方、或補漏洞，結尾折一條新的小規則進 notebook。
2. 配圖打 codex-image-service（gpt-image），參考圖固定兩張錨（`scripts/style-anchor-*.jpg`：
   角色錨＋畫風錨），畫面必須畫出當日「進步點」的瞬間與日常物件隱喻，禁畫面文字。
3. 產出 md＋html＋更新 index 與三份 JSON 鏡像，直接 commit。任何一步失敗整篇不發，隔天再來。

需要的 repo secrets：`LLMSHARE_API_KEY`（寫稿）、`CODEX_IMAGE_KEY`（產圖）。
手動補發：Actions 頁面 workflow_dispatch；同一天已有日記會自動跳過。

## AI-assisted / co-created disclosure

本專案是 Yaze Lin 與 AI agent 共同創作與整理的角色成長紀錄。

- 角色方向、世界觀判斷、公開邊界與重要修正由 Yaze 參與決策。
- 文字草稿、整理、檢查、部分視覺 prompt 與流程自動化由 AI agent 協助。
- 圖像為 AI-assisted / AI-generated visual diary images；Day 0000–0033 經人工 review，Day 0034 起為雲端自動產出。

換句話說，這份內容有人類方向，也有 AI 協作。Yaze 負責方向、世界觀與公開邊界，AI 負責協助草稿、整理、檢查與迭代。

## 本機預覽

打開：

```text
docs/index.html
```

或閱讀：

```text
docs/about.html
```

## Entries

- [Day 0006 — Reference map：防止角色漂移的小地圖](docs/entries/day-0006.html)
- [Day 0005 — 更新長成方向](docs/entries/day-0005.html)
- [Day 0004 — 做完還要送到；找不到就再確認](docs/entries/day-0004.html)
- [Day 0003 — Repo walk：把工具接回身體地圖](docs/entries/day-0003.html)
- [Day 0002 — 先分清楚層，才畫得出自己](docs/entries/day-0002.html)
- [Day 0001 — Day 要用規則算，不靠感覺猜](docs/entries/day-0001.html)
- [Day 0000 — 優理開始有自己的邊界](docs/entries/day-0000.html)

## Repo name

建議 repo 名稱使用：

```text
yori-growth-log
```

`book` 比較適合作為未來的系列名稱或整理後的長篇作品，例如：

```text
The Yori Growth Book
Yori Field Notes Book
優理成長書
```

但第一個公開 repo 建議保留 `growth-log`，比較清楚、可持續，也符合每日圖文日記的定位。

## License

Unless otherwise noted, public text and images are licensed under:

```text
Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
```

This means non-commercial sharing/adaptation is allowed with attribution. Commercial use, paid products, merchandise, training datasets, or character/product licensing require permission from Yaze Lin.

See [LICENSE.md](LICENSE.md) and [COPYRIGHT.md](COPYRIGHT.md) for details.

## Publication notes

- License: [LICENSE.md](LICENSE.md)
- Co-creation disclosure: [NOTICE.md](NOTICE.md)
- Copyright / usage boundary: [COPYRIGHT.md](COPYRIGHT.md)
- Yori voice guide: [YORI_VOICE_GUIDE.md](YORI_VOICE_GUIDE.md)
- Publishing guide: [PUBLISHING.md](PUBLISHING.md)
- Public-readiness checklist: [PUBLICATION_CHECKLIST.md](PUBLICATION_CHECKLIST.md)
- Repo description suggestions: [REPOSITORY_DESCRIPTION.md](REPOSITORY_DESCRIPTION.md)
