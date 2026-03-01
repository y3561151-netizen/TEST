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
        df = yf.download(f"{sid}.TW", period="6mo", progress=False)
        if df.empty:
            df = yf.download(f"{sid}.TWO", period="6mo", progress=False)
            
        if df.empty: return None
        
        df.columns = df.columns.get_level_values(0) if isinstance(df.columns, pd.MultiIndex) else df.columns
        
        df['5MA']  = df['Close'].rolling(5).mean()
        df['10MA'] = df['Close'].rolling(10).mean()
        df['20MA'] = df['Close'].rolling(20).mean()
        df['5VMA'] = df['Volume'].rolling(5).mean()
        df['20VMA'] = df['Volume'].rolling(20).mean()  # 新增：20日均量
        
        latest = df.iloc[-1]
        prev   = df.iloc[-2]  # 新增：前一日資料

        p_close  = float(latest['Close'])
        p_open   = float(latest['Open'])   # 新增：今日開盤（判斷收紅）
        ma5      = float(latest['5MA'])
        ma10     = float(latest['10MA'])
        ma20     = float(latest['20MA'])
        vol_today = float(latest['Volume']) / 1000
        v_ma5    = float(latest['5VMA']) / 1000
        v_ma20   = float(latest['20VMA']) / 1000  # 新增

        # 新增：5天前的20MA（判斷月線方向）
        ma20_5d_ago = float(df.iloc[-6]['20MA']) if len(df) >= 6 else ma20
        # 新增：昨天的5MA（判斷5MA斜率）
        ma5_yesterday = float(prev['5MA'])

        # FinMind 籌碼
        dl = DataLoader()
        dl.login_by_token(api_token=FINMIND_TOKEN)
        inst = dl.taiwan_stock_institutional_investors(
            stock_id=sid,
            start_date=(datetime.now() - timedelta(days=12)).strftime('%Y-%m-%d')
        )
        
        consecutive_buy = False
        total_inst_3d   = 0
        trust_3d        = 0   # 投信近3日
        foreign_3d      = 0   # 外資近3日
        dealer_3d       = 0   # 自營商近3日

        if not inst.empty:
            # 原本的法人合計
            daily = inst.groupby('date').apply(
                lambda x: x[x['name'].isin(['Foreign_Investor', 'Investment_Trust'])]['buy'].sum()
                        - x[x['name'].isin(['Foreign_Investor', 'Investment_Trust'])]['sell'].sum()
            )
            total_inst_3d = daily.tail(3).sum() / 1000
            if len(daily) >= 3 and (daily.tail(3) > 0).all():
                consecutive_buy = True

            # 新增：投信單獨計算
            trust_daily = inst[inst['name'] == 'Investment_Trust'].groupby('date').apply(
                lambda x: x['buy'].sum() - x['sell'].sum()
            )
            trust_3d = trust_daily.tail(3).sum() / 1000

            # 新增：外資單獨計算
            foreign_daily = inst[inst['name'] == 'Foreign_Investor'].groupby('date').apply(
                lambda x: x['buy'].sum() - x['sell'].sum()
            )
            foreign_3d = foreign_daily.tail(3).sum() / 1000

            # 新增：自營商單獨計算
            dealer_daily = inst[inst['name'] == 'Dealer_self'].groupby('date').apply(
                lambda x: x['buy'].sum() - x['sell'].sum()
            )
            dealer_3d = dealer_daily.tail(3).sum() / 1000 if not dealer_daily.empty else 0

        # === 新版評分邏輯 ===

        # 1. 技術趨勢：站上月線 且 月線向上
        trend_ok = (p_close > ma20) and (ma20 > ma20_5d_ago)

        # 2. 技術動能：三線多頭排列 且 5MA斜率向上
        momentum_ok = (ma5 > ma10 > ma20) and (ma5 > ma5_yesterday)

        # 3. 成交量能：今日量 > 20日均量1.5倍 且 收紅（量增價漲）
        price_up  = p_close > p_open
        vol_strong = vol_today > v_ma20 * 1.5
        volume_ok  = vol_strong and price_up

        # 4. 外資近3日買賣超
        foreign_ok = foreign_3d > 0

        # 5. 投信近3日買賣超
        trust_ok = trust_3d > 0

        # 6. 自營商近3日買賣超
        dealer_ok = dealer_3d > 0

        # 技術面必須同時過才有資格（門檻條件）
        tech_pass = trend_ok and momentum_ok
        score = sum([trend_ok, momentum_ok, volume_ok, foreign_ok, trust_ok, dealer_ok])

        return {
            "df": df, "latest": latest,
            "score": score, "tech_pass": tech_pass,
            "p_close": p_close, "p_open": p_open,
            "ma5": ma5, "ma10": ma10, "ma20": ma20,
            "ma20_5d_ago": ma20_5d_ago, "ma5_yesterday": ma5_yesterday,
            "vol_today": vol_today, "v_ma5": v_ma5, "v_ma20": v_ma20,
            "price_up": price_up, "vol_strong": vol_strong,
            "consecutive": consecutive_buy, "total_inst_3d": total_inst_3d,
            "trust_3d": trust_3d, "foreign_3d": foreign_3d, "dealer_3d": dealer_3d,
            "trend_ok": trend_ok, "momentum_ok": momentum_ok,
            "volume_ok": volume_ok,
            "foreign_ok": foreign_ok, "trust_ok": trust_ok, "dealer_ok": dealer_ok,
            "bias": ((p_close - ma20) / ma20) * 100
        }
    except Exception as e:
        return None

