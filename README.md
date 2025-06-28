# Musicbot
ぼくの考えた最強の音楽ぼっと

## 機能
以下のサイトが再生できます。
- YouTube (Premium)
- Spotify
- Apple Music
- Twitch
- Soundcloud
- Bandcamp
- Vimeo
- 添付ファイル

## 仕組み
- まずはLavalinkにURLを通す。
- 通らなかったらyt-dlpを通す。
- 通らなかったら諦める。

## 設定
- `.env.sample`をコピーして`.env`を作成し、BotのAPIキーを記入する。

## おまけ
musicbotフォルダにスラッシュコマンドを初期化するだけのものを入れてます。  
自由に使ってください。