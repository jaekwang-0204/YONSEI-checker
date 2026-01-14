import streamlit as st
import pdfplumber
import re
import pandas as pd
import json
import pytesseract
from PIL import Image, ImageOps, ImageEnhance
import numpy as np

# Tesseract 경로 (필요시 설정, 리눅스/클라우드 환경은 주석 유지)
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

st.set_page_config(page_title="졸업요건 진단기 (Ultimate)", page_icon="🎓")

if 'manual_courses' not in st.session_state:
    st.session_state.manual_courses = []

@st.cache_data
def load_requirements():
    try:
        with open('requirements.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError: return {}

db = load_requirements()

def normalize_string(s):
    # 비교를 위해 모든 공백과 특수문자를 제거
    if not isinstance(s, str): return ""
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', s)

def clean_ocr_line(line):
    # 노이즈 제거
    line = re.sub(r'[~@#$%\^&*_\-=|;:"<>,.?/]', ' ', line)
    return line.strip()

def classify_course_keyword(course_name, year, dept):
    """
    [핵심 솔루션] 키워드 포함 기반 분류
    입력된 과목명에 DB의 핵심 단어가 '포함'되어 있으면 인정
    """
    if year not in db or dept not in db[year]:
        return course_name, "교양/기타"
    
    known = db[year][dept].get("known_courses", {})
    norm_input = normalize_string(course_name) # 예: "임상병리사임상실습3"
    
    # 1. 전공 필수 체크
    for req in known.get("major_required", []):
        # DB의 키워드(예: "임상화학")가 입력값에 들어있으면 OK
        if normalize_string(req) in norm_input:
            return req, "전공필수"
            
    # 2. 전공 선택 체크
    for sel in known.get("major_elective", []):
        # DB의 키워드(예: "정도관리학", "임상병리사임상실습")가 입력값에 들어있으면 OK
        if normalize_string(sel) in norm_input:
            return sel, "전공선택"
            
    return course_name, "교양/기타"

def ocr_image_and_parse(image_file, year, dept):
    try:
        img = Image.open(image_file).convert('L')
        img = ImageOps.autocontrast(img)
        img = ImageEnhance.Contrast(img).enhance(2.0)
        
        text = pytesseract.image_to_string(img, lang='kor+eng', config='--psm 6')
        
        parsed_courses = []
        lines = text.split('\n')
        
        start_parsing = False
        
        for line in lines:
            line = clean_ocr_line(line)
            if not line: continue
            
            # 헤더 감지 (과목, 학점 등이 나오기 전까진 무시)
            if not start_parsing:
                if any(k in line for k in ["과목명", "학점", "성적", "전공", "등급", "이수"]):
                    start_parsing = True
                continue
            
            # 노이즈 줄 건너뛰기
            if any(k in line for k in ["평점", "취득", "총점", "신청", "년", "학기", "KT", "SKT", "LGU"]):
                continue

            # 패턴: (과목명) ... (학점 숫자)
            match = re.search(r'^(.*?)\s+([1-9](?:\.5)?)(?:\s+.*)?$', line)
            
            if match:
                raw_name = match.group(1).strip()
                credit = float(match.group(2))
                
                # 과목명 유효성 검사
                if len(raw_name) < 2 or raw_name.isdigit(): continue
                # 한글/영어가 없으면 무시
                if not re.search(r'[가-힣a-zA-Z]', raw_name): continue
                
                # 분류 실행 (키워드 매칭)
                final_name, final_type = classify_course_keyword(raw_name, year, dept)
                
                # 교양 영역 분류 시도 (전공이 아닌 경우)
                if final_type == "교양/기타":
                    # area_courses DB 확인
                    for area, courses in db.get("area_courses", {}).items():
                        for c in courses:
                            if normalize_string(c) in normalize_string(raw_name):
                                final_type = f"교양({area})"
                                break

                # 중복 방지
                if not any(c['name'] == final_name for c in parsed_courses):
                    parsed_courses.append({
                        "name": final_name, "credit": credit, "type": final_type
                    })
                    
        return text, parsed_courses
    except Exception as e:
        return f"Error: {e}", []

def filter_failed_courses(full_text):
    lines = full_text.split('\n')
    filtered = []
    for line in lines:
        if re.search(r'\sF\s|\sF$|\sNP\s|\sNP$', line): continue
        filtered.append(line)
    return "\n".join(filtered)

@st.dialog("🐛 오류 신고")
def show_bug_report(year, dept):
    st.write("오류 내용을 복사해서 메일을 보내주세요.")
    st.code(f"받는사람: jaekwang1164@gmail.com\n제목: [버그] {year} {dept}")

# --- UI ---
with st.sidebar:
    st.header("⚙️ 설정")
    years = sorted([k for k in db.keys() if k != "area_courses"]) if db else ["2022"]
    selected_year = st.selectbox("입학년도", years)
    
    depts = list(db[selected_year].keys()) if selected_year in db else ["-"]
    selected_dept = st.selectbox("전공", depts)

    st.divider()
    
    # 수동 추가
    with st.form("manual_add", clear_on_submit=True):
        st.caption("수동 입력 (자동 분류됨)")
        m_name = st.text_input("과목명")
        m_credit = st.number_input("학점", 0.5, 10.0, 3.0, 0.5)
        if st.form_submit_button("추가"):
            _, ftype = classify_course_keyword(m_name, selected_year, selected_dept)
            st.session_state.manual_courses.append({"name": m_name, "credit": m_credit, "type": ftype})
            st.success(f"추가됨: {m_name} ({ftype})")

    if st.session_state.manual_courses:
        st.markdown("---")
        for i, c in enumerate(st.session_state.manual_courses):
            c1, c2 = st.columns([4,1])
            c1.text(f"{c['name']}\n({c['type']})")
            if c2.button("x", key=f"del_{i}"):
                del st.session_state.manual_courses[i]
                st.rerun()

# --- 메인 ---
st.title("🎓 연세대 졸업요건 진단기")
st.caption(f"{selected_year}학번 {selected_dept}")

tab1, tab2 = st.tabs(["📄 PDF", "📸 캡쳐/이미지"])
extracted_text = ""
ocr_courses = []

with tab1:
    pdf_file = st.file_uploader("PDF 업로드", type="pdf")
    if pdf_file:
        with pdfplumber.open(pdf_file) as pdf:
            for p in pdf.pages: extracted_text += (p.extract_text() or "") + "\n"

with tab2:
    st.info("에브리타임/포털 캡쳐 (여러장 가능)")
    img_files = st.file_uploader("이미지", type=['png','jpg'], accept_multiple_files=True)
    if img_files:
        with st.spinner("분석 중..."):
            for img in img_files:
                txt, parsed = ocr_image_and_parse(img, selected_year, selected_dept)
                extracted_text += txt + "\n"
                ocr_courses.extend(parsed)

# --- 분석 로직 ---
manual_txt = "\n".join([c['name'] for c in st.session_state.manual_courses])
full_text = extracted_text + "\n" + manual_txt

if full_text.strip():
    if selected_year not in db: st.stop()
    criteria = db[selected_year][selected_dept]
    
    clean_text = filter_failed_courses(full_text)
    
    # 학점 계산 (PDF 우선)
    pdf_total = float((re.search(r'(?:취득학점|학점계)[:\s]*(\d{2,3})', clean_text) or [0,0])[1])
    pdf_req = float((re.search(r'전공필수[:\s]*(\d{1,3})', clean_text) or [0,0])[1])
    pdf_sel = float((re.search(r'전공선택[:\s]*(\d{1,3})', clean_text) or [0,0])[1])
    
    # OCR/수동 합산
    all_added = st.session_state.manual_courses + ocr_courses
    # 중복제거 (이름 기준)
    unique_courses = {v['name']:v for v in all_added}.values()
    
    add_total = sum(c['credit'] for c in unique_courses)
    add_req = sum(c['credit'] for c in unique_courses if c['type'] == '전공필수')
    add_sel = sum(c['credit'] for c in unique_courses if c['type'] == '전공선택')
    
    if pdf_total > 0:
        final_total = pdf_total + sum(c['credit'] for c in st.session_state.manual_courses)
        final_req = pdf_req + sum(c['credit'] for c in st.session_state.manual_courses if c['type'] == '전공필수')
        final_sel = pdf_sel + sum(c['credit'] for c in st.session_state.manual_courses if c['type'] == '전공선택')
    else:
        final_total = add_total
        final_req = add_req
        final_sel = add_sel
        
    final_maj = final_req + final_sel

    # 필수 교양 체크
    gen = criteria.get("general_education", {})
    req_fail = []
    for item in gen.get("required_courses", []):
        # 텍스트 내 키워드 검색
        if not any(kw in clean_text for kw in item["keywords"]):
            # OCR 리스트 내 키워드 검색 (정규화)
            found = False
            for c in unique_courses:
                if any(kw in normalize_string(c['name']) for kw in item["keywords"]):
                    found = True
                    break
            if not found: req_fail.append(item['name'])

    # 영역 체크
    my_area = set()
    # 텍스트 기반 영역 감지
    for area in gen.get("required_areas", []) + gen.get("elective_areas", []):
        if area in clean_text: my_area.add(area)
    
    # OCR 분류 기반 영역 감지 (교양(문학과예술) 형식)
    for c in unique_courses:
        if "교양(" in c['type']:
            detected_area = c['type'].replace("교양(", "").replace(")", "")
            my_area.add(detected_area)

    miss_req_area = set(gen.get("required_areas", [])) - my_area
    elec_cnt = len([a for a in my_area if a in gen.get("elective_areas", [])])
    elec_fail = max(0, gen["elective_min_count"] - elec_cnt)

    # 판정
    is_pass = all([
        final_total >= criteria['total_credits'],
        final_maj >= criteria['major_total'],
        final_req >= criteria['major_required'],
        not req_fail, not miss_req_area, elec_fail == 0
    ])

    st.divider()
    if is_pass: st.success("졸업 가능!"); st.balloons()
    else: st.error("졸업 요건 부족")

    c1, c2, c3 = st.columns(3)
    c1.metric("총 학점", f"{int(final_total)}/{criteria['total_credits']}")
    c2.metric("전공 합계", f"{int(final_maj)}/{criteria['major_total']}")
    c3.metric("전공 필수", f"{int(final_req)}/{criteria['major_required']}")
    
    if not is_pass:
        st.warning("보완 필요 사항")
        if final_total < criteria['total_credits']: st.write(f"- 총점 {int(criteria['total_credits']-final_total)}점 부족")
        if final_req < criteria['major_required']: st.write(f"- 전필 {int(criteria['major_required']-final_req)}점 부족")
        if req_fail: st.write(f"- 필수교양 미이수: {req_fail}")
        if miss_req_area: st.write(f"- 필수영역 미이수: {miss_req_area}")
        if elec_fail: st.write(f"- 선택영역 {elec_fail}개 부족")

    with st.expander("인식된 과목 목록"):
        if unique_courses:
            st.dataframe(pd.DataFrame(unique_courses))
        else:
            st.info("데이터 없음")
