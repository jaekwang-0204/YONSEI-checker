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
    # 특수문자 제거 및 대문자화
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', s).upper()

@st.dialog("🐛 버그 신고 및 문의")
def show_bug_report_dialog(year, dept):
    st.write("시스템 오류가 발생했나요? 아래 정보를 복사해서 메일을 보내주세요.")
    st.divider()
    st.caption("1. 받는 사람 이메일")
    st.code("jaekwang1164@gmail.com", language="text")
    st.caption("2. 메일 제목")
    st.code(f"[졸업진단기 버그신고] {year}학번 {dept}", language="text")
    st.caption("3. 본문 내용")
    st.code("- 오류 현상:\n- 기대 결과:\n- 첨부파일 여부(에타 캡쳐본 등):", language="text")

def classify_course_logic(course_name, year, dept):
    """[분류 로직] RC 우선 및 DB 키워드 매칭"""
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
    """이미지 전처리 및 OCR 파싱"""
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
                # 학점이 10점을 넘으면(학번 등) 노이즈로 간주하여 제외
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
    
    st.divider()
    if st.button("🔄 모든 데이터 초기화"):
        st.session_state.ocr_results = []
        st.rerun()
    
    if st.button("🐛 버그 신고"):
        show_bug_report_dialog(selected_year, selected_dept)

# --- 4. 메인 UI ---
st.title("🎓 연세대 졸업요건 예비진단")
st.info("에브리타임 성적 화면(학점계산기) 캡쳐본을 업로드해주세요. 여러 장 업로드 시 모든 학기를 통합 분석합니다.")

tab1, tab2 = st.tabs(["📸 이미지 분석", "✏️ 과목 수정 및 최종 진단"])

with tab1:
    img_files = st.file_uploader("에브리타임 성적 캡쳐 (PNG, JPG)", type=['png','jpg','jpeg'], accept_multiple_files=True)
    if img_files and st.button("🔍 성적표 분석 실행"):
        with st.spinner("이미지에서 수강 정보를 추출하는 중..."):
            all_results = []
            for img in img_files:
                all_results.extend(ocr_image_parsing(img, selected_year, selected_dept))
            
            df_temp = pd.DataFrame(all_results).drop_duplicates(subset=['과목명'])
            st.session_state.ocr_results = df_temp.to_dict('records')
            st.success(f"총 {len(st.session_state.ocr_results)}개의 과목을 인식했습니다.")

