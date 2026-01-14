import streamlit as st
import re
import pandas as pd
import json
import pytesseract
from PIL import Image, ImageOps, ImageEnhance
import numpy as np

st.set_page_config(page_title="연세대 졸업예비진단", page_icon="🎓", layout="wide")

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

# --- 2. 헬퍼 함수 ---

def normalize_string(s):
    if not isinstance(s, str): return ""
    # 특수문자, 괄호, 공백을 모두 제거하여 비교 정확도 향상
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', s).upper()

def classify_course_logic(course_name, year, dept):
    """[분류 로직] 과목명 매칭을 통한 이수구분 자동 설정"""
    norm_name = normalize_string(course_name)
    if "RC" in norm_name or "리더십" in norm_name:
        return "교양(리더십)"
    if year not in db or dept not in db[year]:
        return "교양/기타"
    
    dept_db = db[year][dept]
    known = dept_db.get("known_courses", {})
    
    # 전공필수/선택 체크
    for req in known.get("major_required", []):
        if normalize_string(req) in norm_name: return "전공필수"
    for sel in known.get("major_elective", []):
        if normalize_string(sel) in norm_name: return "전공선택"
    
    # 교양 영역 체크
    for area, courses in db.get("area_courses", {}).items():
        for c in courses:
            if normalize_string(c) in norm_name: return f"교양({area})"
    return "교양/기타"

def ocr_image_parsing(image_file, year, dept):
    """이미지 OCR 파싱 및 비정상 데이터 필터링"""
    try:
        img = Image.open(image_file).convert('L')
        img = ImageOps.autocontrast(img)
        img = ImageEnhance.Contrast(img).enhance(2.0)
        text = pytesseract.image_to_string(img, lang='kor+eng', config='--psm 6')
        
        parsed_data = []
        for line in text.split('\n'):
            match = re.search(r'^(.*?)\s+(\d+(?:\.\d+)?)(?:\s+.*)?$', line.strip())
            if match:
                raw_name = match.group(1).strip()
                credit = float(match.group(2))
                # 학점 10점 초과(학번 등) 및 짧은 노이즈 제거
                if len(raw_name) < 2 or raw_name.isdigit() or credit > 10: continue
                ftype = classify_course_logic(raw_name, year, dept)
                parsed_data.append({"과목명": raw_name, "학점": credit, "이수구분": ftype})
        return parsed_data
    except: return []

# --- 3. 사이드바 및 메인 구성 ---
with st.sidebar:
    st.header("⚙️ 설정")
    years = sorted([k for k in db.keys() if k != "area_courses"]) if db else ["2022"]
    selected_year = st.selectbox("입학년도", years)
    selected_dept = st.selectbox("전공", list(db[selected_year].keys()) if selected_year in db else ["-"])
    if st.button("🔄 데이터 초기화"):
        st.session_state.ocr_results = []
        st.rerun()

st.title("🎓 연세대 졸업요건 예비진단")
tab1, tab2 = st.tabs(["📸 이미지 분석", "✏️ 과목 수정 및 최종 진단"])

with tab1:
    img_files = st.file_uploader("에타 성적표 캡쳐 업로드", type=['png','jpg','jpeg'], accept_multiple_files=True)
    if img_files and st.button("🔍 분석 실행"):
        results = []
        for img in img_files:
            results.extend(ocr_image_parsing(img, selected_year, selected_dept))
        st.session_state.ocr_results = pd.DataFrame(results).drop_duplicates(subset=['과목명']).to_dict('records')
        st.success("분석 완료! 다음 탭에서 결과를 확인하세요.")

with tab2:
    df_editor = pd.DataFrame(st.session_state.ocr_results)
    if df_editor.empty: df_editor = pd.DataFrame(columns=["과목명", "학점", "이수구분"])
    edited_df = st.data_editor(df_editor, num_rows="dynamic", use_container_width=True, key="main_editor")
    
    st.divider()
    final_courses = edited_df.to_dict('records')
    
    if final_courses:
        criteria = db[selected_year][selected_dept]
        gen = criteria.get("general_education", {})
        known = criteria.get("known_courses", {})
        
        # [사용자 제안 반영] 오로지 강의명 리스트로만 대조하는 논리
        # JSON에서 '심화 과목'으로 분류된 과목들의 이름만 추출하여 Set으로 만듭니다.
        # (JSON의 advanced_keywords는 이제 "이 과목이 심화인가?"를 판단하는 용도로만 내부적으로 사용)
        adv_patterns = known.get("advanced_keywords", [])
        all_majors = known.get('major_required', []) + known.get('major_elective', [])
        
        # 💡 요람(JSON) 내의 심화 과목 정규화 명칭 리스트
        standard_adv_names = [normalize_string(m) for m in all_majors if any(p in normalize_string(m) for p in adv_patterns)]

        def is_advanced_match(course_obj):
            c_name = normalize_string(course_obj['과목명'])
            c_type = str(course_obj['이수구분'])
            # 전공으로 분류된 과목 중, 이름이 JSON 심화 리스트에 있는가?
            if "전공" in c_type:
                # 1:1 매칭 또는 부분 포함 매칭
                return any(adv_n in c_name or c_name in adv_n for adv_n in standard_adv_names)
            return False

        # 학점 집계
        total_sum = sum(c['학점'] for c in final_courses if c['학점'] <= 10)
        maj_sum = sum(c['학점'] for c in final_courses if "전공" in str(c['이수구분']) and c['학점'] <= 10)
        advanced_sum = sum(c['학점'] for c in final_courses if is_advanced_match(c))
        leadership_count = len([c for c in final_courses if "리더십" in str(c['이수구분']) or "RC" in normalize_string(c['과목명'])])
        
        # 결과 리포트
        st.header("🏁 졸업 자격 예비진단 리포트")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 취득학점", f"{int(total_sum)} / {criteria['total_credits']}")
        m2.metric("전공 합계", f"{int(maj_sum)} / {criteria['major_total']}")
        m3.metric("3~4000 단위(심화)", f"{int(advanced_sum)} / {criteria['advanced_course']}", delta=int(advanced_sum - criteria['advanced_course']), delta_color="normal")
        m4.metric("리더십(RC)", f"{leadership_count} / 2")

        

        # 보완 가이드 (추천 강의 리스트 출력)
        if advanced_sum < criteria['advanced_course']:
            with st.expander("🔴 3000~4000단위(심화) 추천 강의 리스트", expanded=True):
                st.info(f"심화 학점이 {int(criteria['advanced_course'] - advanced_sum)}학점 부족합니다.")
                my_names = [normalize_string(c['과목명']) for c in final_courses]
                # JSON 심화 과목 중 내가 듣지 않은 것만 필터링
                not_taken = [m for m in all_majors if normalize_string(m) in standard_adv_names 
                             and not any(normalize_string(m) in n or n in normalize_string(m) for n in my_names)]
                st.write(", ".join(sorted(list(set(not_taken)))))
    else:
        st.info("이미지를 업로드하고 분석을 진행해 주세요.")
