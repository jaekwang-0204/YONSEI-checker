import streamlit as st
import pdfplumber
import re
import pandas as pd
import json
import pytesseract
from PIL import Image, ImageOps, ImageEnhance
import numpy as np

# Tesseract 경로 (필요시 주석 해제)
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

st.set_page_config(page_title="졸업요건 진단기 (Ultimate)", page_icon="🎓", layout="wide")

# --- 세션 상태 초기화 ---
if 'ocr_results' not in st.session_state:
    st.session_state.ocr_results = [] # OCR 결과 저장용

# --- 1. DB 로드 ---
@st.cache_data
def load_requirements():
    try:
        with open('requirements.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

db = load_requirements()

# --- 2. 헬퍼 함수 ---
def normalize_string(s):
    if not isinstance(s, str): return ""
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', s)

def clean_ocr_line(line):
    # 노이즈 제거
    line = re.sub(r'[~@#$%\^&*_\-=|;:"<>,.?/\[\]\{\}]', ' ', line)
    return line.strip()

def classify_course_keyword(course_name, year, dept):
    """키워드 포함 기반 분류"""
    if year not in db or dept not in db[year]:
        return "교양"
    
    known = db[year][dept].get("known_courses", {})
    norm_input = normalize_string(course_name)
    
    # 1. 전공 필수
    for req in known.get("major_required", []):
        if normalize_string(req) in norm_input:
            return "전공필수"
            
    # 2. 전공 선택
    for sel in known.get("major_elective", []):
        if normalize_string(sel) in norm_input:
            return "전공선택"
            
    # 3. 교양 영역 (JSON의 area_courses 활용)
    for area, courses in db.get("area_courses", {}).items():
        for c in courses:
            if normalize_string(c) in norm_input:
                return f"교양({area})"
                
    return "교양"

def ocr_image_parsing(image_file, year, dept):
    """이미지 OCR 및 파싱 (리스트 반환)"""
    try:
        img = Image.open(image_file).convert('L')
        img = ImageOps.autocontrast(img)
        img = ImageEnhance.Contrast(img).enhance(2.0)
        
        text = pytesseract.image_to_string(img, lang='kor+eng', config='--psm 6')
        
        parsed_data = []
        lines = text.split('\n')
        start_parsing = False
        
        for line in lines:
            line = clean_ocr_line(line)
            if not line: continue
            
            # 헤더 감지
            if not start_parsing:
                if any(k in line for k in ["과목명", "학점", "성적", "전공", "등급", "이수"]):
                    start_parsing = True
                continue
            
            # 노이즈 줄 건너뛰기
            if any(k in line for k in ["평점", "취득", "총점", "신청", "년", "학기", "KT", "SKT"]):
                continue

            # 패턴: (과목명) ... (학점 숫자: 0.5 ~ 9.0 허용)
            # 수정된 정규식: 0.5도 잡을 수 있게 (\d+(?:\.\d+)?) 사용
            match = re.search(r'^(.*?)\s+(\d+(?:\.\d+)?)(?:\s+.*)?$', line)
            
            if match:
                raw_name = match.group(1).strip()
                credit = float(match.group(2))
                
                # [강력 필터] 노이즈 제거
                # 1. 이름이 너무 짧거나(1글자), 숫자로만 구성됨
                if len(raw_name) < 2 or raw_name.isdigit(): continue
                # 2. 한글/영어가 없는 특수문자 덩어리
                if not re.search(r'[가-힣a-zA-Z]', raw_name): continue
                # 3. 성적(A, B, P)이나 잡음이 이름으로 인식된 경우 제외
                noise_keywords = ["At", "Bt", "Ap", "Ss", "BO", "Bo", "Pass", "P", "F", "NP"]
                if raw_name in noise_keywords: continue
                # 4. 이름이 3글자 이하 영어인데 소문자가 섞여있으면 잡음일 확률 높음 (예: "At a")
                if len(raw_name) <= 3 and re.search(r'[a-z]', raw_name): continue

                # 분류
                ftype = classify_course_keyword(raw_name, year, dept)
                
                parsed_data.append({
                    "과목명": raw_name,
                    "학점": credit,
                    "이수구분": ftype
                })
                    
        return text, parsed_data
    except Exception as e:
        return f"Error: {e}", []

def filter_failed_courses(full_text):
    lines = full_text.split('\n')
    filtered = []
    for line in lines:
        if re.search(r'\sF\s|\sF$|\sNP\s|\sNP$', line): continue
        filtered.append(line)
    return "\n".join(filtered)

@st.dialog("🐛 버그 신고")
def show_bug_report(year, dept):
    st.write("오류 내용을 복사해서 메일을 보내주세요.")
    st.code(f"받는사람: jaekwang1164@gmail.com\n제목: [버그] {year} {dept}")

# --- 사이드바 ---
with st.sidebar:
    st.header("⚙️ 설정")
    years = sorted([k for k in db.keys() if k != "area_courses"]) if db else ["2022"]
    selected_year = st.selectbox("입학년도", years)
    depts = list(db[selected_year].keys()) if selected_year in db else ["-"]
    selected_dept = st.selectbox("전공", depts)
    
    st.divider()
    st.info("💡 팁: '과목 수정/추가' 탭에서 인식된 과목을 엑셀처럼 수정할 수 있습니다.")
    
    if st.button("🔄 초기화"):
        st.session_state.ocr_results = []
        st.rerun()

    st.divider()
    if st.button("📧 오류 신고"): show_bug_report(selected_year, selected_dept)

# --- 메인 화면 ---
st.title("🎓 연세대 졸업요건 진단기")

# 탭 구성
tab1, tab2, tab3 = st.tabs(["📄 PDF 업로드", "📸 이미지(캡쳐)", "✏️ 과목 수정/추가 (필수 확인)"])
extracted_text_pdf = ""

# 1. PDF 탭
with tab1:
    pdf_file = st.file_uploader("PDF 성적표", type="pdf")
    if pdf_file:
        with pdfplumber.open(pdf_file) as pdf:
            for p in pdf.pages: extracted_text_pdf += (p.extract_text() or "") + "\n"

# 2. 이미지 탭 (OCR)
with tab2:
    st.info("에브리타임/포털 성적 캡쳐 (여러 장 가능)")
    img_files = st.file_uploader("이미지 파일", type=['png','jpg'], accept_multiple_files=True)
    
    if img_files:
        # 이미지가 업로드되면 OCR 실행 (버튼 없이 자동 실행하되 중복 방지 필요)
        # 여기서는 매번 실행되지 않도록 버튼으로 제어하거나, 세션 스테이트 관리
        if st.button("🔍 이미지 분석 실행 (클릭)"):
            with st.spinner("이미지 정밀 분석 중..."):
                temp_results = []
                for img in img_files:
                    _, parsed = ocr_image_parsing(img, selected_year, selected_dept)
                    temp_results.extend(parsed)
                
                # 기존 데이터에 추가 (중복 방지 로직은 에디터에서 사용자가 보고 삭제하게 유도)
                st.session_state.ocr_results = temp_results
                st.success(f"{len(temp_results)}개 과목 인식 완료! '과목 수정/추가' 탭에서 확인하세요.")

# 3. 데이터 에디터 탭 (핵심 기능)
with tab3:
    st.markdown("### 📝 수강 과목 관리")
    st.caption("이미지 인식 결과가 정확하지 않다면 여기서 직접 수정, 추가, 삭제하세요. **이 데이터로 최종 진단합니다.**")
    
    # 데이터프레임 생성 (초기 데이터가 없으면 빈 프레임)
    if st.session_state.ocr_results:
        df_input = pd.DataFrame(st.session_state.ocr_results)
    else:
        df_input = pd.DataFrame(columns=["과목명", "학점", "이수구분"])

    # st.data_editor로 편집 가능한 테이블 생성
    edited_df = st.data_editor(
        df_input,
        num_rows="dynamic", # 행 추가/삭제 가능
        use_container_width=
