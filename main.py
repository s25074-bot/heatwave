import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium
import requests

# -----------------------------------------------------------------------------
# 1. 페이지 설정
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="전국 폭염일수 대시보드",
    page_icon="☀️",
    layout="wide"
)

st.title("☀️ 전국 폭염일수 지도 및 통계 대시보드")
st.markdown("연도별 폭염일수 현황 및 관련 통계 데이터를 지도와 표로 확인하세요.")

# -----------------------------------------------------------------------------
# 2. 기상청 관측지점 -> 시군구 행정구역명 매핑 딕셔너리
#    (GeoJSON 파일의 '시군구' 속성과 일치하도록 매핑)
# -----------------------------------------------------------------------------
STATION_TO_SIGUNGU = {
    # 주요 도시 및 지역
    "서울": "서울특별시",
    "강릉": "강릉시",
    "춘천": "춘천시",
    "원주": "원주시",
    "속초": "속초시",
    "동해": "동해시",
    "태백": "태백시",
    "대관령": "평창군",
    "추풍령": "영동군",
    "대전": "대전광역시",
    "청주": "청주시",
    "충주": "충주시",
    "제천": "제천시",
    "홍성": "홍성군",
    "전주": "전주시",
    "군산": "군산시",
    "익산": "익산시",
    "목포": "목포시",
    "여수": "여수시",
    "순천": "순천시",
    "광주": "광주광역시",
    "대구": "대구광역시",
    "포항": "포항시",
    "경주": "경주시",
    "안동": "안동시",
    "구미": "구미시",
    "창원": "창원시",
    "진주": "진주시",
    "통영": "통영시",
    "부산": "부산광역시",
    "울산": "울산광역시",
    "제주": "제주시",
    "서귀포": "서귀포시",
    "수원": "수원시",
    "인천": "인천광역시",
    "양평": "양평군",
    "이천": "이천시",
    " 강화": "강화군",
}

# -----------------------------------------------------------------------------
# 3. 데이터 로드 및 파싱 함수
# -----------------------------------------------------------------------------
@st.cache_data
def load_heatwave_data(file_path="heatwave.csv"):
    """
    하나의 CSV 파일 안에 여러 섹션으로 나눠진 데이터를 파싱하는 함수입니다.
    인코딩 실패 시 utf-8 -> cp949 순으로 재시도합니다.
    """
    lines = []
    # 1) 인코딩 처리 (utf-8 실패 시 cp949 시도)
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="cp949") as f:
            lines = f.readlines()

    # 섹션별 라인 번호 찾기
    sec1_idx, sec2_idx, sec3_idx = None, None, None

    for i, line in enumerate(lines):
        if "가장 긴 폭염" in line:
            sec1_idx = i
        elif "가장 빠른/가장 늦은 폭염" in line:
            sec2_idx = i
        elif "전국 폭염일수" in line:
            sec3_idx = i

    # 파일 수동 분할 로드 (io.StringIO 활용)
    from io import StringIO

    # 섹션 1: 가장 긴 폭염
    sec1_lines = lines[sec1_idx + 1:sec2_idx] if sec1_idx is not None and sec2_idx is not None else []
    df_longest = pd.read_csv(StringIO("".join(sec1_lines))) if sec1_lines else pd.DataFrame()

    # 섹션 2: 가장 빠른/가장 늦은 폭염
    sec2_lines = lines[sec2_idx + 1:sec3_idx] if sec2_idx is not None and sec3_idx is not None else []
    df_extreme_dates = pd.read_csv(StringIO("".join(sec2_lines))) if sec2_lines else pd.DataFrame()

    # 섹션 3: 전국 폭염일수 원자료
    sec3_lines = lines[sec3_idx + 1:] if sec3_idx is not None else []
    df_raw = pd.read_csv(StringIO("".join(sec3_lines))) if sec3_lines else pd.DataFrame()

    # 열 이름 공백 제거 (데이터 정제)
    for df in [df_longest, df_extreme_dates, df_raw]:
        if not df.empty:
            df.columns = df.columns.str.strip()

    return df_longest, df_extreme_dates, df_raw

@st.cache_data
def load_geojson():
    """시군구 GeoJSON 경계 데이터 로드"""
    url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"
    res = requests.get(url)
    return res.json()

# 데이터 불러오기
try:
    df_longest, df_extreme_dates, df_raw = load_heatwave_data("heatwave.csv")
    geojson_data = load_geojson()
except Exception as e:
    st.error(f"데이터를 로드하는 중 오류가 발생했습니다: {e}")
    st.stop()

# -----------------------------------------------------------------------------
# 4. 사이드바 - 연도 선택 슬라이더
# -----------------------------------------------------------------------------
st.sidebar.header("⚙️ 검색 옵션")

