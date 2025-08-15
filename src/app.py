
import pandas as pd
import numpy as np
import streamlit as st
import altair as alt
import streamlit.components.v1 as components
import json
import time
import math
from pathlib import Path
from typing import Iterable, Optional, Tuple, List, Dict

st.set_page_config(
    page_title = "강원 산불 시각화 프로젝트",
    page_icon = "🔥",
    layout = "wide",
)

def prep_casualty_stack_area(
    df: pd.DataFrame,
    ymd_col: str = "OCRN_YMD",
    death_col: str = "DCSD_CNT",
    inj_col: str = "INJPSN_CNT",
) -> Tuple[pd.DataFrame, List[Dict]]:
    """
    D3 면그래프(사망자·부상자)용 연도 집계 전처리.

    반환:
      - merged: year, deaths, injuries 컬럼을 가진 집계 DataFrame(int)
      - records: [{"year": int, "deaths": int, "injuries": int}, ...]
    """
    # 컬럼 존재 확인(대/소문자 혼재 방어)
    cols_map = {c.lower(): c for c in df.columns}
    for need in (ymd_col, death_col, inj_col):
        if need not in df.columns and need.lower() in cols_map:
            locals()[need.split("_")[0] + "_col"] = cols_map[need.lower()]
    for need in (ymd_col, death_col, inj_col):
        if need not in df.columns:
            raise KeyError(f"필수 컬럼이 없습니다: {need}")

    d = df.copy()

    # 연도 추출
    d["year"] = d[ymd_col].astype(str).str[:4]

    # 결측/비수치 방어
    d[death_col] = pd.to_numeric(d[death_col], errors="coerce").fillna(0)
    d[inj_col]   = pd.to_numeric(d[inj_col],   errors="coerce").fillna(0)

    # 총사상자 = 사망 + 부상
    d["casualties"] = d[death_col] + d[inj_col]
    d["deaths"]     = d[death_col]

    # 연도별 합계
    cas = d.groupby("year", as_index=False)["casualties"].sum()
    dea = d.groupby("year", as_index=False)["deaths"].sum()

    merged = cas.merge(dea, on="year", how="left")
    merged["injuries"] = (merged["casualties"] - merged["deaths"]).clip(lower=0).astype(int)

    # 정리: year, deaths, injuries만 사용
    merged = (
        merged[["year", "deaths", "injuries"]]
        .assign(year=lambda x: pd.to_numeric(x["year"], errors="coerce").astype("Int64"))
        .dropna(subset=["year"])
        .assign(year=lambda x: x["year"].astype(int),
                deaths=lambda x: x["deaths"].astype(int),
                injuries=lambda x: x["injuries"].astype(int))
        .sort_values("year")
        .reset_index(drop=True)
    )

    records = merged.to_dict(orient="records")
    return merged, records

@st.cache_data(show_spinner=False)
def prep_mobilization_records(
    df: pd.DataFrame,
    date_col: str = "OCRN_YMD",
    total_col: str = "WHOL_MNPW_CNT",
    line_cols: list = None,
) -> list:
    """
    연/월별 동원 인력(막대) + 지원지표(라인)용 레코드 반환.
    반환 형식: [{year:int, month:int, whol_mnpw_cnt:int, <line cols>...}, ...]
    """
    if line_cols is None:
        line_cols = [
            "MBLZ_POLICEO_CNT",    # 경찰 동원
            "MBLZ_SOLD_CNT",       # 군 병력 동원
            "MBLZ_GNRL_OCPT_NOPE", # 일반직 동원
            "ETC_MBLZ_NOPE",       # 기타 동원
            "MBLZ_FFPWR_CNT",      # 소방 인력 동원
        ]

    # 1) 컬럼 소문자 통일
    d = df.copy()
    d.columns = [c.lower() for c in d.columns]
    date_col = date_col.lower()
    total_col = total_col.lower()
    line_cols_l = [c.lower() for c in line_cols]

    # 2) 필수 컬럼 체크
    need = {date_col, total_col}
    if not need.issubset(d.columns):
        missing = need - set(d.columns)
        raise KeyError(f"필수 컬럼 누락: {missing}")

    # 3) 날짜 파싱 / 결측 제거
    d[date_col] = pd.to_datetime(d[date_col].astype(str), format="%Y%m%d", errors="coerce")
    d = d.dropna(subset=[date_col, total_col]).copy()

    # 4) 연/월 추출
    d["year"] = d[date_col].dt.year
    d["month"] = d[date_col].dt.month

    # 5) 사용 가능한 라인 컬럼만 선택 (없으면 생략)
    present_line_cols = [c for c in line_cols_l if c in d.columns]

    # 6) 월별 합계
    monthly_people = (
        d.groupby(["year", "month"], as_index=False)[total_col].sum()
         .sort_values(["year", "month"])
    )

    if present_line_cols:
        monthly_line = (
            d.groupby(["year", "month"], as_index=False)[present_line_cols].sum()
             .sort_values(["year", "month"])
        )
        merged = pd.merge(monthly_people, monthly_line, on=["year","month"], how="left")
    else:
        merged = monthly_people.copy()

    # 7) (모든 연 × 1~12월) 보정 → 빈달 0 채우기
    years = sorted(merged["year"].unique().tolist())
    full_idx = pd.MultiIndex.from_product([years, range(1,13)], names=["year","month"])
    merged = (
        merged.set_index(["year","month"])
              .reindex(full_idx)
              .fillna(0)
              .reset_index()
    )

    # 8) D3가 기대하는 키로 정리 (없는 라인 컬럼은 0으로 생성)
    for c in [c for c in line_cols_l if c not in merged.columns]:
        merged[c] = 0

    merged = merged.rename(columns={total_col: "whol_mnpw_cnt"})
    # 정렬
    merged = merged.sort_values(["year","month"]).reset_index(drop=True)

    # 레코드 반환
    out_cols = ["year","month","whol_mnpw_cnt"] + [c for c in line_cols_l]
    return merged[out_cols].to_dict(orient="records")

