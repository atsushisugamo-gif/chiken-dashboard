#!/bin/bash
# GitHub にデプロイするワンクリックスクリプト
# リポジトリURL は事前埋め込み済み: https://github.com/atsushisugamo-gif/chiken-dashboard

set -e
cd "$(dirname "$0")"

REPO_URL="https://github.com/atsushisugamo-gif/chiken-dashboard.git"

echo "=== 治験ダッシュボード GitHub デプロイ ==="
echo "作業ディレクトリ: $(pwd)"
echo "リポジトリ: $REPO_URL"
echo ""

# git があるか
if ! command -v git >/dev/null; then
    echo "❌ git がインストールされていません。https://git-scm.com/ から入れてください。"
    read -n 1 -s -r -p "Enterで閉じる"; exit 1
fi

# .gitignore の安全チェック
if [ ! -f .gitignore ] || ! grep -q "credentials.json" .gitignore; then
    echo "❌ .gitignore に credentials.json が含まれていません。中断します。"
    read -n 1 -s -r -p "Enterで閉じる"; exit 1
fi

# Cowork サンドボックスで作られた壊れた .git を一旦掃除
if [ -d .git ]; then
    echo "▶ 既存の .git を削除中..."
    rm -rf .git
fi

# git init & commit
echo "▶ git init"
git init -b main -q
git config user.email "$(git config --global user.email || echo atsushi.sugamo@gmail.com)"
git config user.name  "$(git config --global user.name  || echo Atsushi)"
git add .

echo ""
echo "▶ コミット予定のファイル:"
git status --short
echo ""
echo "▶ .gitignore で除外されるファイル:"
git status --ignored --short | grep "^!!" || echo "  (なし)"
echo ""
read -p "このままコミット&プッシュしますか？ [Y/n]: " ans
ans=${ans:-Y}
if [[ ! "$ans" =~ ^[Yy] ]]; then
    echo "中断しました。"
    read -n 1 -s -r -p "Enterで閉じる"; exit 0
fi

git commit -m "Initial commit: 治験入院案件ダッシュボード" -q
echo "✅ コミット完了"
echo ""

# remote 設定 & push
echo "▶ GitHub に push（認証ダイアログが出たら進めてください）"
git remote add origin "$REPO_URL" 2>/dev/null || git remote set-url origin "$REPO_URL"
if git push -u origin main; then
    echo ""
    echo "✅ push 完了！"
    echo ""
    echo "▶ 次にやること: GitHub Pages の有効化"
    echo "   ブラウザで以下を開いて、Branch を main / (root) にして Save:"
    echo "   https://github.com/atsushisugamo-gif/chiken-dashboard/settings/pages"
    echo ""
    echo "   数十秒後に  https://atsushisugamo-gif.github.io/chiken-dashboard/  で公開"
    echo ""
    # macOS なら自動で開く
    open "https://github.com/atsushisugamo-gif/chiken-dashboard/settings/pages" 2>/dev/null || true
else
    echo ""
    echo "⚠️ push が失敗しました。よくある原因:"
    echo "  ・GitHub の認証未設定 → Personal Access Token を作る"
    echo "    https://github.com/settings/tokens"
    echo "  ・あるいは GitHub CLI: brew install gh && gh auth login"
    echo "  再試行: git push -u origin main"
fi

echo ""
read -n 1 -s -r -p "Enterで閉じる"
