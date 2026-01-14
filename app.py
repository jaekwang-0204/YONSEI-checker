import streamlit as st
import pdfplumber
import re
import pandas as pd
import json
import pytesseract
from PIL import Image, ImageOps, ImageEnhance
import numpy as np
import difflib

# --- 설정 및 초기화 ---
st.set_page_config(page_title="졸업요건 진단기 (Ultimate)", page_icon="🎓", layout="wide")

if 'ocr_results' not in st.session_state:
    st.session_state.ocr_results = []

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
    line = re.sub(r'[~@#$%\^&*_\-=|;:"<>,.?/\[\]\{\}]', ' ', line)
    return line.strip()

def classify_course_keyword(course_name, year, dept):
    if year not in db or dept not in db[year]: return "교양"
    known = db[year][dept].get("known_courses", {})
    norm_input = normalize_string(course_name)
    
    for req in known.get("major_required", []):
        if normalize_string(req) in norm_input: return "전공필수"
    for sel in known.get("major_elective", []):
        if normalize_string(sel) in norm_input: return "전공선택"
    for area, courses in db.get("area_courses", {}).items():
        for c in courses:
            if normalize_string(c) in norm_input: return f"교양({area})"
    return "교양"

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
            line = clean_ocr_line(line)
            if not line: continue
            if not start_parsing:
                if any(k in line for k in ["과목명", "학점", "성적", "전공", "등급", "이수"]):
                    start_parsing = True
                continue
            if any(k in line for k in ["평점", "취득", "총점", "신청", "년", "학기", "KT", "SKT"]): continue

            # 0.5 학점 포함 패턴 인식
            match = re.search(r'^(.*?)\s+(\d+(?:\.\d+)?)(?:\s+.*)?$', line)
            if match:
                raw_name = match.group(1).strip()
                credit = float(match.group(2))
                if len(raw_name) < 2 or raw_name.isdigit(): continue
                if not re.search(r'[가-힣a-zA-Z]', raw_name): continue
                if raw_name in ["At", "Bt", "Ap", "Ss", "BO", "Bo", "Pass", "P", "F", "NP", "Total"]: continue
                if len(raw_name) <= 3 and re.search(r'[a-z]', raw_name): continue

                ftype = classify_course_keyword(raw_name, year, dept)
                parsed_data.append({"과목명": raw_name, "학점": credit, "이수구분": ftype})
        return text, parsed_data
    except Exception as e:
        return f"Error: {e}", []

def filter_failed_courses(full_text):
    lines = full_text.split('\n')
    filtered = [line for line in lines if not re.search(r'\sF\s|\sF$|\sNP\s|\sNP$', line)]
    return "\n".join(filtered)

# --- 사이드바 ---
with st.sidebar:
    st.header("⚙️ 설정")
    years = sorted([k for k in db.keys() if k != "area_courses"]) if db else ["2022"]
    selected_year = st.selectbox("입학년도", years)
    depts = list(db[selected_year].keys()) if selected_year in db else ["-"]
    selected_dept = st.selectbox("전공", depts)
    
    st.divider()
    if st.button("🔄 테이블 초기화"):
        st.session_state.ocr_results = []
        st.rerun()

# --- 메인 화면 ---
st.title("🎓 연세대 졸업요건 진단기")

tab1, tab2, tab3 = st.tabs(["📄 PDF 업로드", "📸 이미지(캡쳐)", "✏️ 과목 수정/삭제 (필수 확인)"])
extracted_text_pdf = ""

with tab1:
    pdf_file = st.file_uploader("PDF 성적표", type="pdf")
    if pdf_file:
        with pdfplumber.open(pdf_file) as pdf:
            for p in pdf.pages: extracted_text_pdf += (p.extract_text() or "") + "\n"

with tab2:
    st.info("에브리타임 캡쳐본을 업로드하세요.")
    img_files = st.file_uploader("이미지 파일", type=['png','jpg','jpeg'], accept_multiple_files=True)
    if img_files and st.button("🔍 이미지 분석 실행"):
        with st.spinner("이미지 분석 중..."):
            temp_results = []
            for img in img_files:
                _, parsed = ocr_image_parsing(img, selected_year, selected_dept)
                temp_results.extend(parsed)
            st.session_state.ocr_results = temp_results
            st.success("인식 완료! 다음 탭에서 확인하세요.")