def prep_region_year_counts(
    df: pd.DataFrame,
    year_col_candidates: Iterable[str] = ("year", "YEAR", "Year", "연도"),
    region_col: str = "GRNDS_SGG_NM",
    year_range: Optional[Tuple[int, int]] = None,   # 예: (2016, 2022)
    drop_na_region: bool = True,
):
    """
    지역×연도 건수 집계 → D3 가로 막대용 데이터 준비.

    Parameters
    ----------
    df : pd.DataFrame
        원본 데이터프레임
    year_col_candidates : iterable[str]
        연도 컬럼 후보명들(대소문자/언어 혼재 대비)
    region_col : str
        지역(시군구) 컬럼명
    year_range : (min_year, max_year) | None
        연도 필터링 구간(포함)
    drop_na_region : bool
        지역 결측/공백 제거 여부

    Returns
    -------
    counts_df : pd.DataFrame
        columns = ['year', 'region', 'count']
    data_json : str
        __DATA_JSON__ 치환용 JSON 문자열
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame")

    # 1) 컬럼명 정리(공백 제거)
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]

    # 2) year 컬럼 탐색(후보 우선)
    year_col = None
    # 후보 우선
    for c in year_col_candidates:
        if c in df.columns:
            year_col = c
            break
    # 후보에 없으면 'year'와 케이스 무시 비교
    if year_col is None:
        for c in df.columns:
            if c.lower() == "year":
                year_col = c
                break

    if year_col is None or region_col not in df.columns:
        raise ValueError(f"필수 컬럼이 없습니다: year({year_col_candidates}) 또는 {region_col}")

    # 3) 연도 숫자화(+결측 제거)
    df[year_col] = pd.to_numeric(df[year_col], errors="coerce")
    df = df.dropna(subset=[year_col])
    df[year_col] = df[year_col].astype(int)

    # 4) 지역 공백/결측 처리
    if drop_na_region:
        df[region_col] = df[region_col].astype(str).str.strip()
        df = df[df[region_col].ne("") & df[region_col].ne("nan")]

    # 5) 연도 필터
    if year_range is not None:
        ymin, ymax = year_range
        df = df[(df[year_col] >= ymin) & (df[year_col] <= ymax)]

    # 6) 집계
    counts = (
        df.groupby([year_col, region_col], observed=True)
          .size()
          .reset_index(name="count")
          .rename(columns={year_col: "year", region_col: "region"})
    )

    # 7) JSON 변환(D3 템플릿용)
    data_json = json.dumps(counts.to_dict(orient="records"), ensure_ascii=False)

    return counts, data_json

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

    st.markdown("""
        2016년부터 2022년까지 전국 화재 발생 건수의 추이를 살펴보면, 연도별 변동 폭이 크다는 특징이 있습니다.  

        2017년에는 692건으로 전년도 대비 크게 증가했으며, 이후 2018년에 496건으로 감소했다가 2019년(653건)과 2020년(620건)에는 다시 높은 수준을 유지했습니다.  

        2021년에는 349건으로 큰 폭의 감소가 나타났지만, 2022년에는 756건으로 급격히 증가하며 조사 기간 중 가장 많은 화재 건수를 기록했습니다.
    """)

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
    st.markdown("""
        **강원도 동부와 경상북도 동해안 지역**은 산불 발생 건수와 평균 피해 면적 모두에서 높은 수치를 보여 전형적인 **고위험 지역**임을 알 수 있다.  
        이 지역들은 건조한 계절풍, 산악 지형, 조밀한 산림 분포 등 **기상·지리적 요인**이 복합적으로 작용해 산불이 자주 발생하고, 한 번 발생하면 대규모 피해로 이어질 가능성이 높다.  

        반면 **수도권과 대도시권**은 발생 건수와 피해 면적 모두 낮은 편으로, 산불 발생 시에도 **신속한 대응**이 가능하다는 점을 시사한다.  

        흥미로운 점은 **전라남도 일부 해안 및 도서 지역**으로, 발생 건수는 적지만 한 번 발생하면 피해 면적이 매우 큰 **저빈도·대규모 피해형 산불** 양상을 보인다.  
        이는 소방 인프라의 접근성, 해양성 기후 조건, 바람 방향 등의 영향으로 추정된다.  

        이러한 분석을 바탕으로  
        - **강원·경북 동해안권**: 예방과 초기 진화 체계 강화 필요  
        - **저빈도 대규모 피해 지역**: 비상 대응 역량 확충 필요  
        - **상대적으로 안전한 지역**: 기후 변화에 대비한 지속적인 산림 관리와 예방 교육 필요
    """)

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
        """
        최근 몇 년간 강원도는 전국에서 가장 심각한 산불 피해를 겪고 있는 지역으로, 특히 동해안과 접한 동부 지역은 건조한 봄철 계절풍, 급경사의 산악 지형, 조밀한 산림 분포가 복합적으로 작용해 산불 발생 위험이 매우 높은 것으로 나타났습니다.  

        대형 산불이 발생하면 강한 바람과 넓은 연소 확산 경로로 인해 피해 규모가 빠르게 확대되며, 2022년 강릉·삼척 산불과 같은 초대형 화재 사례는 전국적으로 주목을 받았습니다.  

        이러한 특성은 기후 변화로 인한 건조일수 증가와 맞물려 향후 산불 발생 빈도와 피해 규모가 더 커질 가능성을 시사하며, 예방과 초기 진화 역량 강화가 시급한 상황입니다.
        """
    )

    st.subheader("📊 화재 건수")

    st.markdown('📍 **연도별 비교**')
    st.markdown(
        """
        2017년(127건)과 2021년(120건)에 비교적 많은 화재가 발생했으며, 특히 2018년(72건)과 2020년(78건)에는 전년 대비 뚜렷한 감소세가 나타났습니다.  

        이러한 변동은 기상 조건, 산림 관리 정책, 그리고 대형 산불 발생 여부와 같은 일시적·환경적 요인의 영향을 크게 받는 것으로 보입니다.  

        최근 감소세와 증가세가 반복되는 패턴은 장기적 안정세보다는 연간 위험 요인에 따라 급변할 수 있음을 시사합니다.
        """
    )

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

    
    st.markdown('📍 **월별(계절별) 비교**')
    st.markdown(
        """
        월별 화재 발생 추이를 보면, **봄철(3~5월)**에 발생 건수가 압도적으로 높습니다. 특히 4월은 158건으로 연중 최고치를 기록하며, 전체 화재의 상당 부분을 차지합니다. 이는 건조한 날씨와 강한 바람, 그리고 산림 활동 증가가 복합적으로 작용한 결과로 보입니다.  

        반면 여름철(6 ~ 8월)과 가을철(9 ~ 11월)에는 발생 건수가 현저히 낮으며, 특히 9월은 3건으로 최저치를 나타냅니다. 겨울철(12~2월)에는 상대적으로 발생이 늘어나지만, 봄철에 비하면 절대 건수는 낮습니다.  

        이러한 계절별 패턴은 **봄철 산불 예방과 초기 진화 역량 강화**가 화재 피해 최소화를 위한 핵심 전략임을 시사합니다.
        """
    )

    months_df = prep_month_season_chart(df_gangwon)

    # D3 템플릿 로드 & 데이터 치환
    TPL_PATH = Path("../components/강원_월별_발생수.html")   # 아래 HTML 템플릿 파일명
    html_src  = TPL_PATH.read_text(encoding="utf-8")
    data_json = json.dumps(months_df.to_dict(orient="records"), ensure_ascii=False)

    html_filled = html_src.replace("__DATA_JSON__", data_json)

    # 렌더
    components.html(html_filled, height=400, scrolling=False)

    st.markdown('📍 **시간대별 비교**')
    st.markdown(
        """
        오전 11시부터 오후 3시 사이에는 화재 발생이 집중적으로 나타나며, 특히 오전 11시와 12시에는 각각 75건 이상으로 정점을 기록한다. 이는 낮 시간대(11~15시)에 기온이 상승하고 야외 활동이 증가하는 동시에 건조한 환경이 조성되면서 복합적으로 작용한 결과로 보인다.

        한편, 심야·새벽 시간대에도 주목할 만한 특징이 있다. 새벽 2시에는 40건이 넘는 화재가 발생했으며, 이는 주로 취침 중 부주의, 난방기구 사용, 전기적 요인 등과 관련이 있는 것으로 추정된다.

        화재의 주요 원인을 살펴보면, 담뱃불·라이터불은 낮 11시~15시 사이에 급격히 증가하며, 이는 야외 흡연 및 산림 인근 활동 증가와 밀접하게 연관된다. 불꽃·불티와 작동기기(전기·기계) 역시 낮 시간대 발생 비중이 높게 나타난다. 반면 폭발물·폭죽은 전체 건수는 적지만 특정 활동 시간대(오전·오후)에 집중되는 경향을 보인다.

        이러한 분석은 정책적 시사점을 제공한다. 낮 시간대, 특히 11시~15시 구간에 대한 집중 감시와 순찰이 필요하며, 봄철과 맞물릴 경우 대형 산불로 확산될 가능성이 높아 경고 방송과 계도 활동을 강화해야 한다. 또한 새벽 2시 화재 발생 패턴을 고려해 주거·숙박시설의 전기·난방기기 안전 점검을 철저히 하는 것이 중요하다.
        """
    )

    data_hourly, data_cause = prep_hourly_cause(df_gangwon, top_n=5)

    HTML_PATH = Path("../components/강원_시간별_화재요인별_발생수.html")  # 경로 확인/조정
    html_src = HTML_PATH.read_text(encoding="utf-8")

    html_filled = (
        html_src
        .replace("__DATA_HOURLY__", json.dumps(data_hourly, ensure_ascii=False))
        .replace("__DATA_CAUSE__",  json.dumps(data_cause,  ensure_ascii=False))
    )

    components.html(html_filled, height=450, scrolling=False)
    
    st.markdown('📍 **지역별 비교**')
    st.markdown(
        """
        현재 동향을 반영한 이 차트를 보면, 최근 강원도 내 화재 건수는 **홍천군(87건)**과 **춘천시(80건)**가 가장 높은 발생 빈도를 보이고 있습니다. 특히 이 두 지역은 도내 다른 시·군에 비해 20건 이상 높은 수치를 기록하며, 화재 취약 지역으로 분류될 가능성이 큽니다.

        그 뒤를 이어 원주시(60건), 강릉시(59건), 횡성군(49건), 철원군(46건) 등이 상대적으로 높은 발생 건수를 기록하고 있어, 동부·중부 내륙뿐 아니라 해안 지역까지 화재 위험이 고르게 분포하고 있음을 보여줍니다.

        반면, 동해시(8건), 속초시(7건), 태백시(5건)는 비교적 낮은 건수를 보이지만, 이는 절대적인 안전성을 의미하지 않으며 계절·기상 조건 변화 시 급격한 증가 가능성을 배제할 수 없습니다.

        종합적으로, 홍천군과 춘천시를 중심으로 한 북부·중부 내륙 지역의 화재 예방 및 감시 강화, 강릉·원주 등 도심 및 관광지 주변의 안전 관리가 향후 주요 대응 전략으로 필요합니다.
        """
    )

    counts_df, data_json = prep_region_year_counts(
        df_gangwon,
        year_col_candidates=("year", "YEAR"),
        region_col="GRNDS_SGG_NM",
        year_range=None,  # 예: (2016, 2022) 로 제한하고 싶으면 지정
    )

    HTML_PATH = Path("../components/강원_지역별_발생수.html")
    html_src = HTML_PATH.read_text(encoding="utf-8")
    html_filled = html_src.replace("__DATA_JSON__", data_json)

    components.html(html_filled, height=560, scrolling=False)

    st.subheader("📊 역할별 인력수")
    st.markdown(
        """
        2016년부터 2022년까지의 **월별 동원 인력과 지원 지표**를 분석한 결과, 모든 연도에서 **3월과 4월**에 인력 동원이 집중되었습니다.  
        이는 봄철 건조한 기상 조건, 강풍, 산림 인근 활동 증가 등 복합적인 요인으로 인해 대규모 산불 위험이 높아지는 시기와 일치합니다.  

        특히 **2022년**의 경우 3월에 동원 인력이 **약 2만 명**에 달하며, 이는 분석 기간 중 가장 높은 수치입니다.  
        군 병력 동원이 가장 큰 비중을 차지했으며, 일반직·소방 인력도 대규모로 투입되었습니다. 4월에도 여전히 높은 수준의 인력 투입이 이어졌지만, 이후에는 급격히 감소했습니다.  
        이러한 패턴은 대규모 산불이 발생한 특정 사건(예: 울진·삼척 산불)과 밀접하게 관련이 있는 것으로 보입니다.  

        계절별로 보면,  
        - **봄철(3~4월)**: 인력·장비 투입이 절대적으로 많음  
        - **겨울철(1~2월, 12월)**: 봄에 비해 낮지만, 2월에는 일부 해에서 상대적으로 높은 인력 투입 발생  
        - **여름철(6~8월)**: 장마와 높은 습도로 화재 위험이 낮아 인력 투입 최소  
        - **가을철(9~11월)**: 전반적으로 낮은 수준이나, 일부 해에는 11월에 소규모 증가  

        지원 지표 역시 인력 투입과 비슷한 흐름을 보였으며, **특히 2022년 3월 군 병력 투입량이 압도적으로 많아** 해당 시기의 대형 산불 대응을 뒷받침합니다.  

        **정책적 시사점**  
        - 봄철(특히 3월) 집중 대응 체계 강화 및 군·경·소방의 통합 작전 계획 사전 수립  
        - 대규모 산불 발생 가능성이 높은 이상 기후 해에는 사전 예측을 통한 선제 대응 필요  
        - 겨울철(2월) 화재 증가 패턴을 고려한 난방·전기 안전 점검 강화  
        """
    )
    records = prep_mobilization_records(df_gangwon)
    # HTML 템플릿 로드 & 데이터 주입
    TPL = Path("../components/강원_역할별_인력수.html")
    html_src = TPL.read_text(encoding="utf-8")
    html_filled = html_src.replace("__DATA_JSON__", json.dumps(records, ensure_ascii=False))

left, center, right = st.columns([1, 12, 1]) 

with center:
    components.html(html_filled, height = 1550, scrolling=False)


left, center, right = st.columns([1, 2, 1]) 

with center:
    st.subheader("📊 인명 피해 현황")
    st.markdown(
        """
        2016년부터 2022년까지의 **인명 피해 추이**를 살펴보면, 2018년에 **부상자**가 약 *17명*으로 **최고치**를 기록하며 전체 기간 중 가장 큰 피해가 발생했습니다. 이 시기는 **대규모 사고가 집중된 시기**로 추정됩니다.  

        **사망자**의 경우 2017년과 2019년에 상대적으로 증가했는데, 특히 2019년에는 부상자 수가 2018년보다 줄었음에도 사망자 수가 늘어나 **중소규모지만 치명적인 사고**가 발생했을 가능성을 시사합니다.  

        2020년 이후로는 **부상자와 사망자 모두 꾸준히 감소**하는 모습을 보이며, 이는 **안전 관리 강화**, **정책 개선**, 그리고 **팬데믹으로 인한 사회적 활동 감소** 등이 영향을 준 것으로 해석할 수 있습니다.  

        전체적으로는 **2016년부터 2018년까지 증가**하다 이후 감소하는 **피크형 추세**를 보이며, 향후 안정세를 유지하려면 **고위험 시기에 대한 대응 전략**이 필요합니다.
        """
    )
    
    merged, records = prep_casualty_stack_area(df_gangwon)

    html_src = Path("../components/강원_상태별_사상자수.html").read_text(encoding="utf-8")
    html_filled = html_src.replace("__DATA_JSON__", json.dumps(records, ensure_ascii=False))

    components.html(html_filled, height=440, scrolling=False)
    


# 페이지 Road
time.sleep(1)  # 렌더링 안정성 위해 약간의 지연
if overlay is not None:
    overlay.empty()
    st.session_state["boot_done"] = True