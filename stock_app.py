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
data = get_stock_analysis(st.session_state.stock_id)

if data:
    # 判斷當前是上市還是上櫃（僅顯示用）
    market_suffix = "上市" if yf.download(f"{st.session_state.stock_id}.TWO", period="1d", progress=False).empty else "上櫃"
    
    st.header(f"📈 {st.session_state.stock_id} 深度診斷 ({market_suffix}) | 最新價格：{data['p_close']:.2f}")

    # 第一區：趨勢與風險
    st.subheader("📍 趨勢指標與風險")
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("短線趨勢 (5MA>10MA)", "🔴 多方" if data['ma5'] > data['ma10'] else "🟢 空方")
    t2.metric("長線趨勢 (價格>20MA)", "🔴 多方" if data['p_close'] > data['ma20'] else "🟢 空方")
    t3.metric("月線乖離率", f"{data['bias']:.1f}%")
    t4.metric("乖離狀態", "過熱" if data['bias'] > 10 else "安全", delta_color="inverse")

    # 第二區：量能
    st.subheader("📊 量能監控")
    b1, b2, b3 = st.columns(3)
    b1.metric("今日成交張數", f"{data['vol_today']:.0f} 張")
    b2.metric("量能狀態", "爆量攻擊" if data['vol_today'] > data['v_ma5']*1.5 else "正常", delta=f"{data['vol_today']/data['v_ma5']:.1f}x 均量")
    
    # 第三區：AI 診斷報告
st.divider()
st.subheader("🤖 AI 投資客綜合診斷")

# === 條件判斷 ===

# 1. 技術趨勢：站上月線 且 月線向上
trend_ok = data['p_close'] > data['ma20'] and data['ma20'] > data['ma20_5d_ago']
trend_text = "✅ 站上月線且月線向上" if trend_ok else ("⚠️ 站上月線但月線向下" if data['p_close'] > data['ma20'] else "❌ 月線之下")
trend_status = "強勢多方" if trend_ok else ("弱勢反彈" if data['p_close'] > data['ma20'] else "空方")

# 2. 技術動能：三線多頭排列 且 5MA斜率向上
momentum_ok = data['ma5'] > data['ma10'] > data['ma20'] and data['ma5'] > data['ma5_yesterday']
momentum_text = "✅ 三線多頭且動能向上" if momentum_ok else ("⚠️ 5MA>10MA但排列不完整" if data['ma5'] > data['ma10'] else "❌ 均線空頭排列")
momentum_status = "強勁" if momentum_ok else ("普通" if data['ma5'] > data['ma10'] else "疲弱")

# 3. 成交量能：今日量 > 20日均量1.5倍 且 收紅（量增價漲）
price_up = data['p_close'] > data['p_open']
vol_strong = data['vol_today'] > data['v_ma20'] * 1.5
volume_ok = vol_strong and price_up
volume_text = "✅ 量增價漲（突破均量1.5倍）" if volume_ok else ("⚠️ 帶量但收黑（注意出貨）" if vol_strong and not price_up else "❌ 量能不足")
volume_status = "熱絡" if volume_ok else ("警示" if vol_strong and not price_up else "常態")

# 4. 籌碼力道：投信優先，外資+投信更強
inst_strong = data['trust_3d'] > 0 and data['foreign_3d'] > 0   # 外資+投信同買
inst_ok = data['trust_3d'] > 0                                    # 至少投信買超
chip_text = "🔥 外資+投信聯合買超" if inst_strong else ("✅ 投信持續買超" if inst_ok else ("⚠️ 僅外資買超" if data['foreign_3d'] > 0 else "❌ 法人賣出"))
chip_status = "強力推升" if inst_strong else ("推升" if inst_ok else ("觀望" if data['foreign_3d'] > 0 else "壓力"))

# === 評分邏輯：技術面必須同時過才有資格 ===
tech_pass = trend_ok and momentum_ok   # 技術面是基本門檻
score = sum([trend_ok, momentum_ok, volume_ok, inst_ok])

if tech_pass and score >= 3:
    st.success(f"🔥 綜合評價：強力關注 (得分: {score}/4)")
elif tech_pass and score == 2:
    st.warning(f"👀 綜合評價：技術面穩固，持續觀察 (得分: {score}/4)")
else:
    st.info(f"⚖️ 綜合評價：中性觀望 (得分: {score}/4)")

diag_rows = [
    ["1", "技術趨勢", trend_text, trend_status],
    ["2", "技術動能", momentum_text, momentum_status],
    ["3", "成交量能", volume_text, volume_status],
    ["4", "籌碼力道", chip_text, chip_status],
]

diag_df = pd.DataFrame(diag_rows, columns=["#", "項目", "診斷結果與標準定義", "狀態"])
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

