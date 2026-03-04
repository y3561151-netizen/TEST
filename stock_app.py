import streamlit as st
import yfinance as yf
import pandas as pd
from FinMind.data import DataLoader
from datetime import datetime, timedelta

# --- 設定區 ---
FINMIND_TOKEN = st.secrets["FINMIND_TOKEN"]
st.set_page_config(page_title="台股智慧分析師 Pro Max", layout="wide")

# --- 初始化狀態 ---
if 'stock_id' not in st.session_state:
    st.session_state.stock_id = "2330"
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None
if 'show_scan' not in st.session_state:
    st.session_state.show_scan = False

# =====================================================================
# 函式 1：只跑技術面（用 yfinance，不消耗 FinMind 額度）
# =====================================================================
def get_tech_only(sid):
    try:
        # 不動代號，原樣使用
        df = yf.download(f"{sid}.TW", period="6mo", progress=False, auto_adjust=True)
        if df.empty:
            df = yf.download(f"{sid}.TWO", period="6mo", progress=False, auto_adjust=True)
        if df.empty:
            return None

        df.columns = df.columns.get_level_values(0) if isinstance(df.columns, pd.MultiIndex) else df.columns
        df['5MA']   = df['Close'].rolling(5).mean()
        df['10MA']  = df['Close'].rolling(10).mean()
        df['20MA']  = df['Close'].rolling(20).mean()
        df['20VMA'] = df['Volume'].rolling(20).mean()

        if df['20MA'].isna().iloc[-1]:
            return None

        latest = df.iloc[-1]
        prev   = df.iloc[-2]

        p_close   = float(latest['Close'])
        p_open    = float(latest['Open'])
        ma5       = float(latest['5MA'])
        ma10      = float(latest['10MA'])
        ma20      = float(latest['20MA'])
        vol_today = float(latest['Volume']) / 1000
        v_ma20    = float(latest['20VMA']) / 1000
        ma20_5d_ago   = float(df.iloc[-6]['20MA']) if len(df) >= 6 else ma20
        ma5_yesterday = float(prev['5MA'])

        trend_ok    = (p_close > ma20) and (ma20 > ma20_5d_ago)
        momentum_ok = (ma5 > ma10 > ma20) and (ma5 > ma5_yesterday)
        tech_pass   = trend_ok and momentum_ok

        return {
            "tech_pass": tech_pass,
            "trend_ok": trend_ok, "momentum_ok": momentum_ok,
            "p_close": p_close, "p_open": p_open,
            "ma5": ma5, "ma10": ma10, "ma20": ma20,
            "ma20_5d_ago": ma20_5d_ago, "ma5_yesterday": ma5_yesterday,
            "vol_today": vol_today, "v_ma20": v_ma20,
            "price_up": p_close > p_open,
            "vol_strong": vol_today > v_ma20 * 1.5,
            "bias": ((p_close - ma20) / ma20) * 100,
            "df": df,
        }
    except:
        return None

