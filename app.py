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
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', s).upper()

def classify_course_logic(course_name, year, dept):
    norm_name = normalize_string(course_name)
    if "RC" in norm_name or "리더십" in norm_name:
        return "교양(리더십)"
    if year not in db or dept not in db[year]:
        return "교양/기타"
    
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
                if len(raw_name) < 2 or raw_name.isdigit() or credit > 10: continue
                ftype = classify_course_logic(raw_name, year, dept)
                parsed_data.append({"과목명": raw_name, "학점": credit, "이수구분": ftype})
        return parsed_data
    except: return []

# --- 3. 사이드바 구성 ---
with st.sidebar:
    st.header("⚙️ 설정")
    years = sorted([k for k in db.keys() if k != "area_courses"]) if db else ["2022"]
    selected_year = st.selectbox("입학년도", years)
    selected_dept = st.selectbox("전공", list(db[selected_year].keys()) if selected_year in db else ["-"])
    if st.button("🔄 모든 데이터 초기화"):
        st.session_state.ocr_results = []
        st.rerun()

# --- 4. 메인 UI ---
st.title("🎓 연세대 졸업요건 예비진단")
tab1, tab2 = st.tabs(["📸 이미지 분석", "✏️ 과목 수정 및 최종 진단"])

with tab1:
    img_files = st.file_uploader("에브리타임 성적 캡쳐 업로드", type=['png','jpg','jpeg'], accept_multiple_files=True)
    if img_files and st.button("🔍 성적표 분석 실행"):
        all_results = []
        for img in img_files:
            all_results.extend(ocr_image_parsing(img, selected_year, selected_dept))
        st.session_state.ocr_results = pd.DataFrame(all_results).drop_duplicates(subset=['과목명']).to_dict('records')
        st.success(f"총 {len(st.session_state.ocr_results)}개의 과목을 인식했습니다.")

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
        all_major_list = known.get('major_required', []) + known.get('major_elective', [])
        adv_patterns = [normalize_string(p) for p in known.get("advanced_keywords", [])]

        # [핵심 수정] 심화 학점 판정 함수 (매우 유연한 매칭)
        def get_advanced_score_final(course):
            c_name = normalize_string(course['과목명'])
            c_type = str(course['이수구분'])
            c_credit = float(course['학점'])
            
            if "전공" in c_type:
                # 1. 과목명에 BML3, 3000 등이 직접 포함된 경우
                if any(p in c_name for p in adv_patterns): return c_credit
                # 2. JSON 전공 리스트 중 하나라도 과목명에 포함되거나 앞 3자가 일치하는 경우
                for m in all_major_list:
                    m_norm = normalize_string(m)
                    # JSON상의 과목이 심화 과목일 때만 체크
                    if any(p in m_norm for p in adv_patterns):
                        if m_norm[:3] in c_name or c_name in m_norm: return c_credit
            return 0

        # 결과 집계
        total_sum = sum(c['학점'] for c in final_courses if c['학점'] <= 10)
        maj_sum = sum(c['학점'] for c in final_courses if "전공" in str(c['이수구분']) and c['학점'] <= 10)
        advanced_sum = sum(get_advanced_score_final(c) for c in final_courses)
        leadership_count = len([c for c in final_courses if "리더십" in str(c['이수구분']) or "RC" in normalize_string(c['과목명'])])
        
        # 교양 영역 체크
        passed_areas = set()
        for c in final_courses:
            for area, area_list in db.get("area_courses", {}).items():
                if any(normalize_string(ac) in normalize_string(c['과목명']) for ac in area_list): passed_areas.add(area)
        missing_areas = sorted(list(set(gen.get("required_areas", [])) - passed_areas))

        # 리포트 출력
        st.header("🏁 졸업 자격 예비진단 리포트")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 취득학점", f"{int(total_sum)} / {criteria['total_credits']}")
        m2.metric("전공 합계", f"{int(maj_sum)} / {criteria['major_total']}")
        m3.metric("3~4000 단위(심화)", f"{int(advanced_sum)} / {criteria['advanced_course']}", delta=int(advanced_sum - criteria['advanced_course']), delta_color="normal")
        m4.metric("리더십(RC)", f"{leadership_count} / 2")

        

        if not (total_sum >= criteria['total_credits'] and advanced_sum >= criteria['advanced_course'] and not missing_areas):
            st.markdown("### 💡 부족 요건 보완 가이드")
            if advanced_sum < criteria['advanced_course']:
                with st.expander("🔴 3000~4000단위(심화) 추천 강의 리스트", expanded=True):
                    adv_candidates = [m for m in all_major_list if any(p in normalize_string(m) for p in adv_patterns)]
                    my_names = [normalize_string(c['과목명']) for c in final_courses]
                    not_taken = [m for m in adv_candidates if not any(normalize_string(m)[:3] in n for n in my_names)]
                    st.write(", ".join(sorted(list(set(not_taken)))))
            if missing_areas:
                with st.expander("🟠 부족한 교양 이수 영역 추천 강의", expanded=True):
                    for area in missing_areas:
                        st.subheader(f"📍 {area} 영역")
                        st.write(", ".join(db.get("area_courses", {}).get(area, [])))
    else:
        st.info("성적표 이미지를 업로드해주세요.")
