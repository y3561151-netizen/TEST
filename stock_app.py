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

# --- 核心數據函式 ---
def get_stock_analysis(sid):
    try:
        # 自動判斷上市 (.TW) 或 上櫃 (.TWO)
        df = yf.download(f"{sid}.TW", period="8mo", progress=False)
        if df.empty:
            df = yf.download(f"{sid}.TWO", period="8mo", progress=False)
        if df.empty: return None
        
        df.columns = df.columns.get_level_values(0) if isinstance(df.columns, pd.MultiIndex) else df.columns
        
        # 指標計算
        df['5MA'] = df['Close'].rolling(5).mean()
        df['10MA'] = df['Close'].rolling(10).mean()
        df['20MA'] = df['Close'].rolling(20).mean()
        df['20VMA'] = df['Volume'].rolling(20).mean()
        
        l, p, f = df.iloc[-1], df.iloc[-2], df.iloc[-6]
        p_close, p_change = float(l['Close']), float(l['Close']) - float(p['Close'])
        ma5, ma10, ma20 = float(l['5MA']), float(l['10MA']), float(l['20MA'])
        ma20_old, ma5_old = float(f['20MA']), float(p['5MA'])
        vol_today, v_ma20 = float(l['Volume']), float(l['20VMA'])

        # --- 四大診斷條件 ---
        c1 = (p_close > ma20) and (ma20 > ma20_old) # 1. 趨勢：月線站上且向上
        c2 = (ma5 > ma10 > ma20) and (ma5 > ma5_old) # 2. 動能：三線多頭且5MA向上
        c3 = (vol_today > v_ma20 * 1.5) and (p_change > 0) # 3. 量能：價漲量增 1.5x
        
        # 4. 籌碼力道細分
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
                total_inst_buy = (s_net + f_net) > 0 # 僅計算投信與外資總和
        except: pass

        # 評分與狀態判定
        tech_pass = c1 and c2
        score = sum([c1, c2, c3, sitc_buy])
        
        if not tech_pass: status = "📉 弱勢整理 (技術門檻未過)"
        elif sitc_buy and foreign_buy and c3: status = "🚀 強力關注 (雙資併買+量能攻擊)"
        elif sitc_buy: status = "🔥 趨勢偏多 (投信積極介入)"
        else: status = "👀 觀察 (技術過、籌碼普普)"

        return {
            "p_close": p_close, "ma20": ma20, "score": score, "status": status,
            "c1": c1, "c2": c2, "c3": c3, "sitc_buy": sitc_buy, "foreign_buy": foreign_buy, "total_inst_buy": total_inst_buy
        }
    except: return None

# --- 主畫面 ---
st.sidebar.title("⚙️ 診斷設定")
stock_input = st.sidebar.text_input("輸入台股代號", value="2330")
if st.sidebar.button("立即診斷"):
    st.session_state.stock_id = stock_input

data = get_stock_analysis(st.session_state.stock_id)

if data:
    st.header(f"📈 {st.session_state.stock_id} 深度診斷報告")
    st.subheader(f"🤖 綜合評價：{data['status']}")
    
    # 診斷表格內容更新
    diag_rows = [
        ["1", "技術趨勢", "✅ 站上月線且月線向上" if data['c1'] else "❌ 月線下彎或股價未站上", "通過" if data['c1'] else "未過"],
        ["2", "技術動能", "✅ 5>10>20 多頭排列" if data['c2'] else "❌ 均線排列混亂", "通過" if data['c2'] else "未過"],
        ["3", "成交量能", "✅ 價漲且量增 1.5 倍" if data['c3'] else "⚖️ 量能縮減或價跌", "加分" if data['c3'] else "無"],
        ["4", "投信動向 (核心)", "🔥 投信買超中" if data['sitc_buy'] else "❌ 投信無動作", "通過" if data['sitc_buy'] else "未過"],
        ["5", "外資動向 (輔助)", "✅ 外資買超中" if data['foreign_buy'] else "⚖️ 外資賣超或無動作", "加分" if data['foreign_buy'] else "無"],
        ["6", "法人整體 (投+外)", "🚀 雙法人同步作多" if (data['sitc_buy'] and data['foreign_buy']) else "⚖️ 意見分歧", "強勢" if data['total_inst_buy'] else "保守"]
    ]
    
    diag_df = pd.DataFrame(diag_rows, columns=["#", "診斷指標", "標準定義與現況", "狀態"])
    st.write(diag_df.to_html(index=False, justify='left'), unsafe_allow_html=True)

    # 視覺化提示
    if "強力關注" in data['status']:
        st.success("🎯 符合「技術門檻過關 + 雙法人連買 + 量能發動」之完美模型！")
    elif "未過" in data['status']:
        st.error("⚠️ 技術面尚未成形，建議維持觀望，避開下彎均線風險。")

else:
    st.error("請確認輸入的代號是否正確，或稍後再試。")
