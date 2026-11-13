# 想成為圖文作家的優理｜Yori Growth Log

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

1. 看新聞找靈感：透過 gemini-web 的 Google 搜尋，找台灣上班族午餐會聊的新聞，挑一則轉成辦公室日常的
   一個小場面（不照抄、不評論新聞）。新聞抓不到就從上班族日常自己找題材。用過的新聞記在 entries.json
   的 `inspiration`，之後避開。
2. 先寫四格（`write_comic`，2026-11-02 起）：同一個模型先想三個結局不同的版本，照 `GAG_RULES` 自我檢查
   （遮住第四格猜不猜得到結局、第四格有沒有在講道理）挑一個，寫成分鏡與標題橫幅。日記再圍著定稿的四格寫。
   改版原因：Day 0057–0094 的四格是寫完日記才拆出來的，常見的毛病是第四格把道理講出來、第三格先把笑點說掉、
   四格變成一天行程的四個地點、標題橫幅先講結局。劇本存在 entries.json 的 `comic`，之後可以回頭查哪篇沒成立。
   手藝經驗（`scripts/craft.json`）：每篇寫完有一步審稿，照四格規則與白話規則挑毛病，寫成一句心得存進 `notes`，
   連同結局類型（隔天優先換一種）。隔天寫四格與日記都會讀最近十條心得。每月整理日把心得折成最多八條 `principles`。
   畫圖前另有一步當天審稿（`review_comic`）：劇本跟四格標準有差距就照意見重寫一次。每篇的心得附分數（1–10）與有沒有重寫，
   之後看 `craft.json` 的分數變化，就知道經驗有沒有在累積。
   長進靠這份檔案累積，日記本身不寫分鏡、笑點設計、Yaze 看稿這類幕後話。審稿失敗不擋發佈。
3. 寫稿：llmshare 閘道（預設 deepseek-v4.1-flash，2026-10-01 從 kimi-k2.6 換過來，可用環境變數 TEXT_MODEL 覆蓋），餵語氣規範、三篇固定範本（Day 0027／0030／0033）、
   小規則帳本（`scripts/rules.json`，參考用）、最近十四天標題。題材分類有冷卻：最近三篇用過的分類當天不選。
   每篇收一條新的小規則回帳本（`new_rule`，只填欄位；2026-11-13 起圖文短文不再把小規則寫進文中，
   文字要 250 到 400 字、停在場面的最後一個動作或反應）。
   **語氣閘門**（`scripts/voice_gate.py`，規則在 `scripts/voice_rules.json`，2026-11-13 加）：寫完的圖文短文先過程式檢查
   （長度、句型黑名單、口頭禪七篇內最多一次、結尾和前十四篇太像），再給 deepseek 用審稿人的提示詞逐句挑
   「像語言模型寫的句子」，點名超過兩句就退。沒過就帶著被點名的原句重寫，最多三輪；三輪都沒過，或審稿人連不上，
   當天不發，workflow 開一張 issue。審稿人點過的句子記在 `voice_rules.json` 的 `ledger`，
   同一個四字以上的片段在兩天被點名，就自動加進口頭禪額度。
   量測：六段 2014–2020 年的真人散文，deepseek 最多點 2 句（全過）；六篇舊稿多在 3 句以上（退五篇）。
   gemini-web 當審稿人分不開真人與舊稿，所以不用。本機檢查某一篇：`python3 scripts/voice_gate.py --day 104`；
   本機試跑整晚但不產圖：`DRY_RUN=1 DRY_NO_IMAGE=1 python3 scripts/publish_entry.py`。
   每月 1 號是整理日：那天不看新聞，他回顧帳本，把兩三條相近的規則折併成一條（`merged_days` 移除舊條），
   日記內容就是整理的過程。帳本因此有界，context 不會無限長大。
   日記加了白話規則（第三人稱、東西寫本來的樣子、比喻最多一個）。提示詞一律寫「要做什麼」（2026-11-02 起），
   範例只留成功的那篇。2026-11-02 同一則四格各寫三篇、盲評挑不通順的句子：
   直寫中文 11 句、先寫英文再翻中文 12 句、直寫中文加白話規則 4 句。先英後中沒有變順，還多了翻譯腔，
   三篇都把 Yaze 譯成「亞澤」、改用「我」自稱，所以不採用。
   寫完先過一道標點修正（`fix_punct`）：破折號改逗號、中文之間的半形標點改全形；`python3 scripts/publish_entry.py --selftest` 檢查這段。
   （2026-09-24 改版前，Day 0034–0056 只餵自己的舊日記、每篇強制接著升級前一條規則，
   結果連續十幾天都在寫「寄出前還要檢查什麼」，所以改成上面這樣。）
4. 配圖：codex-image-service（gpt-image）畫一則四格漫畫，參考圖固定兩張錨（`scripts/style-anchor-*.jpg`：
   角色錨＋畫風錨）。
5. 產出 md＋html＋更新 index 與三份 JSON 鏡像，直接 commit。圖一律存 webp（q85），站上不放 PNG。任何一步失敗整篇不發，隔天再來。

管線只會改上面列的檔。`about.html`、`experiments/radar-v0.html` 不會被更新，所以這兩頁只寫不會變的事（不寫「目前第幾天」「最新一篇」），導覽列也不放指向某一篇的 Latest 連結，最新日記一律看 index。

需要的 repo secrets：`LLMSHARE_API_KEY`（寫稿）、`CODEX_IMAGE_KEY`（產圖）、`GEMINI_API_KEY`（看新聞，缺了就不看新聞照寫）。
手動補發：Actions 頁面 workflow_dispatch；同一天已有日記會自動跳過。

## Larch 版（2026-11-03 起）

日記也同步成 Larch 作品《優理的圖文日記》（`larch/config.json` 的 `project_id`）：月曆選一天，翻開那天的日記頁，
旁白逐句念，四格漫畫會放大正在講的那一格，右邊站著優理。

- 每晚發完日記後，同一個 workflow 跑 `scripts/larch_yori.py`：產日記頁背景（`docs/larch/bg/`），
  模型看圖替每句挑格子與表情（快取在 `larch/faces/`），再把每個月的白板推上 Larch。
  手動重跑用 workflow 的「只同步到 Larch」。
- 月曆、白板結構沿用格莉奇日記的 `scripts/larch_sync.py`；立繪在 `docs/larch/sprites/`。
- 標題畫面與對話框是 `larch/ui/title.html`、`larch/ui/dialogue.html`，跟線上不同時同步程式會推上去。
  書封、紙條、攤開的手帳、森林這幾張質感圖在 `docs/larch/ui/`，日記頁的內頁是 `larch/sheet.webp`（都是生圖後去背）。
- 本機看成品：`python3 scripts/larch_yori.py --local docs/_preview.json`，再用 larch-preview 開那個檔（素材走預覽伺服器的 `/files/`，還沒推上去也看得到）。
- 需要 Actions secret `LARCH_AGENT_KEY`；沒設的話這一步會跳過，日記照常發。

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
