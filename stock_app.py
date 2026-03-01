import streamlit as st
import yfinance as yf
import pandas as pd
from FinMind.data import DataLoader
from datetime import datetime, timedelta

# --- 1. 基礎設定與 Token 安全檢查 ---
st.set_page_config(page_title="台股智慧分析師 Pro Max", layout="wide")
FINMIND_TOKEN = st.secrets.get("FINMIND_TOKEN", "")

if 'stock_id' not in st.session_state:
    st.session_state.stock_id = "2330"

# --- 2. 核心分析引擎 ---
def get_stock_analysis(sid):
    try:
        # 自動切換上市櫃字尾
        df = yf.download(f"{sid}.TW", period="8mo", progress=False)
        if df.empty:
            df = yf.download(f"{sid}.TWO", period="8mo", progress=False)
        if df.empty: return None
        
        df.columns = df.columns.get_level_values(0) if isinstance(df.columns, pd.MultiIndex) else df.columns
        
        # 技術指標計算
        df['5MA'] = df['Close'].rolling(5).mean()
        df['10MA'] = df['Close'].rolling(10).mean()
        df['20MA'] = df['Close'].rolling(20).mean()
        df['20VMA'] = df['Volume'].rolling(20).mean()
        
        l, p, f = df.iloc[-1], df.iloc[-2], df.iloc[-6]
        p_close = float(l['Close'])
        p_change = p_close - float(p['Close'])
        ma5, ma10, ma20 = float(l['5MA']), float(l['10MA']), float(l['20MA'])
        ma20_old, ma5_old = float(f['20MA']), float(p['5MA'])
        vol_today, v_ma20 = float(l['Volume']), float(l['20VMA'])

        # --- 診斷邏輯 ---
        c1 = (p_close > ma20) and (ma20 > ma20_old)        # 趨勢：站上且月線向上
        c2 = (ma5 > ma10 > ma20) and (ma5 > ma5_old)      # 動能：多頭排列且5MA向上
        c3 = (vol_today > v_ma20 * 1.5) and (p_change > 0) # 量能：價漲量增
        
        # 籌碼數據抓取
        sitc_buy, foreign_buy, total_inst_buy = False, False, False
        try:
            dl = DataLoader()
            dl.login_by_token(api_token=FINMIND_TOKEN)
            inst = dl.taiwan_stock_institutional_investors(stock_id=sid, start_date=(datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d'))
            if not inst.empty:
                last_d = inst['date'].max()
                t_inst = inst[inst['date'] == last_d]
                s_net = t_inst[t_inst['name'] == 'Investment_Trust']['buy'].sum() - t_inst[t_inst['name'] == 'Investment_Trust']['sell'].sum()
                f_net = t_inst[t_inst['name'] == 'Foreign_Investor']['buy'].sum() - t_inst[t_inst['name'] == 'Foreign_Investor']['sell'].sum()
                sitc_buy = s_net > 0
                foreign_buy = f_net > 0
                total_inst_buy = (s_net + f_net) > 0
        except: pass

        # 狀態判定
        tech_pass = c1 and c2
        if not tech_pass: status = "📉 弱勢整理 (技術門檻未過)"
        elif sitc_buy and foreign_buy and c3: status = "🚀 強力關注 (雙資併買+量能攻擊)"
        elif sitc_buy: status = "🔥 趨勢偏多 (投信積極介入)"
        else: status = "👀 觀察 (技術過、籌碼普普)"

        return {
            "p_close": p_close, "p_change": p_change, "ma5": ma5, "ma10": ma10, "ma20": ma20,
            "vol_today": vol_today/1000, "v_ma20": v_ma20/1000, "bias": ((p_close - ma20) / ma20) * 100,
            "c1": c1, "c2": c2, "c3": c3, "sitc_buy": sitc_buy, "foreign_buy": foreign_buy, "status": status
        }
    except: return None

# --- 3. 側邊欄 ---
with st.sidebar:
    st.title("⚙️ 診斷設定")
    stock_input = st.text_input("輸入台股代號", value=st.session_state.stock_id)
    if st.button("執行診斷"):
        st.session_state.stock_id = stock_input
        st.rerun()
    st.divider()
    st.info("💡 提示：支援上市(.TW)與上櫃(.TWO)自動切換")

# --- 4. 主畫面顯示 ---
data = get_stock_analysis(st.session_state.stock_id)

if data:
    st.header(f"📈 {st.session_state.stock_id} 深度診斷報告")
    
    # 第一區：即時數據儀表板
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("當前價格", f"{data['p_close']:.2f}", f"{data['p_change']:+.2f}")
    t2.metric("月線乖離率", f"{data['bias']:.1f}%", "過熱" if data['bias'] > 10 else "安全", delta_color="inverse")
    t3.metric("今日成交張數", f"{data['vol_today']:.0f} 張")
    t4.metric("量能狀態", "爆量攻擊" if data['c3'] else "常態")

    # 第二區：AI 診斷表格 (包含您要求的所有籌碼指標)
    st.divider()
    st.subheader(f"🤖 AI 綜合診斷結果：{data['status']}")
    
    diag_rows = [
        ["1", "技術趨勢", "✅ 站上月線且月線向上" if data['c1'] else "❌ 月線下彎或股價未站上", "通過" if data['c1'] else "失敗"],
        ["2", "技術動能", "✅ 5>10>20 多頭排列且5MA向上" if data['c2'] else "❌ 排列混亂或動能轉弱", "通過" if data['c2'] else "失敗"],
        ["3", "成交量能", "✅ 價漲且量增 1.5 倍" if data['c3'] else "❌ 量能不足或價跌", "加分" if data['c3'] else "無"],
        ["4", "投信指標", "✅ 投信買超中 (最重要指標)" if data['sitc_buy'] else "❌ 投信無動作", "通過" if data['sitc_buy'] else "未過"],
        ["5", "外資指標", "✅ 外資同步買超" if data['foreign_buy'] else "❌ 外資賣超或無動作", "加分" if data['foreign_buy'] else "無"],
        ["6", "法人共識", "✅ 投信與外資聯手作多" if (data['sitc_buy'] and data['foreign_buy']) else "❌ 意見分歧", "強勢" if data['sitc_buy'] else "保守"]
    ]
    diag_df = pd.DataFrame(diag_rows, columns=["#", "診斷指標項目", "詳細標準定義與現況", "判定"])
    st.write(diag_df.to_html(index=False, justify='left'), unsafe_allow_html=True)

    # 第三區：新聞模組
    st.divider()
    st.subheader("📰 即時相關新聞")
    try:
        dl = DataLoader()
        dl.login_by_token(api_token=FINMIND_TOKEN)
        news = dl.taiwan_stock_news(stock_id=st.session_state.stock_id, start_date=(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'))
        if not news.empty:
            for _, row in news.head(5).iterrows():
                with st.expander(f"📌 {row['title']}"):
                    st.write(f"來源: {row['source']} | [閱讀全文]({row['link']})")
        else: st.write("近期無相關新聞。")
    except: st.warning("新聞模組暫時無法使用。")

else:
    st.error(f"❌ 查無代號 {st.session_state.stock_id}。請檢查代號是否正確。")

st.caption(f"更新時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 嚴謹邏輯版 V3.0")

