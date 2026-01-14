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
    if not s or not isinstance(s, str): return ""
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', s).upper()

def classify_course_logic(course_name, year, dept):
    norm_name = normalize_string(course_name)
    if not norm_name: return "교양/기타"
    if "RC" in norm_name or "리더십" in norm_name: return "교양(리더십)"
    if year not in db or dept not in db[year]: return "교양/기타"
    
    known = db[year][dept].get("known_courses", {})
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
                try:
                    credit = float(match.group(2))
                except: continue
                
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
    if df_editor.empty:
        df_editor = pd.DataFrame(columns=["과목명", "학점", "이수구분"])
    
    # 💡 데이터 에디터 - 수정 즉시 하단 결과에 반영
    edited_df = st.data_editor(df_editor, num_rows="dynamic", use_container_width=True, key="main_editor")
    
    st.divider()
    
    # --- [실시간 분석 엔진] ---
    if not edited_df.empty:
        criteria = db[selected_year][selected_dept]
        known = criteria.get("known_courses", {})
        # JSON의 심화 키워드를 대문자/특수문자 제거 상태로 리스트화
        adv_kws = [normalize_string(k) for k in known.get("advanced_keywords", [])]
        
        # 누계 변수 초기화
        current_total_credits = 0.0
        current_major_credits = 0.0
        current_advanced_credits = 0.0
        
        # 리스트를 직접 순회하며 즉시 합산 (타입 오류 원천 차단)
        for _, row in edited_df.iterrows():
            try:
                c_name = str(row['과목명'])
                c_credit = float(row['학점'])
                c_type = str(row['이수구분'])
                c_name_norm = normalize_string(c_name)
            except: continue
            
            # 1. 총 학점 (노이즈 필터링)
            if c_credit <= 10:
                current_total_credits += c_credit
            
            # 2. 전공 및 심화 학점 판정
            if "전공" in c_type:
                current_major_credits += c_credit
                # 심화 키워드 포함 여부 검사
                for kw in adv_kws:
                    if kw and kw in c_name_norm:
                        current_advanced_credits += c_credit
                        break # 중복 합산 방지

        # --- 리포트 출력 ---
        st.header("🏁 졸업 자격 예비진단 리포트")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 취득학점", f"{int(current_total_credits)} / {criteria['total_credits']}")
        m2.metric("전공 합계", f"{int(current_major_credits)} / {criteria['major_total']}")
        m3.metric("3~4000 단위(심화)", f"{int(current_advanced_credits)} / {criteria['advanced_course']}", 
                  delta=int(current_advanced_credits - criteria['advanced_course']), delta_color="normal")
        
        # 보완 가이드 (추천 강의)
        if current_advanced_credits < criteria['advanced_course']:
            with st.expander("🔴 3000~4000단위(심화) 추천 강의 리스트", expanded=True):
                st.info(f"심화 학점이 {int(criteria['advanced_course'] - current_advanced_credits)}학점 부족합니다.")
                all_majors = known.get('major_required', []) + known.get('major_elective', [])
                my_names_norm = [normalize_string(str(n)) for n in edited_df['과목명']]
                
                not_taken = []
                for m in all_majors:
                    m_norm = normalize_string(m)
                    # JSON 상에서 심화 과목인 것 중 내가 안 들은 것
                    if any(kw in m_norm for kw in adv_kws):
                        if not any(m_norm[:3] in mine for mine in my_names_norm):
                            not_taken.append(m)
                st.write(", ".join(sorted(list(set(not_taken)))))
    else:
        st.info("성적표를 업로드하거나 과목을 추가해주세요.")
