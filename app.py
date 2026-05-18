from flask import Flask, request, abort
import os
import npb_team_stats as npb

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    QuickReply,
    QuickReplyItem,
    MessageAction
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

app = Flask(__name__)

# 🔑 保留您的正式憑證
LINE_CHANNEL_ACCESS_TOKEN = 'DmjqjDUd46PY0uH4XDzfLub8ZBuKGBdCxjSlRwnGg1CpQ0Zl3OJgJLCjiNap3GMiehSzy6WOhpuJx8glSQPv/nl0xSu8ywkQtQwJNO22U2IYNr6g43EdQp+aPEI1Nr+dmCyQP0frMj2UD6q2RdGVHwdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = 'dcdc8182d2a1eca73a46d20f1035cc14'

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

def generate_line_report(team, games, st):
    n = st["total_games"]
    report = f"⚾ 【{team['short']}】 近 {n} 場戰報\n"
    report += "〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"
    
    pw = st["pyth_wp"]
    aw = st["actual_wp"]
    diff_wp = aw - pw
    trend = "🔥近期運氣佳" if diff_wp > 0.02 else "❄️近期運氣差" if diff_wp < -0.02 else "⚖️表現穩定"
    
    report += f"🎯 戰績：{st['wins']}勝 {st['losses']}敗 {st['draws']}平\n"
    report += f"📊 勝率：{aw:.3f} (畢氏預期: {pw:.3f})\n"
    report += f"💡 狀態：{trend}\n\n"
    
    hg, hs, ha = st["home_games"], st["home_scored"], st["home_allowed"]
    ag, as_, aa = st["away_games"], st["away_scored"], st["away_allowed"]
    if hg > 0:
        report += f"🏠 主場({hg}G)：均得 {hs/hg:.1f} / 均失 {ha/hg:.1f}\n"
    if ag > 0:
        report += f"✈️ 客場({ag}G)：均得 {as_/ag:.1f} / 均失 {aa/ag:.1f}\n"
    report += "\n"

    report += "📋 近 5 場賽況：\n"
    for g in games[:5]:
        v = "主" if g["venue"] == "home" else "客"
        r = "勝" if g["result"] == "W" else "敗" if g["result"] == "L" else "平"
        report += f"{g['date'][5:]} ({v}) vs {g['opponent'][:2]:<2} | {g['scored']}:{g['allowed']} {r}\n"

    # 牛棚與一分差比賽
    orn = st["one_run_games"]
    orw = st["one_run_wins"]
    if orn > 0:
        or_wp = orw / orn
        report += f"\n🤏 一分差戰績：{orn}場 {orw}勝 (勝率 {or_wp:.3f})"
    
    # 新增：大比分差 LINE 戰報輸出
    bon = st["blowout_games"]
    bow = st["blowout_wins"]
    bol = st["blowout_losses"]
    if bon > 0:
        bo_wp = bow / bon
        report += f"\n💥 大比分戰績：{bon}場 {bow}勝 {bol}敗 (勝率 {bo_wp:.3f})"
    
    return report

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_text = event.message.text.strip()
    
    target_team = None
    for t in npb.ALL_TEAMS:
        if user_text in [t['short'], t['name'], t['abbr']]:
            target_team = t
            break

    if target_team:
        try:
            games = npb.fetch_game_results(target_team, max_games=10)
            if not games:
                reply_text = f"⚠️ 目前無法獲取 {target_team['short']} 的資料。"
                reply_message = TextMessage(text=reply_text)
            else:
                st = npb.compute_all(games)
                reply_text = generate_line_report(target_team, games, st)
                reply_message = TextMessage(text=reply_text)
        except Exception as e:
            reply_text = f"⚠️ 抓取或處理資料時發生錯誤：\n{str(e)}\n請稍後再試。"
            reply_message = TextMessage(text=reply_text)
            
    else:
        quick_reply_items = []
        for t in npb.ALL_TEAMS:
            quick_reply_items.append(
                QuickReplyItem(
                    action=MessageAction(
                        label=t['short'],
                        text=t['short']
                    )
                )
            )
        
        reply_message = TextMessage(
            text="⚾ 歡迎使用日職進階戰報小幫手！\n\n請點選下方按鈕，選擇您想查詢的球隊：",
            quick_reply=QuickReply(items=quick_reply_items)
        )

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[reply_message]
            )
        )

if __name__ == "__main__":
    app.run(port=5000)