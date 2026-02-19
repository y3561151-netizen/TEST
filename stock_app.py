import streamlit as st
import yfinance as yf
import pandas as pd
from FinMind.data import DataLoader
from datetime import datetime, timedelta
import time

# 頁面設定
st.set_page_config(page_title="台股全能診斷師", layout="wide")

# --- 強化版 FinMind 初始化 (帶快取) ---
@st.cache_resource
def get_dl_client():
    try:
        if "FINMIND_TOKEN" not in st.secrets:
            return None
        token = st.secrets["FINMIND_TOKEN"]
        dl = DataLoader()
        # 注意：某些 FinMind 版本不需要 login 屬性，改用直接帶入或 token 驗證
        try:
            dl.login(token=token)
        except AttributeError:
            pass 
        return dl
    except:
        return None

# --- 資料抓取 (帶快取，避免重複請求觸發 Rate Limit) ---
@st.cache_data(ttl=3600) # 資料暫存 1 小時
def fetch_stock_data(stock_id, _dl):
    # yfinance 基礎行情
    ticker = yf.Ticker(f"{stock_id}.TW")
    df_yf = ticker.history(period="3mo")
    if df_yf.empty:
        ticker = yf.Ticker(f"{stock_id}.TWO")
        df_yf = ticker.history(period="3mo")
    
    # 籌碼數據
    df_inst = pd.DataFrame()
    if _dl and not df_yf.empty:
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=20)).strftime('%Y-%m-%d')
            df_inst = _dl.taiwan_stock_institutional_investors(
                stock_id=stock_id, start_date=start_date, end_date=end_date
            )
        except:
            pass # 抓不到籌碼則回傳空表
            
    return df_yf, df_inst, ticker

# --- 主程式 ---
dl_client = get_dl_client()

st.sidebar.title("🚀 選股神器 2.0")
stock_id = st.sidebar.text_input("輸入股票代碼", value="2330")
analyze_btn = st.sidebar.button("執行全方位診斷")

if analyze_btn or stock_id:
    # 顯示載入動畫
    with st.spinner('正在分析市場數據...'):
        df_yf, df_inst, ticker = fetch_stock_data(stock_id, dl_client)
        
    if df_yf.empty:
        st.error(f"❌ 找不到代碼 {stock_id} 的資料。")
    else:
        # --- 顯示介面 ---
        info = ticker.info
        name = info.get('longName') or info.get('shortName') or stock_id
        curr = df_yf['Close'].iloc[-1]
        prev = df_yf['Close'].iloc[-2]
        diff = curr - prev
        pct = (diff / prev) * 100

        st.title(f"📈 {name} 診斷報告")
        c1, c2, c3 = st.columns(3)
        c1.metric("價格", f"{curr:.2f}", f"{diff:+.2f} ({pct:+.2f}%)")
        
        # 簡易技術分析
        ma5 = df_yf['Close'].rolling(5).mean().iloc[-1]
        vol_ratio = (df_yf['Volume'].iloc[-1] / df_yf['Volume'].tail(5).mean())
        
        c2.metric("五日均線", f"{ma5:.2f}", "多頭" if curr > ma5 else "空頭")
        c3.metric("相對量能", f"{vol_ratio:.2f}x")

        st.divider()

        # 籌碼面
        st.subheader("👥 法人籌碼 (近 3 日)")
        if not df_inst.empty:
            df_inst['buy_net'] = df_inst['buy'] - df_inst['sell']
            summary = df_inst.groupby('name')['buy_net'].apply(lambda x: x.tail(3).sum()).reset_index()
            i1, i2 = st.columns(2)
            for idx, row in summary.iterrows():
                col = i1 if idx % 2 == 0 else i2
                col.write(f"**{row['name']}**: {'⬆️' if row['buy_net']>0 else '⬇️'} {int(row['buy_net']):,} 股")
        else:
            st.warning("⚠️ 籌碼數據目前無法取得 (API 限制中)，請稍後再試。")

        # 新聞區
        st.subheader("📰 相關焦點新聞")
        news = ticker.news
        if news:
            for item in news[:3]:
                with st.expander(item['title']):
                    st.write(f"來源: {item['publisher']}")
                    st.link_button("閱讀完整內容", item['link'])

st.caption(f"最後更新時間: {datetime.now().strftime('%H:%M:%S')}")
