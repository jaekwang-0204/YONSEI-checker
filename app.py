import streamlit as st
import pdfplumber
import re
import pandas as pd
import json
import pytesseract
from PIL import Image
import os

# Tesseract 경로 설정 (로컬/서버 환경 분기)
# Streamlit Cloud 등 리눅스 환경에서는 보통 자동 인식되나, 필요시 설정
# pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

st.set_page_config(page_title="졸업요건 진단기 (Ultimate)", page_icon="🎓")

# --- 세션 상태 초기화 (수동 입력 데이터 유지용) ---
if 'manual_courses' not in st.session_state:
    st.session_state.manual_courses = []

# --- 1. 졸업요건 DB 로드 ---
@st.cache_data
def load_requirements():
    try:
        with open('requirements.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

db = load_requirements()

# --- 2. 헬퍼 함수들 ---
def filter_failed_courses(full_text):
    lines = full_text.split('\n')
    filtered_lines = []
    for line in lines:
        if re.search(r'\sF\s|\sF$|\sNP\s|\sNP$', line):
            continue 
        filtered_lines.append(line)
    return "\n".join(filtered_lines)

def ocr_image(image_file):
    try:
        image = Image.open(image_file)
        # 한글+영어 모드로 추출
        text = pytesseract.image_to_string(image, lang='kor+eng')
        return text
    except Exception as e:
        return f"Error: {e}"

# --- 3. 사이드바 (설정 & 수동 입력) ---
with st.sidebar:
    st.header("⚙️ 설정")
    
    # 연도/전공 선택
    if db:
        available_years = sorted([k for k in db.keys() if k != "area_courses"])
    else:
        available_years = ["2022", "2023"]
    selected_year = st.selectbox("입학년도", available_years)
    
    if selected_year in db:
        dept_list = list(db[selected_year].keys())
        selected_dept = st.selectbox("전공", dept_list)
    else:
        selected_dept = st.selectbox("전공", ["지원되는 학과 없음"])

    st.divider()

    # [기능 2] 수동 과목 추가 (핵심 기능)
    st.markdown("### ➕ 과목 수동 추가")
    st.caption("성적표에 없거나 누락된 과목을 직접 추가하세요.")
    
    with st.form("add_course_form", clear_on_submit=True):
        m_name = st.text_input("과목명 (예: 글쓰기)")
        m_credit = st.number_input("학점", min_value=0.0, max_value=10.0, step=0.5, value=3.0)
        m_type = st.selectbox("이수 구분", ["전공필수", "전공선택", "교양/기타"])
        m_add = st.form_submit_button("추가하기")
        
        if m_add and m_name:
            st.session_state.manual_courses.append({
                "name": m_name,
                "credit": m_credit,
                "type": m_type
            })
            st.success(f"'{m_name}' 추가됨!")

    # 추가된 과목 리스트 보여주기 & 삭제 기능
    if st.session_state.manual_courses:
        st.markdown("---")
        st.write("**추가된 과목 목록**")
        for i, course in enumerate(st.session_state.manual_courses):
            col_t, col_d = st.columns([4, 1])
            col_t.text(f"{course['name']} ({course['credit']}학점, {course['type']})")
            if col_d.button("❌", key=f"del_{i}"):
                del st.session_state.manual_courses[i]
                st.rerun()

    st.divider()
    
    # 버그 신고
    st.markdown("### 🐛 버그 신고")
    email_subject = f"[졸업진단기 버그신고] {selected_year}학번 {selected_dept}"
    mailto_link = f"mailto:jaekwang1164@gmail.com?subject={email_subject}"
    st.markdown(f'<a href="{mailto_link}" target="_blank">📧 개발자에게 메일 보내기</a>', unsafe_allow_html=True)


# --- 메인 화면 ---
st.title("🎓 연세대 졸업요건 정밀 진단")
st.markdown(f"**{selected_year}학번 {selected_dept}** 기준 분석 중")

# 수동 인증 체크
col1, col2 = st.columns(2)
is_eng = col1.checkbox("외국어 인증 완료", value=False)
is_info = col2.checkbox("정보/산학 인증 완료", value=False)

st.divider()

# --- 4. 데이터 입력 (탭 확장) ---
tab1, tab2, tab3 = st.tabs(["📂 PDF 업로드", "🖼️ 이미지/캡쳐 (OCR)", "📝 텍스트 붙여넣기"])
extracted_text = ""

with tab1:
    uploaded_pdf = st.file_uploader("성적증명서 PDF", type="pdf")
    if uploaded_pdf:
        with pdfplumber.open(uploaded_pdf) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text: extracted_text += text + "\n"

with tab2:
    st.info("에브리타임 시간표나 성적표 캡쳐화면을 업로드하세요. (인식에 시간이 걸릴 수 있습니다)")
    uploaded_img = st.file_uploader("이미지 파일", type=['png', 'jpg', 'jpeg'])
    if uploaded_img:
        with st.spinner("이미지에서 글자를 읽어오는 중..."):
            extracted_text += ocr_image(uploaded_img)

with tab3:
    manual_input = st.text_area("텍스트 직접 붙여넣기", height=150)
    if manual_input: extracted_text += manual_input

# --- 5. 분석 및 병합 로직 ---
# 기본 텍스트 + 수동 추가된 과목명 합치기 (검색용)
manual_text_block = " ".join([c['name'] for c in st.session_state.manual_courses])
full_analysis_text = extracted_text + "\n" + manual_text_block

if full_analysis_text.strip():
    if selected_year not in db or selected_dept not in db[selected_year]:
        st.error("지원되지 않는 학번/학과입니다.")
        st.stop()

    criteria = db[selected_year][selected_dept]
    gen_rule = criteria.get("general_education", {})
    clean_text = filter_failed_courses(full_analysis_text)
    
    # --- [중요] 학점 계산 로직 수정 (자동 추출 + 수동 합산) ---
    
    # 1. 문서에서 자동 추출된 학점
    auto_total = float((re.search(r'(?:취득학점|학점계)[:\s]*(\d{2,3})', clean_text) or [0,0])[1])
    auto_maj_req = float((re.search(r'전공필수[:\s]*(\d{1,3})', clean_text) or [0,0])[1])
    auto_maj_sel = float((re.search(r'전공선택[:\s]*(\d{1,3})', clean_text) or [0,0])[1])
    auto_upper = float((re.search(r'3~4천단위[:\s]*(\d{1,3})', clean_text) or [0,0])[1])
    
    # 2. 수동 입력된 학점 합산
    manual_total = sum([c['credit'] for c in st.session_state.manual_courses])
    manual_maj_req = sum([c['credit'] for c in st.session_state.manual_courses if c['type'] == "전공필수"])
    manual_maj_sel = sum([c['credit'] for c in st.session_state.manual_courses if c['type'] == "전공선택"])
    
    # 3. 최종 학점
    final_total = auto_total + manual_total
    final_maj_req = auto_maj_req + manual_maj_req
    final_maj_sel = auto_maj_sel + manual_maj_sel
    final_maj_total = final_maj_req + final_maj_sel
    
    # (주의: 3000단위는 수동 입력에서 체크하기 어려워 자동 추출값 유지하거나, 필요시 수동 입력에 체크박스 추가 가능)
    final_upper = auto_upper 

    # --- 교양 체크 로직 ---
    # 필수 과목
    req_courses_fail_list = [] 
    for item in gen_rule.get("required_courses", []):
        count = 0
        for kw in item["keywords"]:
            count += clean_text.count(kw) # 수동 입력된 과목명도 clean_text에 있으므로 카운트됨
        if count < 1: 
            req_courses_fail_list.append(item['name'])

    # 교양 영역
    all_req_areas = set(gen_rule.get("required_areas", []))
    all_elec_areas = set(gen_rule.get("elective_areas", []))
    
    my_req_areas = [a for a in all_req_areas if a in clean_text]
    my_elec_areas = [a for a in all_elec_areas if a in clean_text]
    
    missing_req_areas = all_req_areas - set(my_req_areas)
    missing_elec_count = gen_rule["elective_min_count"] - len(my_elec_areas)
    unused_elec_areas = all_elec_areas - set(my_elec_areas)

    # --- 판정 ---
    pass_total = final_total >= criteria['total_credits']
    pass_maj_tot = final_maj_total >= criteria['major_total']
    pass_maj_req = final_maj_req >= criteria['major_required']
    pass_upper = final_upper >= criteria['advanced_course']
    pass_eng = is_eng
    pass_info = is_info
    pass_gen_req_course = len(req_courses_fail_list) == 0
    pass_gen_area_req = len(missing_req_areas) == 0
    pass_gen_area_elec = missing_elec_count <= 0

    final_pass = all([pass_total, pass_maj_tot, pass_maj_req, pass_upper, pass_eng, pass_info, pass_gen_req_course, pass_gen_area_req, pass_gen_area_elec])

    # --- 결과 출력 ---
    st.divider()
    st.header("🏁 종합 판정 결과")
    
    if final_pass:
        st.success("🎉 **졸업 가능합니다!** 모든 요건을 충족했습니다.")
        st.balloons()
    else:
        st.error("⚠️ **졸업 불가능** (보완 필요)")

    # 요약
    c1, c2, c3 = st.columns(3)
    c1.metric("총 학점", f"{int(final_total)} / {criteria['total_credits']}", delta=f"+{manual_total} 수동" if manual_total else None)
    c2.metric("전공 학점", f"{int(final_maj_total)} / {criteria['major_total']}", delta=f"+{manual_maj_req+manual_maj_sel} 수동" if (manual_maj_req+manual_maj_sel) else None)
    c3.metric("필수 교양", "이수" if pass_gen_req_course else "미이수")

    # 상세 텍스트 확인
    with st.expander("📄 분석된 전체 텍스트 (PDF/이미지 + 수동입력)", expanded=False):
        st.text(clean_text)

    # 보완 가이드
    if not final_pass:
        st.subheader("🛠️ 보완 가이드")
        if not pass_total: st.warning(f"**[총 학점]** {int(criteria['total_credits'] - final_total)}학점 부족")
        if not pass_maj_tot: st.warning(f"**[전공 전체]** {int(criteria['major_total'] - final_maj_total)}학점 부족")
        if not pass_maj_req: st.warning(f"**[전공 필수]** {int(criteria['major_required'] - final_maj_req)}학점 부족")
        if not pass_upper: st.warning(f"**[3000단위 이상]** {int(criteria['advanced_course'] - final_upper)}학점 부족")
        
        if not pass_gen_req_course: st.error(f"**[필수 교양 미이수]** {', '.join(req_courses_fail_list)}")
        if not pass_gen_area_req: st.error(f"**[필수 영역 미이수]** {', '.join(missing_req_areas)}")
        
        if not pass_gen_area_elec:
            st.error(f"**[선택 영역 부족]** {missing_elec_count}개 영역 추가 필요")
            # 추천 강의 로직
            st.markdown("---")
            st.markdown("##### 💡 추천 강의")
            rec_map = gen_rule.get("area_courses", {}) or db.get("area_courses", {})
            for area in unused_elec_areas:
                if area in rec_map:
                    st.info(f"**[{area}]** {', '.join(rec_map[area])}")
                else:
                    st.info(f"**[{area}]** 강의를 찾아보세요.")
        
        if not pass_eng: st.warning("**[외국어 인증]** 미완료")
        if not pass_info: st.warning("**[정보/산학 인증]** 미완료")

else:
    st.info("👆 성적표(PDF, 이미지)를 업로드하거나 텍스트를 입력해주세요.")