# 원자료에서 연도 컬럼 추출 ('년도' 또는 '연도' 컬럼 자동 대응)
year_col = '년도' if '년도' in df_raw.columns else ('연도' if '연도' in df_raw.columns else df_raw.columns[0])

# 연도 범위 계산 및 슬라이더 생성
available_years = sorted(df_raw[year_col].unique())
selected_year = st.sidebar.slider(
    "조회할 연도를 선택하세요",
    min_value=int(min(available_years)),
    max_value=int(max(available_years)),
    value=int(max(available_years)), # 기본값: 최신 연도
    step=1
)

# 선택한 연도의 데이터 필터링
df_year = df_raw[df_raw[year_col] == selected_year]

# 지점별 폭염일수 집계
station_col = '지점' if '지점' in df_raw.columns else df_raw.columns[2]
df_counts = df_year.groupby(station_col).size().reset_index(name='폭염일수')

# 관측지점 명칭 -> 행정구역(시군구) 명칭 변환
df_counts['시군구'] = df_counts[station_col].map(STATION_TO_SIGUNGU).fillna(df_counts[station_col])

# -----------------------------------------------------------------------------
# 5. 상단 지표 카드 (Metrics)
# -----------------------------------------------------------------------------
avg_days = round(df_counts['폭염일수'].mean(), 1) if not df_counts.empty else 0
total_stations = len(df_counts)

if not df_counts.empty:
    max_row = df_counts.loc[df_counts['폭염일수'].idxmax()]
    max_station_info = f"{max_row[station_col]} ({max_row['폭염일수']}일)"
else:
    max_station_info = "-"

col1, col2, col3 = st.columns(3)
col1.metric(label=f"📊 {selected_year}년 전국 평균 폭염일수", value=f"{avg_days} 일")
col2.metric(label=f"🔥 {selected_year}년 최다 폭염 관측지", value=max_station_info)
col3.metric(label="📍 총 관측 지점 수", value=f"{total_stations} 곳")

st.markdown("---")

# -----------------------------------------------------------------------------
# 6. 지도 시각화 (Folium 단계구분도)
# -----------------------------------------------------------------------------
st.subheader(f"🗺️ {selected_year}년 전국 시군구별 폭염일수 지도")

# 지도 초기 위치 (대한민국 중심)
m = folium.Map(location=[36.5, 127.5], zoom_start=7, tiles="CartoDB positron")

# 단계구분도(Choropleth) 추가
folium.Choropleth(
    geo_data=geojson_data,
    data=df_counts,
    columns=['시군구', '폭염일수'],
    key_on='feature.properties.시군구',
    fill_color='YlOrRd', # 노랑-주황-빨강 색상 계열
    fill_opacity=0.7,
    line_opacity=0.3,
    legend_name=f'{selected_year}년 폭염일수 (일)',
    nan_fill_color='white'
).add_to(m)

# Folium 지도 앱에 출력
st_folium(m, width="100%", height=500)

st.markdown("---")

# -----------------------------------------------------------------------------
# 7. 상위/하위 10곳 표 구성
# -----------------------------------------------------------------------------
st.subheader(f"🏆 {selected_year}년 폭염일수 순위")

col_top, col_bottom = st.columns(2)

with col_top:
    st.markdown("##### 🔴 폭염일수 상위 10곳")
    df_top10 = df_counts.sort_values(by='폭염일수', ascending=False).head(10).reset_index(drop=True)
    st.dataframe(df_top10[[station_col, '시군구', '폭염일수']], use_container_width=True)

with col_bottom:
    st.markdown("##### 🔵 폭염일수 하위 10곳")
    df_bottom10 = df_counts.sort_values(by='폭염일수', ascending=True).head(10).reset_index(drop=True)
    st.dataframe(df_bottom10[[station_col, '시군구', '폭염일수']], use_container_width=True)

st.markdown("---")

# -----------------------------------------------------------------------------
# 8. 역대 관련 통계 표 (섹션 1, 섹션 2 데이터)
# -----------------------------------------------------------------------------
st.subheader("📚 폭염 주요 기록 통계")

col_sec1, col_sec2 = st.columns(2)

with col_sec1:
    st.markdown("##### ⏳ 가장 긴 폭염 기록")
    if not df_longest.empty:
        st.dataframe(df_longest, use_container_width=True, hide_index=True)
    else:
        st.info("데이터가 없습니다.")

with col_sec2:
    st.markdown("##### 🗓️ 가장 빠른 / 가장 늦은 폭염 관측일")
    if not df_extreme_dates.empty:
        st.dataframe(df_extreme_dates, use_container_width=True, hide_index=True)
    else:
        st.info("데이터가 없습니다.")
