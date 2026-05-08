---
name: weekly-dashboard-update
description: 週次：治験ダッシュボード再生成 → Slack DMにGitHub Pages URLを送信
---

治験案件の週次ダッシュボード更新タスク。セッション間依存を排除し、ユーザーフォルダ内で完結する。

## 前提
- scraper.py と add_timeline.py はユーザーフォルダ内に存在
- ホスティングは GitHub Pages（`https://atsushisugamo-gif.github.io/chiken-dashboard/`）
- サンドボックスから git push できないため、デプロイはユーザーが Mac から行う前提（手動 push）
- データ更新は生活向上WEB と通院型試験を含む拡張版（入院のみ／入院+通院／通院のみ で分類）

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

## 2. スクレイパー実行（data.json 更新）

ユーザーフォルダ内の scraper.py を実行。実行時間目安：2-4分。サンドボックスでタイムアウトしても既存 data.json で続行する。

```python
import subprocess
scraper = os.path.join(user_folder, 'scraper.py')
result = subprocess.run(['python3', scraper], capture_output=True, text=True, timeout=600)
print("=== scraper output ===")
print(result.stdout)
if result.returncode != 0:
    print("WARN: scraper returned non-zero; stderr:", result.stderr[-1000:])
```

## 3. ダッシュボード再生成

```python
script = os.path.join(user_folder, 'add_timeline.py')
result2 = subprocess.run(['python3', script], capture_output=True, text=True, timeout=120)
print("=== add_timeline output ===")
print(result2.stdout)
if result2.returncode != 0:
    raise RuntimeError(f"add_timeline.py failed:\n{result2.stderr}")
```

## 4. Slack DM 通知（URL のみ）

channel_id: `U03QB903TJ4`（DM）。シンプルに公開URLだけ送る。

メッセージ本文（fixed）:
```
📊 治験ダッシュボード更新しました
https://atsushisugamo-gif.github.io/chiken-dashboard/
```

`mcp__73ceca66-fad3-4f74-ba4b-f0cde6bb974a__slack_send_message` を `channel_id="U03QB903TJ4"` で呼び出す。

## 注意事項

- 自動実行（スケジュール）と手動実行で同じ動作をする設計
- NFD/NFC 正規化に注意：`unicodedata.normalize('NFC', e)` で比較
- `prev_data.json` は `add_timeline.py` が毎回自動更新
- scraper.py がタイムアウトしたら既存 data.json を使って続行（dashboard再生成は必須）
- サンドボックスからは GitHub に git push できない。本タスクで生成した index.html はユーザーが Mac で `git push` してはじめて公開URL に反映される

## エラー時の対応

- ユーザーフォルダ未発見 → Slack DMで「ユーザーフォルダ未発見」通知
- `data.json` 未存在 → Slack DMで「データファイル未投入」通知
- `scraper.py` 実行エラー → 警告表示後、既存 data.json で続行
- `add_timeline.py` 実行エラー → stderr を Slack に貼って通知
- その他例外 → エラー全文を Slack に貼って通知
