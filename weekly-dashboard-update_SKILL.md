---
name: weekly-dashboard-update
description: 週次：治験ダッシュボード再生成（10サイト対応）→ git push で GitHub Pages 自動デプロイ → Slackチャンネル通知
---

治験入院案件の週次ダッシュボード更新タスク。セッション間依存を排除し、ユーザーフォルダ内で完結する。

## 前提
- scraper.py と add_timeline.py はユーザーフォルダ内に存在
- ホスティングは **GitHub Pages**（`https://atsushisugamo-gif.github.io/chiken-dashboard/`）
- リポジトリ: `atsushisugamo-gif/chiken-dashboard`
- `git push` するだけで GitHub Pages が自動デプロイされる
- データ更新は **全10サイト対応**。サイトごと逐次・REQUEST_DELAY=0.5秒スリープ
- ログインが必要なサイトは credentials.json から自動ログイン
- **prev_data.json は .gitignore 済み**（git add 対象に含めない）

## 1. ユーザーフォルダを特定（セッション名非依存）

```python
import os, unicodedata
base = '/sessions'
user_folder = None
for sess in os.listdir(base):
    mnt = os.path.join(base, sess, 'mnt')
    if not os.path.isdir(mnt):
        continue
    try:
        for e in os.listdir(mnt):
            if 'デイリー治験ダッシュボード' in unicodedata.normalize('NFC', e):
                user_folder = os.path.join(mnt, e)
                break
    except PermissionError:
        continue
    if user_folder:
        break

if not user_folder:
    raise RuntimeError("ユーザーフォルダが見つかりません")
print(f"User folder: {user_folder}")
```

## 2. 差分計算のため prev スナップショットを保存（add_timeline 前に必要）

`add_timeline.py` 実行後に `prev_data.json` は最新の `data.json` で上書きされてしまうため、**スクレイパー実行前に**現在の `prev_data.json` の内容をメモリに退避しておく。

```python
import json
prev_path = os.path.join(user_folder, 'prev_data.json')
if os.path.exists(prev_path):
    with open(prev_path) as f:
        prev_snapshot = json.load(f)
else:
    prev_snapshot = {'items': []}
```

## 3. スクレイパー実行

```python
import subprocess
scraper = os.path.join(user_folder, 'scraper.py')
result = subprocess.run(['python3', scraper], capture_output=True, text=True, timeout=1200)
print(result.stdout)
if result.returncode != 0:
    print("WARN:", result.stderr[-1000:])
```

## 4. ダッシュボード再生成（HTML 更新）

```python
script = os.path.join(user_folder, 'add_timeline.py')
result2 = subprocess.run(['python3', script], capture_output=True, text=True, timeout=120)
print(result2.stdout)
if result2.returncode != 0:
    raise RuntimeError(f"add_timeline.py failed:\n{result2.stderr}")
```

## 5. 差分計算（prev_snapshot vs 新 data.json）

```python
with open(os.path.join(user_folder, 'data.json')) as f:
    cur = json.load(f)

cur_by_url = {i['url']: i for i in cur['items']}
prev_by_url = {i['url']: i for i in prev_snapshot.get('items', [])}

new_items = [cur_by_url[u] for u in (set(cur_by_url) - set(prev_by_url))]
removed_items = [prev_by_url[u] for u in (set(prev_by_url) - set(cur_by_url))]
updated_items = []
for url in set(cur_by_url) & set(prev_by_url):
    c, p = cur_by_url[url], prev_by_url[url]
    if (c.get('compensation_num') != p.get('compensation_num')
        or c.get('title') != p.get('title')
        or c.get('scraped_start_date') != p.get('scraped_start_date')):
        updated_items.append((c, p))

updated_at = cur.get('updated_at', '不明')
errors = cur.get('errors', [])
total_diff = len(new_items) + len(updated_items) + len(removed_items)
```

## 6. GitHub Pages へデプロイ（差分があった場合のみ push）

**重要**: `prev_data.json` は .gitignore に含まれているため add に渡さない（渡すとエラー終了し後続コマンドが連鎖失敗する）。

```python
from datetime import datetime
push_ok = True
push_msg = ''
if total_diff > 0:
    commit_msg = f"chore: weekly update {datetime.now().strftime('%Y-%m-%d')} (+{len(new_items)}/~{len(updated_items)}/-{len(removed_items)})"
    cmds = [
        ['git', '-C', user_folder, 'add', 'data.json', 'index.html', 'dashboard.html'],
        ['git', '-C', user_folder, 'commit', '-m', commit_msg],
        ['git', '-C', user_folder, 'push', 'origin', 'main'],
    ]
    for cmd in cmds:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        print(f"$ {' '.join(cmd)}\n{r.stdout}{r.stderr}")
        if r.returncode != 0 and 'nothing to commit' not in (r.stdout + r.stderr):
            if cmd[3] == 'push':
                push_ok = False
    push_msg = '🚀 GitHub Pages デプロイ完了' if push_ok else '⚠️ git push 失敗。手動で確認してください'
else:
    push_msg = '（差分なしのためデプロイ省略）'
```