# =====================================================================
# 函式 2：完整分析（技術面 + FinMind 籌碼 + 中文名稱）
# =====================================================================
def get_stock_analysis(sid, stock_info_df=None):
    try:

        tech = get_tech_only(sid)
        if tech is None:
            return None

        df          = tech['df']
        p_close     = tech['p_close']
        p_open      = tech['p_open']
        ma5         = tech['ma5']
        ma10        = tech['ma10']
        ma20        = tech['ma20']
        vol_today   = tech['vol_today']
        v_ma20      = tech['v_ma20']
        price_up    = tech['price_up']
        vol_strong  = tech['vol_strong']
        trend_ok    = tech['trend_ok']
        momentum_ok = tech['momentum_ok']
        ma20_5d_ago   = tech['ma20_5d_ago']
        ma5_yesterday = tech['ma5_yesterday']

        # 中文名稱
        stock_name = ""
        try:
            if stock_info_df is not None:
                match = stock_info_df[stock_info_df['stock_id'] == sid]
            else:
                dl_info = DataLoader()
                dl_info.login_by_token(api_token=FINMIND_TOKEN)
                info = dl_info.taiwan_stock_info()
                match = info[info['stock_id'] == sid]
            stock_name = match.iloc[0]['stock_name'] if not match.empty else ""
        except:
            stock_name = ""

        # FinMind 籌碼
        dl = DataLoader()
        dl.login_by_token(api_token=FINMIND_TOKEN)
        inst = dl.taiwan_stock_institutional_investors(
            stock_id=sid,
            start_date=(datetime.now() - timedelta(days=12)).strftime('%Y-%m-%d')
        )

        consecutive_buy = False
        total_inst_3d = trust_3d = foreign_3d = dealer_3d = 0

        if not inst.empty:
            daily = inst.groupby('date').apply(
                lambda x: x[x['name'].isin(['Foreign_Investor', 'Investment_Trust'])]['buy'].sum()
                        - x[x['name'].isin(['Foreign_Investor', 'Investment_Trust'])]['sell'].sum()
            )
            total_inst_3d = daily.tail(3).sum() / 1000
            if len(daily) >= 3 and (daily.tail(3) > 0).all():
                consecutive_buy = True

            trust_daily = inst[inst['name'] == 'Investment_Trust'].groupby('date').apply(
                lambda x: x['buy'].sum() - x['sell'].sum()
            )
            trust_3d = trust_daily.tail(3).sum() / 1000

            foreign_daily = inst[inst['name'] == 'Foreign_Investor'].groupby('date').apply(
                lambda x: x['buy'].sum() - x['sell'].sum()
            )
            foreign_3d = foreign_daily.tail(3).sum() / 1000

            dealer_daily = inst[inst['name'] == 'Dealer_self'].groupby('date').apply(
                lambda x: x['buy'].sum() - x['sell'].sum()
            )
            dealer_3d = dealer_daily.tail(3).sum() / 1000 if not dealer_daily.empty else 0

        volume_ok  = vol_strong and price_up
        foreign_ok = foreign_3d > 0
        trust_ok   = trust_3d > 0
        dealer_ok  = dealer_3d > 0
        tech_pass  = trend_ok and momentum_ok
        score      = sum([trend_ok, momentum_ok, volume_ok, foreign_ok, trust_ok, dealer_ok])

        return {
            "df": df, "score": score, "tech_pass": tech_pass,
            "p_close": p_close, "p_open": p_open,
            "ma5": ma5, "ma10": ma10, "ma20": ma20,
            "ma20_5d_ago": ma20_5d_ago, "ma5_yesterday": ma5_yesterday,
            "vol_today": vol_today, "v_ma20": v_ma20,
            "price_up": price_up, "vol_strong": vol_strong,
            "consecutive": consecutive_buy, "total_inst_3d": total_inst_3d,
            "trust_3d": trust_3d, "foreign_3d": foreign_3d, "dealer_3d": dealer_3d,
            "trend_ok": trend_ok, "momentum_ok": momentum_ok, "volume_ok": volume_ok,
            "foreign_ok": foreign_ok, "trust_ok": trust_ok, "dealer_ok": dealer_ok,
            "bias": ((p_close - ma20) / ma20) * 100,
            "stock_name": stock_name
        }
    except:
        return None

# =====================================================================
# 函式 3：全市場掃描（當日成交量前50）—— 含除錯輸出
# =====================================================================
# 台股常態高成交量股票清單（涵蓋上市上櫃主要熱門股約100支）
SCAN_LIST = [
    # 電子大型股
    "2330","2317","2454","2382","2308","2303","2357","2379","2395",
    "2376","2377","2408","2409","2412","2474","2492","2498","3008",
    "3045","3481","3711","3034","3037","2344","2356","2360","2404",
    "2441","3231","3293","6415","6669","8069","8046","2049","2367",
    "2327","2353","2376","2379","3673","6176","6244","6446","6770",
    # 金融股
    "2881","2882","2886","2891","2892","2884","2885","2887","2883",
    "2880","2890","5880","2823","2838","5876","2834","2836",
    # 傳產/航運
    "2002","2006","1301","1303","1326","1216","1101","1102","2207",
    "2201","2105","2603","2609","2610","2615","2618","2637","2641",
    # 中小型熱門股
    "3293","4904","4938","6505","9910","9921","2006","1513","2059",
    "3714","6153","6278","6285","6449","6533","3037","6271","5274",
]
# 過濾確保都是4位數字代號
SCAN_LIST = [s for s in SCAN_LIST if s.isdigit() and len(s) == 4]
# 去除重複
SCAN_LIST = list(dict.fromkeys(SCAN_LIST))


