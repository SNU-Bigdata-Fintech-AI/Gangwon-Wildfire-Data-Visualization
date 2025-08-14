# app.py
import json
from pathlib import Path
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import altair as alt

st.set_page_config(
    page_title="강원도 산불 피해면적 시각화",
    page_icon="🔥",
    layout="wide"
)

# -------------------------
# 공통 스타일
# -------------------------
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

st.title("🔥 강원도 산불 피해면적 시각화")
st.markdown(
    "<div class='description'>"
    "시도별 평균 피해 면적 지도와 월별 화재 발생 빈도(계절 구분), "
    "그리고 연도별 동원 인력(막대) & 지원지표(라인, 애니메이션)를 확인할 수 있습니다."
    "</div>", unsafe_allow_html=True
)
st.markdown("---")

st.sidebar.header("📊 페이지 정보")
st.sidebar.write("""
- **데이터 출처:** 강원특별자치도 산불 현황  
- **분석 항목:** 시도별 평균 피해 면적 + 월별/계절별 화재 발생 빈도 + 연도별 동원 인력/지원지표  
- **시각화 방식:** 지도 + 막대그래프 + D3 라인 애니메이션  
""")


# =========================
# 유틸: 데이터 로딩/전처리
# =========================
def load_csv(path: Path, encoding="utf-8"):
    try:
        return pd.read_csv(path, encoding=encoding)
    except Exception as e:
        st.error(f"CSV 로드 오류: {e}")
        st.stop()

def prep_month_season_chart(df: pd.DataFrame):
    # (선택) 연도 필터
    if "startyear" in df.columns:
        min_y, max_y = int(df["startyear"].min()), int(df["startyear"].max())
        y1, y2 = st.slider("연도 범위 선택", min_value=min_y, max_value=max_y, value=(min_y, max_y), step=1)
        df = df[(df["startyear"] >= y1) & (df["startyear"] <= y2)]

    # 월 값 0~11로 정렬/카운트
    sm = df["startmonth"]
    if sm.min() == 1 and sm.max() == 12:
        sm = sm - 1

    month_counts = sm.value_counts().reindex(range(12), fill_value=0).sort_index()
    months_df = pd.DataFrame({
        "month0": list(range(12)),
        "month": [m + 1 for m in range(12)],
        "count": month_counts.values
    })
    return months_df

def render_month_season_chart(months_df: pd.DataFrame):
    y_max = max(1, int(months_df["count"].max() * 1.2))

    # 계절 영역
    seasons_df = pd.DataFrame([
        {"name": "겨울", "x0": -0.5, "x1":  1.5, "color": "#C1E1FF"},
        {"name": "겨울", "x0": 10.5, "x1": 11.5, "color": "#C1E1FF"},
        {"name": "봄",   "x0":  1.5, "x1":  4.5, "color": "#FFDDC1"},
        {"name": "여름", "x0":  4.5, "x1":  7.5, "color": "#C1FFD7"},
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
                "name:N", title="계절",
                scale=alt.Scale(
                    domain=["봄", "여름", "가을", "겨울"],
                    range=["#b3de69", "#fb8072", "#fdb462", "#80b1d3"],
                ),
                legend=alt.Legend(orient="top", direction="horizontal"),
            ),
        )
    )

    rules_df = pd.DataFrame({"x": [1.5, 4.5, 7.5, 10.5]})
    rules = alt.Chart(rules_df).mark_rule(color="red", strokeDash=[6, 4], strokeWidth=1).encode(x="x:Q")

    bars = (
        alt.Chart(months_df)
        .mark_bar(color="orange", stroke="black", strokeWidth=1, width=20)
        .encode(
            x=alt.X(
                "month0:Q",
                scale=alt.Scale(domain=[-0.6, 11.6]),
                axis=alt.Axis(title="월", values=list(range(12)), labelExpr="datum.value + 1"),
            ),
            y=alt.Y("count:Q", title="건수", scale=alt.Scale(domain=[0, y_max])),
            tooltip=[alt.Tooltip("month:Q", title="월"), alt.Tooltip("count:Q", title="건수")],
        )
    )

    chart = (
        alt.layer(rects, rules, bars)
        .properties(title="월별 화재 발생 건수 (계절 구분 포함)")
        .configure_title(anchor="start")
        .interactive()
    )
    return chart


# =========================
# 1) 시도별 평균 피해면적 HTML
# =========================
st.subheader("📍 시도별 평균 피해 면적 지도")
html_file = Path("/Users/sharks2/Desktop/SNU FinTech/Visualization Web Development/Gangwon Wildfire Data Visualization/src/시도별_평균_피해면적_지도.html")
if html_file.exists():
    components.html(html_file.read_text(encoding="utf-8"), height=800, scrolling=False)
