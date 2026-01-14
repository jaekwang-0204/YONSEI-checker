import streamlit as st
import pdfplumber
import re
import pandas as pd
import json
import pytesseract
from PIL import Image, ImageOps

# --- Tesseract 경로 설정 (필요 시 주석 해제) ---
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

st.set_page_config(page_title="졸업요건 진단기 (Ultimate)", page_icon="🎓")

# --- 세션 상태 초기화 ---
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

def clean_ocr_text(text):
    """OCR 오타 수정 및 정제"""
    corrections = {
        r'At': 'A+', r'Bt': 'B+', r'Ct': 'C+', r'Dt': 'D+',
        r'Ap': 'A+', r'Bp': 'B+', r'Poy': 'P', r'Pay': 'P', 
        r'Pass': 'P', r'NP': 'NP', r'F': 'F'
    }
    cleaned_lines = []
    for line in text.split('\n'):
        if len(line.strip()) < 2: continue
        for err, corr in corrections.items():
            line = re.sub(err, corr, line)
        # 특수문자 제거 (괄호, 점, 공백, 한글, 영문, 숫자, +, - 허용)
        line = re.sub(r'[^가-힣a-zA-Z0-9\s\+\-\(\)\.]', '', line)
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)

def filter_failed_courses(full_text):
    """F/NP 학점 제거"""
    lines = full_text.split('\n')
    filtered = []
    for line in lines:
        if re.search(r'\sF\s|\sF$|\sNP\s|\sNP$', line): continue
        filtered.append(line)
    return "\n".join(filtered)

def predict_course_type(course_name, year, dept):
    """[NEW] 과목명으로 이수 구분(전필/전선/교양) 자동 분류"""
    if year not in db or dept not in db[year]:
        return "교양/기타"
    
    known = db[year][dept].get("known_courses", {})
    
    # 1. 전공 필수 체크
    for req in known.get("major_required", []):
        # 띄어쓰기 무시하고 비교
        if req.replace(" ", "") in course_name.replace(" ", ""):
            return "전공필수"
            
    # 2. 전공 선택 체크
    for sel in known.get("major_elective", []):
        if sel.replace(" ", "") in course_name.replace(" ", ""):
            return "전공선택"
            
    # 3. 기본값
    return "교양/기타"

def ocr_image_and_parse(image_file, year, dept):
    """OCR 실행 및 과목/학점 자동 추출"""
    try:
        image = Image.open(image_file).convert('L')
        image = ImageOps.autocontrast(image)
        text = pytesseract.image_to_string(image, lang='kor+eng')
        text = clean_ocr_text(text)
        
        # 이미지에서 과목 정보 추출 (단순 텍스트 + 구조화된 데이터)
        parsed_courses = []
        # 패턴: 과목명 (공백) 학점 (공백) 성적 (예: 인체해부학 3 A+)
        # 한글/영문 과목명 뒤에 숫자(학점)가 오고 뒤에 알파벳(성적)이 오는 패턴
        matches = re.finditer(r'([가-힣a-zA-Z\(\)\d]+(?:\s+[가-힣a-zA-Z\(\)\d]+)*)\s+([1-9](?:\.5)?)\s+([A-Z]\+?|P)', text)
        
        for m in matches:
            c_name = m.group(1).strip()
            c_credit = float(m.group(2))
            c_type = predict_course_type(c_name, year, dept) # 자동 분류
            parsed_courses.append({"name": c_name, "credit": c_credit, "type": c_type})
            
        return text, parsed_courses
    except Exception as e:
        return f"Error: {e}", []

@st.dialog("🐛 버그 신고 및 문의")
def show_bug_report_dialog(year, dept):
    st.write("오류 내용을 복사해서 메일을 보내주세요.")
    st.code(f"받는사람: jaekwang1164@gmail.com\n제목: [졸업진단기 버그] {year} {dept}\n내용: 오류 상황 설명", language="text")

