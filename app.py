import streamlit as st
import pdfplumber
import re
import pandas as pd
import json
import pytesseract
from PIL import Image, ImageOps, ImageEnhance
import numpy as np

st.set_page_config(page_title="졸업요건 진단기 (Ultimate)", page_icon="🎓", layout="wide")

if 'ocr_results' not in st.session_state:
    st.session_state.ocr_results = []

# --- 1. DB 로드 ---
@st.cache_data
def load_requirements():
    try:
        with open('requirements.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError: return {}

db = load_requirements()

# --- 2. 헬퍼 함수 ---
def normalize_string(s):
    if not isinstance(s, str): return ""
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', s).upper() # 영문 대문자 통일

def classify_course_logic(course_name, year, dept):
    """[개선된 분류 로직] RC 우선 처리 및 전공/교양 분류"""
    norm_name = normalize_string(course_name)
    
    # 1. RC 특별 처리 (가장 우선)
    if "RC" in norm_name:
        return "교양(리더십)"

    if year not in db or dept not in db[year]:
        return "교양/기타"
    
    known = db[year][dept].get("known_courses", {})
    
    # 2. 전공 필수/선택 체크
    for req in known.get("major_required", []):
        if normalize_string(req) in norm_name or norm_name in normalize_string(req):
            return "전공필수"
    for sel in known.get("major_elective", []):
        if normalize_string(sel) in norm_name or norm_name in normalize_string(sel):
            return "전공선택"
            
    # 3. 교양 영역 체크 (area_courses 활용)
    for area, courses in db.get("area_courses", {}).items():
        for c in courses:
            if normalize_string(c) in norm_name:
                # 리더십 영역은 별도 표시
                if "리더십" in area: return "교양(리더십)"
                return f"교양({area})"
                
    return "교양/기타"

def ocr_image_parsing(image_file, year, dept):
    try:
        img = Image.open(image_file).convert('L')
        img = ImageOps.autocontrast(img)
        img = ImageEnhance.Contrast(img).enhance(2.0)
        text = pytesseract.image_to_string(img, lang='kor+eng', config='--psm 6')
        
        parsed_data = []
        lines = text.split('\n')
        start_parsing = False
        
        for line in lines:
            if not start_parsing:
                if any(k in line for k in ["과목명", "학점", "성적", "전공"]): start_parsing = True
                continue
            
            # (과목명) ... (학점 숫자)
            match = re.search(r'^(.*?)\s+(\d+(?:\.\d+)?)(?:\s+.*)?$', line)
            if match:
                raw_name = match.group(1).strip()
                credit = float(match.group(2))
                
                # 노이즈 필터
                if len(raw_name) < 2 or raw_name.isdigit(): continue
                if raw_name.upper() in ["AT", "BT", "AP", "SS", "BO", "PASS", "NP"]: continue

                # 개선된 분류 로직 적용
                ftype = classify_course_logic(raw_name, year, dept)
                
                parsed_data.append({"과목명": raw_name, "학점": credit, "이수구분": ftype})
        return parsed_data
    except: return []

# --- UI 및 사이드바 (기존과 동일) ---
with st.sidebar:
    st.header("⚙️ 설정")
    years = sorted([k for k in db.keys() if k != "area_courses"]) if db else ["2022"]
    selected_year = st.selectbox("입학년도", years)
    selected_dept = st.selectbox("전공", list(db[selected_year].keys()) if selected_year in db else ["-"])
    if st.button("🔄 테이블 초기화"):
        st.session_state.ocr_results = []; st.rerun()

st.title("🎓 연세대 졸업요건 진단기")
tab1, tab2, tab3 = st.tabs(["📄 PDF 업로드", "📸 이미지(캡쳐)", "✏️ 과목 수정/삭제"])

with tab1:
    pdf_file = st.file_uploader("PDF 성적표", type="pdf")
    pdf_text = ""
    if pdf_file:
        with pdfplumber.open(pdf_file) as pdf:
            for p in pdf.pages: pdf_text += (p.extract_text() or "") + "\n"

with tab2:
    img_files = st.file_uploader("이미지 파일", type=['png','jpg','jpeg'], accept_multiple_files=True)
    if img_files and st.button("🔍 이미지 분석 실행"):
        with st.spinner("분석 중..."):
            results = []
            for img in img_files: results.extend(ocr_image_parsing(img, selected_year, selected_dept))
            st.session_state.ocr_results = results
            st.success("인식 완료!")

with tab3:
    df_input = pd.DataFrame(st.session_state.ocr_results) if st.session_state.ocr_results else pd.DataFrame(columns=["과목명", "학점", "이수구분"])
    edited_df = st.data_editor(
        df_input, num_rows="dynamic", use_container_width=True,
        column_config={
            "학점": st.column_config.NumberColumn("학점", step=0.5),
            "이수구분": st.column_config.SelectboxColumn("이수구분", options=["전공필수", "전공선택", "교양(리더십)", "교양(문학과예술)", "교양(인간과역사)", "교양(언어와표현)", "교양(가치와윤리)", "교양(국가와사회)", "교양(지역과세계)", "교양(논리와수리)", "교양(자연과우주)", "교양(생명과환경)", "교양(정보와기술)", "교양(체육과건강)", "교양/기타"])
        }, key="editor"
    )

# --- 분석 로직 ---
st.divider()
final_courses = edited_df.to_dict('records')
all_course_names_text = pdf_text + "\n" + "\n".join([c['과목명'] for c in final_courses])

if all_course_names_text.strip():
    criteria = db[selected_year][selected_dept]
    gen = criteria.get("general_education", {})
    
    # 학점 합산
    total_credits = sum(c['학점'] for c in final_courses)
    maj_req_credits = sum(c['학점'] for c in final_courses if c['이수구분'] == "전공필수")
    maj_sel_credits = sum(c['학점'] for c in final_courses if c['이수구분'] == "전공선택")
    
    # 1. 리더십 요건 체크 (개선됨: RC 포함 또는 리더십 분류 강의가 2개 이상)
    leadership_count = len([c for c in final_courses if "리더십" in c['이수구분'] or "RC" in c['과목명'].upper()])
    pass_leadership = leadership_count >= 2

    # 2. 필수 교양 과목 체크
    req_fail = []
    for item in gen.get("required_courses", []):
        # 리더십은 위에서 별도로 체크하므로 제외하고 체크
        if item['name'] == "리더십":
            if not pass_leadership: req_fail.append("리더십(RC 포함 2과목 미달)")
            continue
            
        found = any(kw in normalize_string(all_course_names_text) for kw in item["keywords"])
        if not found: req_fail.append(item['name'])

    # 결과 출력
    is_pass = all([total_credits >= criteria['total_credits'], (maj_req_credits+maj_sel_credits) >= criteria['major_total'], maj_req_credits >= criteria['major_required'], not req_fail])

    if is_pass: st.success("🎉 졸업 가능 요건을 모두 충족했습니다!")
    else: st.error("⚠️ 졸업 요건이 부족합니다.")

    c1, c2, c3 = st.columns(3)
    c1.metric("총 학점", f"{int(total_credits)}/{criteria['total_credits']}")
    c2.metric("전공 합계", f"{int(maj_req_credits+maj_sel_credits)}/{criteria['major_total']}")
    c3.metric("리더십(RC)", f"{leadership_count}/2 이수")

    if req_fail:
        st.warning(f"**미이수 필수교양:** {', '.join(req_fail)}")
