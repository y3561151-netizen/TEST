import streamlit as st
import yfinance as yf
import pandas as pd
from FinMind.data import DataLoader
from datetime import datetime, timedelta

# 頁面設定
st.set_page_config(page_title="台股智慧分析師", layout="wide")

# 從 Secrets 讀取 Token
FINMIND_TOKEN = st.secrets["FINMIND_TOKEN"]
dl = DataLoader()
dl.login(token=FINMIND_TOKEN)

# --- 側邊欄：功能選單 ---
st.sidebar.title("🚀 選股神器 2.0")
stock_id = st.sidebar.text_input("輸入股票代碼", value="2330")
analyze_btn = st.sidebar.button("開始診斷")

def get_stock_data(stock_id):
    # 取得 yfinance 數據
    ticker = yf.Ticker(f"{stock_id}.TW")
    df_yf = ticker.history(period="1mo")
    
    # 取得 FinMind 數據 (用於技術指標)
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
    df_fm = dl.taiwan_stock_daily(stock_id=stock_id, start_date=start_date, end_date=end_date)
    
    return df_yf, df_fm, ticker

if analyze_btn or stock_id:
    try:
        df_yf, df_fm, ticker = get_stock_data(stock_id)
        info = ticker.info
        current_price = df_yf['Close'].iloc[-1]
        prev_price = df_yf['Close'].iloc[-2]
        change = current_price - prev_price
        change_pct = (change / prev_price) * 100

        # --- 1. 核心報價 ---
        st.title(f"📈 {info.get('longName', stock_id)} 診斷報告")
        col1, col2, col3 = st.columns(3)
        col1.metric("最新價格", f"{current_price:.2f}", f"{change:+.2f} ({change_pct:+.2f}%)")
        
        # --- 2. 技術診斷 ---
        st.subheader("🔍 技術面分析")
        ma5 = df_yf['Close'].rolling(5).mean().iloc[-1]
        ma20 = df_yf['Close'].rolling(20).mean().iloc[-1]
        
        t_col1, t_col2 = st.columns(2)
        with t_col1:
            status = "多頭排列 💹" if current_price > ma5 > ma20 else "空頭排列 📉" if current_price < ma5 < ma20 else "震盪整理 ⚖️"
            st.info(f"**短中線趨勢：** {status}")
        with t_col2:
            bias = ((current_price - ma20) / ma20) * 100
            st.warning(f"**月線乖離率：** {bias:.2f}%")

        st.divider()

        # --- 3. 量能監控 ---
        st.subheader("📊 量能監控")
        current_vol = df_yf['Volume'].iloc[-1] / 1000  # 換算成張數
        avg_vol = df_yf['Volume'].tail(5).mean() / 1000
        vol_ratio = current_vol / avg_vol if avg_vol > 0 else 1
        
        v_col1, v_col2 = st.columns(2)
        with v_col1:
            st.metric("今日成交張數", f"{int(current_vol):,} 張")
        with v_col2:
            vol_status = "爆量攻擊" if vol_ratio > 1.5 else "量縮整理" if vol_ratio < 0.7 else "量能平穩"
            st.metric("量能狀態", vol_status, f"{vol_ratio:.1f}x 均量")

        st.divider()

        # --- 4. 最新相關新聞 (新增區塊) ---
        st.subheader("📰 相關焦點新聞")
        news = ticker.news
        if news:
            for item in news[:5]: # 只顯示前 5 則新聞
                with st.expander(item['title']):
                    st.write(f"**來源：** {item['publisher']}")
                    st.write(f"**發布時間：** {datetime.fromtimestamp(item['providerPublishTime']).strftime('%Y-%m-%d %H:%M')}")
                    st.link_button("閱讀完整內容", item['link'])
        else:
            st.write("暫無相關新聞。")

        st.divider()

        # --- 5. 綜合評價 ---
        st.subheader("💡 AI 投資建議")
        score = 0
        if current_price > ma5: score += 40
        if vol_ratio > 1: score += 30
        if bias < 5: score += 30
        
        st.progress(score / 100)
        st.write(f"目前診斷總分：**{score} 分**")

    except Exception as e:
        st.error(f"資料讀取失敗，請確認代碼是否正確。錯誤訊息: {e}")

# 版權宣告
st.caption("數據僅供參考，投資有風險，入市需謹慎。")