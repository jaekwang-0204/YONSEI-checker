import streamlit as st
import pdfplumber
import re
import pandas as pd
import json

st.set_page_config(page_title="졸업요건 진단기 (Final)", page_icon="🎓")

# --- 1. 졸업요건 DB 로드 ---
@st.cache_data
def load_requirements():
    try:
        with open('requirements.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

db = load_requirements()

# --- 2. F학점 및 NP 제거 함수 (핵심) ---
def filter_failed_courses(full_text):
    """
    텍스트를 줄 단위로 쪼개서 성적이 F 또는 NP인 줄을 제거합니다.
    단, 단순 텍스트에 'F'글자가 들어간다고 지우면 안 되므로,
    성적표 패턴(학점+성적 구조)을 고려하거나 명확한 등급 표시를 찾습니다.
    """
    lines = full_text.split('\n')
    filtered_lines = []
    
    for line in lines:
        # F 학점 체크 (공백+F+공백 또는 줄 끝의 F)
        # 예: "3.0 F", " F " 패턴 등
        if re.search(r'\sF\s|\sF$|\sNP\s|\sNP$', line):
            continue # 이 줄은 건너뜀 (삭제)
        filtered_lines.append(line)
    
    return "\n".join(filtered_lines)

# --- 3. UI 구성 ---
st.title("🎓 연세대 졸업요건 진단")
st.markdown("입학년도와 전공을 선택하면, 해당 기준에 맞춰 **낙제(F) 과목을 제외하고** 진단합니다.")

# (1) 드롭다운: 학번 및 전공 선택
col1, col2 = st.columns(2)
with col1:
    # DB에 있는 연도만 선택 가능하게 하거나 기본 목록 제공
    available_years = sorted(list(db.keys())) if db else ["2022", "2023", "2024"]
    selected_year = st.selectbox("입학년도", available_years)

with col2:
    # 선택된 연도에 해당하는 학과만 로드
    if selected_year in db:
        dept_list = list(db[selected_year].keys())
        selected_dept = st.selectbox("전공", dept_list)
    else:
        # DB에 연도가 없으면 빈 리스트 -> 아래에서 처리
        selected_dept = st.selectbox("전공", ["지원되는 학과 없음"])

# (2) 수동 인증 체크
st.markdown("##### ✅ 필수 인증 (성적표에 안 나올 경우 체크)")
ck1, ck2 = st.columns(2)
is_eng = ck1.checkbox("외국어 인증 완료", value=False)
is_info = ck2.checkbox("정보/산학 인증 완료", value=False)

st.divider()

# --- 4. 데이터 입력 ---
tab1, tab2 = st.tabs(["📂 PDF 업로드", "📝 텍스트 붙여넣기"])
full_text = ""

with tab1:
    uploaded_file = st.file_uploader("성적증명서 PDF", type="pdf")
    if uploaded_file:
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text: full_text += text + "\n"

with tab2:
    manual_input = st.text_area("텍스트 붙여넣기", height=200)
    if manual_input: full_text = manual_input

# --- 5. 분석 로직 ---
if full_text:
    # (0) 지원 여부 확인
    if selected_year not in db or selected_dept not in db[selected_year]:
        st.error(f"🚫 죄송합니다. {selected_year}학번 {selected_dept}에 대한 졸업요건 데이터는 아직 지원되지 않습니다.")
        st.info("개발자에게 해당 학번/학과의 졸업요건 자료를 제공해주세요.")
        st.stop() # 여기서 코드 중단

    # 기준 로드
    criteria = db[selected_year][selected_dept]
    gen_rule = criteria.get("general_education", {})
    
    # (1) F학점 제거 전처리
    clean_text = filter_failed_courses(full_text)
    
    st.subheader(f"📊 분석 결과 ({selected_year} {selected_dept})")

    # (2) 학점 추출
    # 총점
    total_match = re.search(r'(?:취득학점|학점계)[:\s]*(\d{2,3})', clean_text)
    my_total = float(total_match.group(1)) if total_match else 0.0
    
    # 전공 (필수/선택)
    maj_req = float((re.search(r'전공필수[:\s]*(\d{1,3})', clean_text) or [0,0])[1])
    maj_sel = float((re.search(r'전공선택[:\s]*(\d{1,3})', clean_text) or [0,0])[1])
    my_maj_total = maj_req + maj_sel
    
    # 3000단위
    my_upper = float((re.search(r'3~4천단위[:\s]*(\d{1,3})', clean_text) or [0,0])[1])

    # (3) 교양 기초 상세 분석 (리더십, RC, 진로 등)
    req_courses_res = []
    for item in gen_rule.get("required_courses", []):
        # 해당 키워드가 텍스트에 몇 번 등장하는지 카운트 (간이 방식)
        # 더 정확히 하려면 과목 코드로 매칭해야 하나, 현재는 키워드로 진행
        found_count = 0
        for kw in item["keywords"]:
            found_count += clean_text.count(kw)
        
        # 진로/경력 등은 P/NP라 학점이 0일 수 있어 횟수로 체크하거나, 
        # 사용자가 수동 확인하도록 유도. 여기선 발견 여부로 체크
        status = "✅" if found_count >= 1 else "❌"
        req_courses_res.append([item['name'], f"{item['count']}과목 이상", f"{'이수함' if found_count > 0 else '미발견'}", status])

    # (4) 교양 영역 (8영역)
    my_req_areas = [a for a in gen_rule.get("required_areas", []) if a in clean_text]
    my_elec_areas = [a for a in gen_rule.get("elective_areas", []) if a in clean_text]
    
    req_area_pass = len(my_req_areas) == len(gen_rule["required_areas"])
    elec_area_pass = len(my_elec_areas) >= gen_rule["elective_min_count"]

    # --- 결과 출력 ---
    
    # 1. 학점 요약
    st.markdown("#### 1️⃣ 학점 이수 현황")
    df_credit = pd.DataFrame([
        ["총 취득학점", criteria['total_credits'], int(my_total), "✅" if my_total >= criteria['total_credits'] else "❌"],
        ["전공 합계", criteria['major_total'], int(my_maj_total), "✅" if my_maj_total >= criteria['major_total'] else "❌"],
        ["전공 필수", criteria['major_required'], int(maj_req), "✅" if maj_req >= criteria['major_required'] else "❌"],
        ["3000단위 이상", criteria['advanced_course'], int(my_upper), "✅" if my_upper >= criteria['advanced_course'] else "❌"]
    ], columns=["구분", "기준", "내 점수", "판정"])
    st.table(df_credit)

    # 2. 교양 기초 및 필수 과목
    st.markdown("#### 2️⃣ 교양 기초 / 필수 과목 (F학점 제외)")
    df_courses = pd.DataFrame(req_courses_res, columns=["과목(영역)", "기준", "내 현황", "판정"])
    st.table(df_courses)
    
    # 3. 교양 영역
    st.markdown("#### 3️⃣ 대학교양 영역 (8개 영역)")
    col_a, col_b = st.columns(2)
    with col_a:
        st.write(f"**필수 영역 ({len(my_req_areas)}/{len(gen_rule['required_areas'])})**")
        st.caption(f"이수: {', '.join(my_req_areas) if my_req_areas else '없음'}")
    with col_b:
        st.write(f"**선택 영역 ({len(my_elec_areas)}/{len(gen_rule['elective_areas'])})**")
        st.caption(f"이수: {', '.join(my_elec_areas) if my_elec_areas else '없음'}")
    
    if req_area_pass and elec_area_pass:
        st.success("✅ 교양 영역 조건을 모두 충족했습니다!")
    else:
        st.error("❌ 교양 영역 이수가 부족합니다. (필수 영역 누락 혹은 선택 영역 개수 부족)")

    # 4. 인증
    st.markdown("#### 4️⃣ 필수 인증")
    st.write(f"- 외국어 인증: {'✅ 완료' if is_eng else '❌ 미완료'}")
    st.write(f"- 정보/산학 인증: {'✅ 완료' if is_info else '❌ 미완료'}")
    
    # 디버깅
    with st.expander("개발자용: F학점 제거된 텍스트 보기"):
        st.text(clean_text)
