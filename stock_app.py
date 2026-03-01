import streamlit as st
import yfinance as yf
import pandas as pd
from FinMind.data import DataLoader
from datetime import datetime, timedelta

# --- 頁面設定 ---
st.set_page_config(page_title="台股智慧分析師 Pro Max", layout="wide")

# 安全取得 Token
FINMIND_TOKEN = st.secrets.get("FINMIND_TOKEN", "")

# 1. 初始化狀態
if 'stock_id' not in st.session_state:
    st.session_state.stock_id = "2330"
if 'custom_list' not in st.session_state:
    st.session_state.custom_list = "2330, 2317, 2454, 8069, 3293, 2603, 1513"

# --- 核心數據函式 ---
def get_stock_analysis(sid):
    try:
        # 自動判斷上市 (.TW) 或 上櫃 (.TWO)
        df = yf.download(f"{sid}.TW", period="8mo", progress=False)
        if df.empty:
            df = yf.download(f"{sid}.TWO", period="8mo", progress=False)
        
        if df.empty: return None
        
        # 處理 yfinance 欄位結構
        df.columns = df.columns.get_level_values(0) if isinstance(df.columns, pd.MultiIndex) else df.columns
        
        # 計算技術指標
        df['5MA'] = df['Close'].rolling(5).mean()
        df['10MA'] = df['Close'].rolling(10).mean()
        df['20MA'] = df['Close'].rolling(20).mean()
        df['20VMA'] = df['Volume'].rolling(20).mean()
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        five_days_ago = df.iloc[-6]
        
        p_close = float(latest['Close'])
        p_change = p_close - float(prev['Close'])
        ma5, ma10, ma20 = float(latest['5MA']), float(latest['10MA']), float(latest['20MA'])
        ma20_old = float(five_days_ago['20MA'])
        ma5_old = float(prev['5MA'])
        vol_today, v_ma20 = float(latest['Volume']), float(latest['20VMA'])

        # --- 新邏輯：四項診斷條件 ---
        # 1. 技術趨勢：站上月線 且 月線向上
        cond_1 = (p_close > ma20) and (ma20 > ma20_old)
        
        # 2. 技術動能：5 > 10 > 20 多頭排列 且 5MA 斜率向上
        cond_2 = (ma5 > ma10 > ma20) and (ma5 > ma5_old)
        
        # 3. 成交量能：成交量 > 20日均量 1.5倍 且 價漲
        cond_3 = (vol_today > v_ma20 * 1.5) and (p_change > 0)
        
        # 4. 籌碼力道：投信買超
        sitc_buy, foreign_buy = False, False
        try:
            dl = DataLoader()
            dl.login_by_token(api_token=FINMIND_TOKEN)
            inst = dl.taiwan_stock_institutional_investors(stock_id=sid, start_date=(datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d'))
            if not inst.empty:
                last_date = inst['date'].max()
                today_inst = inst[inst['date'] == last_date]
                sitc_net = today_inst[today_inst['name'] == 'Investment_Trust']['buy'].sum() - today_inst[today_inst['name'] == 'Investment_Trust']['sell'].sum()
                foreign_net = today_inst[today_inst['name'] == 'Foreign_Investor']['buy'].sum() - today_inst[today_inst['name'] == 'Foreign_Investor']['sell'].sum()
                sitc_buy = sitc_net > 0
                foreign_buy = foreign_net > 0
        except:
            pass
        
        # --- 評分機制調整 ---
        # 門檻：1 和 2 必須同時成立
        tech_pass = cond_1 and cond_2
        score = sum([cond_1, cond_2, cond_3, sitc_buy])
        
        if not tech_pass:
            status = "📉 弱勢整理 (技術面未達標)"
        elif tech_pass and sitc_buy and cond_3:
            status = "🚀 強力關注 (全方位達標)"
        elif tech_pass and sitc_buy:
            status = "🔥 趨勢偏多 (投信加持)"
        else:
            status = "👀 觀察 (技術過、籌碼未跟)"

        return {
            "p_close": p_close, "ma5": ma5, "ma10": ma10, "ma20": ma20,
            "vol_today": vol_today/1000, "v_ma20": v_ma20/1000,
            "cond_1": cond_1, "cond_2": cond_2, "cond_3": cond_3, "cond_4": sitc_buy,
            "sitc_buy": sitc_buy, "foreign_buy": foreign_buy,
            "score": score, "status": status, "bias": ((p_close - ma20) / ma20) * 100
        }
    except: return None

# --- 側邊欄 ---
with st.sidebar:
    st.title("⚙️ 診斷設定")
    st.text_input("輸入台股代號", key="stock_id")
    st.divider()
    st.title("🎯 選股神器 2.0")
    input_list = st.text_area("編輯掃描清單", st.session_state.custom_list)
    if st.button("開始 AI 掃描"):
        st.session_state.custom_list = input_list
        scan_list = [s.strip() for s in input_list.split(",")]
        with st.status("同步掃描中...", expanded=False):
            for s_id in scan_list:
                res = get_stock_analysis(s_id)
                if res and "強力關注" in res['status']:
                    if st.button(f"🚀 {s_id} (強力關注)", key=f"btn_{s_id}"):
                        st.session_state.stock_id = s_id
                        st.rerun()

# --- 主畫面 ---
data = get_stock_analysis(st.session_state.stock_id)

if data:
    st.header(f"📈 {st.session_state.stock_id} 深度診斷 | {data['status']}")
    
    # 核心指標展示
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("價格", f"{data['p_close']:.2f}")
    c2.metric("月線乖離", f"{data['bias']:.1f}%")
    c3.metric("今日張數", f"{data['vol_today']:.0f}張")
    c4.metric("投信動向", "買超" if data['sitc_buy'] else "未買")

    # AI 診斷表
    st.divider()
    st.subheader("🤖 AI 投資客嚴謹診斷")
    diag_rows = [
        ["1", "技術趨勢", "✅ 站上月線且月線向上" if data['cond_1'] else "❌ 月線下彎或股價未站上", "通過" if data['cond_1'] else "失敗"],
        ["2", "技術動能", "✅ 5>10>20 多頭且5MA向上" if data['cond_2'] else "❌ 排列混亂或動能轉弱", "通過" if data['cond_2'] else "失敗"],
        ["3", "成交量能", "✅ 量增價漲 (1.5倍量)" if data['cond_3'] else "⚖️ 量縮或價跌", "加分" if data['cond_3'] else "不加分"],
        ["4", "籌碼力道", "🔥 投信+外資雙買" if (data['sitc_buy'] and data['foreign_buy']) else "✅ 投信買超" if data['sitc_buy'] else "❌ 籌碼無優勢", "強勢" if data['sitc_buy'] else "一般"]
    ]
    diag_df = pd.DataFrame(diag_rows, columns=["#", "項目", "診斷結果與標準定義", "狀態"])
    st.write(diag_df.to_html(index=False, justify='left'), unsafe_allow_html=True)

    # 新聞模組
    st.divider()
    st.subheader("📰 即時相關新聞")
    try:
        dl = DataLoader()
        dl.login_by_token(api_token=FINMIND_TOKEN)
        news = dl.taiwan_stock_news(stock_id=st.session_state.stock_id, start_date=(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'))
        if not news.empty:
            for _, row in news.head(5).iterrows():
                with st.expander(f"📌 {row['title']}"):
                    st.write(f"來源: {row['source']} | [連結]({row['link']})")
    except: st.write("新聞讀取中或 API 限制。")
else:
    st.error("查無數據，請確認代號並稍後再試。")