with tab3:
    st.markdown("### 📝 수강 과목 관리")
    st.caption("잘못 인식된 행은 **가장 왼쪽 칸을 클릭 후 Delete키**로 삭제할 수 있습니다.")
    
    df_input = pd.DataFrame(st.session_state.ocr_results) if st.session_state.ocr_results else pd.DataFrame(columns=["과목명", "학점", "이수구분"])

    # 행 삭제/추가 기능을 지원하는 데이터 에디터
    edited_df = st.data_editor(
        df_input,
        num_rows="dynamic", # 이 옵션이 행 추가/삭제 버튼을 활성화함
        use_container_width=True,
        column_config={
            "과목명": st.column_config.TextColumn("과목명", required=True),
            "학점": st.column_config.NumberColumn("학점", min_value=0.0, max_value=20.0, step=0.5, format="%.1f"),
            "이수구분": st.column_config.SelectboxColumn(
                "이수구분",
                options=["전공필수", "전공선택", "교양", "교양(문학과예술)", "교양(인간과역사)", "교양(언어와표현)", "교양(가치와윤리)", "교양(국가와사회)", "교양(지역과세계)", "교양(논리와수리)", "교양(자연과우주)", "교양(생명과환경)", "교양(정보와기술)", "교양(체육과건강)", "기타"],
                required=True
            )
        },
        key="editor"
    )

# --- 분석 로직 ---
st.divider()
final_courses = edited_df.to_dict('records')
manual_text = "\n".join([c['과목명'] for c in final_courses if c['과목명']])
full_text = extracted_text_pdf + "\n" + manual_text

if full_text.strip():
    if selected_year not in db: st.stop()
    criteria = db[selected_year][selected_dept]
    clean_text = filter_failed_courses(full_text)
    
    # 학점 계산
    pdf_total = float((re.search(r'(?:취득학점|학점계)[:\s]*(\d{2,3})', clean_text) or [0,0])[1])
    pdf_req = float((re.search(r'전공필수[:\s]*(\d{1,3})', clean_text) or [0,0])[1])
    
    add_total = sum(c['학점'] for c in final_courses if c['학점'])
    add_req = sum(c['학점'] for c in final_courses if c['이수구분'] == '전공필수')
    add_sel = sum(c['학점'] for c in final_courses if c['이수구분'] == '전공선택')
    
    if pdf_total > 0:
        final_total, final_req, final_sel = pdf_total, pdf_req, sum(c['학점'] for c in final_courses if c['이수구분'] == '전공선택')
    else:
        final_total, final_req, final_sel = add_total, add_req, add_sel
    final_maj = final_req + final_sel

    # 교양 및 영역 체크
    gen = criteria.get("general_education", {})
    req_fail = [item['name'] for item in gen.get("required_courses", []) if not any(kw in clean_text for kw in item["keywords"])]
    
    my_area = {area for area in gen.get("required_areas", []) + gen.get("elective_areas", []) if area in clean_text}
    for c in final_courses:
        if "교양(" in c['이수구분']: my_area.add(c['이수구분'].replace("교양(", "").replace(")", ""))

    miss_req_area = set(gen.get("required_areas", [])) - my_area
    elec_cnt = len([a for a in my_area if a in gen.get("elective_areas", [])])
    elec_fail = max(0, gen["elective_min_count"] - elec_cnt)

    # UI 출력
    c1, c2 = st.columns(2)
    with c1: is_eng = st.checkbox("외국어 인증 완료", False)
    with c2: is_info = st.checkbox("정보 인증 완료", False)

    is_pass = all([final_total >= criteria['total_credits'], final_maj >= criteria['major_total'], final_req >= criteria['major_required'], not req_fail, not miss_req_area, elec_fail == 0, is_eng, is_info])

    if is_pass: st.success("🎉 졸업 가능합니다!"); st.balloons()
    else: st.error("⚠️ 졸업 요건이 부족합니다.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("총 학점", f"{int(final_total)} / {criteria['total_credits']}")
    m2.metric("전공 합계", f"{int(final_maj)} / {criteria['major_total']}")
    m3.metric("전공 필수", f"{int(final_req)} / {criteria['major_required']}")
    m4.metric("교양 영역", f"{elec_cnt} / {gen['elective_min_count']}")

    if not is_pass:
        with st.expander("🔎 상세 부족 요건 확인"):
            if final_total < criteria['total_credits']: st.write(f"학점: {int(criteria['total_credits']-final_total)} 부족")
            if req_fail: st.write(f"필수교양 미이수: {', '.join(req_fail)}")
            if miss_req_area: st.write(f"필수영역 미이수: {', '.join(miss_req_area)}")
            if elec_fail: st.write(f"선택교양 영역: {elec_fail}개 더 필요")
