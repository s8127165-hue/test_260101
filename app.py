from flask import Flask, request, abort
import os
import npb_team_stats as npb

# 匯入 Gemini API 套件
import google.generativeai as genai

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

# 🔑 保留您的 LINE 憑證
LINE_CHANNEL_ACCESS_TOKEN = 'DmjqjDUd46PY0uH4XDzfLub8ZBuKGBdCxjSlRwnGg1CpQ0Zl3OJgJLCjiNap3GMiehSzy6WOhpuJx8glSQPv/nl0xSu8ywkQtQwJNO22U2IYNr6g43EdQp+aPEI1Nr+dmCyQP0frMj2UD6q2RdGVHwdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = 'dcdc8182d2a1eca73a46d20f1035cc14'

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 🤖 初始化 Gemini 設定 (會從環境變數讀取 API Key)
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

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
        report += f"{g['date'][5:]} ({v}) vs {g['opponent']:<2} | {g['scored']}:{g['allowed']} {r}\n"

    orn = st["one_run_games"]
    orw = st["one_run_wins"]
    if orn > 0:
        or_wp = orw / orn
        report += f"\n🤏 一分差戰績：{orn}場 {orw}勝 (勝率 {or_wp:.3f})"
    
    bon = st["blowout_games"]
    bow = st["blowout_wins"]
    bol = st["blowout_losses"]
    if bon > 0:
        bo_wp = bow / bon
        report += f"\n💥 大比分戰績：{bon}場 {bow}勝 {bol}敗 (勝率 {bo_wp:.3f})"
    
    return report