else:
    st.error(f"❌ HTML 파일을 찾을 수 없습니다.\n{html_file}")

# =========================
# 2) 월별/계절별 빈도(Altair)
# =========================
st.subheader("📅 월별/계절별 화재 발생 빈도")
data_file = Path("../data/전국_산불현황_정렬_2016_2024.csv")
if data_file.exists():
    df_ms = load_csv(data_file)
    months_df = prep_month_season_chart(df_ms)
    chart = render_month_season_chart(months_df)
    st.altair_chart(chart, use_container_width=True)
else:
    st.error(f"❌ 데이터 파일을 찾을 수 없습니다.\n{data_file}")

# =========================
# 3) 연도별 동원 인력(막대) & 지원지표(라인, 애니메이션, 스크롤 트리거)
# =========================
st.subheader("📈 연도별 동원 인력(막대) & 지원지표(라인, 애니메이션) — 스크롤 트리거")

CSV_PATH = Path("../data/강원도_2016-2022.csv")
df = load_csv(CSV_PATH)
df.columns = [c.lower() for c in df.columns]
required = {"ocrn_ymd", "whol_mnpw_cnt"}
if not required.issubset(df.columns):
    st.error(f"필수 컬럼 누락: {required - set(df.columns)}")
    st.write("현재 컬럼:", list(df.columns))
    st.stop()

df["ocrn_ymd"] = pd.to_datetime(df["ocrn_ymd"], format="%Y%m%d", errors="coerce")
base_len = len(df)
df = df.dropna(subset=["ocrn_ymd", "whol_mnpw_cnt"]).copy()
if df.empty:
    st.warning(f"유효 데이터가 없습니다. (원본 {base_len}행)")
    st.stop()

df["year"] = df["ocrn_ymd"].dt.year
df["month"] = df["ocrn_ymd"].dt.month

line_cols = [
    "mblz_policeo_cnt",    # 경찰 동원
    "mblz_sold_cnt",       # 군 병력 동원
    "mblz_gnrl_ocpt_nope", # 일반직 동원
    "etc_mblz_nope",       # 기타 동원
    "mblz_ffpwr_cnt",      # 소방 인력 동원
]
use_cols = [c for c in line_cols if c in df.columns]

monthly_people = (
    df.groupby(["year","month"], as_index=False)["whol_mnpw_cnt"]
      .sum().sort_values(["year","month"])
)

if use_cols:
    monthly_mblz = (
        df.groupby(["year","month"], as_index=False)[use_cols]
          .sum().sort_values(["year","month"])
    )
    merged = pd.merge(monthly_people, monthly_mblz, on=["year","month"], how="left")
else:
    merged = monthly_people.copy()
    for c in line_cols:
        merged[c] = 0

records = merged[["year","month","whol_mnpw_cnt"] + line_cols].to_dict(orient="records")
data_json = json.dumps(records, ensure_ascii=False)

