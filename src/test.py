import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import altair as alt

# 페이지 기본 설정
st.set_page_config(
    page_title="강원도 산불 피해면적 시각화",
    page_icon="🔥",
    layout="wide"
)

# 스타일 커스터마이징
st.markdown("""
    <style>
    body {
        background-color: #f9f9f9;
        font-family: 'Noto Sans KR', sans-serif;
    }
    h1 {
        color: #d9534f;
    }
    .description {
        font-size: 1.1rem;
        color: #555;
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

# 제목과 설명
st.title("🔥 강원도 산불 피해면적 시각화")
st.markdown(
    "<div class='description'>"
    "이 페이지에서는 시도별 평균 피해 면적 지도와 월별 화재 발생 빈도(계절 구분 포함)를 함께 확인할 수 있습니다."
    "</div>",
    unsafe_allow_html=True
)
st.markdown("---")

# 사이드바 정보
st.sidebar.header("📊 페이지 정보")
st.sidebar.write("""
- **데이터 출처:** 강원특별자치도 산불 현황  
- **분석 항목:** 시도별 평균 피해 면적 + 월별/계절별 화재 발생 빈도  
- **시각화 방식:** 지도 + 막대그래프  
""")

# 1️⃣ HTML 지도 시각화 로드
st.subheader("📍 시도별 평균 피해 면적 지도")
html_file = Path("/Users/sharks2/Desktop/SNU FinTech/Visualization Web Development/Gangwon Wildfire Data Visualization/src/시도별_평균_피해면적_지도.html")

if html_file.exists():
    with open(html_file, "r", encoding="utf-8") as f:
        html_content = f.read()
    components.html(html_content, height=800, scrolling=True)
else:
    st.error(f"❌ HTML 파일을 찾을 수 없습니다.\n{html_file}")

import altair as alt

st.subheader("📅 월별/계절별 화재 발생 빈도")

data_file = Path("../data/전국_산불현황_정렬_2016_2024.csv")

if data_file.exists():
    df = pd.read_csv(data_file)

    # (선택) 연도 필터: startyear가 있을 때만
    if "startyear" in df.columns:
        min_y, max_y = int(df["startyear"].min()), int(df["startyear"].max())
        y1, y2 = st.slider("연도 범위 선택", min_value=min_y, max_value=max_y, value=(min_y, max_y), step=1)
        df = df[(df["startyear"] >= y1) & (df["startyear"] <= y2)]

    # 월 컬럼 보정: 1~12 → 0~11
    sm = df["startmonth"]
    if sm.min() == 1 and sm.max() == 12:
        sm = sm - 1

    # 0~11 모두 포함해 카운트(빈월 0 채움)
    month_counts = sm.value_counts().reindex(range(12), fill_value=0).sort_index()
    months_df = pd.DataFrame({
        "month0": list(range(12)),           # 내부 인덱스(0~11)
        "month": [m + 1 for m in range(12)], # 라벨용(1~12)
        "count": month_counts.values
    })

    # y축 상한 (계절 배경 rect 높이 맞춤)
    y_max = max(1, int(months_df["count"].max() * 1.2))

    # --- 막대(히스토그램 로직 유지) ---
    bars = (
        alt.Chart(months_df)
        .mark_bar(color="orange", stroke="black", strokeWidth=1, width=20)
        .encode(
            x=alt.X(
                "month0:Q",
                # 전체 0~11월이 다 보이도록 도메인 수정
                scale=alt.Scale(domain=[-0.6, 11.6]),
                axis=alt.Axis(title="월", values=list(range(12)), labelExpr="datum.value + 1"),
            ),
            y=alt.Y("count:Q", title="건수", scale=alt.Scale(domain=[0, y_max])),
            tooltip=[alt.Tooltip("month:Q", title="월"), alt.Tooltip("count:Q", title="건수")],
        )
    )

    # --- 계절 배경 & 경계선 (국내 기준으로 정확히 반영) ---
    seasons_df = pd.DataFrame([
        # 겨울(12, 1, 2) → 2구간으로 분리
        {"name": "겨울", "x0": -0.5, "x1":  1.5, "color": "#C1E1FF"},  # 1~2월
        {"name": "겨울", "x0": 10.5, "x1": 11.5, "color": "#C1E1FF"},  # 12월
        # 봄(3,4,5)
        {"name": "봄",   "x0":  1.5, "x1":  4.5, "color": "#FFDDC1"},
        # 여름(6,7,8)
        {"name": "여름", "x0":  4.5, "x1":  7.5, "color": "#C1FFD7"},
        # 가을(9,10,11)
        {"name": "가을", "x0":  7.5, "x1": 10.5, "color": "#FFD6A5"},
    ])
    seasons_df["y0"] = 0
    seasons_df["y1"] = y_max

    rects = (
        alt.Chart(seasons_df)
        .mark_rect(opacity=0.3)
        .encode(
            x=alt.X("x0:Q"), x2="x1:Q",
            y="y0:Q", y2="y1:Q",
            color=alt.Color(
                "name:N",
                title="계절",
                scale=alt.Scale(
                    domain=["봄", "여름", "가을", "겨울"],
                    range=["#b3de69", "#fb8072", "#fdb462", "#80b1d3"],
                ),
                legend=alt.Legend(orient="top", direction="horizontal"),
            ),
        )
    )

    # 계절 경계선: (겨울↔봄) 1.5, (봄↔여름) 4.5, (여름↔가을) 7.5, (가을↔겨울) 10.5
    rules_df = pd.DataFrame({"x": [1.5, 4.5, 7.5, 10.5]})
    rules = alt.Chart(rules_df).mark_rule(color="red", strokeDash=[6, 4], strokeWidth=1).encode(x="x:Q")

    chart = (
        alt.layer(rects, rules, bars)
        .encode(
            x=alt.X("month0:Q", scale=alt.Scale(domain=[4.6, 8.6])),
            y=alt.Y("count:Q", scale=alt.Scale(domain=[0, y_max]))
        )
        .properties(
            title="월별 화재 발생 건수 (계절 구분 포함)"
        )
        .configure_title(anchor="start")
        .interactive()
    )


    st.altair_chart(chart, use_container_width=True)

else:
    st.error(f"❌ 데이터 파일을 찾을 수 없습니다.\n{data_file}")