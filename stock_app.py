import streamlit as st
import yfinance as yf
import pandas as pd
from FinMind.data import DataLoader
from datetime import datetime, timedelta

# --- 設定區 ---
FINMIND_TOKEN = st.secrets["FINMIND_TOKEN"] 
st.set_page_config(page_title="台股智慧分析師 Pro Max", layout="wide")

# 1. 初始化狀態
if 'stock_id' not in st.session_state:
    st.session_state.stock_id = "2330"
if 'custom_list' not in st.session_state:
    st.session_state.custom_list = "2330, 2317, 2454, 8069, 3293, 2603, 1513, 2881"

# --- 核心數據函式 ---
def get_stock_analysis(sid):
    try:
        # --- 修改處：自動判斷上市 (.TW) 或 上櫃 (.TWO) ---
        df = yf.download(f"{sid}.TW", period="6mo", progress=False)
        if df.empty:
            df = yf.download(f"{sid}.TWO", period="6mo", progress=False)
            
        if df.empty: return None
        
        # 處理 MultiIndex 欄位問題
        df.columns = df.columns.get_level_values(0) if isinstance(df.columns, pd.MultiIndex) else df.columns
        
        df['5MA'] = df['Close'].rolling(5).mean()
        df['10MA'] = df['Close'].rolling(10).mean()
        df['20MA'] = df['Close'].rolling(20).mean()
        df['5VMA'] = df['Volume'].rolling(5).mean()
        
        latest = df.iloc[-1]
        p_close, ma5, ma10, ma20 = float(latest['Close']), float(latest['5MA']), float(latest['10MA']), float(latest['20MA'])
        vol_today, v_ma5 = float(latest['Volume'])/1000, float(latest['5VMA'])/1000
        
        # FinMind 籌碼與新聞部分
        dl = DataLoader()
        dl.login_by_token(api_token=FINMIND_TOKEN)
        inst = dl.taiwan_stock_institutional_investors(stock_id=sid, start_date=(datetime.now() - timedelta(days=12)).strftime('%Y-%m-%d'))
        
        consecutive_buy, total_inst_3d = False, 0
        if not inst.empty:
            daily = inst.groupby('date').apply(lambda x: x[x['name'].isin(['Foreign_Investor', 'Investment_Trust'])]['buy'].sum() - x[x['name'].isin(['Foreign_Investor', 'Investment_Trust'])]['sell'].sum())
            total_inst_3d = daily.tail(3).sum() / 1000
            if len(daily) >= 3 and (daily.tail(3) > 0).all(): consecutive_buy = True
        
        return {
            "df": df, "latest": latest, "score": (1 if p_close > ma20 else 0) + (1 if ma5 > ma10 else 0) + (1 if vol_today > v_ma5 else 0) + (1 if total_inst_3d > 0 else 0),
            "p_close": p_close, "ma5": ma5, "ma10": ma10, "ma20": ma20, "vol_today": vol_today, "v_ma5": v_ma5,
            "consecutive": consecutive_buy, "total_inst_3d": total_inst_3d, 
            "bias": ((p_close - ma20) / ma20) * 100
        }
    except Exception as e:
        return None

# --- 2. 側邊欄 ---
with st.sidebar:
    st.title("⚙️ 診斷設定")
    # 這裡讓使用者輸入純數字代號
    st.text_input("輸入台股代號 (上市/上櫃)", key="stock_id")
    st.divider()
    st.title("🎯 選股神器 2.0")
    input_list = st.text_area("編輯掃描清單", st.session_state.custom_list)
    if st.button("開始 AI 掃描"):
        st.session_state.custom_list = input_list
        scan_list = [s.strip() for s in input_list.split(",")]
        with st.status("同步掃描中...", expanded=False):
            for s_id in scan_list:
                res = get_stock_analysis(s_id)
                if res and res['score'] >= 3:
                    label = f"🚀 {s_id} ({res['score']}分)"
                    if res['consecutive']: label += " 🔥連買"
                    # 使用唯一 Key 避免 Streamlit 報錯
                    if st.button(label, key=f"btn_scan_{s_id}"):
                        st.session_state.stock_id = s_id
                        st.rerun()

    st.write("📋 **統一篩選邏輯說明**")
    logic_df = pd.DataFrame({"項目": ["1.技術趨勢", "2.技術動能", "3.量能表現", "4.籌碼力道"], "標準": ["價格 > 20MA", "5MA > 10MA", "今日量 > 均量", "3日法人買超"]})
    st.write(logic_df.to_html(index=False, justify='center'), unsafe_allow_html=True)