# --- D3 HTML (방향 조건 제거 + 전체 스크롤 기준, rAF 보강) ---
html = r"""
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<title>D3 - 스크롤 트리거</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Noto Sans KR", Arial, sans-serif; margin:0; padding:12px; }
  .grid { display:grid; grid-template-columns: repeat(2, minmax(320px, 1fr)); gap:16px; }
  .panel { background:#fff; border:1px solid #eee; border-radius:12px; padding:10px 12px 8px; box-shadow:0 2px 10px rgba(0,0,0,0.06); }
  .title { font-weight:600; margin:2px 0 8px 2px; font-size:14px; color:#333; display:flex; justify-content:space-between; align-items:center; gap:8px; }
  .title button { font-size:12px; padding:4px 8px; border:1px solid #ddd; background:#fafafa; border-radius:6px; cursor:pointer; }
  .title button:hover { background:#f0f0f0; }
  .axis path, .axis line { stroke:#ccc; }
  .bar { fill:#90caf9; }
  .legend text { font-size:12px; fill:#333; }
  .legend rect.bg { rx:6; ry:6; fill: rgba(255,255,255,0.9); stroke:#ddd; }
  .tooltip { position: fixed; pointer-events: none; background: rgba(0,0,0,0.78); color:#fff; padding:6px 8px; border-radius:6px; font-size:12px; line-height:1.4; z-index:9999; }
</style>
</head>
<body>
<div id="chart" class="grid"></div>
<div id="tooltip" class="tooltip" style="opacity:0;"></div>

<script>
const raw = __DATA_JSON__;

const labelMap = {
  whol_mnpw_cnt: "동원 인력(합계)",
  mblz_policeo_cnt: "경찰 동원",
  mblz_sold_cnt: "군 병력 동원",
  mblz_gnrl_ocpt_nope: "일반직 동원",
  etc_mblz_nope: "기타 동원",
  mblz_ffpwr_cnt: "소방 인력 동원",
};
const lineCols = Object.keys(labelMap).filter(k => k !== "whol_mnpw_cnt");

const groups = d3.group(raw, d => d.year);
const years = Array.from(groups.keys()).sort((a,b) => a-b);

const W=620, H=320, M={top:28, right:56, bottom:40, left:48};
const innerW = W - M.left - M.right;
const innerH = H - M.top - M.bottom;

const color = d3.scaleOrdinal().domain(lineCols).range(d3.schemeTableau10);
const tooltip = d3.select("#tooltip");
const container = d3.select("#chart");

// 패널 생성
years.forEach(year => {
  const data = groups.get(year).map(d => ({
    month: +d.month,
    whol_mnpw_cnt: +(d.whol_mnpw_cnt||0),
    mblz_policeo_cnt: +(d.mblz_policeo_cnt||0),
    mblz_sold_cnt: +(d.mblz_sold_cnt||0),
    mblz_gnrl_ocpt_nope: +(d.mblz_gnrl_ocpt_nope||0),
    etc_mblz_nope: +(d.etc_mblz_nope||0),
    mblz_ffpwr_cnt: +(d.mblz_ffpwr_cnt||0),
  }));

  const panel = container.append("div").attr("class","panel").attr("data-year", year);
  const header = panel.append("div").attr("class","title");
  header.append("span").text(`${year}년 월별 동원 인력(막대) & 지원지표(라인)`);
  header.append("button").attr("class","replay").text("Replay");

  const svg = panel.append("svg").attr("width", W).attr("height", H);
  const g = svg.append("g").attr("transform", `translate(${M.left}, ${M.top})`);

  const months = d3.range(1,13);
  const x = d3.scaleBand().domain(months).range([0, innerW]).padding(0.18);
  const y0 = d3.scaleLinear().domain([0, d3.max(data, d => d.whol_mnpw_cnt) || 1]).nice().range([innerH, 0]);
  const y1Max = d3.max(lineCols, c => d3.max(data, d => d[c]||0)) || 1;
  const y1 = d3.scaleLinear().domain([0, y1Max]).nice().range([innerH, 0]);

  // 축/그리드
  g.append("g").attr("class","axis grid")
    .call(d3.axisLeft(y0).ticks(5).tickSize(-innerW))
    .call(g => g.select(".domain").remove())
    .call(g => g.selectAll(".tick line").attr("stroke","#eee"));
  g.append("g").attr("transform", `translate(0, ${innerH})`)
    .call(d3.axisBottom(x).tickValues(months).tickFormat(d => String(d).padStart(2,"0")));
  g.append("g").call(d3.axisLeft(y0).ticks(5));
  g.append("g").attr("transform", `translate(${innerW},0)`).call(d3.axisRight(y1).ticks(5));

  // 레이어 그룹
  const barsG = g.append("g").attr("class","bars");
  const linesG = g.append("g").attr("class","lines");
  const dotsG  = g.append("g").attr("class","dots");

  // 범례(오른쪽 상단)
  const items = ["whol_mnpw_cnt", ...lineCols.filter(c => d3.sum(data, d => d[c]||0) > 0)];
  const legend = g.append("g").attr("class","legend");
  const itemH = 18, pad = 8;
  const temp = legend.append("g").attr("opacity", 0);
  let maxW = 0;
  items.forEach(k => {
    const t = temp.append("text").text(labelMap[k] || k).attr("font-size", 12);
    maxW = Math.max(maxW, t.node().getBBox().width);
  });
  temp.remove();
  const boxW = maxW + 48, boxH = pad*2 + itemH * items.length;
  const boxX = innerW - boxW, boxY = 0;
  legend.append("rect").attr("class","bg").attr("x", boxX).attr("y", boxY).attr("width", boxW).attr("height", boxH);
  items.forEach((k,i) => {
    const y = boxY + pad + i*itemH + 12;
    const swatch = (k === "whol_mnpw_cnt") ? "#90caf9" : color(k);
    legend.append("rect").attr("x", boxX + 10).attr("y", y-9).attr("width", 14).attr("height", 14).attr("fill", swatch);
    legend.append("text").attr("x", boxX + 30).attr("y", y).attr("dominant-baseline","middle").text(labelMap[k] || k);
  });

  function draw() {
    // bars
    barsG.selectAll("rect")
      .data(data)
      .join("rect")
        .attr("class","bar")
        .attr("x", d => x(d.month))
        .attr("width", x.bandwidth())
        .attr("y", innerH)
        .attr("height", 0)
      .on("mousemove", (event,d) => {
        tooltip.style("opacity", 1)
               .style("left", (event.clientX + 12) + "px")
               .style("top",  (event.clientY - 12) + "px")
               .html(`<b>${year}년 ${String(d.month).padStart(2,'0')}월</b><br/>동원 인력: <b>${d.whol_mnpw_cnt.toLocaleString()}</b>`);
      })
      .on("mouseleave", () => tooltip.style("opacity", 0))
      .transition()
        .duration(800).ease(d3.easeCubicOut)
        .attr("y", d => y0(d.whol_mnpw_cnt))
        .attr("height", d => innerH - y0(d.whol_mnpw_cnt));

    // lines
    lineCols.forEach((col,i) => {
      const sum = d3.sum(data, d => d[col] || 0);
      if (!sum) return;

      const path = linesG.append("path")
        .datum(data)
        .attr("fill","none")
        .attr("stroke", color(col))
        .attr("stroke-width", 2)
        .attr("d", d3.line()
              .x(d => x(d.month) + x.bandwidth()/2)
              .y(d => y1(d[col] || 0))
              .curve(d3.curveMonotoneX)
          );

      const L = path.node().getTotalLength();
      path.attr("stroke-dasharray", `${L} ${L}`)
          .attr("stroke-dashoffset", L)
          .transition()
            .delay(200 + i*250)
            .duration(1200)
            .ease(d3.easeCubic)
            .attr("stroke-dashoffset", 0);

      dotsG.selectAll(`circle.dot-${col}`)
        .data(data)
        .join("circle")
          .attr("class", `dot dot-${col}`)
          .attr("cx", d => x(d.month) + x.bandwidth()/2)
          .attr("cy", d => y1(d[col] || 0))
          .attr("r", 3)
          .attr("fill", color(col))
          .attr("opacity", 0)
          .on("mousemove", (event, d) => {
            tooltip.style("opacity", 1)
                   .style("left", (event.clientX + 12) + "px")
                   .style("top",  (event.clientY - 12) + "px")
                   .html(`<b>${year}년 ${String(d.month).padStart(2,'0')}월</b><br/>${labelMap[col]}: <b>${(d[col]||0).toLocaleString()}</b>`);
          })
          .on("mouseleave", () => tooltip.style("opacity", 0))
          .transition()
            .delay(200 + i*250 + 900)
            .duration(400)
            .attr("opacity", 1);
    });

    panel.node()._drawn = true;
  }

  function reset() {
    // 모든 요소 제거 (초기화)
    g.selectAll(".bars *").interrupt().remove();
    g.selectAll(".lines *").interrupt().remove();
    g.selectAll(".dots *").interrupt().remove();
    panel.node()._drawn = false;
  }

  header.select(".replay").on("click", () => { reset(); draw(); });

  // 핸들러 저장
  panel.node()._draw = draw;
  panel.node()._reset = reset;
});

// ===== IntersectionObserver: 전체 스크롤 기준(방향 무시) =====
const panels = document.querySelectorAll(".panel");
const io = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    const node = entry.target;
    const ratio = entry.intersectionRatio;

    // 1) 25% 이상 보이면 draw
    if (ratio >= 0.25 && !node._drawn) node._draw?.();

    // 2) 완전히 벗어나면 reset
    if (ratio === 0 && node._drawn) node._reset?.();
  });
}, {
  root: null,                 // 전체 페이지(iframe) 스크롤 기준
  rootMargin: "0px 0px 0px 0px",
  threshold: [0, 0.25]        // 진입/이탈 임계값 최소화
});
panels.forEach(p => io.observe(p));

// ===== 보강: 빠른 스크롤 시 완전 이탈 강제 reset (rAF 스로틀) =====
let rafId = null;
function onScrollCheck() {
  if (rafId) return;
  rafId = requestAnimationFrame(() => {
    const vh = window.innerHeight;
    panels.forEach(p => {
      const rect = p.getBoundingClientRect();
      const out = (rect.bottom <= 0) || (rect.top >= vh);
      if (out && p._drawn) p._reset?.();
    });
    rafId = null;
  });
}
window.addEventListener('scroll', onScrollCheck, { passive: true });
window.addEventListener('resize', onScrollCheck);
</script>
</body>
</html>
"""

# 데이터 삽입
html_filled = html.replace("__DATA_JSON__", data_json)

# 컴포넌트 렌더 (scrolling=False → 페이지 전체 스크롤 기준)
years_n = merged["year"].nunique()
rows = (years_n + 1) // 2
height = max(380 * rows, 420)
components.html(html_filled, height=height, scrolling=False)
st.caption(f"패널 수: {years_n}개 / 컴포넌트 높이: {height}px")