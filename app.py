import streamlit as st
import pdfplumber
import re
import pandas as pd
import json
import pytesseract
from PIL import Image, ImageOps, ImageEnhance
import numpy as np

st.set_page_config(page_title="졸업요건 진단기 (Pro)", page_icon="🎓", layout="wide")

# --- 세션 상태 초기화 ---
if 'ocr_results' not in st.session_state:
    st.session_state.ocr_results = []

# --- 1. 졸업요건 DB 로드 ---
@st.cache_data
def load_requirements():
    try:
        with open('requirements.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError: return {}

db = load_requirements()

# --- 2. 헬퍼 함수 (초안 및 기존 로직 통합) ---

def normalize_string(s):
    if not isinstance(s, str): return ""
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', s).upper()

def filter_failed_courses(full_text):
    """[초안 반영] F 또는 NP가 포함된 줄 제외"""
    lines = full_text.split('\n')
    filtered_lines = []
    for line in lines:
        if re.search(r'\sF\s|\sF$|\sNP\s|\sNP$', line):
            continue 
        filtered_lines.append(line)
    return "\n".join(filtered_lines)

@st.dialog("🐛 버그 신고 및 문의")
def show_bug_report_dialog(year, dept):
    """[초안 반영] 다이얼로그 기반 버그 신고"""
    st.write("시스템 오류가 발생했나요? 아래 정보를 복사해서 메일을 보내주세요.")
    st.divider()
    st.caption("1. 받는 사람 이메일")
    st.code("jaekwang1164@gmail.com", language="text")
    st.caption("2. 메일 제목")
    st.code(f"[졸업진단기 버그신고] {year}학번 {dept}", language="text")
    st.caption("3. 본문 내용")
    st.code("- 오류 현상:\n- 기대 결과:\n- 첨부파일 여부:", language="text")

def classify_course_logic(course_name, year, dept):
    """[분류 로직] RC 우선 및 DB 매칭"""
    norm_name = normalize_string(course_name)
    if "RC" in norm_name or "리더십" in norm_name: return "교양(리더십)"
    if year not in db or dept not in db[year]: return "교양/기타"
    
    dept_db = db[year][dept]
    known = dept_db.get("known_courses", {})
    
    for req in known.get("major_required", []):
        if normalize_string(req) in norm_name: return "전공필수"
    for sel in known.get("major_elective", []):
        if normalize_string(sel) in norm_name: return "전공선택"
            
    for area, courses in db.get("area_courses", {}).items():
        for c in courses:
            if normalize_string(c) in norm_name: return f"교양({area})"
                
    return "교양/기타"

# --- 3. 이미지 파이프라인 (OCR) ---
def ocr_image_parsing(image_file, year, dept):
    try:
        img = Image.open(image_file).convert('L')
        img = ImageOps.autocontrast(img)
        img = ImageEnhance.Contrast(img).enhance(2.0)
        text = pytesseract.image_to_string(img, lang='kor+eng', config='--psm 6')
        
        parsed_data = []
        for line in text.split('\n'):
            match = re.search(r'^(.*?)\s+(\d+(?:\.\d+)?)(?:\s+.*)?$', line)
            if match:
                raw_name = match.group(1).strip()
                credit = float(match.group(2))
                if len(raw_name) < 2 or raw_name.isdigit(): continue
                ftype = classify_course_logic(raw_name, year, dept)
                parsed_data.append({"과목명": raw_name, "학점": credit, "이수구분": ftype})
        return parsed_data
    except: return []

# --- 4. UI 및 사이드바 ---
with st.sidebar:
    st.header("⚙️ 설정")
    years = sorted([k for k in db.keys() if k != "area_courses"]) if db else ["2022"]
    selected_year = st.selectbox("입학년도", years)
    selected_dept = st.selectbox("전공", list(db[selected_year].keys()) if selected_year in db else ["-"])
    
    st.divider()
    if st.button("🔄 데이터 초기화"):
        st.session_state.ocr_results = []; st.rerun()
    
    if st.button("🐛 버그 신고"):
        show_bug_report_dialog(selected_year, selected_dept)

st.title("🎓 연세대 졸업요건 통합 진단기")
tab1, tab2, tab3 = st.tabs(["📂 성적표 업로드 (PDF/이미지)", "✏️ 과목 수정 및 확인", "📊 최종 진단 결과"])

# --- 5. 독립적 데이터 추출 파이프라인 ---
pdf_course_list = []
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### 📄 PDF 파이프라인")
        pdf_file = st.file_uploader("텍스트 복사 가능 PDF 전용", type="pdf")
        if pdf_file:
            with pdfplumber.open(pdf_file) as pdf:
                full_pdf_text = ""
                for p in pdf.pages: full_pdf_text += (p.extract_text() or "") + "\n"
            
            clean_pdf_text = filter_failed_courses(full_pdf_text)
            for line in clean_pdf_text.split('\n'):
                # PDF 텍스트 파싱 (과목명 학점 패턴)
                match = re.search(r'^(.*?)\s+(\d+(?:\.\d+)?)(?:\s+[A-F][+-]?|Pass|P|NP|F)?$', line.strip())
                if match:
                    p_name, p_credit = match.group(1).strip(), float(match.group(2))
                    if len(p_name) >= 2 and not p_name.isdigit():
                        p_type = classify_course_logic(p_name, selected_year, selected_dept)
                        pdf_course_list.append({"과목명": p_name, "학점": p_credit, "이수구분": p_type})
            st.success(f"PDF에서 {len(pdf_course_list)}개 과목 추출 완료")

    with col2:
        st.markdown("##### 📸 이미지 파이프라인")
        img_files = st.file_uploader("에브리타임 캡쳐/이미지 PDF", type=['png','jpg','jpeg'], accept_multiple_files=True)
        if img_files and st.button("🔍 이미지 분석 실행"):
            with st.spinner("이미지 분석 중..."):
                results = []
                for img in img_files: results.extend(ocr_image_parsing(img, selected_year, selected_dept))
                st.session_state.ocr_results = results
                st.success(f"이미지에서 {len(results)}개 과목 추출 완료")

with tab2:
    st.markdown("### 📝 수강 과목 통합 관리")
    st.caption("PDF 데이터와 이미지 데이터가 이곳으로 모입니다. 수정사항은 실시간 반영됩니다.")
    
    # 세션(이미지) 데이터와 실시간 PDF 데이터를 합쳐서 에디터에 초기값 제공
    initial_df = pd.DataFrame(st.session_state.ocr_results + pdf_course_list)
    if initial_df.empty:
        initial_df = pd.DataFrame(columns=["과목명", "학점", "이수구분"])
    else:
        initial_df = initial_df.drop_duplicates(subset=['과목명'])

    edited_df = st.data_editor(
        initial_df, num_rows="dynamic", use_container_width=True,
        column_config={
            "학점": st.column_config.NumberColumn("학점", step=0.5),
            "이수구분": st.column_config.SelectboxColumn("이수구분", options=["전공필수", "전공선택", "교양(리더십)", "교양(문학과예술)", "교양(인간과역사)", "교양(언어와표현)", "교양(가치와윤리)", "교양(국가와사회)", "교양(지역과세계)", "교양(논리와수리)", "교양(자연과우주)", "교양(생명과환경)", "교양(정보와기술)", "교양(체육과건강)", "교양/기타"])
        }, key="main_editor"
    )

with tab3:
    # 최종 통합 데이터 (에디터에 있는 내용이 최종본)
    combined_courses = edited_df.to_dict('records')
    
    if combined_courses:
        criteria = db[selected_year][selected_dept]
        gen = criteria.get("general_education", {})
        
        # 1. 학점 계산
        total_credits = sum(c['학점'] for c in combined_courses)
        maj_req = sum(c['학점'] for c in combined_courses if c['이수구분'] == "전공필수")
        maj_sel = sum(c['학점'] for c in combined_courses if c['이수구분'] == "전공선택")
        
        # 2. 리더십 및 필수교양 체크 (RC 및 키워드 기반)
        leadership_count = len([c for c in combined_courses if "리더십" in str(c['이수구분']) or "RC" in normalize_string(c['과목명'])])
        
        # 필수교양 검색용 텍스트
        search_text = "\n".join([c['과목명'] for c in combined_courses])
        req_fail = []
        for item in gen.get("required_courses", []):
            if item['name'] == "리더십":
                if leadership_count < 2: req_fail.append("리더십(RC포함 2과목)")
                continue
            if not any(normalize_string(kw) in normalize_string(search_text) for kw in item["keywords"]):
                req_fail.append(item['name'])

        # 3. 결과 출력
        is_pass = all([total_credits >= criteria['total_credits'], (maj_req+maj_sel) >= criteria['major_total'], maj_req >= criteria['major_required'], not req_fail])

        st.header("🏁 최종 졸업 자격 진단")
        if is_pass: st.success("🎉 모든 요건을 충족했습니다!"); st.balloons()
        else: st.error("⚠️ 요건 미충족 사항이 있습니다.")

        c1, c2, c3 = st.columns(3)
        c1.metric("총 취득학점", f"{int(total_credits)} / {criteria['total_credits']}")
        c2.metric("전공(필+선)", f"{int(maj_req + maj_sel)} / {criteria['major_total']}")
        c3.metric("리더십(RC포함)", f"{leadership_count} / 2")

        if req_fail:
            st.warning(f"**미이수 항목:** {', '.join(req_fail)}")
            
        with st.expander("📊 상세 과목 통계"):
            st.table(pd.DataFrame(combined_courses))
    else:
        st.info("데이터가 없습니다. 성적표를 업로드해주세요.")
