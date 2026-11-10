import os
import time
import subprocess
import json
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ==========================================
# 驅動程式自動化載入（自動適應本機與雲端）
# ==========================================
def init_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")

    # 檢查是否為 GitHub Actions 雲端環境
    if os.environ.get("CI") == "true":
        print("☁️ 偵測到雲端環境 (GitHub Actions)，啟用無頭模式...")
        options.add_argument("--headless=new")
    else:
        # 本機環境才載入個人 Profile 資料夾
        profile_path = r"C:\Users\esb18509\RPA\Fantasy\YahooFantasyProfile"
        if os.path.exists(profile_path):
            options.add_argument(f"user-data-dir={profile_path}")

    try:
        print("正在自動初始化並載入 ChromeDriver...")
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    except Exception as err:
        raise RuntimeError(f"ChromeDriver 初始化失敗: {err}") from err

# --- 初始化 WebDriver ---
driver = init_driver()

try:
    # 連線至 Yahoo Fantasy 聯盟頁面（公開聯盟可直接抓取）
    driver.get("https://basketball.fantasysports.yahoo.com/nba/68528")
    
    # 如果是在本機執行且需要登入，保留暫停；如果在雲端，則自動等待幾秒讓頁面渲染
    if os.environ.get("CI") != "true":
        print("請確認是否需要登入 Yahoo 帳號。若需要，請在 30 秒內完成登入...")
        time.sleep(3)
    else:
        print("☁️ 雲端環境執行中，等待頁面載入...")
        time.sleep(5)

    # --- 1. 爬蟲與資料處理設定 ---
    total_weeks = 5 
    all_weeks_matrix = {}
    all_weeks_matchups = {}
    valid_teams = []
    team_records = {} 

    ignore_words = ["League Chat", "Team Stats", "Managers", "Email League", "Rosters", "Transactions", "Standings", "Schedule", "Playoffs", "Ratings & Levels", "View Matchup", "Home", "Players", "Draft", "League"]

    week_final_status = {}
    raw_week_data = {}

    for week in range(1, total_weeks + 1):
        print(f"正在抓取 Week {week} 的賽況...")
        driver.get(f"https://basketball.fantasysports.yahoo.com/nba/68528?week={week}")
        time.sleep(3)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        page_text = soup.get_text()
        is_final = "Final" in page_text or "Final Score" in page_text
        week_final_status[week] = is_final

        matchup_section = soup.select_one('#matchupweek') or soup
        team_links = matchup_section.select('a[href*="/nba/68528/"]')
        
        current_week_teams = []
        for link in team_links:
            name = link.get_text(strip=True)
            if name and name not in ignore_words and not name.endswith(('th', 'st', 'nd', 'rd')) and len(name) > 1 and not any(w in name for w in ignore_words):
                
                record_div = link.find_next('div', class_=lambda c: c and 'F-shade' in c)
                if record_div:
                    team_records[name] = record_div.get_text(strip=True)
                
                if name not in current_week_teams:
                    current_week_teams.append(name)
                    if name not in valid_teams:
                        valid_teams.append(name)

        current_week_teams = current_week_teams[:10]
        valid_teams = valid_teams[:10]
        scores = [el.get_text(strip=True) for el in matchup_section.select('.Ta-c, .Fz-lg, [class*="score"], div[class*="Grid-u-1-3"] span') if el.get_text(strip=True).isdigit() and len(el.get_text(strip=True)) <= 2]

        raw_week_data[week] = {
            "teams": current_week_teams,
            "scores": scores
        }

    # 自動決定預設顯示的未結算週
    current_unsettled_week = total_weeks
    for w in range(1, total_weeks + 1):
        if not week_final_status.get(w, False):
            current_unsettled_week = w
            break

    for week in range(1, total_weeks + 1):
        w_data = raw_week_data[week]
        current_week_teams = w_data["teams"]
        scores = w_data["scores"]
        is_final = week_final_status[week]

        week_matrix_results = {}
        week_matchup_list = []
        
        for i in range(0, len(current_week_teams), 2):
            if i + 1 < len(current_week_teams):
                t1, t2 = current_week_teams[i], current_week_teams[i+1]
                idx = int(i / 2) * 2
                s1 = int(scores[idx]) if idx < len(scores) else 0
                s2 = int(scores[idx + 1]) if idx + 1 < len(scores) else 0
                
                week_matchup_list.append({"t1": t1, "s1": s1, "t2": t2, "s2": s2})
                
                if not is_final:
                    week_matrix_results[t1], week_matrix_results[t2] = "-", "-"
                else:
                    if s1 > s2: week_matrix_results[t1], week_matrix_results[t2] = "W", "-100"
                    elif s2 > s1: week_matrix_results[t2], week_matrix_results[t1] = "W", "-100"
                    else: week_matrix_results[t1], week_matrix_results[t2] = "D", "D"

        all_weeks_matrix[f"Week{week}"] = week_matrix_results
        all_weeks_matchups[f"Week{week}"] = week_matchup_list

    # --- 2. 計算總獎金池 ---
    total_prize = sum(100 for results in all_weeks_matrix.values() for res in results.values() if res == "-100")

    # --- 3. 準備前端 JavaScript 下拉選單資料 ---
    matchups_js_data = {}
    for w in range(1, total_weeks + 1):
        w_key = f"Week{w}"
        html_cards = ""
        if w_key in all_weeks_matchups and all_weeks_matchups[w_key]:
            for m in all_weeks_matchups[w_key]:
                html_cards += f"""
                <div class="flex justify-between items-center bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-lg hover:border-slate-700 transition-colors">
                    <div class="w-1/3 text-right">
                        <div class="font-semibold text-slate-300">{m['t1']}</div>
                        <div class="text-[10px] text-slate-500 font-mono mt-0.5">{team_records.get(m['t1'], '')}</div>
                    </div>
                    <div class="w-1/3 text-center text-xl font-black text-white">{m['s1']} <span class="text-slate-600 text-sm mx-2">vs</span> {m['s2']}</div>
                    <div class="w-1/3 text-left">
                        <div class="font-semibold text-slate-300">{m['t2']}</div>
                        <div class="text-[10px] text-slate-500 font-mono mt-0.5">{team_records.get(m['t2'], '')}</div>
                    </div>
                </div>"""
        else:
            html_cards = "<div class='text-slate-500 p-4'>當週賽程尚未產生或還未開打</div>"
        
        matchups_js_data[w] = {
            "html": html_cards,
            "status": "Final" if week_final_status.get(w, False) else "In Progress"
        }

    matchups_json_str = json.dumps(matchups_js_data, ensure_ascii=False)

    # --- 4. 隊伍專屬視覺設定 ---
    team_styles = {
        "MK": {"bg": "bg-red-600 text-white", "char": "MK"},
        "小丑NO.1": {"bg": "bg-blue-400 text-slate-950", "char": "小"},
        "Ray聲大雨點小": {"bg": "bg-sky-600 text-white", "char": "R"},
        "夏衣隊": {"bg": "bg-green-700 text-white", "char": "夏"},
        "咬稻總頭": {"bg": "bg-slate-600 text-white", "char": "咬"},
        "咬稻德頭": {"bg": "bg-slate-600 text-white", "char": "咬"}, 
        "汪汪隊請加油": {"bg": "bg-orange-500 text-slate-950", "char": "汪"},
        "泡嬌最後一舞": {"bg": "bg-pink-700 text-white", "char": "泡"},
        "紫氣Don來": {"bg": "bg-purple-700 text-white", "char": "紫"},
        "少林斑馬": {"bg": "bg-black border border-slate-700 text-white", "char": "少"},
        "山貓不是三腳貓": {"bg": "bg-rose-700 text-white", "char": "山"}
    }

    # --- 5. 生成戰績矩陣 ---
    matrix_html = ""
    
    def get_rank(team_name):
        record_str = team_records.get(team_name, "")
        if "|" in record_str:
            rank_part = record_str.split("|")[-1] 
            rank_num = "".join([c for c in rank_part if c.isdigit()])
            if rank_num:
                return int(rank_num)
        return 999 

    sorted_teams = sorted(valid_teams, key=get_rank)

    for team in sorted_teams:
        style = team_styles.get(team, {"bg": "bg-gray-500 text-white", "char": team[0]})
        record_text = team_records.get(team, "")
        
        matrix_html += f"""
        <tr class="hover:bg-slate-800/30 transition-colors group">
            <td class="p-4 flex items-center gap-3">
                <div class="w-10 h-10 rounded-full {style['bg']} flex items-center justify-center font-bold text-lg">{style['char']}</div>
                <div class="flex flex-col">
                    <span class="font-semibold text-slate-200 group-hover:text-white transition-colors">{team}</span>
                    <span class="text-xs text-slate-500 font-mono mt-0.5">{record_text}</span>
                </div>
            </td>"""
        
        team_total_penalty = 0
        for week in range(1, total_weeks + 1):
            res = all_weeks_matrix[f"Week{week}"].get(team, "-")
            if res == "W":
                badge = '<span class="inline-flex items-center justify-center w-10 h-8 rounded bg-green-500/20 text-green-400 font-bold border border-green-500/30">W</span>'
            elif res == "-100":
                badge = '<span class="inline-flex items-center justify-center px-2 h-8 rounded bg-red-900/50 text-red-400 font-bold border border-red-700/50">-100</span>'
                team_total_penalty -= 100
            elif res == "D":
                badge = '<span class="inline-flex items-center justify-center w-10 h-8 rounded bg-slate-600/30 text-slate-400 font-bold border border-slate-600/50">D</span>'
            else:
                badge = '<span class="p-4 text-center text-slate-600">-</span>'
                
            matrix_html += f'<td class="p-4 text-center">{badge}</td>'
        
        matrix_html += f'<td class="p-4 text-right pr-6 font-mono font-bold {"text-red-400" if team_total_penalty < 0 else "text-slate-300"}">{team_total_penalty if team_total_penalty < 0 else 0}</td></tr>'

    # --- 6. 組合並寫入最終 HTML ---
    html_content = f"""<!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Taiwan Incredible League Dashboard</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
            body {{ font-family: 'Inter', sans-serif; }}
            .hide-scrollbar::-webkit-scrollbar {{ display: none; }}
            .hide-scrollbar {{ -ms-overflow-style: none; scrollbar-width: none; }}
        </style>
    </head>
    <body class="bg-slate-950 text-slate-200 min-h-screen p-4 md:p-8">

        <div class="max-w-6xl mx-auto">
            <div class="flex flex-col md:flex-row justify-between items-start md:items-center mb-8 gap-4">
                <div>
                    <h1 class="text-3xl font-bold text-white tracking-tight">Taiwan Incredible League</h1>
                    <p class="text-slate-400 mt-1">Season 2026-2027 • Regular Season Standings</p>
                </div>
                <button onclick="shareDashboard()" class="bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2.5 rounded-lg font-medium transition-all shadow-lg shadow-indigo-500/20 flex items-center gap-2">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z"></path></svg>
                    Share Dashboard
                </button>
            </div>

            <div class="bg-gradient-to-br from-amber-900/40 to-slate-900 border border-amber-700/30 rounded-2xl p-8 mb-12 text-center shadow-2xl relative overflow-hidden">
                <div class="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/cubes.png')] opacity-10"></div>
                <h2 class="text-amber-500/80 font-semibold tracking-widest text-sm uppercase mb-2">Total Prize Pool</h2>
                <div class="text-6xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-amber-200 to-yellow-500">
                    ${total_prize}
                </div>
            </div>

            <div class="mb-10">
                <div class="flex justify-between items-end border-l-4 border-indigo-500 pl-3 mb-5">
                    <div class="flex items-center gap-3">
                        <h3 class="text-xl font-bold text-white tracking-wide">Matchups</h3>
                        <select id="weekSelect" onchange="changeWeekData(this.value)" class="bg-slate-900 text-indigo-400 font-bold border border-indigo-500/50 rounded-lg px-3 py-1.5 focus:outline-none focus:border-indigo-400 transition-colors cursor-pointer">
                            <option value="1">Week 1</option>
                            <option value="2">Week 2</option>
                            <option value="3">Week 3</option>
                            <option value="4">Week 4</option>
                            <option value="5">Week 5</option>
                        </select>
                    </div>
                    <span id="weekStatusBadge" class="text-xs font-bold tracking-widest uppercase flex items-center gap-2">
                        <span id="statusDot" class="w-2 h-2 rounded-full"></span> <span id="statusText"></span>
                    </span>
                </div>
                <div id="matchupsContainer" class="grid grid-cols-1 md:grid-cols-2 gap-4">
                </div>
            </div>

            <div class="bg-slate-900 border border-slate-800 rounded-2xl shadow-xl overflow-hidden">
                <div class="overflow-x-auto hide-scrollbar">
                    <table class="w-full text-left border-collapse min-w-[800px]">
                        <thead>
                            <tr class="border-b border-slate-800 bg-slate-900/50 text-xs uppercase tracking-wider text-slate-400">
                                <th class="p-4 font-semibold w-64">Team</th>
                                <th class="p-4 font-semibold text-center">Week 1</th>
                                <th class="p-4 font-semibold text-center">Week 2</th>
                                <th class="p-4 font-semibold text-center">Week 3</th>
                                <th class="p-4 font-semibold text-center">Week 4</th>
                                <th class="p-4 font-semibold text-center">Week 5</th>
                                <th class="p-4 font-semibold text-right pr-6">Regular Season<br>Total</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-800/50">
                            {matrix_html}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <div id="toast" class="fixed bottom-6 left-1/2 -translate-x-1/2 bg-slate-800 text-white px-6 py-3 rounded-full shadow-2xl flex items-center gap-2 transform translate-y-full opacity-0 transition-all duration-300 border border-slate-700">
            <svg class="w-5 h-5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
            <span>Link copied to clipboard!</span>
        </div>

        <script>
            const allWeeksData = {matchups_json_str};
            
            let defaultWeek = {current_unsettled_week};
            document.getElementById('weekSelect').value = defaultWeek;
            changeWeekData(defaultWeek);

            function changeWeekData(weekNum) {{
                const data = allWeeksData[weekNum];
                if (!data) return;

                document.getElementById('matchupsContainer').innerHTML = data.html;

                const badge = document.getElementById('weekStatusBadge');
                const dot = document.getElementById('statusDot');
                const text = document.getElementById('statusText');

                text.innerText = data.status;
                if (data.status === 'Final') {{
                    badge.className = "text-xs font-bold text-slate-400 tracking-widest uppercase flex items-center gap-2";
                    dot.className = "w-2 h-2 rounded-full bg-slate-400";
                }} else {{
                    badge.className = "text-xs font-bold text-emerald-400 tracking-widest uppercase animate-pulse flex items-center gap-2";
                    dot.className = "w-2 h-2 rounded-full bg-emerald-400 animate-ping";
                }}
            }}

            function shareDashboard() {{
                const tempInput = document.createElement('input');
                document.body.appendChild(tempInput);
                tempInput.value = window.location.href;
                tempInput.select();
                document.execCommand('copy');
                document.body.removeChild(tempInput);
                
                const toast = document.getElementById('toast');
                toast.classList.remove('translate-y-full', 'opacity-0');
                
                setTimeout(() => {{
                    toast.classList.add('translate-y-full', 'opacity-0');
                }}, 3000);
            }}
        </script>
    </body>
    </html>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    print("✅ 網頁生成成功 (Cloud Version)！")

finally:
    driver.quit()