# --- 3. 사이드바 ---
with st.sidebar:
    st.header("⚙️ 설정")
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

    # [기능 개선] 수동 과목 추가 (자동 분류 적용)
    st.markdown("### ➕ 과목 수동 추가")
    with st.form("add_course_form", clear_on_submit=True):
        m_name = st.text_input("과목명 (예: 인체해부학)")
        m_credit = st.number_input("학점", 0.5, 10.0, 3.0, 0.5)
        # 사용자가 굳이 선택 안 해도 됨 (자동)
        m_manual_type = st.selectbox("이수 구분 (자동 감지됨)", ["자동(권장)", "전공필수", "전공선택", "교양/기타"])
        m_add = st.form_submit_button("추가하기")
        
        if m_add and m_name:
            final_type = m_manual_type
            if m_manual_type == "자동(권장)":
                final_type = predict_course_type(m_name, selected_year, selected_dept)
            
            st.session_state.manual_courses.append({
                "name": m_name, "credit": m_credit, "type": final_type
            })
            st.success(f"'{m_name}' -> [{final_type}]로 추가됨!")

    if st.session_state.manual_courses:
        st.markdown("---")
        for i, c in enumerate(st.session_state.manual_courses):
            c1, c2 = st.columns([4, 1])
            c1.text(f"{c['name']} ({c['type']}, {c['credit']}학점)")
            if c2.button("❌", key=f"d{i}"):
                del st.session_state.manual_courses[i]
                st.rerun()
    
    st.divider()
    if st.button("📧 버그 신고"): show_bug_report_dialog(selected_year, selected_dept)

# --- 메인 화면 ---
st.title("🎓 연세대 졸업요건 정밀 진단")
st.caption(f"기준: {selected_year}학번 {selected_dept}")

col1, col2 = st.columns(2)
is_eng = col1.checkbox("외국어 인증", value=False)
is_info = col2.checkbox("정보/산학 인증", value=False)

st.divider()

# --- 4. 데이터 입력 ---
tab1, tab2, tab3 = st.tabs(["📂 PDF", "🖼️ 이미지(캡쳐)", "📝 텍스트"])
extracted_text = ""
ocr_courses = [] # 이미지에서 자동 인식된 과목 리스트

with tab1:
    up_pdf = st.file_uploader("성적증명서 PDF", type="pdf")
    if up_pdf:
        with pdfplumber.open(up_pdf) as pdf:
            for page in pdf.pages: extracted_text += (page.extract_text() or "") + "\n"

with tab2:
    st.info("에브리타임/포털 성적 캡쳐 (여러 장 가능)")
    up_imgs = st.file_uploader("이미지", type=['png','jpg'], accept_multiple_files=True)
    if up_imgs:
        with st.spinner("이미지 분석 및 과목 자동 분류 중..."):
            for img in up_imgs:
                txt, parsed = ocr_image_and_parse(img, selected_year, selected_dept)
                extracted_text += txt + "\n"
                ocr_courses.extend(parsed)

with tab3:
    txt_in = st.text_area("텍스트 입력", height=150)
    if txt_in: extracted_text += txt_in

# --- 5. 분석 로직 ---
# 텍스트 합치기 (수동입력 과목도 텍스트에 포함시켜야 교양 키워드 검색에 걸림)
manual_txt = "\n".join([c['name'] for c in st.session_state.manual_courses])
full_text = extracted_text + "\n" + manual_txt

