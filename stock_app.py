import streamlit as st
import yfinance as yf
import pandas as pd
from FinMind.data import DataLoader
from datetime import datetime, timedelta

# 頁面設定
st.set_page_config(page_title="台股全能診斷師", layout="wide")

# --- 資料抓取與自動判斷上市櫃 ---
@st.cache_data(ttl=3600) # 快取 1 小時以節省 API 流量
def fetch_stock_dfs(stock_id):
    # 1. 優先嘗試上市公司字尾 (.TW)
    suffix = ".TW"
    ticker = yf.Ticker(f"{stock_id}{suffix}")
    df_yf = ticker.history(period="3mo")
    
    # 2. 如果上市公司沒資料，切換嘗試上櫃公司字尾 (.TWO)
    if df_yf.empty:
        suffix = ".TWO"
        ticker = yf.Ticker(f"{stock_id}{suffix}")
        df_yf = ticker.history(period="3mo")
    
    # 3. 抓取 FinMind 籌碼資料 (需 Token)
    df_inst = pd.DataFrame()
    if "FINMIND_TOKEN" in st.secrets:
        try:
            dl = DataLoader()
            dl.login(token=st.secrets["FINMIND_TOKEN"])
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=20)).strftime('%Y-%m-%d')
            df_inst = dl.taiwan_stock_institutional_investors(
                stock_id=stock_id, start_date=start_date, end_date=end_date
            )
        except:
            pass # 若 FinMind API 達到上限，則略過籌碼部分
            
    return df_yf, df_inst, suffix

# --- 側邊欄設計 ---
st.sidebar.title("🚀 選股神器 2.0")
stock_id = st.sidebar.text_input("輸入代碼 (例: 2330 或 8069)", value="2330")
analyze_btn = st.sidebar.button("執行診斷")

# --- 主畫面邏輯 ---
if analyze_btn or stock_id:
    with st.spinner('連線交易所中...'):
        df_yf, df_inst, active_suffix = fetch_stock_dfs(stock_id)
        # 建立即時物件
        ticker_obj = yf.Ticker(f"{stock_id}{active_suffix}")
        
    if df_yf.empty:
        st.error(f"❌ 找不到代碼 {stock_id}。請檢查代號是否正確。")
    else:
        # 取得股票基本資訊
        info = ticker_obj.info
        name = info.get('longName') or info.get('shortName') or stock_id
        curr = df_yf['Close'].iloc[-1]
        prev = df_yf['Close'].iloc[-2]
        diff = curr - prev
        pct = (diff / prev) * 100

        # --- 顯示區塊 1: 即時報價 ---
        st.title(f"📈 {name} ({stock_id}{active_suffix})")
        c1, c2, c3 = st.columns(3)
        c1.metric("當前價格", f"{curr:.2f}", f"{diff:+.2f} ({pct:+.2f}%)")
        
        # 技術面指標 (MA5)
        ma5 = df_yf['Close'].rolling(5).mean().iloc[-1]
        c2.metric("五日均線", f"{ma5:.2f}", "多頭排列" if curr > ma5 else "空頭排列")
        
        # 量能指標
        vol_ratio = (df_yf['Volume'].iloc[-1] / df_yf['Volume'].tail(5).mean())
        c3.metric("相對量能", f"{vol_ratio:.2f}x", "爆量" if vol_ratio > 1.5 else "常態")

        st.divider()

        # --- 顯示區塊 2: 法人籌碼 ---
        st.subheader("👥 近三日法人買賣超")
        if not df_inst.empty:
            df_inst['buy_net'] = df_inst['buy'] - df_inst['sell']
            summary = df_inst.groupby('name')['buy_net'].apply(lambda x: x.tail(3).sum()).reset_index()
            i1, i2 = st.columns(2)
            for idx, row in summary.iterrows():
                col = i1 if idx % 2 == 0 else i2
                icon = "⬆️" if row['buy_net'] > 0 else "⬇️"
                col.write(f"**{row['name']}**: {icon} {int(row['buy_net']):,} 股")
        else:
            st.warning("⚠️ 目前 API 忙碌中或無籌碼數據，請參考報價與新聞。")

        # --- 顯示區塊 3: 焦點新聞 ---
        st.subheader("📰 最新焦點新聞")
        try:
            news = ticker_obj.news
            if news:
                for item in news[:3]:
                    with st.expander(item['title']):
                        st.write(f"來源: {item['publisher']}")
                        st.link_button("閱讀全文", item['link'])
            else:
                st.write("目前無相關新聞。")
        except:
            st.write("暫時無法取得新聞。")

st.caption(f"更新時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 系統支援上市(.TW)及上櫃(.TWO)股票查詢")