## 7. Slack 通知（差分のみ）

channel_id: `C0B2GPTPW10`（#毎週更新案件ダッシュボード）。

**差分が0件の場合**:

```
📊 *治験ダッシュボード週次更新（全10サイト）*

✅ 前回からの差分はありません（新規 0 件 / 更新 0 件 / 削除 0 件）

• データ更新日: {updated_at}
• 🌐 <https://atsushisugamo-gif.github.io/chiken-dashboard/|ダッシュボードを開く>

_次回自動更新: 来週月曜 9:00_
```

**差分がある場合**: 新規・更新・削除の3セクションを必要に応じて含める。各案件は `[サイト] タイトル抜粋 ¥報酬` の形式で最大20件まで。

```python
def fmt_item(i):
    return f"   • [{i.get('site','?')}] {i.get('title','')[:55]}  ¥{i.get('compensation_num',0):,}"

lines = ["📊 *治験ダッシュボード週次更新（全10サイト）*", ""]
lines.append(f"前回からの差分: 🆕 新規 {len(new_items)} / 📝 更新 {len(updated_items)} / 🗑 削除 {len(removed_items)}")
lines.append("")
if new_items:
    lines.append(f"*🆕 新規 ({len(new_items)}件)*")
    for i in new_items[:20]:
        lines.append(fmt_item(i))
    if len(new_items) > 20:
        lines.append(f"   …他 {len(new_items)-20} 件")
    lines.append("")
if updated_items:
    lines.append(f"*📝 更新 ({len(updated_items)}件)*")
    for c, p in updated_items[:20]:
        change = []
        if c.get('compensation_num') != p.get('compensation_num'):
            change.append(f"¥{p.get('compensation_num',0):,}→¥{c.get('compensation_num',0):,}")
        if c.get('scraped_start_date') != p.get('scraped_start_date'):
            change.append(f"日程 {p.get('scraped_start_date')}→{c.get('scraped_start_date')}")
        suffix = ' (' + ', '.join(change) + ')' if change else ''
        lines.append(fmt_item(c) + suffix)
    if len(updated_items) > 20:
        lines.append(f"   …他 {len(updated_items)-20} 件")
    lines.append("")
if removed_items:
    lines.append(f"*🗑 削除 ({len(removed_items)}件)*")
    for i in removed_items[:20]:
        lines.append(fmt_item(i))
    if len(removed_items) > 20:
        lines.append(f"   …他 {len(removed_items)-20} 件")
    lines.append("")
lines.append(f"• データ更新日: {updated_at}")
if errors:
    lines.append(f"• ⚠️ エラー: {' / '.join(errors)}")
lines.append(f"• {push_msg}")
lines.append("• 🌐 <https://atsushisugamo-gif.github.io/chiken-dashboard/|ダッシュボードを開く>")
lines.append("")
lines.append("_次回自動更新: 来週月曜 9:00_")
message = "\n".join(lines)
```

その後、Slack ツールで `channel_id='C0B2GPTPW10'`, `message=message` を送信。

## 注意事項

- 自動実行（スケジュール）と手動実行で同じ動作をする設計
- NFD/NFC 正規化に注意：`unicodedata.normalize('NFC', e)` で比較
- **prev_data.json は scraper 実行前にメモリへ退避**してから差分計算（順序に注意）
- **prev_data.json は git add に渡さない**（.gitignore 済み・連鎖失敗の原因になる）
- 個別サイトが落ちても errors[] に記録して他サイトの処理は継続
- git push のために GitHub への認証（PAT または SSH キー）が設定済みである前提
- main ブランチが origin/main を追跡している前提（初回 push 済み: commit 8245f1b）

## エラー時の対応

- ユーザーフォルダ未発見 → Slackチャンネル `C0B2GPTPW10` で通知
- `data.json` 未存在 → Slackチャンネル `C0B2GPTPW10` で通知
- `scraper.py` 全体エラー → 警告表示後、既存 data.json で続行
- `add_timeline.py` 実行エラー → stderr を Slack に貼って通知
- 個別サイトのスクレイプエラー → errors[] に記録され、Slack 通知の「⚠️ エラー」行に列挙
- `git push` 失敗 → Slack 通知に「⚠️ git push 失敗」を表示
- その他例外 → エラー全文を Slack に貼って通知