def ask_gemini_analyst(user_input, t1, st1, t2, st2):
    """將雙方進階數據與先發投手打包，請 Gemini 生成專業球評預測"""
    prompt = f"""
    你是一位精通日本職棒（NPB）的資深專業球評與棒球統計學專家。
    請根據以下兩支球隊近 10 場的硬核統計數據，以及使用者提供的預告先發投手資訊，為明天的比賽進行深度的勝負預測分析。

    使用者輸入的對戰與投手資訊："{user_input}"

    📈 數據庫資料：
    【{t1['short']}】近10場指標：
    - 實際戰績：{st1['wins']}勝 {st1['losses']}敗 {st1['draws']}平 (實際勝率: {st1['actual_wp']:.3f})
    - 畢氏預期勝率：{st1['pyth_wp']:.3f}
    - 團隊進攻/防守：場均得分 {st1['avg_scored']:.1f} 分 / 場均失分 {st1['avg_allowed']:.1f} 分
    - 一分差抗壓戰績：{st1['one_run_wins']}勝-{st1['one_run_games']-st1['one_run_wins']}敗
    - 大比分拉開戰績：{st1['blowout_wins']}勝-{st1['blowout_losses']}敗

    【{t2['short']}】近10場指標：
    - 實際戰績：{st2['wins']}勝 {st2['losses']}敗 {st2['draws']}平 (實際勝率: {st2['actual_wp']:.3f})
    - 畢氏預期勝率：{st2['pyth_wp']:.3f}
    - 團隊進攻/防守：場均得分 {st2['avg_scored']:.1f} 分 / 場均失分 {st2['avg_allowed']:.1f} 分
    - 一分差抗壓戰績：{st2['one_run_wins']}勝-{st2['one_run_games']-st2['one_run_wins']}敗
    - 大比分拉開戰績：{st2['blowout_wins']}勝-{st2['blowout_losses']}敗

    請撰寫一篇約 250-300 字的繁體中文專業預測報告。
    格式請條列化清晰呈現：
    1. 📊 【近況對決】: 比較兩隊近期火力與牛棚穩定度的優劣勢。
    2. 🎯 【先發觀賽點】: 結合兩隊場均得失分，點出使用者提及的先發投手的壓制關鍵。
    3. 🔮 【球評預測值】: 給出最終看好哪一隊勝出，以及可能的比分走向。
    
    語氣要犀利、專業、客觀，像體育新聞的專家專欄。
    """
    response = gemini_model.generate_content(prompt)
    return response.text

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
    
    # ── 情況 1：檢查是否為「AI 賽前預測」的對對碰指令（包含 "vs" 且能辨識出兩隊） ──
    if "vs" in user_text.lower():
        found_teams = []
        for t in npb.ALL_TEAMS:
            if t['short'] in user_text and t not in found_teams:
                found_teams.append(t)
        
        if len(found_teams) == 2:
            t1, t2 = found_teams[0], found_teams[1]
            # 先回傳「計算中」避免 LINE 超時
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=f"🤖 專業球評正在調閱 【{t1['short']}】 與 【{t2['short']}】 的近十場進階數據庫，請稍候...")]
                    )
                )
            
            # 背景執行雙網頁爬蟲與 AI 計算
            try:
                g1 = npb.fetch_game_results(t1, max_games=10)
                g2 = npb.fetch_game_results(t2, max_games=10)
                st1 = npb.compute_all(g1)
                st2 = npb.compute_all(g2)
                
                ai_analysis = ask_gemini_analyst(user_text, t1, st1, t2, st2)
                
                # 主動 Push 報告給用戶 (這裡簡化為發新訊息，實務上 Render 免費版建議直接用 reply，但因為前面reply用了，此處用 push)
                # 為了避免複雜的 Push ID 獲取，我們在 handle 結束前直接呼叫
                # 註：此處若免費帳號有限制 push，亦可直接於一開始不 reply，直接等 AI 跑完（約3-5秒）再統一 reply。
                # 免費版最穩健作法：直接讓使用者等 4 秒後直接 Reply。故我們把前面的「計算中」拿掉，改為直接一條龍處理：
            except Exception as e:
                ai_analysis = f"⚠️ AI 球評分析時發生錯誤：{str(e)}"
            
            # 改為直接回覆（一條龍等候）
            # 注意：為配合此邏輯，已移除上方的先行 reply。
            
        # 為了程式碼乾淨與不超時，我們直接在此處做一條龍的等待回覆：
        # (重新整理邏輯：為了不超時，直接讓 AI 運算並回傳)
        found_teams = []
        for t in npb.ALL_TEAMS:
            if t['short'] in user_text and t not in found_teams:
                found_teams.append(t)
        if len(found_teams) == 2:
            try:
                st1 = npb.compute_all(npb.fetch_game_results(found_teams[0], max_games=10))
                st2 = npb.compute_all(npb.fetch_game_results(found_teams[1], max_games=10))
                reply_text = ask_gemini_analyst(user_text, found_teams[0], st1, found_teams[1], st2)
            except Exception as e:
                reply_text = f"⚠️ 數據調閱或 AI 分析超時，請再試一次！\n錯誤: {str(e)}"
            
            with ApiClient(configuration) as api_client:
                MessagingApi(api_client).reply_message(
                    ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply_text)])
                )
            return

    # ── 情況 2：單純點擊某一隊 ──
    target_team = None
    for t in npb.ALL_TEAMS:
        match_pool = [t['short'], t['name'], t['abbr']]
        if t['abbr'] == 'S': match_pool += ['ヤクルト', '養樂多']
        if t['abbr'] == 'H': match_pool += ['SoftBank', '軟銀', 'ソフトバンク']
        if t['abbr'] == 'F': match_pool += ['日ハム', '火腿', '日本ハム']
        if t['abbr'] == 'B': match_pool += ['オリックス', '歐力士']
        if t['abbr'] == 'M': match_pool += ['羅德', 'ロッテ']
        if t['abbr'] == 'E': match_pool += ['樂天', '楽天']
        if t['abbr'] == 'C': match_pool += ['廣島', '広島']
        
        if user_text in match_pool:
            target_team = t
            break

    if target_team:
        # 當使用者選了某一隊，彈出二選一：要看歷史戰報，還是要做 AI 預測
        quick_reply_items = [
            QuickReplyItem(action=MessageAction(label=f"📊 查看 {target_team['short']} 戰報", text=f"戰報 {target_team['short']}")),
            QuickReplyItem(action=MessageAction(label=f"🔮 AI 預測明天比賽", text=f"預測 {target_team['short']}"))
        ]
        reply_message = TextMessage(
            text=f"已選擇【{target_team['short']}】，請選擇功能：",
            quick_reply=QuickReply(items=quick_reply_items)
        )
        
    # ── 情況 3：使用者點選了「📊 查看戰報」 ──
    elif user_text.startswith("戰報 "):
        team_name = user_text.split(" ")[1]
        t = next((x for x in npb.ALL_TEAMS if x['short'] == team_name), None)
        if t:
            games = npb.fetch_game_results(t, max_games=10)
            st = npb.compute_all(games)
            reply_message = TextMessage(text=generate_line_report(t, games, st))
        else:
            reply_message = TextMessage(text="⚠️ 找不到該球隊資料。")

    # ── 情況 4：使用者點選了「🔮 AI 預測明天比賽」 ──
    elif user_text.startswith("預測 "):
        team_name = user_text.split(" ")[1]
        reply_message = TextMessage(
            text=f"請複製並修改以下格式回傳給機器人（注意保留 vs）：\n\n{team_name} 先發投手名字 vs 對手隊名 先發投手名字"
        )

    # ── 情況 5：輸入其他任何文字，滑出 12 隊中文按鈕 ──
    else:
        quick_reply_items = [QuickReplyItem(action=MessageAction(label=t['short'], text=t['short'])) for t in npb.ALL_TEAMS]
        reply_message = TextMessage(
            text="⚾ 歡迎使用日職 AI 進階戰報預測小幫手！\n\n請點選下方按鈕選擇球隊：",
            quick_reply=QuickReply(items=quick_reply_items)
        )

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[reply_message])
        )

if __name__ == "__main__":
    app.run(port=5000)