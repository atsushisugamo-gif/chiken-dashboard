#!/bin/bash

# ── 治験ダッシュボード 自動セットアップ ──

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.chiken.dashboard.server.plist"
PLIST_SRC="$SCRIPT_DIR/$PLIST_NAME"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo ""
echo "🏥 治験ダッシュボード セットアップ中..."
echo ""

# LaunchAgentsフォルダがなければ作成
mkdir -p "$HOME/Library/LaunchAgents"

# 既存があればアンロード
if [ -f "$PLIST_DST" ]; then
    launchctl unload "$PLIST_DST" 2>/dev/null
fi

# plistをコピー
cp "$PLIST_SRC" "$PLIST_DST"

# サーバー起動登録
launchctl load "$PLIST_DST"

echo "✅ セットアップ完了！"
echo ""
echo "📊 ダッシュボードURL: http://localhost:8765"
echo "   → Mac起動時に自動で立ち上がります"
echo "   → ブラウザで上のURLを開くだけでOK"
echo ""

# ブラウザで開く
sleep 1
open "http://localhost:8765"

echo "ブラウザが開きました。このウィンドウは閉じてOKです。"
echo ""
read -p "Enterキーで閉じます..."
