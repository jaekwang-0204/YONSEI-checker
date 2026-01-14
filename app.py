import streamlit as st
import re
import pandas as pd
import json
import pytesseract
from PIL import Image, ImageOps, ImageEnhance
import numpy as np

st.set_page_config(page_title="연세대 졸업예비진단", page_icon="🎓", layout="wide")

if 'ocr_results' not in st.session_state:
    st.session_state.ocr_results = []

@st.cache_data
def load_requirements():
    try:
        with open('requirements.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError: return {}

db = load_requirements()

def normalize(s):
    if not s: return ""
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', str(s)).upper().strip()

# --- 이미지 분석 로직 ---
def ocr_image_parsing(image_file, year, dept):
    try:
        img = Image.open(image_file).convert('L')
        img = ImageOps.autocontrast(img)
        text = pytesseract.image_to_string(img, lang='kor+eng', config='--psm 6')
        results = []
        for line in text.split('\n'):
            match = re.search(r'^(.*?)\s+(\d+(?:\.\d+)?)(?:\s+.*)?$', line.strip())
            if match:
                name, credit = match.group(1).strip(), float(match.group(2))
                if len(name) < 2 or credit > 10: continue
                results.append({"과목명": name, "학점": credit, "이수구분": "전공선택"})
        return results
    except: return []

# --- UI 구성 ---
with st.sidebar:
    st.header("⚙️ 설정")
    years = sorted([k for k in db.keys() if k != "area_courses"]) if db else ["2022"]
    selected_year = st.selectbox("학번", years)
    selected_dept = st.selectbox("전공", list(db[selected_year].keys()) if selected_year in db else ["-"])
    if st.button("🔄 데이터 초기화"):
        st.session_state.ocr_results = []
        st.rerun()

st.title("🎓 연세대 졸업요건 예비진단")
tab1, tab2 = st.tabs(["📸 이미지 분석", "✏️ 과목 수정 및 최종 진단"])

with tab1:
    img_files = st.file_uploader("성적표 업로드", type=['png','jpg','jpeg'], accept_multiple_files=True)
    if img_files and st.button("🔍 분석 실행"):
        all_res = []
        for f in img_files: all_res.extend(ocr_image_parsing(f, selected_year, selected_dept))
        st.session_state.ocr_results = pd.DataFrame(all_res).drop_duplicates(subset=['과목명']).to_dict('records')
        st.success("분석 완료!")

with tab2:
    df_editor = pd.DataFrame(st.session_state.ocr_results)
    if df_editor.empty: df_editor = pd.DataFrame(columns=["과목명", "학점", "이수구분"])
    edited_df = st.data_editor(df_editor, num_rows="dynamic", use_container_width=True, key="main_editor")
    
    if not edited_df.empty:
        criteria = db[selected_year][selected_dept]
        known = criteria.get("known_courses", {})
        adv_kws = [normalize(k) for k in known.get("advanced_keywords", [])]
        
        # --- 🚀 사용자 제안: 강의수 기반 직접 합산 로직 ---
        total_credits = 0.0
        major_credits = 0.0
        advanced_course_count = 0  # 심화 강의 개수 카운트
        
        for _, row in edited_df.iterrows():
            name_raw = str(row['과목명'])
            name_norm = normalize(name_raw)
            credit = float(row['학점'])
            ftype = str(row['이수구분'])
            
            # 1. 총 취득학점 합산
            if credit <= 10: total_credits += credit
            
            # 2. 전공 및 심화 판정
            if "전공" in ftype:
                major_credits += credit
                # 키워드 매칭 시 강의 수 카운트 증가
                for kw in adv_kws:
                    if kw and kw in name_norm:
                        advanced_course_count += 1
                        break # 한 과목이 여러 키워드에 걸려도 1개로 처리

        # 💡 최종 심화 학점 = 강의 수 * 3
        final_advanced_credits = advanced_course_count * 3

        # 리포트 출력
        st.header("🏁 졸업 자격 예비진단 리포트")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 취득학점", f"{int(total_credits)} / {criteria['total_credits']}")
        m2.metric("전공 합계", f"{int(major_credits)} / {criteria['major_total']}")
        m3.metric("3~4000 단위(심화)", f"{int(final_advanced_credits)} / {criteria['advanced_course']}", 
                  delta=int(final_advanced_credits - criteria['advanced_course']), delta_color="normal")
        m4.metric("심화 강의 수", f"{advanced_course_count} 과목")

        # 보완 가이드 (추천 강의)
        if final_advanced_credits < criteria['advanced_course']:
            with st.expander("🔴 부족한 심화 과목 추천 리스트", expanded=True):
                all_majors = known.get('major_required', []) + known.get('major_elective', [])
                my_names = [normalize(n) for n in edited_df['과목명']]
                not_taken = [m for m in all_majors if any(kw in normalize(m) for kw in adv_kws) 
                             and not any(normalize(m)[:3] in mine for mine in my_names)]
                st.write(", ".join(sorted(list(set(not_taken)))))