# --- 2. 側邊欄 ---
with st.sidebar:
    st.title("⚙️ 診斷設定")
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
                if res and res['tech_pass'] and res['score'] >= 5:  # 技術面必須過，6選5
                    label = f"🚀 {s_id} ({res['score']}分)"
                    if res['consecutive']: label += " 🔥連買"
                    if st.button(label, key=f"btn_scan_{s_id}"):
                        st.session_state.stock_id = s_id
                        st.rerun()

    st.write("📋 **統一篩選邏輯說明**")
    logic_df = pd.DataFrame({
        "項目": ["1.技術趨勢", "2.技術動能", "3.量能表現", "4.外資", "5.投信", "6.自營商"],
        "標準": ["價格>20MA 且月線向上", "5MA>10MA>20MA 且斜率向上", "量>20均量1.5倍 且收紅", "近3日買超", "近3日買超", "近3日買超"]
    })
    st.write(logic_df.to_html(index=False, justify='center'), unsafe_allow_html=True)

# --- 3. 主畫面 ---
data = get_stock_analysis(st.session_state.stock_id)

if data:
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
    b2.metric("量能狀態", "爆量攻擊" if data['vol_strong'] else "正常", delta=f"{data['vol_today']/data['v_ma20']:.1f}x 20日均量")

    # 第三區：AI 診斷報告
    st.divider()
    st.subheader("🤖 AI 投資客綜合診斷")

    # 技術趨勢文字
    if data['trend_ok']:
        trend_text, trend_status = "✅ 站上月線且月線向上", "強勢多方"
    elif data['p_close'] > data['ma20']:
        trend_text, trend_status = "⚠️ 站上月線但月線向下", "弱勢反彈"
    else:
        trend_text, trend_status = "❌ 月線之下", "空方"

    # 技術動能文字
    if data['momentum_ok']:
        momentum_text, momentum_status = "✅ 三線多頭且動能向上", "強勁"
    elif data['ma5'] > data['ma10']:
        momentum_text, momentum_status = "⚠️ 5MA>10MA但排列不完整", "普通"
    else:
        momentum_text, momentum_status = "❌ 均線空頭排列", "疲弱"

    # 成交量能文字
    if data['volume_ok']:
        volume_text, volume_status = "✅ 量增價漲（突破均量1.5倍）", "熱絡"
    elif data['vol_strong'] and not data['price_up']:
        volume_text, volume_status = "⚠️ 帶量但收黑（注意出貨）", "警示"
    else:
        volume_text, volume_status = "❌ 量能不足", "常態"

    # 外資文字
    if data['foreign_ok']:
        foreign_text, foreign_status = f"✅ 買超 {data['foreign_3d']:.0f} 張", "買超"
    else:
        foreign_text, foreign_status = f"❌ 賣超 {abs(data['foreign_3d']):.0f} 張", "賣超"

    # 投信文字
    if data['trust_ok']:
        trust_text, trust_status = f"✅ 買超 {data['trust_3d']:.0f} 張", "買超"
    else:
        trust_text, trust_status = f"❌ 賣超 {abs(data['trust_3d']):.0f} 張", "賣超"

    # 自營商文字
    if data['dealer_ok']:
        dealer_text, dealer_status = f"✅ 買超 {data['dealer_3d']:.0f} 張", "買超"
    else:
        dealer_text, dealer_status = f"❌ 賣超 {abs(data['dealer_3d']):.0f} 張", "賣超"

    # 綜合評價（技術面必須同時過，6選5以上強力關注）
    if data['tech_pass'] and data['score'] >= 5:
        st.success(f"🔥 綜合評價：強力關注 (得分: {data['score']}/6)")
    elif data['tech_pass'] and data['score'] == 4:
        st.warning(f"👀 綜合評價：技術面穩固，持續觀察 (得分: {data['score']}/6)")
    else:
        st.info(f"⚖️ 綜合評價：中性觀望 (得分: {data['score']}/6)")

    diag_rows = [
        ["1", "技術趨勢",  trend_text,    trend_status],
        ["2", "技術動能",  momentum_text, momentum_status],
        ["3", "成交量能",  volume_text,   volume_status],
        ["4", "外資(3日)", foreign_text,  foreign_status],
        ["5", "投信(3日)", trust_text,    trust_status],
        ["6", "自營商(3日)", dealer_text, dealer_status],
    ]
    diag_df = pd.DataFrame(diag_rows, columns=["#", "項目", "診斷結果與標準定義", "狀態"])
    st.write(diag_df.to_html(index=False, justify='left'), unsafe_allow_html=True)

    # 第五區：新聞
    st.divider()
    st.subheader("📰 即時相關新聞")
    try:
        dl_news = DataLoader()
        dl_news.login_by_token(api_token=FINMIND_TOKEN)
        news = dl_news.taiwan_stock_news(
            stock_id=st.session_state.stock_id,
            start_date=(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        )
        if not news.empty:
            for _, row in news.head(5).iterrows():
                with st.expander(f"📌 {row['title']}"):
                    st.write(f"來源: {row['source']} | [連結]({row['link']})")
        else:
            st.info("近期無相關新聞。")
    except:
        st.warning("新聞模組讀取失敗。")
else:
    st.error(f"查無 {st.session_state.stock_id} 數據，請確認代號是否正確。")