if full_text.strip():
    if selected_year not in db: st.stop()
    criteria = db[selected_year][selected_dept]
    gen_rule = criteria.get("general_education", {})
    clean_text = filter_failed_courses(full_text)
    
    # 1. 학점 계산 (우선순위: PDF > OCR/수동 합산)
    pdf_total = float((re.search(r'(?:취득학점|학점계)[:\s]*(\d{2,3})', clean_text) or [0,0])[1])
    pdf_maj_req = float((re.search(r'전공필수[:\s]*(\d{1,3})', clean_text) or [0,0])[1])
    pdf_maj_sel = float((re.search(r'전공선택[:\s]*(\d{1,3})', clean_text) or [0,0])[1])
    pdf_upper = float((re.search(r'3~4천단위[:\s]*(\d{1,3})', clean_text) or [0,0])[1])

    # OCR/수동 리스트 합산
    # (OCR로 인식된 과목들도 predict_course_type을 거쳤으므로 전필/전선 구분이 되어 있음)
    all_added_courses = st.session_state.manual_courses + ocr_courses
    
    added_total = sum(c['credit'] for c in all_added_courses)
    added_req = sum(c['credit'] for c in all_added_courses if c['type'] == '전공필수')
    added_sel = sum(c['credit'] for c in all_added_courses if c['type'] == '전공선택')
    
    # 최종 학점 결정
    if pdf_total > 0:
        # PDF가 있으면 PDF 기준 + 수동 추가분만 (OCR은 PDF에 포함되었을테니 중복 방지 로직 필요하나 단순 합산)
        # PDF 인식 시 OCR 탭은 안 쓴다고 가정
        final_total = pdf_total + sum(c['credit'] for c in st.session_state.manual_courses)
        final_req = pdf_maj_req + sum(c['credit'] for c in st.session_state.manual_courses if c['type'] == '전공필수')
        final_sel = pdf_maj_sel + sum(c['credit'] for c in st.session_state.manual_courses if c['type'] == '전공선택')
    else:
        # 이미지만 있는 경우 -> OCR 인식분 + 수동 추가분
        final_total = added_total
        final_req = added_req
        final_sel = added_sel

    final_maj = final_req + final_sel
    
    # 2. 교양 체크 (키워드 검색)
    # clean_text 안에 OCR 결과와 수동입력 과목명이 다 들어있으므로 검색 가능
    req_fail = []
    for item in gen_rule.get("required_courses", []):
        if not any(kw in clean_text for kw in item["keywords"]):
            req_fail.append(item['name'])

    all_areas = set(gen_rule.get("required_areas", []) + gen_rule.get("elective_areas", []))
    my_areas = [a for a in all_areas if a in clean_text]
    
    req_areas_fail = set(gen_rule.get("required_areas", [])) - set(my_areas)
    elec_cnt_fail = max(0, gen_rule["elective_min_count"] - len([a for a in my_areas if a in gen_rule.get("elective_areas", [])]))

    # 3. 판정 및 출력
    final_pass = all([
        final_total >= criteria['total_credits'],
        final_maj >= criteria['major_total'],
        final_req >= criteria['major_required'],
        pdf_upper >= criteria['advanced_course'], # 3000단위는 PDF만 신뢰
        len(req_fail) == 0,
        len(req_areas_fail) == 0,
        elec_cnt_fail == 0,
        is_eng, is_info
    ])
    
    st.divider()
    st.header("🏁 진단 결과")
    if final_pass: st.balloons(); st.success("졸업 가능합니다!")
    else: st.error("졸업 요건이 부족합니다.")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("총 학점", f"{int(final_total)} / {criteria['total_credits']}")
    c2.metric("전공(필+선)", f"{int(final_maj)} / {criteria['major_total']}")
    c3.metric("전공 필수", f"{int(final_req)} / {criteria['major_required']}")
    
    if not final_pass:
        st.subheader("🛠️ 보완 필요")
        if final_total < criteria['total_credits']: st.warning(f"총 학점 {criteria['total_credits']-final_total}점 부족")
        if final_req < criteria['major_required']: st.warning(f"전공필수 {criteria['major_required']-final_req}점 부족 (부족 과목: 인체해부학 등)")
        if req_fail: st.error(f"필수교양 미이수: {req_fail}")
        if req_areas_fail: st.error(f"필수영역 미이수: {req_areas_fail}")
        
    with st.expander("📄 분석 상세 (OCR 인식 과목 등)"):
        if ocr_courses:
            st.write("📸 이미지에서 인식된 과목:")
            st.dataframe(pd.DataFrame(ocr_courses))
        st.text(clean_text)
