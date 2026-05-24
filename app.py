from flask import Flask, request, abort
import os
import requests
from bs4 import BeautifulSoup
import npb_team_stats as npb
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

# 🤖 初始化 Gemini 設定
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
gemini_model = genai.GenerativeModel('gemini-2.0-flash')

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
    prompt = f"""
    你是一位精通日本職棒（NPB）的資深專業球評與棒球統計學專家。
    請根據以下兩支球隊近 10 場的硬核統計數據，以及最新的預告先發投手資訊，為明天的比賽進行深度的勝負預測分析。

    比賽資訊："{user_input}"

    📈 數據庫資料：
    【{t1['short']}】近10場指標：
    - 實際戰績：{st1['wins']}勝 {st1['losses']}敗 (勝率: {st1['actual_wp']:.3f}) / 畢氏勝率：{st1['pyth_wp']:.3f}
    - 場均得失分：得 {st1['avg_scored']:.1f} / 失 {st1['avg_allowed']:.1f}
    - 一分差戰績：{st1['one_run_wins']}勝-{st1['one_run_games']-st1['one_run_wins']}敗 / 大比分戰績：{st1['blowout_wins']}勝-{st1['blowout_losses']}敗

    【{t2['short']}】近10場指標：
    - 實際戰績：{st2['wins']}勝 {st2['losses']}敗 (勝率: {st2['actual_wp']:.3f}) / 畢氏勝率：{st2['pyth_wp']:.3f}
    - 場均得失分：得 {st2['avg_scored']:.1f} / 失 {st2['avg_allowed']:.1f}
    - 一分差戰績：{st2['one_run_wins']}勝-{st2['one_run_games']-st2['one_run_wins']}敗 / 大比分戰績：{st2['blowout_wins']}勝-{st2['blowout_losses']}敗

    請撰寫一篇約 250-300 字的繁體中文專業預測報告。
    格式請條列化清晰呈現：
    1. 📊 【近況對決】: 比較兩隊近期火力與牛棚穩定度的優劣勢。
    2. 🎯 【先發觀賽點】: 結合兩隊場均得失分，點出先發投手的壓制關鍵。
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
    
    # ── 情況 1：手動輸入「對戰」模式 (保留這個彩蛋，如果您想測試假設性的對決) ──
    if "vs" in user_text.lower():
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

    # ── 情況 2：辨識使用者點擊的球隊 ──
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

    # ── 情況 4：全新功能！全自動抓取 NPB 預告先發與 AI 分析 ──
    elif user_text.startswith("預測 "):
        team_name = user_text.split(" ")[1]
        t = next((x for x in npb.ALL_TEAMS if x['short'] == team_name), None)
        
        if t:
            try:
                # 步驟 A：爬取 NPB 官網預告先發
                url = "https://npb.jp/announcement/starter/"
                r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
                r.encoding = 'utf-8'
                soup = BeautifulSoup(r.text, "html.parser")
                # 轉成純文字並移除日文全形空白，方便 AI 閱讀
                raw_text = soup.get_text(separator=' ', strip=True).replace(" ", "")
                
                # 步驟 B：呼叫 Gemini 當資料擷取員，精準找出對手與投手
                extraction_prompt = f"""
                這是 NPB 官網「預告先發」的純文字：
                {raw_text[:4000]}
                
                請幫我找出【{team_name}】的「對戰對手」與雙方「先發投手」。
                請回傳一行文字，用半形逗號分隔，格式嚴格如下：
                對手簡稱,{team_name}的投手,對手的投手
                
                注意：
                1. 對手簡稱必須是這 12 個之一：巨人, 阪神, 廣島, DeNA, 中日, 養樂多, 軟銀, 西武, 火腿, 歐力士, 羅德, 樂天。
                2. 若無賽程，直接回傳: NOT_FOUND
                """
                matchup_str = gemini_model.generate_content(extraction_prompt).text.strip()
                
                if "NOT_FOUND" in matchup_str or "," not in matchup_str:
                    reply_message = TextMessage(text=f"⚠️ 目前 NPB 官網尚未公布【{team_name}】的預告先發，或是明日無賽程（週一通常休兵）。")
                else:
                    parts = [p.strip() for p in matchup_str.split(",")]
                    opp_name, my_pitcher, opp_pitcher = parts[0], parts[1], parts[2]
                    
                    opp_team = next((x for x in npb.ALL_TEAMS if x['short'] == opp_name), None)
                    if not opp_team:
                        reply_message = TextMessage(text=f"⚠️ 抓取成功，但無法辨識對手名稱：{opp_name}")
                    else:
                        # 步驟 C：自動調閱雙方近 10 場硬核數據
                        g1 = npb.fetch_game_results(t, max_games=10)
                        g2 = npb.fetch_game_results(opp_team, max_games=10)
                        st1 = npb.compute_all(g1)
                        st2 = npb.compute_all(g2)
                        
                        # 步驟 D：呼叫 Gemini 球評進行專業賽前預測
                        user_input_mock = f"預告先發：【{team_name}】{my_pitcher} vs 【{opp_name}】{opp_pitcher}"
                        analysis_text = ask_gemini_analyst(user_input_mock, t, st1, opp_team, st2)
                        
                        reply_message = TextMessage(text=f"✅ 已自動取得預告先發資料！\n{user_input_mock}\n\n{analysis_text}")
                        
            except Exception as e:
                reply_message = TextMessage(text=f"⚠️ 自動查詢先發或分析時發生網路錯誤：\n{str(e)}")

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