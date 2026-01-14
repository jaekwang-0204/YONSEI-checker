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

# --- 세션 상태 ---
if 'manual_courses' not in st.session_state:
    st.session_state.manual_courses = []

# --- 1. DB 로드 ---
@st.cache_data
def load_requirements():
    try:
        with open('requirements.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

db = load_requirements()

# --- 2. 텍스트 처리 헬퍼 함수 ---

def normalize_string(s):
    """비교를 위해 한글/영어/숫자만 남기고 공백 등 제거"""
    if not isinstance(s, str): return ""
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', s)

def clean_ocr_line(line):
    """OCR 결과 라인별 노이즈 정리"""
    # 1. 등급 오타 수정
    corrections = {
        r'At': 'A+', r'Bt': 'B+', r'Ct': 'C+', r'Dt': 'D+',
        r'Ap': 'A+', r'Bp': 'B+', r'Poy': 'P', r'Pay': 'P',
        r'Pass': 'P', r'NP': 'NP', r'F': 'F'
    }
    for err, corr in corrections.items():
        line = re.sub(err, corr, line)
    
    # 2. 물결표(~), 특수문자 제거 (괄호는 살림)
    line = re.sub(r'[~@#$%\^&*_\-=|;:"<>,.?/]', ' ', line)
    return line.strip()

def find_course_in_db(course_name, year, dept):
    """
    OCR된 과목명(오타 가능성 있음)을 DB의 정확한 명칭과 매칭 시도
    """
    if year not in db or dept not in db[year]:
        return course_name, "교양/기타" # 매칭 불가 시 원본 이름 사용
    
    known = db[year][dept].get("known_courses", {})
    clean_input = normalize_string(course_name)
    
    # 너무 짧으면(1글자 등) 매칭 포기
    if len(clean_input) < 2:
        return course_name, "교양/기타"

    # 1. 전공 필수 매칭
    for req in known.get("major_required", []):
        if normalize_string(req) in clean_input: # 포함 관계 확인
            return req, "전공필수" # DB의 정확한 명칭 반환
            
    # 2. 전공 선택 매칭
    for sel in known.get("major_elective", []):
        if normalize_string(sel) in clean_input:
            return sel, "전공선택"
            
    return course_name, "교양/기타"

def ocr_image_and_parse(image_file, year, dept):
    try:
        # 이미지 전처리 (흑백, 대비 강화)
        img = Image.open(image_file).convert('L')
        img = ImageOps.autocontrast(img)
        img = ImageEnhance.Contrast(img).enhance(2.0)
        
        # OCR 실행
        text = pytesseract.image_to_string(img, lang='kor+eng', config='--psm 6')
        
        parsed_courses = []
        lines = text.split('\n')
        
        for line in lines:
            line = clean_ocr_line(line)
            if not line: continue
            
            # [핵심 로직] 오른쪽 끝에서부터 "학점"과 "성적" 패턴 찾기
            # 예: "미래설계리빙랩 3 P" -> Name="미래설계리빙랩", Credit=3, Grade=P
            # 패턴: (과목명...) (공백) (숫자1~9) (공백) (성적 A~F or P/NP)
            match = re.search(r'^(.*?)\s+([1-9](?:\.5)?)\s+([A-Z]\+?|P|NP|F)$', line)
            
            if match:
                raw_name = match.group(1).strip()
                credit = float(match.group(2))
                grade = match.group(3)
                
                # 에브리타임 빈칸("0", "At" 등) 걸러내기
                if raw_name in ["0", "O", "o"] or len(raw_name) < 2:
                    continue
                if "학점" in raw_name or "평점" in raw_name: # 헤더 걸러내기
                    continue

                # DB 매칭 (전공 여부 확인)
                final_name, final_type = find_course_in_db(raw_name, year, dept)
                
                # 중복 방지 (이미지 여러장일 때)
                if not any(c['name'] == final_name for c in parsed_courses):
                    parsed_courses.append({
                        "name": final_name,
                        "credit": credit,
                        "type": final_type,
                        "grade": grade
                    })
                    
        return text, parsed_courses
        
    except Exception as e:
        return f"Error: {e}", []

def filter_failed_courses(full_text):
    """F/NP 제거 (OCR 파싱된 데이터는 이미 처리하므로 PDF용 텍스트만 처리)"""
    lines = full_text.split('\n')
    filtered = []
    for line in lines:
        if re.search(r'\sF\s|\sF$|\sNP\s|\sNP$', line): continue
        filtered.append(line)
    return "\n".join(filtered)

@st.dialog("🐛 버그 신고")
def show_bug_report_dialog(year, dept):
    st.write("오류 내용을 복사해서 메일을 보내주세요.")
    st.code(f"받는사람: jaekwang1164@gmail.com\n제목: [버그] {year} {dept}", language="text")


# --- UI 구성 ---
with st.sidebar:
    st.header("⚙️ 설정")
    if db:
        years = sorted([k for k in db.keys() if k != "area_courses"])
    else:
        years = ["2022"]
    selected_year = st.selectbox("입학년도", years)
    
    if selected_year in db:
        depts = list(db[selected_year].keys())
        selected_dept = st.selectbox("전공", depts)
    else:
        selected_dept = st.selectbox("전공", ["-"])

    st.divider()
    
    st.markdown("### ➕ 과목 수동 추가")
    with st.form("add_form", clear_on_submit=True):
        m_name = st.text_input("과목명")
        m_credit = st.number_input("학점", 0.5, 10.0, 3.0, 0.5)
        m_type_sel = st.selectbox("구분", ["자동감지", "전공필수", "전공선택", "교양/기타"])
        if st.form_submit_button("추가"):
            if m_type_sel == "자동감지":
                _, ftype = find_course_in_db(m_name, selected_year, selected_dept)
            else:
                ftype = m_type_sel
            
            st.session_state.manual_courses.append({
                "name": m_name, "credit": m_credit, "type": ftype
            })
            st.success(f"{m_name} 추가됨")
            
    if st.session_state.manual_courses:
        st.markdown("---")
        for i, c in enumerate(st.session_state.manual_courses):
            c1, c2 = st.columns([4,1])
            c1.text(f"{c['name']} ({c['type']})")
            if c2.button("x", key=f"d{i}"):
                del st.session_state.manual_courses[i]
                st.rerun()
    
    st.divider()
    if st.button("📧 오류 신고"): show_bug_report_dialog(selected_year, selected_dept)


# --- 메인 ---
st.title("🎓 연세대 졸업요건 진단기")
st.caption(f"기준: {selected_year}학번 {selected_dept}")

c1, c2 = st.columns(2)
is_eng = c1.checkbox("외국어 인증", False)
is_info = c2.checkbox("정보 인증", False)

st.divider()

tab1, tab2, tab3 = st.tabs(["📄 PDF", "📸 캡쳐/이미지", "⌨️ 텍스트"])
extracted_text = ""
ocr_courses = []

with tab1:
    pdf_file = st.file_uploader("성적증명서 PDF", type="pdf")
    if pdf_file:
        with pdfplumber.open(pdf_file) as pdf:
            for p in pdf.pages: extracted_text += (p.extract_text() or "") + "\n"

with tab2:
    st.info("에브리타임, 포털 캡쳐 (여러 장 가능, 흑백 자동보정)")
    img_files = st.file_uploader("이미지", type=['png','jpg'], accept_multiple_files=True)
    if img_files:
        with st.spinner("이미지 정밀 분석 중..."):
            for img in img_files:
                txt, parsed = ocr_image_and_parse(img, selected_year, selected_dept)
                extracted_text += txt + "\n"
                ocr_courses.extend(parsed)

with tab3:
    txt_in = st.text_area("텍스트 입력")
    if txt_in: extracted_text += txt_in

# --- 분석 ---
manual_txt = "\n".join([c['name'] for c in st.session_state.manual_courses])
full_text = extracted_text + "\n" + manual_txt

if full_text.strip():
    if selected_year not in db: st.stop()
    criteria = db[selected_year][selected_dept]
    gen_rule = criteria.get("general_education", {})
    clean_text = filter_failed_courses(full_text)
    
    # 1. 학점 계산
    # (A) PDF에서 총점 찾기
    pdf_total = float((re.search(r'(?:취득학점|학점계)[:\s]*(\d{2,3})', clean_text) or [0,0])[1])
    pdf_maj_req = float((re.search(r'전공필수[:\s]*(\d{1,3})', clean_text) or [0,0])[1])
    pdf_maj_sel = float((re.search(r'전공선택[:\s]*(\d{1,3})', clean_text) or [0,0])[1])
    pdf_upper = float((re.search(r'3~4천단위[:\s]*(\d{1,3})', clean_text) or [0,0])[1])
    
    # (B) OCR/수동 합산
    all_added = st.session_state.manual_courses + ocr_courses
    # 중복 제거 (과목명 기준)
    unique_added = {v['name']:v for v in all_added}.values()
    
    added_total = sum(c['credit'] for c in unique_added)
    added_req = sum(c['credit'] for c in unique_added if c['type'] == '전공필수')
    added_sel = sum(c['credit'] for c in unique_added if c['type'] == '전공선택')
    
    # (C) 최종 결정
    if pdf_total > 0:
        # PDF 우선 + 수동(세션)만 추가
        final_total = pdf_total + sum(c['credit'] for c in st.session_state.manual_courses)
        final_req = pdf_maj_req + sum(c['credit'] for c in st.session_state.manual_courses if c['type'] == '전공필수')
        final_sel = pdf_maj_sel + sum(c['credit'] for c in st.session_state.manual_courses if c['type'] == '전공선택')
    else:
        # 이미지/수동 모드 -> 합산값 사용
        final_total = added_total
        final_req = added_req
        final_sel = added_sel
    
    final_maj = final_req + final_sel

    # 2. 교양 체크 (수정된 로직)
    req_fail = []
    for item in gen_rule.get("required_courses", []):
        # 1. 텍스트에서 키워드 찾기
        found_in_text = any(kw in clean_text for kw in item["keywords"])
        
        # 2. 텍스트에 없으면 OCR/수동 리스트에서 찾기 (정규화 비교)
        found_in_list = False
        if not found_in_text:
            for course in unique_added:
                # 과목명 정규화 (공백 등 제거)
                norm_name = normalize_string(course['name'])
                if any(kw in norm_name for kw in item["keywords"]):
                    found_in_list = True
                    break
                    
        if not found_in_text and not found_in_list:
            req_fail.append(item['name'])

    all_area = set(gen_rule.get("required_areas", []) + gen_rule.get("elective_areas", []))
    my_area = [a for a in all_area if a in clean_text]
    
    miss_req_area = set(gen_rule.get("required_areas", [])) - set(my_area)
    elec_fail_cnt = max(0, gen_rule["elective_min_count"] - len([a for a in my_area if a in gen_rule.get("elective_areas", [])]))

    # 3. 판정
    final_pass = all([
        final_total >= criteria['total_credits'],
        final_maj >= criteria['major_total'],
        final_req >= criteria['major_required'],
        # 3000단위는 OCR로 힘들어서 PDF일때만 체크 (이미지일 땐 0>=50 False 뜨므로 조건 완화 필요하나 일단 유지)
        (pdf_upper >= criteria['advanced_course'] if pdf_total > 0 else True), 
        not req_fail, not miss_req_area, elec_fail_cnt == 0,
        is_eng, is_info
    ])
    
    st.divider()
    if final_pass: st.balloons(); st.success("졸업 가능!")
    else: st.error("졸업 요건 부족")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("총 학점", f"{int(final_total)}/{criteria['total_credits']}")
    c2.metric("전공(필+선)", f"{int(final_maj)}/{criteria['major_total']}")
    c3.metric("전공필수", f"{int(final_req)}/{criteria['major_required']}")
    
    if not final_pass:
        st.subheader("🛠️ 보완 필요")
        if final_total < criteria['total_credits']: st.warning(f"총점 {int(criteria['total_credits']-final_total)} 부족")
        if final_req < criteria['major_required']: st.warning(f"전필 {int(criteria['major_required']-final_req)} 부족")
        if req_fail: st.error(f"필수교양 미이수: {', '.join(req_fail)}")
        if miss_req_area: st.error(f"필수영역 미이수: {', '.join(miss_req_area)}")
        if elec_fail_cnt: 
            st.error(f"선택영역 {elec_fail_cnt}개 부족")
            with st.expander("추천 강의"):
                rmap = gen_rule.get("area_courses", {}) or db.get("area_courses", {})
                for a in (set(gen_rule.get("elective_areas", [])) - set(my_area)):
                    st.write(f"**[{a}]**", ", ".join(rmap.get(a, [])))

    with st.expander("📸 OCR 인식된 과목 목록 확인"):
        if ocr_courses:
            df = pd.DataFrame(ocr_courses)
            # 중복 제거해서 보여주기
            df = df.drop_duplicates(subset=['name'])
            st.dataframe(df)
            st.caption(f"인식된 총 학점 합계: {added_total}점")
        else:
            st.info("이미지에서 인식된 과목이 없습니다.")
            
    with st.expander("📄 전체 분석 텍스트"):
        st.text(clean_text)

else:
    st.info("성적표를 업로드해주세요.")
