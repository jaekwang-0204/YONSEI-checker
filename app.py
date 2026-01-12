import streamlit as st
import pdfplumber
import re
import pandas as pd
import json
import os

st.set_page_config(page_title="졸업요건 진단기 (Pro)", page_icon="🎓")

st.title("🎓 연세대 졸업요건 진단 (맞춤형)")
st.markdown("""
**[시스템 안내]**
학번과 학과를 자동으로 인식하여, **연도별 졸업 요건 DB**에 맞춰 진단합니다.
* 현재 지원: 2022학번 임상병리학과 (데이터베이스 확장 중)
""")

st.divider()

# --- 1. 졸업요건 DB 로딩 함수 ---
@st.cache_data
def load_requirements():
    # GitHub에 올린 requirements.json 파일을 읽습니다.
    # 로컬 테스트 시 같은 폴더에 파일이 있어야 합니다.
    try:
        with open('requirements.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None

# DB 로드
requirements_db = load_requirements()

if requirements_db is None:
    st.error("⚠️ 'requirements.json' 파일을 찾을 수 없습니다. GitHub에 파일을 올려주세요.")
    st.stop()

# --- 2. 탭 구성 ---
tab1, tab2 = st.tabs(["📂 성적표 업로드 (PDF)", "📝 텍스트 붙여넣기"])

full_text = ""

with tab1:
    uploaded_file = st.file_uploader("성적증명서 PDF를 업로드하세요", type="pdf")
    if uploaded_file:
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text: full_text += text + "\n"

with tab2:
    manual_text = st.text_area("PDF 내용을 복사해서 붙여넣으세요", height=200)
    if manual_text:
        full_text = manual_text

# --- 3. 분석 및 판정 로직 ---
if full_text:
    st.divider()
    
    # (1) 기본 정보 추출
    # 학번 추출 (2022xxxxx) -> 입학연도 파악
    id_match = re.search(r'학\s*번[:\s]*(\d{4})', full_text)
    student_year = id_match.group(1) if id_match else "2022" # 기본값
    
    # 학과 추출
    dept_match = re.search(r'소\s*속[:\s]*([가-힣\s]+대학)?\s*([가-힣]+과)', full_text)
    department = dept_match.group(2) if dept_match else "임상병리학과" # 기본값

    st.subheader(f"👤 분석 대상: {student_year}학번 {department}")

    # (2) DB에서 해당 학번/학과 기준 가져오기
    if student_year in requirements_db and department in requirements_db[student_year]:
        criteria = requirements_db[student_year][department]
        st.success(f"✅ {student_year}년도 {department} 졸업요건 데이터를 불러왔습니다.")
    else:
        st.warning(f"⚠️ {student_year}년도 {department} 데이터를 DB에서 찾을 수 없어 '2022 임상병리학과' 기준을 적용합니다.")
        criteria = requirements_db["2022"]["임상병리학과"]

    # (3) 성적표 데이터 파싱 (정규표현식)
    # 총 취득학점
    total_match = re.search(r'(?:취득학점|학점계)[:\s]*(\d{2,3})', full_text)
    my_total = float(total_match.group(1)) if total_match else 0.0

    # 전공필수
    maj_req_match = re.search(r'전공필수[:\s]*(\d{1,3})', full_text)
    my_maj_req = float(maj_req_match.group(1)) if maj_req_match else 0.0

    # 전공선택
    maj_sel_match = re.search(r'전공선택[:\s]*(\d{1,3})', full_text)
    my_maj_sel = float(maj_sel_match.group(1)) if maj_sel_match else 0.0
    
    # 3~4천단위 (심화과목)
    upper_match = re.search(r'3~4천단위[:\s]*(\d{1,3})', full_text)
    my_upper = float(upper_match.group(1)) if upper_match else 0.0

    # 교양기초 (성적표에 명시되어 있다면 추출, 없다면 추정)
    # 보통 '교양기초' 라는 키워드 옆 숫자를 찾음
    gen_base_match = re.search(r'교양기초[:\s]*(\d{1,3})', full_text)
    my_gen_base = float(gen_base_match.group(1)) if gen_base_match else 0.0

    # (4) 비교 및 결과 표 생성
    results = []
    
    # 1. 총 학점
    res_total = "✅ 충족" if my_total >= criteria['total_credits'] else f"❌ 부족 ({int(criteria['total_credits'] - my_total)}점)"
    results.append(["총 취득학점", f"{int(criteria['total_credits'])}점", f"{int(my_total)}점", res_total])

    # 2. 전공 합계 (필수+선택)
    my_maj_total = my_maj_req + my_maj_sel
    res_maj_tot = "✅ 충족" if my_maj_total >= criteria['major_total'] else f"❌ 부족 ({int(criteria['major_total'] - my_maj_total)}점)"
    results.append(["전공 전체(필+선)", f"{criteria['major_total']}점", f"{int(my_maj_total)}점", res_maj_tot])

    # 3. 전공 필수
    res_maj_req = "✅ 충족" if my_maj_req >= criteria['major_required'] else f"❌ 부족 ({int(criteria['major_required'] - my_maj_req)}점)"
    results.append(["전공 필수", f"{criteria['major_required']}점", f"{int(my_maj_req)}점", res_maj_req])

    # 4. 심화 과목 (3000단위 이상)
    res_upper = "✅ 충족" if my_upper >= criteria['advanced_course'] else f"❌ 부족 ({int(criteria['advanced_course'] - my_upper)}점)"
    results.append(["3~4천단위 과목", f"{criteria['advanced_course']}점", f"{int(my_upper)}점", res_upper])
    
    # 결과 출력
    df = pd.DataFrame(results, columns=["구분", "졸업 기준", "내 점수", "판정"])
    st.table(df)

    # 최종 코멘트
    if my_total >= criteria['total_credits'] and my_maj_total >= criteria['major_total'] and my_maj_req >= criteria['major_required']:
        st.balloons()
        st.success("🎉 축하합니다! 주요 졸업 요건을 충족했습니다.")
    else:
        st.error("⚠️ 아직 부족한 요건이 있습니다. 위 표를 확인해주세요.")

    # 디버깅용
    with st.expander("개발자용: 원본 텍스트 보기"):
        st.text(full_text)