def run_market_scan():
    results = []
    progress = st.progress(0, text="正在抓取昨日成交量排行...")

    # 初始化 FinMind（只登入一次，後面重複使用）
    stock_info_df = None
    try:
        dl = DataLoader()
        dl.login_by_token(api_token=FINMIND_TOKEN)
        stock_info_df = dl.taiwan_stock_info()
    except Exception as e:
        st.warning(f"FinMind 登入失敗：{e}")
        progress.empty()
        return []

    top50 = SCAN_LIST
    st.info(f"📊 掃描 {len(top50)} 支主要熱門股")

    # 第一階段：yfinance 技術面快篩
    tech_pass_list = []
    for i, sid in enumerate(top50):
        progress.progress((i + 1) / len(top50), text=f"技術面掃描中... {sid} ({i+1}/{len(top50)})")
        tech = get_tech_only(sid)
        if tech and tech['tech_pass']:
            tech_pass_list.append(sid)

    st.info(f"✅ **除錯⑤** 技術面過關：{len(tech_pass_list)} 支 → {tech_pass_list}")

    # 第二階段：技術面過關才呼叫 FinMind 籌碼
    for i, sid in enumerate(tech_pass_list):
        progress.progress(
            (i + 1) / max(len(tech_pass_list), 1),
            text=f"籌碼面分析中... {sid} ({i+1}/{len(tech_pass_list)})"
        )
        full = get_stock_analysis(sid, stock_info_df=stock_info_df)
        if full and full['score'] >= 4:
            results.append({"stock_id": sid, **full})

    progress.empty()
    results.sort(key=lambda x: x['score'], reverse=True)
    return results

# =====================================================================
# 側邊欄
# =====================================================================
with st.sidebar:
    st.title("⚙️ 診斷設定")
    st.text_input("輸入台股代號 (上市/上櫃)", key="stock_id")
    if st.button("查詢個股"):
        st.session_state.show_scan = False
        st.rerun()

    st.divider()
    st.title("🎯 選股神器 2.0")
    st.caption("掃描台股主要熱門股，篩出 4/6 以上強勢股")

    if st.button("🚀 開始 AI 掃描"):
        st.session_state.show_scan = True
        with st.spinner("掃描中，請稍候..."):
            st.session_state.scan_results = run_market_scan()
        st.rerun()

    st.divider()
    st.write("📋 **篩選邏輯說明**")
    logic_df = pd.DataFrame({
        "項目": ["1.技術趨勢", "2.技術動能", "3.量能表現", "4.外資", "5.投信", "6.自營商"],
        "標準": ["價格>20MA 且月線向上", "5MA>10MA>20MA 且斜率向上", "量>20均量1.5倍 且收紅", "近3日買超", "近3日買超", "近3日買超"]
    })
    st.write(logic_df.to_html(index=False, justify='center'), unsafe_allow_html=True)

# =====================================================================
# 主畫面
# =====================================================================

# --- 模式 A：顯示掃描結果 ---
if st.session_state.show_scan and st.session_state.scan_results is not None:
    results = st.session_state.scan_results

    st.header("🔍 AI 全市場掃描結果")
    st.caption(f"台股主要熱門股中，符合 4/6 以上條件的股票（共 {len(results)} 檔）")

    if not results:
        st.info("本次掃描無符合條件的股票，市場可能偏弱或資料尚未更新。")
    else:
        for idx, r in enumerate(results):
            score = r['score']
            sid   = r['stock_id']
            name  = r['stock_name']
            badge = f"🔥 {score}/6" if score >= 5 else f"👀 {score}/6"

            with st.expander(f"{badge}　{sid} {name}　｜　現價 {r['p_close']:.2f}　｜　乖離 {r['bias']:.1f}%"):
                c1, c2, c3 = st.columns(3)
                c1.metric("技術趨勢", "✅ 多方" if r['trend_ok'] else "❌ 空方")
                c2.metric("技術動能", "✅ 強勁" if r['momentum_ok'] else "❌ 疲弱")
                c3.metric("成交量能", "✅ 爆量收紅" if r['volume_ok'] else ("⚠️ 爆量收黑" if r['vol_strong'] else "❌ 量能不足"))

                c4, c5, c6 = st.columns(3)
                c4.metric("外資(3日)", f"{'✅' if r['foreign_ok'] else '❌'} {r['foreign_3d']:.0f} 張")
                c5.metric("投信(3日)", f"{'✅' if r['trust_ok'] else '❌'} {r['trust_3d']:.0f} 張")
                c6.metric("自營商(3日)", f"{'✅' if r['dealer_ok'] else '❌'} {r['dealer_3d']:.0f} 張")

                if st.button(f"查看 {sid} {name} 完整診斷", key=f"goto_{idx}_{sid}"):
                    st.session_state.stock_id = sid
                    st.session_state.show_scan = False
                    st.rerun()

