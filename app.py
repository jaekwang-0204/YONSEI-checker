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
    # 매칭률을 높이기 위해 특수문자와 공백을 완전히 제거
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', s).upper()

def classify_course_logic(course_name, year, dept):
    """이미지 분석 시 초기 분류"""
    norm_name = normalize_string(course_name)
    if "RC" in norm_name or "리더십" in norm_name: return "교양(리더십)"
    if year not in db or dept not in db[year]: return "교양/기타"
    
    known = db[year][dept].get("known_courses", {})
    # 전공 리스트에 포함되는지 확인
    for req in known.get("major_required", []):
        if normalize_string(req) in norm_name: return "전공필수"
    for sel in known.get("major_elective", []):
        if normalize_string(sel) in norm_name: return "전공선택"
    return "교양/기타"

def ocr_image_parsing(image_file, year, dept):
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
                if len(raw_name) < 2 or credit > 10: continue
                ftype = classify_course_logic(raw_name, year, dept)
                parsed_data.append({"과목명": raw_name, "학점": credit, "이수구분": ftype})
        return parsed_data
    except: return []

# --- 3. UI 구성 ---
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
    img_files = st.file_uploader("성적표 업로드", type=['png','jpg','jpeg'], accept_multiple_files=True)
    if img_files and st.button("🔍 분석 실행"):
        results = []
        for img in img_files:
            results.extend(ocr_image_parsing(img, selected_year, selected_dept))
        st.session_state.ocr_results = pd.DataFrame(results).drop_duplicates(subset=['과목명']).to_dict('records')
        st.success("분석 완료! 다음 탭에서 확인하세요.")

with tab2:
    st.markdown("### 📝 수강 과목 관리")
    df_editor = pd.DataFrame(st.session_state.ocr_results)
    if df_editor.empty: df_editor = pd.DataFrame(columns=["과목명", "학점", "이수구분"])
    
    # 💡 데이터 에디터 - 사용자가 수정하는 즉시 아래 결과에 반영됩니다.
    edited_df = st.data_editor(df_editor, num_rows="dynamic", use_container_width=True, key="main_editor")
    
    st.divider()
    final_courses = edited_df.to_dict('records')
    
    if final_courses:
        criteria = db[selected_year][selected_dept]
        known = criteria.get("known_courses", {})
        adv_keywords = [normalize_string(k) for k in known.get("advanced_keywords", [])]

        # 🚀 [가장 중요한 수정] 실시간 심화 판정 로직
        def is_advanced_final(course_obj):
            c_name_norm = normalize_string(str(course_obj['과목명']))
            c_type = str(course_obj['이수구분'])
            
            # 1. 사용자가 이수구분을 '전공'으로 설정했는지 확인 (실시간 수정 반영)
            if "전공" in c_type:
                # 2. 과목명에 심화 키워드가 하나라도 포함되어 있는지 확인
                for kw in adv_keywords:
                    if kw in c_name_norm:
                        return True
            return False

        # 학점 집계
        total_sum = sum(float(c['학점']) for c in final_courses if float(c['학점']) <= 10)
        maj_sum = sum(float(c['학점']) for c in final_courses if "전공" in str(c['이수구분']))
        advanced_sum = sum(float(c['학점']) for c in final_courses if is_advanced_final(c))
        
        # 리포트 출력
        st.header("🏁 졸업 자격 예비진단 리포트")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 취득학점", f"{int(total_sum)} / {criteria['total_credits']}")
        m2.metric("전공 합계", f"{int(maj_sum)} / {criteria['major_total']}")
        m3.metric("3~4000 단위(심화)", f"{int(advanced_sum)} / {criteria['advanced_course']}", 
                  delta=int(advanced_sum - criteria['advanced_course']), delta_color="normal")
        
        # 보완 가이드
        if advanced_sum < criteria['advanced_course']:
            with st.expander("🔴 3000~4000단위(심화) 추천 강의 리스트", expanded=True):
                st.info(f"심화 학점이 {int(criteria['advanced_course'] - advanced_sum)}학점 부족합니다.")
                all_majors = known.get('major_required', []) + known.get('major_elective', [])
                my_names = [normalize_string(str(c['과목명'])) for c in final_courses]
                # 수강하지 않은 심화 과목 필터링
                not_taken = [m for m in all_majors if any(kw in normalize_string(m) for kw in adv_keywords) 
                             and not any(normalize_string(m) in n or n in normalize_string(m) for n in my_names)]
                st.write(", ".join(sorted(list(set(not_taken)))))
    else:
        st.info("성적표를 업로드해주세요.")