# --- 3. 主畫面 ---
def get_stock_analysis(sid):
    try:
        # 自動判定上市櫃抓取資料
        df = yf.download(f"{sid}.TW", period="8mo", progress=False) # 增加長度以計算斜率
        if df.empty:
            df = yf.download(f"{sid}.TWO", period="8mo", progress=False)
        if df.empty: return None
        
        df.columns = df.columns.get_level_values(0) if isinstance(df.columns, pd.MultiIndex) else df.columns
        
        # --- 技術指標計算 ---
        df['5MA'] = df['Close'].rolling(5).mean()
        df['10MA'] = df['Close'].rolling(10).mean()
        df['20MA'] = df['Close'].rolling(20).mean()
        df['20VMA'] = df['Volume'].rolling(20).mean() # 改採 20 日均量
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        five_days_ago = df.iloc[-6]
        
        p_close = float(latest['Close'])
        p_change = p_close - float(prev['Close']) # 今日漲跌
        
        ma5, ma10, ma20 = float(latest['5MA']), float(latest['10MA']), float(latest['20MA'])
        ma20_old = float(five_days_ago['20MA'])
        ma5_old = float(prev['5MA'])
        
        vol_today = float(latest['Volume'])
        v_ma20 = float(latest['20VMA'])
        
        # --- 1. 技術趨勢：站上月線 且 月線向上 ---
        cond_1 = (p_close > ma20) and (ma20 > ma20_old)
        
        # --- 2. 技術動能：5 > 10 > 20 多頭排列 且 5MA 斜率向上 ---
        cond_2 = (ma5 > ma10 > ma20) and (ma5 > ma5_old)
        
        # --- 3. 成交量能：量增 (1.5倍) 且 價漲 ---
        cond_3 = (vol_today > v_ma20 * 1.5) and (p_change > 0)
        
        # --- 4. 籌碼力道：投信優先 ---
        dl = DataLoader()
        dl.login_by_token(api_token=FINMIND_TOKEN)
        inst = dl.taiwan_stock_institutional_investors(stock_id=sid, start_date=(datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d'))
        
        sitc_buy = False # 投信
        foreign_buy = False # 外資
        if not inst.empty:
            # 抓取最後一天的法人資料
            last_date = inst['date'].max()
            today_inst = inst[inst['date'] == last_date]
            
            sitc_data = today_inst[today_inst['name'] == 'Investment_Trust']
            foreign_data = today_inst[today_inst['name'] == 'Foreign_Investor']
            
            if not sitc_data.empty and (sitc_data['buy'].sum() - sitc_data['sell'].sum()) > 0:
                sitc_buy = True
            if not foreign_data.empty and (foreign_data['buy'].sum() - foreign_data['sell'].sum()) > 0:
                foreign_buy = True
        
        # 籌碼過關定義：投信買超 (單獨過) 或 投信+外資買超 (強力過)
        cond_4 = sitc_buy # 依照你的需求，投信買超才算過
        
        # --- 最終評分與評價邏輯 ---
        final_score = 0
        if cond_1: final_score += 1
        if cond_2: final_score += 1
        if cond_3: final_score += 1
        if cond_4: final_score += 1
        
        status = "整理中"
        if cond_1 and cond_2:
            if cond_3 and cond_4:
                status = "🚀 強力關注 (全過)"
            elif cond_4:
                status = "🔥 趨勢偏多 (籌碼加持)"
            else:
                status = "👀 觀察 (技術過但籌碼未跟)"
        else:
            status = "📉 弱勢/未成形"

        return {
            "p_close": p_close, "ma5": ma5, "ma10": ma10, "ma20": ma20,
            "vol_today": vol_today / 1000, "v_ma20": v_ma20 / 1000,
            "cond_1": cond_1, "cond_2": cond_2, "cond_3": cond_3, "cond_4": cond_4,
            "sitc_buy": sitc_buy, "foreign_buy": foreign_buy,
            "score": final_score, "status": status,
            "bias": ((p_close - ma20) / ma20) * 100
        }
    except: return None
    
   # --- 第三區：AI 診斷報告 ---
    st.divider()
    st.subheader(f"🤖 AI 投資客綜合診斷：{data['status']}")
    
    # 建立診斷表格資料
    diag_rows = [
        ["1", "技術趨勢", "✅ 站上月線且月線向上" if data['cond_1'] else "❌ 趨勢未成 (月線向下或股價其下)", "多方" if data['cond_1'] else "偏弱"],
        ["2", "技術動能", "✅ 5>10>20 多頭且5MA向上" if data['cond_2'] else "❌ 動能不足 (未排列或斜率向下)", "強勁" if data['cond_2'] else "疲弱"],
        ["3", "成交量能", "✅ 量增價漲 (1.5倍均量)" if data['cond_3'] else "⚖️ 量縮或量增價跌", "攻擊" if data['cond_3'] else "保守"],
        ["4", "籌碼力道", "🔥 投信+外資雙買" if (data['sitc_buy'] and data['foreign_buy']) else "✅ 投信買超" if data['sitc_buy'] else "❌ 籌碼不具優勢", "推升" if data['sitc_buy'] else "壓力"]
    ]
    
    # 根據評價等級顯示不同顏色
    if "強力關注" in data['status']:
        st.success(f"🏆 綜合評價：{data['status']} (得分: {data['score']}/4)")
    elif "觀察" in data['status'] or "趨勢偏多" in data['status']:
        st.warning(f"💡 綜合評價：{data['status']} (得分: {data['score']}/4)")
    else:
        st.error(f"⚠️ 綜合評價：{data['status']} (得分: {data['score']}/4)")
        
    diag_df = pd.DataFrame(diag_rows, columns=["#", "項目", "診斷結果與嚴謹標準", "狀態"])
    st.write(diag_df.to_html(index=False, justify='left'), unsafe_allow_html=True)

    # 第五區：新聞
    st.divider()
    st.subheader("📰 即時相關新聞")
    try:
        dl_news = DataLoader()
        dl_news.login_by_token(api_token=FINMIND_TOKEN)
        news = dl_news.taiwan_stock_news(stock_id=st.session_state.stock_id, start_date=(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'))
        if not news.empty:
            for _, row in news.head(5).iterrows():
                with st.expander(f"📌 {row['title']}"):
                    st.write(f"來源: {row['source']} | [連結]({row['link']})")
        else: st.info("近期無相關新聞。")
    except: st.warning("新聞模組讀取失敗。")
else:
    st.error(f"查無 {st.session_state.stock_id} 數據，請確認代號是否正確。")


