"""
npb_team_stats.py  v8_chinese_localized
資料來源：https://npb.jp/bis/teams/results_{npb_id}_{suffix}.html
新增：matplotlib 視覺化（得分分布直方圖、主客場趨勢折線、回戰系列賽分析）
擴充：大比分差判讀統計 (差距 >= 5分)
優化：全專案繁體中文在地化，自動翻譯日文對手名稱
"""

import argparse, json, re, sys, time, platform, math
from datetime import datetime
from collections import defaultdict

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("請先安裝：pip install requests beautifulsoup4"); sys.exit(1)

IS_WINDOWS = platform.system() == "Windows"
RESET="\033[0m"; BOLD="\033[1m"; DIM="\033[2m"
CYAN="\033[96m"; YELLOW="\033[93m"; GREEN="\033[92m"
RED="\033[91m";  WHITE="\033[97m"; MAGENTA="\033[95m"
BG_SEL="\033[48;5;24m"; BG_HDR="\033[48;5;236m"; BG_SEC="\033[48;5;17m"

if IS_WINDOWS:
    import ctypes
    try: ctypes.windll.kernel32.SetConsoleMode(ctypes.windll.kernel32.GetStdHandle(-11),7)
    except: pass

# ── 球隊資料 (簡稱已全部中文化) ───────────────────────────────────────────────
CL_TEAMS = [
    {"abbr":"G",  "short":"巨人",      "name":"讀賣巨人",            "npb_id":"g",  "home_venues":["東京ドーム"], "color":"#E8522A"},
    {"abbr":"T",  "short":"阪神",      "name":"阪神虎",              "npb_id":"t",  "home_venues":["甲子園"],     "color":"#F5D000"},
    {"abbr":"C",  "short":"廣島",      "name":"廣島東洋鯉魚",        "npb_id":"c",  "home_venues":["マツダ"],     "color":"#D40000"},
    {"abbr":"DB", "short":"DeNA",     "name":"橫濱DeNA海灣星",      "npb_id":"db", "home_venues":["横浜","ハマスタ"], "color":"#004990"},
    {"abbr":"D",  "short":"中日",      "name":"中日龍",              "npb_id":"d",  "home_venues":["バンテリン","ナゴヤ"], "color":"#003087"},
    {"abbr":"S",  "short":"養樂多",    "name":"東京養樂多燕子",       "npb_id":"s",  "home_venues":["神宮"],       "color":"#006AB7"},
]
PL_TEAMS = [
    {"abbr":"H",  "short":"軟銀",      "name":"福岡軟銀鷹",          "npb_id":"h",  "home_venues":["みずほ","PayPay","福岡"], "color":"#F5A800"},
    {"abbr":"L",  "short":"西武",      "name":"埼玉西武獅",          "npb_id":"l",  "home_venues":["ベルーナ","所沢"], "color":"#00529C"},
    {"abbr":"F",  "short":"火腿",      "name":"北海道日本火腿鬥士",  "npb_id":"f",  "home_venues":["エスコン","北広島"], "color":"#003087"},
    {"abbr":"B",  "short":"歐力士",    "name":"歐力士猛牛",          "npb_id":"b",  "home_venues":["京セラ","舞洲"], "color":"#004889"},
    {"abbr":"M",  "short":"羅德",      "name":"千葉羅德海洋",        "npb_id":"m",  "home_venues":["ZOZO","ZOZOマリン"], "color":"#000000"},
    {"abbr":"E",  "short":"樂天",      "name":"東北樂天金鷲",        "npb_id":"e",  "home_venues":["楽天モバイル","宮城"], "color":"#8B0000"},
]
ALL_TEAMS = CL_TEAMS + PL_TEAMS

# 日文對手名稱自動翻譯對照表
JAP_TEAM_MAP = {
    "巨人": "巨人", "阪神": "阪神", "中日": "中日", "広島": "廣島", "ＤｅＮＡ": "DeNA", "DeNA": "DeNA", "ヤクルト": "養樂多",
    "ソフトバンク": "軟銀", "西武": "西武", "ロッテ": "羅德", "楽天": "樂天", "オリックス": "歐力士", "日本ハム": "火腿", "日ハム": "火腿"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,ja-JP;q=0.8",
    "Referer": "https://npb.jp/",
}

# ── 按鍵 ──────────────────────────────────────────────────────────────────────
def getch():
    if IS_WINDOWS:
        import msvcrt
        ch = msvcrt.getwch()
        if ch in ("\x00","\xe0"):