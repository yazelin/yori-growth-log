# Publishing Guide

Target repo name:

```text
yori-growth-log
```

Recommended visibility:

```text
public
```

Recommended GitHub Pages source:

```text
branch: main
folder: /docs
```

## First publish flow

Only run these commands after explicit approval to create/push the public repo.

```bash
cd public-export

gh repo create yori-growth-log --public --source=. --remote=origin --push

gh repo edit yori-growth-log \
  --description "Yori / 優理 growth log — a Mori-family AI apprentice diary with daily images" \
  --homepage "https://yazelin.github.io/yori-growth-log/"
```

Then enable GitHub Pages in repo settings:

```text
Settings → Pages → Build and deployment → Deploy from a branch → main / docs
```

Or via API/gh if available in the environment.

## Daily reviewed publish flow

Future entries should follow the current public-site shape, not the old Markdown-link prototype.

1. Generate private entry + prompt.
2. Generate image.
3. Run delivery validator.
4. Export public-safe entry and image.
5. Convert the entry into an HTML page under `docs/entries/day-NNNN.html`.
6. Keep the Markdown source under `docs/entries/day-NNNN.md` for versioned source text.
7. Update `manifest.json` and `docs/entries.json`.
8. Update `docs/index.html` with latest-first ordering.
9. Point `Latest` to the newest HTML page, not the Markdown file.
10. Run the Yori voice check in `YORI_VOICE_GUIDE.md`.
11. Check homepage layout guards: 首頁 `.panel` 保留 `margin-block:28px`，避免 About / Radar stacked cards 黏在一起。
12. Review the public diff.
13. Commit and push after approval.


Required site behavior:

```text
Latest → docs/entries/day-NNNN.html
Homepage cards → newest first
Read links → HTML pages, not .md files
Markdown files → source/archive only
```

Recommended commit message format:

```text
Add Day 0007 Yori growth log
```

## Rollback

If a public entry/image has an issue:

```bash
git revert <commit-sha>
git push
```

For urgent removal, delete or replace the affected entry/image and push a corrective commit, then document the reason in the repo issue or maintenance note.