with tab2:
    st.markdown("### 📝 수강 과목 관리")
    st.caption("OCR 인식 결과가 틀렸다면 직접 수정하세요. 이수구분이 '전공'으로 되어야 심화 학점에 집계됩니다.")
    
    df_editor = pd.DataFrame(st.session_state.ocr_results)
    if df_editor.empty:
        df_editor = pd.DataFrame(columns=["과목명", "학점", "이수구분"])

    edited_df = st.data_editor(
        df_editor, num_rows="dynamic", use_container_width=True,
        column_config={
            "학점": st.column_config.NumberColumn("학점", step=0.5, format="%.1f"),
            "이수구분": st.column_config.SelectboxColumn("이수구분", options=[
                "전공필수", "전공선택", "교양(리더십)", "교양(문학과예술)", "교양(인간과역사)", 
                "교양(언어와표현)", "교양(가치와윤리)", "교양(국가와사회)", "교양(지역과세계)", 
                "교양(논리와수리)", "교양(자연과우주)", "교양(생명과환경)", "교양(정보와기술)", 
                "교양(체육과건강)", "교양/기타"
            ])
        }, key="main_editor"
    )

    # --- 5. 최종 분석 결과 표시 및 보완 가이드 ---
    st.divider()
    final_courses = edited_df.to_dict('records')
    
    if final_courses:
        criteria = db[selected_year][selected_dept]
        gen = criteria.get("general_education", {})
        known = criteria.get("known_courses", {})
        
        # JSON 데이터 확보
        all_major_list = known.get('major_required', []) + known.get('major_elective', [])
        adv_patterns = known.get("advanced_keywords", [])

        # [핵심] 유연한 심화 학점 판정 함수 (앞글자 4자 매칭)
        def get_advanced_score_flexible(course):
            c_name_norm = normalize_string(str(course['과목명']))
            c_type = str(course['이수구분'])
            c_credit = float(course['학점'])
            
            # 학점이 비정상적이면 제외
            if c_credit > 10: return 0
            
            if "전공" in c_type:
                # 1. 과목명에 직접 심화 키워드(BML3 등)가 포함된 경우
                if any(kw in c_name_norm for kw in adv_patterns):
                    return c_credit
                
                # 2. JSON 전공 리스트와 앞 4글자 매칭
                for major_name in all_major_list:
                    major_norm = normalize_string(major_name)
                    # JSON상의 과목이 심화 과목인지 확인 후, 앞 4글자 일치 여부 판정
                    if any(kw in major_norm for kw in adv_patterns):
                        if (len(major_norm) >= 4 and major_norm[:4] in c_name_norm) or (major_norm in c_name_norm):
                            return c_credit
            return 0

        # 학점 합계 (필터링 적용)
        total_sum = sum(c['학점'] for c in final_courses if c['학점'] <= 10)
        maj_total_sum = sum(c['학점'] for c in final_courses if "전공" in str(c['이수구분']) and c['학점'] <= 10)
        advanced_sum = sum(get_advanced_score_flexible(c) for c in final_courses)
        
        # 리더십 및 영역 분석
        leadership_count = len([c for c in final_courses if "리더십" in str(c['이수구분']) or "RC" in normalize_string(str(c['과목명']))])
        
        passed_areas = set()
        for course in final_courses:
            course_norm = normalize_string(str(course['과목명']))
            for area, area_course_list in db.get("area_courses", {}).items():
                if any(normalize_string(ac) in course_norm for ac in area_course_list):
                    passed_areas.add(area)
        
        missing_areas = sorted(list(set(gen.get("required_areas", [])) - passed_areas))

        # 최종 판정
        is_all_pass = all([total_sum >= criteria['total_credits'], advanced_sum >= criteria['advanced_course'], not missing_areas])

        st.header("🏁 졸업 자격 예비진단 리포트")
        if is_all_pass: st.success("🎉 모든 졸업 요건을 충족했습니다."); st.balloons()
        else: st.error("⚠️ 아직 충족되지 않은 요건이 있습니다.")

        # 대시보드 (4열)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 취득학점", f"{int(total_sum)} / {criteria['total_credits']}", delta=int(total_sum - criteria['total_credits']))
        m2.metric("전공 합계", f"{int(maj_total_sum)} / {criteria['major_total']}")
        m3.metric("3~4000 단위(심화)", f"{int(advanced_sum)} / {criteria['advanced_course']}", delta=int(advanced_sum - criteria['advanced_course']), delta_color="normal")
        m4.metric("리더십(RC)", f"{leadership_count} / 2")

        

        # 보완 가이드
        if not is_all_pass:
            st.markdown("### 💡 부족 요건 보완 가이드")
            if advanced_sum < criteria['advanced_course']:
                with st.expander("🔴 3000~4000단위(심화) 추천 강의 리스트", expanded=True):
                    st.info(f"심화 학점이 {int(criteria['advanced_course'] - advanced_sum)}학점 부족합니다.")
                    adv_candidates = [m for m in all_major_list if any(kw in normalize_string(m) for kw in adv_patterns)]
                    my_norms = [normalize_string(c['과목명']) for c in final_courses]
                    not_taken = [m for m in adv_candidates if not any(normalize_string(m)[:4] in n for n in my_norms)]
                    st.write(", ".join(sorted(list(set(not_taken)))))

            if missing_areas:
                with st.expander("🟠 부족한 교양 이수 영역 추천 강의", expanded=True):
                    for area in missing_areas:
                        st.subheader(f"📍 {area} 영역")
                        st.write(", ".join(db.get("area_courses", {}).get(area, [])))
            
        with st.expander("📊 수강 과목 상세 통계"):
            st.dataframe(pd.DataFrame(final_courses), use_container_width=True)
    else:
        st.info("성적표 이미지를 업로드하고 분석 버튼을 눌러주세요.")
