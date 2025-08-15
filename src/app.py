
import pandas as pd
import numpy as np
import streamlit as st
import altair as alt
import streamlit.components.v1 as components
import json
from pathlib import Path
import time

st.set_page_config(
    page_title = "강원 산불 시각화 프로젝트",
    page_icon = "🔥",
    layout = "wide",
)

def show_loading_overlay(text: str = "✨ 페이지를 준비 중입니다... 잠시만요 ✨"):
    """화면 전체를 덮는 로딩 오버레이를 띄우고, 제거용 placeholder를 반환."""
    ph = st.empty()
    ph.markdown(
        f"""
        <div id="__global_loader">
          <div class="loader-card">
            <div class="spinner"></div>
            <div class="msg">{text}</div>
          </div>
        </div>
        <style>
          /* 화면 전체 덮기 */
          #__global_loader {{
            position: fixed;
            inset: 0;
            background: rgba(15, 17, 22, 0.85); /* 어두운 반투명 */
            backdrop-filter: blur(2px);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 999999; /* 최상단 */
          }}
          .loader-card {{
            display:flex; flex-direction:column; align-items:center; gap:14px;
            background: #111827; border: 1px solid #1f2937; color:#fff;
            padding: 22px 26px; border-radius: 14px; box-shadow: 0 10px 30px rgba(0,0,0,0.35);
          }}
          .spinner {{
            width: 48px; height: 48px; border-radius: 50%;
            border: 4px solid #2a3342; border-top-color: #60a5fa;
            animation: spin .9s linear infinite;
          }}
          .msg {{ font-size: 15px; color:#e5e7eb; }}
          @keyframes spin {{ to {{ transform: rotate(360deg) }} }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    return ph

# ----------------------------------------------------------
# 1) 오버레이: 첫 로딩 때만 보여주고 이후 인터랙션엔 숨김
# ----------------------------------------------------------
if "boot_done" not in st.session_state:
    st.session_state["boot_done"] = False

overlay = None
if not st.session_state["boot_done"]:
    overlay = show_loading_overlay()

df_whole = pd.read_csv('../data/전국_산불현황_정렬_2016_2024.csv')
df_gangwon = pd.read_csv('../data/강원도_2016-2022.csv')

@st.cache_data(show_spinner=False)
def load_html(p: Path) -> str:
    return p.read_text(encoding="utf-8")

def prep_hourly_cause(
    df: pd.DataFrame,
    hour_col: str = "FIRE_OCRN_HR",
    cause_col: str = "IGTN_HTSRC_LCLSF_NM",
    top_n: int = 5,
):
    """
    시간대별 총 건수(막대) + 원인별 시간대 건수(라인)용 데이터 전처리.
    반환값:
      data_hourly: [{hour:0..23, count:int}, ...]
      data_cause : [{cause:str, hour:int(0..23), count:int}, ...]
    """

    if hour_col not in df.columns or cause_col not in df.columns:
        raise KeyError(f"입력 DataFrame에 필요한 컬럼이 없습니다: {hour_col}, {cause_col}")

    d = df.copy()

    # 1) 시간(0~23) 추출 (예: '0930', '9', '09', '09:30' 등 → 앞 1~2자리)
    d['hour'] = d['FIRE_OCRN_HR'].astype(str).str.zfill(6).str[:2]
    d['hour'] = pd.to_numeric(d['hour'], errors='coerce')
    d.dropna(subset=['hour'], inplace=True)
    d['hour'] = d['hour'].astype(int)

    # 2) 원인 정리 (결측/공백 → '미상')
    cause_raw = d[cause_col].fillna("미상").astype(str).str.strip()
    d["cause"] = cause_raw.replace({"": "미상"})

    # 3) 상위 N개 원인만 라인으로, 나머지는 '기타'
    if top_n is not None and top_n > 0:
        top_causes = d["cause"].value_counts().nlargest(top_n).index
        d["cause_top"] = np.where(d["cause"].isin(top_causes), d["cause"], "기타")
    else:
        # top_n=None 이면 전체 사용
        d["cause_top"] = d["cause"]

    # 4) 시간대 총 발생 건수(바)
    hourly = (
        d.groupby("hour", as_index=False)
         .size()
         .rename(columns={"size": "count"})
         .set_index("hour")
         .reindex(range(24), fill_value=0)  # 0~23 모두 포함
         .reset_index()
    )
    data_hourly = hourly.to_dict(orient="records")

    # 5) 원인별-시간대 발생건수(선) + 빠진 조합 0 채우기
    cause_hour = (
        d.groupby(["cause_top", "hour"], as_index=False)
         .size()
         .rename(columns={"cause_top": "cause", "size": "count"})
    )
    all_causes = sorted(cause_hour["cause"].unique().tolist())
    full_index = pd.MultiIndex.from_product([all_causes, range(24)], names=["cause", "hour"])
    cause_hour = (
        cause_hour.set_index(["cause", "hour"])
                  .reindex(full_index, fill_value=0)
                  .reset_index()
    )
    data_cause = cause_hour.to_dict(orient="records")

    return data_hourly, data_cause

def prep_month_season_chart(df: pd.DataFrame):
    # --- 연/월 추출 (OCRN_YMD: YYYYMMDD) ---
    df = df.copy()
    df["year"]  = pd.to_numeric(df["OCRN_YMD"].astype(str).str[:4],  errors="coerce")
    df["month"] = pd.to_numeric(df["OCRN_YMD"].astype(str).str[4:6], errors="coerce")
    df = df.dropna(subset=["year","month"])
    df["year"]  = df["year"].astype(int)
    df["month"] = df["month"].astype(int)

    # (선택) 연도 필터 UI
    min_y, max_y = int(df["year"].min()), int(df["year"].max())

    y1, y2 = st.slider("📅 연도 범위 선택", min_value=min_y, max_value=max_y, value=(min_y, max_y), step=1)
    df = df[(df["year"] >= y1) & (df["year"] <= y2)].copy()

    # 월(1~12) 카운트 → 빈월 0 채움
    month_counts = (df["month"].value_counts()
                        .reindex(range(1,13), fill_value=0)
                        .sort_index())

    # D3용 DataFrame (month, count)
    months_df = pd.DataFrame({
        "month": list(range(1,13)),     # 1~12
        "count": month_counts.values
    })
    return months_df

left, center, right = st.columns([1, 2, 1]) 

with center:
    st.markdown("""
    <style>
    body {
    background-color: #f9f9f9;
    font-family: 'Noto Sans KR', sans-serif;
    }
    h1 { color: #d9534f; }
    .description {
    font-size: 1.1rem;
    color: #555;
    margin-bottom: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

    st.title("🔥 강원 산불 시각화 프로젝트")
    st.markdown(
        "<div class='description'>"
        "이 프로젝트는 2023년 강원도에서 발생한 산불 데이터를 시각화하여, 산불의 발생 원인과 영향을 분석하는 것을 목표로 합니다. "
        "데이터는 강원도청과 산림청에서 제공한 자료를 기반으로 하며, "
        "산불 발생 지역, 원인, 피해 규모 등을 포함하고 있습니다. "
        "시각화를 통해 산불의 발생 패턴과 지역별 영향을 분석하고, "
        "향후 산불 예방 및 대응 방안을 모색하는 데 기여하고자 합니다."
        "</div>", unsafe_allow_html=True
    )


    # 전국 산불
    st.header("⛰️ 전국 산불 현황")

    st.subheader("📊 연도별 화재 발생 건수")

    st.markdown(
        '전국 화재 현황에 대한 내용'
    )

    # 연도별 건수 계산 (2016~2022년만)
    year_counts = df_whole['startyear'].value_counts().sort_index()
    year_counts_filtered = year_counts.loc[(year_counts.index >= 2016) & (year_counts.index <= 2022)]

    # DataFrame 형식으로 변환
    chart_data = year_counts_filtered.reset_index()
    chart_data.columns = ['year', 'count']

    
    data_json = json.dumps(chart_data.to_dict(orient='records'), ensure_ascii=False)
    HTML_PATH = Path('../components/yearly_active_bars.html')
    html_src = HTML_PATH.read_text(encoding="utf-8")
    html_filled = html_src.replace("__DATA_JSON__", data_json)

    components.html(html_filled, height=450, scrolling=False)

    st.subheader("📊 지역별 화재 발생 비교")

    st.markdown(
        '대충 지역별 화재 발생 현황에 대한 내용'
    )

    # ✨ 탭을 양쪽 끝까지 꽉 채우기 (두 탭 동일 너비)
    st.markdown("""
    <style>
    .stTabs [role="tablist"] { 
    display: flex; 
    justify-content: stretch; 
    gap: 0 !important; 
    }
    .stTabs [role="tab"] {
    flex: 1 1 0;              /* 동일 너비 배분 */
    text-align: center; 
    margin: 0 !important; 
    }

    /* 예전/대체 셀렉터(호환용) */
    div[data-baseweb="tab-list"] { gap: 0 !important; }
    div[data-baseweb="tab"]      { flex: 1 1 0 !important; justify-content: center; }

    /* 보기 좋은 폰트/패딩 */
    .stTabs [role="tab"] p { 
    font-size: 1.05rem; 
    padding: 8px 0; 
    margin: 0; 
    }
    </style>
    """, unsafe_allow_html=True)

    file_count = Path("../components/시도별_발생수_지도.html")
    file_area  = Path("../components/시도별_평균_피해면적_지도.html")

    tab1, tab2 = st.tabs(["🔥 발생 수 기준", "🔥 피해 면적 기준"])
    with tab1:
        if file_count.exists():
            components.html(load_html(file_count), height=800, scrolling=False)
        else:
            st.error(f"파일을 찾을 수 없습니다: {file_count.resolve()}")

    with tab2:
        if file_area.exists():
            components.html(load_html(file_area), height=800, scrolling=False)
        else:
            st.error(f"파일을 찾을 수 없습니다: {file_area.resolve()}")
    
    # 강원 산불
    st.header("🥔 강원 산불 현황")
    st.markdown(
        '강원도 산불 머릿말'
    )

    st.subheader("📊 화재 건수")

    st.markdown(
        ' 연도별 화재 건수에 대한 인사이트'
    )
    
    st.markdown('**📍 연도별 비교**')

    # 연도별 건수 계산 (2016~2022) ---
    year_series = pd.to_numeric(df_gangwon['OCRN_YMD'].astype(str).str[:4], errors='coerce').dropna().astype(int)
    year_counts = year_series.value_counts().sort_index()
    chart_data = year_counts.reset_index()
    chart_data.columns = ['year', 'count']

    data_json = json.dumps(chart_data.to_dict(orient='records'), ensure_ascii=False)
    HTML_PATH = Path('../components/yearly_active_bars.html')
    html_src = HTML_PATH.read_text(encoding="utf-8")
    html_filled = html_src.replace("__DATA_JSON__", data_json)

    components.html(html_filled, height=450, scrolling=False)

    st.markdown(
        ' 월별 화재 건수에 대한 인사이트'
    )

    st.markdown('📍 월별(계절별) 비교')

    months_df = prep_month_season_chart(df_gangwon)

    # D3 템플릿 로드 & 데이터 치환
    TPL_PATH = Path("../components/강원_월별_발생수.html")   # 아래 HTML 템플릿 파일명
    html_src  = TPL_PATH.read_text(encoding="utf-8")
    data_json = json.dumps(months_df.to_dict(orient="records"), ensure_ascii=False)

    html_filled = html_src.replace("__DATA_JSON__", data_json)

    # 렌더
    components.html(html_filled, height=400, scrolling=False)

    st.markdown(
        ' 시간대별 화재 원인 및 화재 요인에 대한 인사이트'
    )

    st.markdown(
        '📍 시간대별 비교'
    )

    data_hourly, data_cause = prep_hourly_cause(df_gangwon, top_n=5)

    HTML_PATH = Path("../components/강원_시간별_화재요인별_발생수.html")  # 경로 확인/조정
    html_src = HTML_PATH.read_text(encoding="utf-8")

    html_filled = (
        html_src
        .replace("__DATA_HOURLY__", json.dumps(data_hourly, ensure_ascii=False))
        .replace("__DATA_CAUSE__",  json.dumps(data_cause,  ensure_ascii=False))
    )

    components.html(html_filled, height=500, scrolling=False)

    st.markdown(
        '📍 지역별 비교'
    )
    time.sleep(1)  # 렌더링 안정성 위해 약간의 지연
    if overlay is not None:
        overlay.empty()
        st.session_state["boot_done"] = True