import streamlit as st
import yfinance as yf
import pandas as pd
from FinMind.data import DataLoader
from datetime import datetime, timedelta

# 頁面設定
st.set_page_config(page_title="台股全能診斷師", layout="wide")

# --- 強化版 FinMind 登入邏輯 ---
@st.cache_resource
def init_finmind():
    try:
        # 檢查 Secrets 是否存在
        if "FINMIND_TOKEN" not in st.secrets:
            st.error("❌ 找不到 FINMIND_TOKEN！請在 Streamlit Cloud 的 Advanced Settings -> Secrets 中設定。")
            return None
        
        token = st.secrets["FINMIND_TOKEN"]
        dl = DataLoader()
        dl.login(token=token)
        return dl
    except Exception as e:
        st.error(f"❌ FinMind 登入異常: {e}")
        return None

# 初始化 DataLoader
dl_client = init_finmind()

# --- 側邊欄：功能選單 ---
st.sidebar.title("🚀 選股神器 2.0")
stock_id = st.sidebar.text_input("輸入股票代碼 (上市/上櫃)", value="2330")
analyze_btn = st.sidebar.button("執行全方位診斷")

def get_data(stock_id, dl):
    # --- 自動判斷上市 (.TW) 或 上櫃 (.TWO) ---
    ticker = yf.Ticker(f"{stock_id}.TW")
    df_yf = ticker.history(period="3mo")
    
    if df_yf.empty:
        ticker = yf.Ticker(f"{stock_id}.TWO")
        df_yf = ticker.history(period="3mo")
    
    # 準備日期
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=100)).strftime('%Y-%m-%d')
    
    # 檢查 dl 是否有效才抓取數據
    df_daily = pd.DataFrame()
    df_inst = pd.DataFrame()
    
    if dl:
        try:
            df_daily = dl.taiwan_stock_daily(stock_id=stock_id, start_date=start_date, end_date=end_date)
            df_inst = dl.taiwan_stock_institutional_investors(stock_id=stock_id, start_date=start_date, end_date=end_date)
        except:
            pass
    
    return df_yf, df_daily, df_inst, ticker

if analyze_btn or stock_id:
    if dl_client is None:
        st.warning("⚠️ 目前處於『離線模式』(FinMind 未登入)，僅顯示基本行情與新聞。")
    
    try:
        df_yf, df_daily, df_inst, ticker = get_data(stock_id, dl_client)
        
        if df_yf.empty:
            st.error(f"❌ 找不到代碼 {stock_id} 的資料，請確認輸入是否正確。")
        else:
            info = ticker.info
            curr = df_yf['Close'].iloc[-1]
            prev = df_yf['Close'].iloc[-2]
            diff = curr - prev
            pct = (diff / prev) * 100

            # --- 1. 核心報價 ---
            name = info.get('longName') or info.get('shortName') or stock_id
            st.title(f"📈 {name} 診斷報告")
            c1, c2, c3 = st.columns(3)
            c1.metric("最新價格", f"{curr:.2f}", f"{diff:+.2f} ({pct:+.2f}%)")
            
            # --- 2. 技術面診斷 ---
            st.subheader("🔍 技術面分析")
            ma5 = df_yf['Close'].rolling(5).mean().iloc[-1]
            ma20 = df_yf['Close'].rolling(20).mean().iloc[-1]
            
            t1, t2, t3 = st.columns(3)
            with t1:
                trend = "多頭排列 🟢" if curr > ma5 else "空頭排列 🔴"
                st.info(f"**五日線趨勢**\n\n{trend}")
            with t2:
                bias = ((curr - ma20) / ma20) * 100
                st.warning(f"**月線乖離**\n\n{bias:.2f}%")
            with t3:
                vol_ratio = (df_yf['Volume'].iloc[-1] / df_yf['Volume'].tail(5).mean())
                st.success(f"**相對量能**\n\n{vol_ratio:.2f} 倍")

            # --- 3. 籌碼面監控 ---
            st.subheader("👥 法人動向 (近 3 日)")
            if not df_inst.empty:
                recent_inst = df_inst.tail(10).copy()
                recent_inst['buy_net'] = recent_inst['buy'] - recent_inst['sell']
                summary_inst = recent_inst.groupby('name')['buy_net'].apply(lambda x: x.tail(3).sum()).reset_index()
                
                i1, i2 = st.columns(2)
                for idx, row in summary_inst.iterrows():
                    col = i1 if idx % 2 == 0 else i2
                    icon = "⬆️" if row['buy_net'] > 0 else "⬇️"
                    col.write(f"**{row['name']}**: {icon} {int(row['buy_net']):,} 股")
            else:
                st.write("💡 無法取得籌碼數據 (請檢查 Token 或稍後再試)")

            st.divider()

            # --- 4. 焦點新聞 ---
            st.subheader("📰 相關焦點新聞")
            news = ticker.news
            if news:
                for item in news[:5]:
                    with st.expander(item['title']):
                        st.write(f"**來源：** {item['publisher']}")
                        st.link_button("閱讀完整內容", item['link'])
            else:
                st.write("目前無相關新聞報導。")

            # --- 5. 評分 ---
            st.subheader("💡 綜合診斷評分")
            score = 0
            if curr > ma5: score += 40
            if vol_ratio > 1.2: score += 30
            if not df_inst.empty and summary_inst['buy_net'].sum() > 0: score += 30
            st.progress(score / 100)
            st.write(f"當前評分：**{score} 分**")

    except Exception as e:
        st.error(f"分析發生錯誤: {e}")

st.caption(f"最後更新: {datetime.now().strftime('%H:%M:%S')} | 支援上市(TW)/上櫃(TWO)")
