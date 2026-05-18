"""
npb_team_stats.py  v8
資料來源：https://npb.jp/bis/teams/results_{npb_id}_{suffix}.html
新增：matplotlib 視覺化（得分分布直方圖、主客場趨勢折線、回戦系列賽分析）
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

# ── 球隊資料 ──────────────────────────────────────────────────────────────────
CL_TEAMS = [
    {"abbr":"G",  "short":"巨人",      "name":"読売ジャイアンツ",            "npb_id":"g",  "home_venues":["東京ドーム"], "color":"#E8522A"},
    {"abbr":"T",  "short":"阪神",      "name":"阪神タイガース",              "npb_id":"t",  "home_venues":["甲子園"],     "color":"#F5D000"},
    {"abbr":"C",  "short":"広島",      "name":"広島東洋カープ",              "npb_id":"c",  "home_venues":["マツダ"],     "color":"#D40000"},
    {"abbr":"DB", "short":"DeNA",     "name":"横浜DeNAベイスターズ",        "npb_id":"db", "home_venues":["横浜","ハマスタ"], "color":"#004990"},
    {"abbr":"D",  "short":"中日",      "name":"中日ドラゴンズ",              "npb_id":"d",  "home_venues":["バンテリン","ナゴヤ"], "color":"#003087"},
    {"abbr":"S",  "short":"ヤクルト",  "name":"東京ヤクルトスワローズ",       "npb_id":"s",  "home_venues":["神宮"],       "color":"#006AB7"},
]
PL_TEAMS = [
    {"abbr":"H",  "short":"SoftBank",  "name":"福岡ソフトバンクホークス",    "npb_id":"h",  "home_venues":["みずほ","PayPay","福岡"], "color":"#F5A800"},
    {"abbr":"L",  "short":"西武",      "name":"埼玉西武ライオンズ",          "npb_id":"l",  "home_venues":["ベルーナ","所沢"], "color":"#00529C"},
    {"abbr":"F",  "short":"日ハム",    "name":"北海道日本ハムファイターズ",  "npb_id":"f",  "home_venues":["エスコン","北広島"], "color":"#003087"},
    {"abbr":"B",  "short":"オリックス","name":"オリックス・バファローズ",     "npb_id":"b",  "home_venues":["京セラ","舞洲"], "color":"#004889"},
    {"abbr":"M",  "short":"ロッテ",    "name":"千葉ロッテマリーンズ",        "npb_id":"m",  "home_venues":["ZOZO","ZOZOマリン"], "color":"#000000"},
    {"abbr":"E",  "short":"楽天",      "name":"東北楽天ゴールデンイーグルス","npb_id":"e",  "home_venues":["楽天モバイル","宮城"], "color":"#8B0000"},
]
ALL_TEAMS = CL_TEAMS + PL_TEAMS

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja-JP,ja;q=0.9",
    "Referer": "https://npb.jp/",
}

# ── 按鍵 ──────────────────────────────────────────────────────────────────────
def getch():
    if IS_WINDOWS:
        import msvcrt
        ch = msvcrt.getwch()
        if ch in ("\x00","\xe0"):
            return {"H":"UP","P":"DOWN"}.get(msvcrt.getwch(),"")
        if ch=="\r": return "ENTER"
        if ch in("q","Q","\x03"): return "QUIT"
        return ch
    else:
        import tty, termios
        fd=sys.stdin.fileno(); old=termios.tcgetattr(fd)
        try:
            tty.setraw(fd); ch=sys.stdin.read(1)
            if ch=="\x1b":
                s=sys.stdin.read(2)
                return "UP" if s=="[A" else "DOWN" if s=="[B" else ""
            if ch in("\r","\n"): return "ENTER"
            if ch in("q","Q","\x03"): return "QUIT"
            return ch
        finally: termios.tcsetattr(fd,termios.TCSADRAIN,old)

def clear_lines(n):
    for _ in range(n): sys.stdout.write("\033[A\033[2K")
    sys.stdout.flush()

# ── 選單 ──────────────────────────────────────────────────────────────────────
def render_menu(cursor):
    lines=[
        f"{BG_HDR}{BOLD}{WHITE}  NPB 球隊得分查詢  ─  請選擇球隊{RESET}",
        f"  {DIM}↑ ↓ 移動　Enter 確認　q 離開{RESET}","",
        f"  {CYAN}{BOLD}セ・リーグ（中央聯盟）{RESET}",
    ]
    for i,t in enumerate(CL_TEAMS):
        sel=(i==cursor)
        lines.append(f"  {BG_SEL+WHITE if sel else ''}{'>> ' if sel else '   '}"
                     f"{t['abbr']:<4}  {t['short']:<10}  {DIM}{t['name']}{RESET}")
    lines+=["",f"  {YELLOW}{BOLD}パ・リーグ（太平洋聯盟）{RESET}"]
    for i,t in enumerate(PL_TEAMS):
        idx=len(CL_TEAMS)+i; sel=(idx==cursor)
        lines.append(f"  {BG_SEL+WHITE if sel else ''}{'>> ' if sel else '   '}"
                     f"{t['abbr']:<4}  {t['short']:<10}  {DIM}{t['name']}{RESET}")
    return lines

def interactive_select():
    cursor,total=0,len(ALL_TEAMS)
    lines=render_menu(cursor); print("\n".join(lines)); rendered=len(lines)
    while True:
        key=getch()
        if   key=="UP":    cursor=(cursor-1)%total
        elif key=="DOWN":  cursor=(cursor+1)%total
        elif key=="ENTER": clear_lines(rendered); return ALL_TEAMS[cursor]
        elif key=="QUIT":  clear_lines(rendered); print("已取消。"); sys.exit(0)
        else: continue
        clear_lines(rendered); lines=render_menu(cursor); print("\n".join(lines)); rendered=len(lines)

# ── 解析 ──────────────────────────────────────────────────────────────────────
COL_DATE=0; COL_OPP=1; COL_ROUND=2; COL_VENUE=3; COL_SCORE=6; COL_RESULT=7

def parse_page(html, team, year):
    soup = BeautifulSoup(html, "html.parser")
    games = []
    home_venues = team["home_venues"]
    current_month = None

    for tr in soup.find_all("tr", class_="terlist"):
        tds = tr.find_all("td")
        if len(tds) < 8: continue

        date_text   = tds[COL_DATE].get_text(strip=True)
        opp_text    = tds[COL_OPP].get_text(strip=True)
        round_text  = tds[COL_ROUND].get_text(strip=True)   # 回戦
        venue_text  = tds[COL_VENUE].get_text(strip=True)
        score_text  = tds[COL_SCORE].get_text(strip=True)
        result_text = tds[COL_RESULT].get_text(strip=True)

        m_full = re.match(r"(\d{1,2})/(\d{1,2})", date_text)
        m_day  = re.match(r"^(\d{1,2})$", date_text)
        if m_full:
            current_month=int(m_full.group(1)); day=int(m_full.group(2))
        elif m_day and current_month:
            day=int(m_day.group(1))
        else:
            continue

        sm = re.match(r"(\d+)-(\d+)", score_text)
        if not sm: continue
        my_score=int(sm.group(1)); opp_score=int(sm.group(2))

        if "○" in result_text:   result="W"
        elif "●" in result_text: result="L"
        elif "△" in result_text: result="D"
        else: continue

        venue    = "home" if any(v in venue_text for v in home_venues) else "away"
        opponent = opp_text.replace("\u3000","").replace("　","").strip()
        round_n  = int(round_text) if round_text.isdigit() else 0
        date_str = f"{year}-{current_month:02d}-{day:02d}"

        games.append({
            "date":date_str, "opponent":opponent,
            "venue":venue, "scored":my_score,
            "allowed":opp_score, "result":result,
            "round": round_n,          # 回戦番號
            "venue_name": venue_text,  # 球場原文
        })
    return games


def build_suffixes():
    now=datetime.today(); suffixes=["index"]
    for mo in range(now.month-1,2,-1):
        suffixes.append(f"{mo:02d}")
    return suffixes


def fetch_game_results(team, max_games=10):
    npb_id=team["npb_id"]; year=datetime.today().year; games=[]
    for suffix in build_suffixes():
        if len(games)>=max_games: break
        url=f"https://npb.jp/bis/teams/results_{npb_id}_{suffix}.html"
        print(f"  抓取 {suffix} 頁面... ",end="",flush=True)
        try:
            r=requests.get(url,headers=HEADERS,timeout=12)
            print(f"HTTP {r.status_code}",end="  ")
            if r.status_code!=200: print(); continue
            r.encoding="utf-8"
        except requests.RequestException as e:
            print(f"失敗：{e}"); time.sleep(0.5); continue
        parsed=parse_page(r.text,team,year)
        parsed.sort(key=lambda x:x["date"],reverse=True)
        print(f"→ {len(parsed)} 場")
        games.extend(parsed); time.sleep(0.4)

    seen,unique=set(),[]
    for g in games:
        k=(g["date"],g["opponent"])
        if k not in seen: seen.add(k); unique.append(g)
    unique.sort(key=lambda x:x["date"],reverse=True)
    return unique[:max_games]

# ── 進階統計 ──────────────────────────────────────────────────────────────────
def compute_all(games):
    n=len(games)
    if n==0: return {}
    home=[g for g in games if g["venue"]=="home"]
    away=[g for g in games if g["venue"]=="away"]
    s=lambda lst,k: sum(g[k] for g in lst)
    ts=s(games,"scored"); ta=s(games,"allowed")
    wins=sum(1 for g in games if g["result"]=="W")
    losses=sum(1 for g in games if g["result"]=="L")
    draws=sum(1 for g in games if g["result"]=="D")
    avg_s=ts/n; avg_a=ta/n
    std_s=math.sqrt(sum((g["scored"]-avg_s)**2 for g in games)/n)
    std_a=math.sqrt(sum((g["allowed"]-avg_a)**2 for g in games)/n)
    pyth_wp=(ts**2/(ts**2+ta**2)) if (ts+ta)>0 else 0
    actual_wp=wins/n

    # 連勝/敗
    streak_val=0; streak_type=""
    sg=sorted(games,key=lambda x:x["date"],reverse=True)
    if sg and sg[0]["result"] in("W","L"):
        streak_type=sg[0]["result"]
        for g in sg:
            if g["result"]==streak_type: streak_val+=1
            else: break

    # 對手
    opp_stats=defaultdict(lambda:{"W":0,"L":0,"D":0,"scored":0,"allowed":0})
    for g in games:
        opp_stats[g["opponent"]][g["result"]]+=1
        opp_stats[g["opponent"]]["scored"]+=g["scored"]
        opp_stats[g["opponent"]]["allowed"]+=g["allowed"]

    # 一分差
    one_run=[g for g in games if abs(g["scored"]-g["allowed"])==1]
    one_run_w=sum(1 for g in one_run if g["result"]=="W")

    # 回戦系列賽（第幾戰勝率）
    series_stats=defaultdict(lambda:{"W":0,"L":0,"D":0})
    for g in games:
        # 把回戦號碼轉換成系列賽內的第幾場
        # NPB 回戦是整季累計，所以同一對手的連續回戦代表同一系列賽
        pass
    # 簡化：直接按回戦號碼 mod 3（或看連續日期判斷）
    # 用對手+回戦組合，找出系列賽位置
    series_pos_stats=defaultdict(lambda:{"W":0,"L":0,"D":0})
    opp_rounds=defaultdict(list)
    for g in sorted(games,key=lambda x:(x["opponent"],x["date"])):
        opp_rounds[g["opponent"]].append(g)
    for opp,og in opp_rounds.items():
        # 按日期排序，找出系列賽內的場次位置（連續日期視為同一系列）
        series_idx=1
        prev_date=None
        for g in og:
            cur=datetime.strptime(g["date"],"%Y-%m-%d")
            if prev_date and (cur-prev_date).days>4:
                series_idx=1  # 新系列賽
            pos=f"系列第{series_idx}場"
            series_pos_stats[pos][g["result"]]+=1
            series_idx+=1
            prev_date=cur

    return {
        "total_games":n,"wins":wins,"losses":losses,"draws":draws,
        "total_scored":ts,"total_allowed":ta,"avg_scored":avg_s,"avg_allowed":avg_a,
        "std_scored":std_s,"std_allowed":std_a,
        "pyth_wp":pyth_wp,"actual_wp":actual_wp,
        "home_games":len(home),"home_scored":s(home,"scored"),"home_allowed":s(home,"allowed"),
        "away_games":len(away),"away_scored":s(away,"scored"),"away_allowed":s(away,"allowed"),
        "streak_val":streak_val,"streak_type":streak_type,
        "opp_stats":dict(opp_stats),
        "one_run_games":len(one_run),"one_run_wins":one_run_w,
        "series_pos_stats":dict(series_pos_stats),
    }

# ── 視覺化 ────────────────────────────────────────────────────────────────────
def plot_charts(team, games, st):
    try:
        import matplotlib
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm
        matplotlib.rcParams["axes.unicode_minus"] = False
    except ImportError:
        print(f"  {YELLOW}[提示] 安裝 matplotlib 以顯示圖表：pip install matplotlib{RESET}")
        return

    # 嘗試載入支援 CJK 的字型（Windows / macOS / Linux 各自優先）
    cjk_fonts = [
        "Microsoft JhengHei",   # Windows 繁體中文
        "Microsoft YaHei",      # Windows 簡體中文
        "Yu Gothic",            # Windows 日文
        "Meiryo", "MS Gothic", "MS Mincho",
        "PingFang TC", "Hiragino Sans",       # macOS
        "Noto Sans CJK JP", "Noto Sans TC",   # Linux
        "IPAGothic", "WenQuanYi Micro Hei",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    chosen = next((f for f in cjk_fonts if f in available), None)
    if chosen:
        plt.rcParams["font.family"] = chosen
        plt.rcParams["axes.unicode_minus"] = False
    else:
        # fallback：把中文標題改成 ASCII，不警告也不亂碼
        plt.rcParams["font.family"] = "DejaVu Sans"

    # 若找不到 CJK 字型，標題改用英文避免方塊
    if chosen:
        t1 = "① 得分分布 Scoring Distribution"
        t2 = "② 主客場趨勢 Home/Away Trend"
        t3 = "④ 系列賽勝率 Series Game Win%"
        ylabel1 = "場次 Games"; ylabel2 = "得分 Runs"; ylabel3 = "勝率 Win%"
        xlabel2 = "日期 Date"; xlabel3 = "場次位置 Series Position"
    else:
        t1 = "Scoring Distribution"
        t2 = "Home/Away Run Trend"
        t3 = "Series Game Win%"
        ylabel1 = "Games"; ylabel2 = "Runs"; ylabel3 = "Win%"
        xlabel2 = "Date"; xlabel3 = "Series Position"
    name  = team["name"]
    n     = len(games)
    sorted_g = sorted(games, key=lambda x: x["date"])  # 時序正向

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle(f"{name}　近{n}場分析", fontsize=15, fontweight="bold", y=1.01)
    fig.patch.set_facecolor("#1a1a2e")
    for ax in axes:
        ax.set_facecolor("#16213e")
        ax.tick_params(colors="white"); ax.xaxis.label.set_color("white")
        ax.yaxis.label.set_color("white"); ax.title.set_color("white")
        for spine in ax.spines.values(): spine.set_edgecolor("#444")

    # ── 圖1：得分分布直方圖 ───────────────────────────────────────────────
    ax1 = axes[0]
    scored  = [g["scored"]  for g in games]
    allowed = [g["allowed"] for g in games]
    bins = range(0, max(max(scored), max(allowed))+2)
    ax1.hist(scored,  bins=bins, alpha=0.75, color="#4CAF50", label="得分 Scored", edgecolor="#1a1a2e")
    ax1.hist(allowed, bins=bins, alpha=0.55, color="#F44336", label="失分 Allowed", edgecolor="#1a1a2e")
    ax1.axvline(st["avg_scored"],  color="#4CAF50", linestyle="--", linewidth=1.5,
                label=f"Avg Scored {st['avg_scored']:.1f}")
    ax1.axvline(st["avg_allowed"], color="#F44336", linestyle="--", linewidth=1.5,
                label=f"Avg Allowed {st['avg_allowed']:.1f}")
    ax1.set_title(t1, fontsize=12, pad=10)
    ax1.set_xlabel("Score"); ax1.set_ylabel(ylabel1)
    ax1.legend(fontsize=9, facecolor="#1a1a2e", labelcolor="white", edgecolor="#444")
    ax1.xaxis.set_major_locator(plt.MaxNLocator(integer=True))

    # ── 圖2：主客場趨勢折線圖 ────────────────────────────────────────────
    ax2 = axes[1]
    dates_label = [g["date"][5:] for g in sorted_g]  # MM-DD
    x = range(len(sorted_g))

    home_x=[i for i,g in enumerate(sorted_g) if g["venue"]=="home"]
    away_x=[i for i,g in enumerate(sorted_g) if g["venue"]=="away"]
    home_sc=[sorted_g[i]["scored"] for i in home_x]
    away_sc=[sorted_g[i]["scored"] for i in away_x]

    ax2.plot(x, [g["scored"] for g in sorted_g],
             color=team["color"], linewidth=1.5, alpha=0.4, zorder=1)
    ax2.scatter(home_x, home_sc, color="#4FC3F7", s=80, zorder=3,
                label="Home", marker="o")
    ax2.scatter(away_x, away_sc, color="#FFB74D", s=80, zorder=3,
                label="Away", marker="^")
    ax2.plot(x, [g["allowed"] for g in sorted_g],
             color="#F44336", linewidth=1, linestyle="--", alpha=0.5, label="Allowed")
    ax2.axhline(st["avg_scored"], color="#4CAF50", linestyle=":", linewidth=1,
                alpha=0.6, label=f"Avg {st['avg_scored']:.1f}")

    # 勝敗標記
    for i,g in enumerate(sorted_g):
        color_r = "#4CAF50" if g["result"]=="W" else "#F44336" if g["result"]=="L" else "#aaa"
        ax2.annotate(g["result"], (i, g["scored"]+0.3), fontsize=7,
                     ha="center", color=color_r)

    from matplotlib.ticker import FixedLocator, FixedFormatter
    ax2.xaxis.set_major_locator(FixedLocator(list(x)))
    ax2.xaxis.set_major_formatter(FixedFormatter(dates_label))
    ax2.tick_params(axis="x", rotation=45, labelsize=8)
    ax2.set_title(t2, fontsize=12, pad=10)
    ax2.set_ylabel(ylabel2); ax2.set_xlabel(xlabel2)
    ax2.legend(fontsize=8, facecolor="#1a1a2e", labelcolor="white", edgecolor="#444")
    ax2.yaxis.set_major_locator(plt.MaxNLocator(integer=True))

    # ── 圖3：回戦系列賽勝率 ──────────────────────────────────────────────
    ax3 = axes[2]
    sps = st["series_pos_stats"]
    positions = sorted(sps.keys())
    if positions:
        wp_list = []
        n_list  = []
        for pos in positions:
            d=sps[pos]; total=d["W"]+d["L"]+d["D"]
            wp=d["W"]/total if total>0 else 0
            wp_list.append(wp); n_list.append(total)

        bar_colors = ["#4CAF50" if w>0.5 else "#F44336" if w<0.5 else "#aaa" for w in wp_list]
        bars = ax3.bar(positions, wp_list, color=bar_colors, edgecolor="#1a1a2e", alpha=0.85)

        for bar_obj, wp, n_g in zip(bars, wp_list, n_list):
            ax3.text(bar_obj.get_x()+bar_obj.get_width()/2,
                     bar_obj.get_height()+0.02,
                     f"{wp:.2f}\n({n_g}G)", ha="center", va="bottom",
                     fontsize=9, color="white")

        ax3.axhline(0.5, color="#FFB74D", linestyle="--", linewidth=1.5,
                    alpha=0.7, label=".500 line")
        ax3.set_ylim(0, 1.15)
        ax3.set_title(t3, fontsize=12, pad=10)
        ax3.set_ylabel(ylabel3); ax3.set_xlabel(xlabel3)
        ax3.legend(fontsize=9, facecolor="#1a1a2e", labelcolor="white", edgecolor="#444")
        from matplotlib.ticker import FixedLocator, FixedFormatter
        ax3.xaxis.set_major_locator(FixedLocator(range(len(positions))))
        ax3.xaxis.set_major_formatter(FixedFormatter(positions))
        ax3.tick_params(axis="x", rotation=15, labelsize=9)
    else:
        ax3.text(0.5,0.5,"數據不足", ha="center",va="center",
                 color="white", transform=ax3.transAxes, fontsize=12)
        ax3.set_title(t3, fontsize=12, pad=10)

    plt.tight_layout()
    plt.show()

# ── Terminal 輸出 ─────────────────────────────────────────────────────────────
R_LBL={"W":f"{GREEN}勝{RESET}","L":f"{RED}敗{RESET}","D":f"{DIM}平{RESET}"}
V_LBL={"home":f"{CYAN}主場{RESET}","away":f"{YELLOW}客場{RESET}"}
LW=64

def section(title):
    print(f"\n  {BG_SEC}{WHITE}{BOLD}  {title}  {RESET}")

def bar_ascii(val, max_val=1.0, width=20, color=GREEN):
    filled=int(val/max_val*width) if max_val>0 else 0
    filled=min(filled,width)
    return f"{color}{'█'*filled}{DIM}{'░'*(width-filled)}{RESET}"

def print_report(team, games, st):
    n=st["total_games"]
    print()
    print(f"{BG_HDR}{WHITE}{BOLD}  {team['name']}（{team['short']}）近 {n} 場完整分析報告{RESET}")
    print("="*LW)

    section("📋 比賽明細")
    print(f"  {'日期':<10}  {'對手':<8}  {'主/客':^4}  {'得':>3}  {'失':>3}  結果  差")
    print("  "+"-"*(LW-2))
    for g in games:
        v=V_LBL.get(g["venue"]); r=R_LBL.get(g["result"])
        sc=f"{GREEN}{g['scored']:>3}{RESET}" if g["scored"]>g["allowed"] else f"{g['scored']:>3}"
        al=f"{RED}{g['allowed']:>3}{RESET}"  if g["allowed"]>g["scored"]  else f"{g['allowed']:>3}"
        diff=g["scored"]-g["allowed"]
        ds=f"{GREEN}+{diff}{RESET}" if diff>0 else f"{RED}{diff}{RESET}" if diff<0 else f"{DIM}±0{RESET}"
        print(f"  {g['date']:<10}  {g['opponent']:<8}  {v}  {sc}  {al}  {r}  {ds}")

    section("📊 基本統計")
    hg,ag=st["home_games"],st["away_games"]
    hs,ha=st["home_scored"],st["home_allowed"]
    as_,aa=st["away_scored"],st["away_allowed"]
    print(f"  戰績：{GREEN}{st['wins']}勝{RESET} {RED}{st['losses']}敗{RESET} {DIM}{st['draws']}平{RESET}"
          f"　勝率：{BOLD}{st['actual_wp']:.3f}{RESET}　得失差 {st['total_scored']-st['total_allowed']:+d}")
    print(f"  {CYAN}主場（{hg}場）{RESET}  得{GREEN}{hs}{RESET} 失{RED}{ha}{RESET}"+(f"  均得{hs/hg:.1f}/失{ha/hg:.1f}" if hg else ""))
    print(f"  {YELLOW}客場（{ag}場）{RESET}  得{GREEN}{as_}{RESET} 失{RED}{aa}{RESET}"+(f"  均得{as_/ag:.1f}/失{aa/ag:.1f}" if ag else ""))

    section("🔢 畢氏勝率")
    pw=st["pyth_wp"]; aw=st["actual_wp"]; diff_wp=aw-pw
    trend=(f"{GREEN}▲ 實際優於預期 +{diff_wp:.3f}（近期運氣佳）{RESET}" if diff_wp>0.02
      else f"{RED}▼ 實際低於預期 {diff_wp:.3f}（近期運氣差）{RESET}" if diff_wp<-0.02
      else f"{DIM}≈ 實際與預期相符（表現穩定）{RESET}")
    print(f"  畢氏預期：{BOLD}{pw:.3f}{RESET}  {bar_ascii(pw,1.0,20,CYAN)}")
    print(f"  實際勝率：{BOLD}{aw:.3f}{RESET}  {bar_ascii(aw,1.0,20,GREEN if aw>=pw else RED)}")
    print(f"  判讀：{trend}")

    section("📈 得分穩定度")
    ss=st["std_scored"]; sa=st["std_allowed"]
    sc_list=[g["scored"] for g in games]
    al_list=[g["allowed"] for g in games]
    print(f"  得分  均值{st['avg_scored']:.2f}  標準差{BOLD}{ss:.2f}{RESET}  最高{max(sc_list)}  最低{min(sc_list)}")
    print(f"  失分  均值{st['avg_allowed']:.2f}  標準差{BOLD}{sa:.2f}{RESET}  最高{max(al_list)}  最低{min(al_list)}")
    stab="穩定" if ss<3 else "普通" if ss<5 else "不穩定"
    sc=GREEN if ss<3 else YELLOW if ss<5 else RED
    print(f"  打線評估：{sc}{BOLD}{stab}{RESET}（σ<3穩定 / 3-5普通 / >5不穩）")

    section("🔥 連勝/敗動能")
    sv=st["streak_val"]; stype=st["streak_type"]
    if sv>0:
        c=GREEN if stype=="W" else RED; lb="連勝" if stype=="W" else "連敗"
        print(f"  {c}{BOLD}{'🔥' if stype=='W' else '❄'} 目前 {sv} {lb}{RESET}")
    else:
        print(f"  {DIM}無連勝/連敗{RESET}")

    section("⚔  對手分析")
    print(f"  {'對手':<8}  {'場':>3}  {'勝':>3}  {'敗':>3}  {'勝率':>6}  {'均得':>5}  {'均失':>5}")
    print("  "+"-"*48)
    for opp,od in sorted(st["opp_stats"].items(),key=lambda x:-(x[1]["W"]+x[1]["L"]+x[1]["D"])):
        gn=od["W"]+od["L"]+od["D"]; wp=od["W"]/gn if gn>0 else 0
        wc=GREEN if wp>0.5 else RED if wp<0.5 else DIM
        print(f"  {opp:<8}  {gn:>3}  {GREEN}{od['W']:>3}{RESET}  {RED}{od['L']:>3}{RESET}"
              f"  {wc}{wp:.3f}{RESET}  {od['scored']/gn:>5.1f}  {od['allowed']/gn:>5.1f}")

    section("🎯 一分差勝率")
    orn=st["one_run_games"]; orw=st["one_run_wins"]
    if orn>0:
        or_wp=orw/orn; oc=GREEN if or_wp>0.5 else RED if or_wp<0.5 else DIM
        print(f"  一分差 {orn}場  勝{GREEN}{orw}{RESET} 敗{RED}{orn-orw}{RESET}  "
              f"勝率 {oc}{BOLD}{or_wp:.3f}{RESET}  {bar_ascii(or_wp,1.0,20,oc)}")
        print(f"  評估：{'牛棚穩健，接戰能力強' if or_wp>0.55 else '接戰偏弱' if or_wp<0.45 else '接戰能力普通'}")
    else:
        print(f"  {DIM}近{n}場無一分差比賽{RESET}")

    section("📅 系列賽第N場勝率")
    sps=st["series_pos_stats"]
    for pos in sorted(sps.keys()):
        d=sps[pos]; total=d["W"]+d["L"]+d["D"]
        wp=d["W"]/total if total>0 else 0
        wc=GREEN if wp>0.5 else RED if wp<0.5 else DIM
        print(f"  {pos}　{total:>2}場　{GREEN}{d['W']}勝{RESET}{RED}{d['L']}敗{RESET}{DIM}{d['D']}平{RESET}"
              f"　勝率 {wc}{wp:.3f}{RESET}  {bar_ascii(wp,1.0,16,wc)}")

    print()
    print(f"  {DIM}資料來源：https://npb.jp/bis/teams/results_{team['npb_id']}_index.html{RESET}")
    print("="*LW); print()

# ── 主程式 ────────────────────────────────────────────────────────────────────
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--games",type=int,default=10)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-chart", action="store_true", help="不顯示圖表")
    args=parser.parse_args()

    team=interactive_select()
    print(f"\n  已選擇：{BOLD}{team['name']}{RESET}　正在抓取近 {args.games} 場數據...\n")

    games=fetch_game_results(team,max_games=args.games)
    if not games:
        print(f"\n{RED}未能取得比賽數據。{RESET}")
        print(f"  https://npb.jp/bis/teams/results_{team['npb_id']}_index.html")
        sys.exit(1)

    st=compute_all(games)

    if args.json:
        out={k:v for k,v in st.items() if k!="opp_stats"}
        out["opp_stats"]={k:dict(v) for k,v in st["opp_stats"].items()}
        out["series_pos_stats"]={k:dict(v) for k,v in st["series_pos_stats"].items()}
        out["games"]=games; out["team"]=team["abbr"]; out["fullName"]=team["name"]
        print(json.dumps(out,ensure_ascii=False,indent=2))
    else:
        print_report(team,games,st)
        if not args.no_chart:
            print(f"  {DIM}正在開啟圖表視窗...（關閉視窗後程式結束）{RESET}\n")
            plot_charts(team,games,st)

if __name__=="__main__":
    main()