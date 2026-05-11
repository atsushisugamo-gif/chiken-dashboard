# 治験入院案件ダッシュボード

複数の治験サイトから「入院案件」を集約して、一覧・タイムライン表示する個人ダッシュボード。

公開URL: https://atsushisugamo-gif.github.io/chiken-dashboard/

## 構成

```
index.html                   # 公開ページ本体（自己完結HTML、データ埋め込み済み）
dashboard.html               # index.html と同じ内容（バックアップ）
data.json                    # スクレイピング結果（入院案件一覧）
prev_data.json               # 差分検出用スナップショット（git管理外）
scraper.py                   # サイト巡回スクレイパー（全10サイト対応）
add_timeline.py              # data.json から index.html を再生成
collect_popularity.py        # 案件の人気度収集（補助）
inject_popularity.py         # 人気度をdataに注入（補助）
serve.py                     # ローカルプレビュー用 HTTP サーバ
credentials.example.json     # 認証情報テンプレ（コピーして credentials.json を作る）
credentials.json             # 実際の認証情報（git管理外）
```

## 使い方（ローカル）

1. `cp credentials.example.json credentials.json` で各サイトのメール/パスワードを記入
2. `python3 scraper.py` で `data.json` を更新
3. `python3 add_timeline.py` で `index.html` を再生成
4. `python3 serve.py` でローカルプレビュー（http://localhost:8000）

## GitHub Pages デプロイ

このリポジトリは `index.html` をルートに置く構成なので、GitHub Pages はそのまま動く。

1. リポジトリの **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: **main** / **/ (root)** を選択して **Save**
4. 数十秒で https://atsushisugamo-gif.github.io/chiken-dashboard/ が公開される

## 更新フロー

```bash
python3 scraper.py        # data.json を更新
python3 add_timeline.py   # index.html を再生成
git add data.json index.html dashboard.html
git commit -m "update YYYY-MM-DD"
git push
```

push するだけで GitHub Pages が再デプロイされる。

## セキュリティ

- `credentials.json` は **絶対にコミットしない**（`.gitignore` で除外済み）
- 公開リポジトリでは `data.json` は誰でも閲覧可能。サイト名と案件タイトル程度なので問題ないが、機密情報が混ざらないよう注意。