# --- 模式 B：顯示個股完整診斷 ---
else:
    data = get_stock_analysis(st.session_state.stock_id)

    if data:
        market_suffix = "上市" if yf.download(f"{st.session_state.stock_id}.TWO", period="1d", progress=False).empty else "上櫃"
        st.header(f"📈 {st.session_state.stock_id} {data['stock_name']} 深度診斷 ({market_suffix}) | 最新價格：{data['p_close']:.2f}")

        st.subheader("📍 趨勢指標與風險")
        t1, t2, t3, t4 = st.columns(4)
        t1.metric("短線趨勢 (5MA>10MA)", "🔴 多方" if data['ma5'] > data['ma10'] else "🟢 空方")
        t2.metric("長線趨勢 (價格>20MA)", "🔴 多方" if data['p_close'] > data['ma20'] else "🟢 空方")
        t3.metric("月線乖離率", f"{data['bias']:.1f}%")
        t4.metric("乖離狀態", "過熱" if data['bias'] > 10 else "安全", delta_color="inverse")

        st.subheader("📊 量能監控")
        b1, b2 = st.columns(2)
        b1.metric("今日成交張數", f"{data['vol_today']:.0f} 張")
        b2.metric("量能狀態", "爆量攻擊" if data['vol_strong'] else "正常",
                  delta=f"{data['vol_today']/data['v_ma20']:.1f}x 20日均量")

        st.divider()
        st.subheader("🤖 AI 投資客綜合診斷")

        if data['trend_ok']:
            trend_text, trend_status = "✅ 站上月線且月線向上", "強勢多方"
        elif data['p_close'] > data['ma20']:
            trend_text, trend_status = "⚠️ 站上月線但月線向下", "弱勢反彈"
        else:
            trend_text, trend_status = "❌ 月線之下", "空方"

        if data['momentum_ok']:
            momentum_text, momentum_status = "✅ 三線多頭且動能向上", "強勁"
        elif data['ma5'] > data['ma10']:
            momentum_text, momentum_status = "⚠️ 5MA>10MA但排列不完整", "普通"
        else:
            momentum_text, momentum_status = "❌ 均線空頭排列", "疲弱"

        if data['volume_ok']:
            volume_text, volume_status = "✅ 量增價漲（突破均量1.5倍）", "熱絡"
        elif data['vol_strong'] and not data['price_up']:
            volume_text, volume_status = "⚠️ 帶量但收黑（注意出貨）", "警示"
        else:
            volume_text, volume_status = "❌ 量能不足", "常態"

        foreign_text  = f"{'✅' if data['foreign_ok'] else '❌'} {'買超' if data['foreign_ok'] else '賣超'} {abs(data['foreign_3d']):.0f} 張"
        trust_text    = f"{'✅' if data['trust_ok'] else '❌'} {'買超' if data['trust_ok'] else '賣超'} {abs(data['trust_3d']):.0f} 張"
        dealer_text   = f"{'✅' if data['dealer_ok'] else '❌'} {'買超' if data['dealer_ok'] else '賣超'} {abs(data['dealer_3d']):.0f} 張"

        if data['tech_pass'] and data['score'] >= 5:
            st.success(f"🔥 綜合評價：強力關注 (得分: {data['score']}/6)")
        elif data['tech_pass'] and data['score'] >= 4:
            st.warning(f"👀 綜合評價：技術面穩固，持續觀察 (得分: {data['score']}/6)")
        else:
            st.info(f"⚖️ 綜合評價：中性觀望 (得分: {data['score']}/6)")

        diag_rows = [
            ["1", "技術趨勢",    trend_text,    trend_status],
            ["2", "技術動能",    momentum_text, momentum_status],
            ["3", "成交量能",    volume_text,   volume_status],
            ["4", "外資(3日)",   foreign_text,  "買超" if data['foreign_ok'] else "賣超"],
            ["5", "投信(3日)",   trust_text,    "買超" if data['trust_ok'] else "賣超"],
            ["6", "自營商(3日)", dealer_text,   "買超" if data['dealer_ok'] else "賣超"],
        ]
        diag_df = pd.DataFrame(diag_rows, columns=["#", "項目", "診斷結果與標準定義", "狀態"])
        st.write(diag_df.to_html(index=False, justify='left'), unsafe_allow_html=True)

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
