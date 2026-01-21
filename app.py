import streamlit as st
import re
import pandas as pd
import json
import pytesseract
from PIL import Image, ImageOps, ImageEnhance
import numpy as np

# --- 0. 페이지 설정 ---
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
    except FileNotFoundError:
        return {}

db = load_requirements()

# --- 2. 헬퍼 함수 ---
def normalize_string(s):
    if not isinstance(s, str): return ""
    # 특수문자 제거 및 대문자화 (매칭 정확도 향상)
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', s).upper()

@st.dialog("🐛 버그 신고 및 문의")
def show_bug_report_dialog(year_key, dept):
    st.write("시스템 오류가 발생했나요? 아래 정보를 복사해서 메일을 보내주세요.")
    st.divider()
    st.caption("1. 받는 사람 이메일")
    st.code("jaekwang1164@gmail.com", language="text")
    st.caption("2. 메일 제목")
    st.code(f"[졸업진단기 버그신고] {year_key} {dept}", language="text")
    st.caption("3. 본문 내용")
    st.code("- 오류 현상:\n- 기대 결과:\n- 첨부파일 여부(에타 캡쳐본 등):", language="text")

def classify_course_logic(course_name, year_key, dept):
    """이미지 분석 시 초기 분류 로직"""
    norm_name = normalize_string(course_name)
    
    # 1. RC 및 리더십 특별 처리
    if "RC" in norm_name or "리더십" in norm_name:
        return "교양(리더십)"

    if year_key not in db or dept not in db[year_key]:
        return "교양/기타"
    
    dept_db = db[year_key][dept]
    known = dept_db.get("known_courses", {})
    
    # 2. 전공 필수/선택 체크
    for req in known.get("major_required", []):
        if normalize_string(req) in norm_name: return "전공필수"
    for sel in known.get("major_elective", []):
        if normalize_string(sel) in norm_name: return "전공선택"
            
    # 3. 교양 영역 체크
    for area, courses in db.get("area_courses", {}).items():
        for c in courses:
            if normalize_string(c) in norm_name: return f"교양({area})"
                
    return "교양/기타"

def ocr_image_parsing(image_file, year_key, dept):
    """이미지 전처리 및 OCR 파싱 (인식률 및 속도 최적화)"""
    try:
        img = Image.open(image_file).convert('L')
        # 해상도 최적화 (1500px 기준)
        if img.width > 1500:
            ratio = 1500 / float(img.width)
            new_height = int(float(img.height) * ratio)
            img = img.resize((1500, new_height), Image.Resampling.LANCZOS)
            
        img = ImageEnhance.Sharpness(img).enhance(2.0)
        img = ImageOps.autocontrast(img)
        img = ImageEnhance.Contrast(img).enhance(2.5)
        
        # PSM 6: 단일 텍스트 블록 가정, OEM 3: 기본 엔진
        custom_config = '--psm 6 --oem 3'
        text = pytesseract.image_to_string(img, lang='kor+eng', config=custom_config)
        
        parsed_data = []
        for line in text.split('\n'):
            # 패턴: (강의명) (학점) 순서
            match = re.search(r'^(.*?)\s+(\d+(?:\.\d+)?)(?:\s+.*)?$', line.strip())
            if match:
                raw_name = match.group(1).strip()
                try:
                    credit = float(match.group(2))
                except: continue
                
                # 학점 컷오프 및 노이즈 필터링
                if credit <= 0 or credit > 5.0: continue
                if len(raw_name) < 2 or raw_name.isdigit(): continue
                
                ftype = classify_course_logic(raw_name, year_key, dept)
                parsed_data.append({"강의명": raw_name, "학점": credit, "이수구분": ftype})
        return parsed_data
    except: return []

# --- 3. 사이드바 구성 ---
with st.sidebar:
    st.header("⚙️ 설정")
    all_keys = [k for k in db.keys() if k != "area_courses"]
    if not all_keys:
        st.error("requirements.json 데이터가 없습니다.")
        st.stop()

    # 1. 입학연도 숫자 추출 (내림차순 정렬)
    years_only = sorted(list(set([re.sub(r'\(.*?\)', '', k) for k in all_keys])), reverse=True)
    selected_year_num = st.selectbox("📅 입학년도 선택", years_only)

    # 2. 졸업 기준 텍스트 추출 및 매핑
    relevant_full_keys = [k for k in all_keys if k.startswith(selected_year_num)]
    
    def extract_version_text(full_key):
        match = re.search(r'\((.*?)\)', full_key)
        return match.group(1) if match else "기본 기준"
        
    version_map = {extract_version_text(k): k for k in relevant_full_keys}
    selected_version_text = st.selectbox("📋 졸업 판정 기준", list(version_map.keys()))
    selected_full_key = version_map[selected_version_text]
    
    # 3. 전공 선택
    dept_options = list(db[selected_full_key].keys()) if selected_full_key in db else ["-"]
    selected_dept = st.selectbox("🎓 전공", dept_options)
    
    st.divider()
    if st.button("🔄 모든 데이터 초기화"):
        st.session_state.ocr_results = []
        st.rerun()
    
    if st.button("🐛 버그 신고"):
        show_bug_report_dialog(selected_full_key, selected_dept)

# --- 4. 메인 UI ---
st.title("🎓 연세대 임상병리학과 졸업요건 예비진단")
st.info("에브리타임 학점계산기 캡쳐본을 업로드해주세요.")

tab1, tab2 = st.tabs(["📸 이미지 분석", "✏️ 강의 수정 및 최종 진단"])

with tab1:
    img_files = st.file_uploader("에브리타임 성적 이미지 업로드 (PNG, JPG)", type=['png','jpg','jpeg'], accept_multiple_files=True)
    if img_files and st.button("🔍 성적 이미지 분석 실행"):
        all_results = []
        with st.spinner(f"{len(img_files)}장의 이미지를 순차 분석 중..."):
            for img in img_files: 
                result = ocr_image_parsing(img, selected_full_key, selected_dept)
                all_results.extend(result)
            
            if all_results:
                df_all = pd.DataFrame(all_results)
                # 채플 중복 유지, 나머지 과목 중복 제거
                is_chapel = df_all['강의명'].apply(lambda x: "채플" in x)
                df_chapel = df_all[is_chapel]
                df_others = df_all[~is_chapel].drop_duplicates(subset=['강의명'])
                df_final = pd.concat([df_chapel, df_others], ignore_index=True)
                
                st.session_state.ocr_results = df_final.to_dict('records')
                st.success(f"분석 완료! {len(st.session_state.ocr_results)}개의 강의를 인식했습니다. '강의 수정' 탭으로 이동하세요.")
                st.rerun()

with tab2:
    st.markdown("### 📝 수강 강의 관리")
    
    # 가이드 이미지 출력
    img_path = f"images/{selected_full_key}_{selected_dept}.png"
    try:
        st.image(Image.open(img_path), caption=f"📖 {selected_full_key} 가이드", use_container_width=True)
    except FileNotFoundError:
        try:
            basic_path = f"images/{selected_year_num}_{selected_dept}.png"
            st.image(Image.open(basic_path), caption=f"📖 {selected_year_num} 가이드", use_container_width=True)
        except:
            st.caption("ℹ️ 해당 기준의 가이드 이미지가 폴더에 없습니다.")

    st.divider()
    df_editor = pd.DataFrame(st.session_state.ocr_results)
    if df_editor.empty:
        df_editor = pd.DataFrame(columns=["강의명", "학점", "이수구분"])

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

    st.divider()
    final_courses = edited_df.to_dict('records')
    
    if final_courses:
        criteria = db[selected_full_key][selected_dept]
        gen = criteria.get("general_education", {})
        known = criteria.get("known_courses", {})
        
        # 1. 학점 계산 로직
        total_sum = sum(c['학점'] for c in final_courses)
        maj_req = sum(c['학점'] for c in final_courses if c['이수구분'] == "전공필수")
        maj_sel = sum(c['학점'] for c in final_courses if c['이수구분'] == "전공선택")
        maj_total_sum = maj_req + maj_sel

        # 2. 심화전공(3~4천단위) 판정 로직
        adv_keywords = [normalize_string(kw) for kw in known.get("advanced_keywords", [])]
        advanced_sum = 0.0
        detected_advanced = []

        for row in final_courses:
            c_name = str(row['강의명']).strip()
            c_type = str(row['이수구분']).strip()
            c_credit = float(row['학점'])
            norm_name = normalize_string(c_name)
            
            is_advanced_by_key = any(kw in norm_name for kw in adv_keywords)
            is_major = "전공" in c_type
            
            # 기초 전공 제외 리스트
            basic_list = ["인체해부학", "의학용어", "해부학", "세포생물학", "병리학", "미생물학"]
            is_exactly_basic = any(c_name == basic for basic in basic_list) or (c_name == "조직학")
            
            # 심화 판정 보강 (진단/실험/종합설계 등)
            is_advanced_work = any(word in c_name for word in ["진단", "실험", "종합설계", "특론"])
            is_basic = is_exactly_basic and not is_advanced_work
            
            if is_advanced_by_key or (is_major and not is_basic):
                advanced_sum += c_credit
                detected_advanced.append(c_name)
            
        # 3. 필수 요건 체크 (리더십, 교양, 전공필수 개별 과목)
        leadership_count = len([c for c in final_courses if "리더십" in str(c['이수구분']) or "RC" in normalize_string(c['강의명'])])
        search_names_combined = " ".join([c['강의명'] for c in final_courses])
        req_fail = []

        # 3-1. 전공필수 개별 과목 이수 체크 (삭제 테스트 대응)
        for mr_course in known.get("major_required", []):
            if not any(normalize_string(mr_course) in normalize_string(c['강의명']) for c in final_courses):
                req_fail.append(f"전공필수({mr_course})")

        # 3-2. 필수교양 영역 및 과목 체크
        for item in gen.get("required_courses", []):
            if item['name'] == "리더십":
                if leadership_count < 2: req_fail.append("리더십(RC) 2과목")
            elif not any(normalize_string(kw) in normalize_string(search_names_combined) for kw in item["keywords"]):
                req_fail.append(item['name'])

        # 4. 최종 판정 로직
        pass_total = total_sum >= criteria['total_credits']
        pass_major_total = maj_total_sum >= criteria['major_total']
        pass_major_req = maj_req >= criteria['major_required']
        pass_advanced = advanced_sum >= criteria['advanced_course']
        pass_req_courses = len(req_fail) == 0
        
        is_all_pass = all([pass_total, pass_major_total, pass_major_req, pass_advanced, pass_req_courses])

        # 5. 결과 리포트 출력
        st.info("ℹ️ 본 진단 결과는 참고용이며, 정확한 졸업 여부는 학과 사무실을 통해 최종확인하시기 바랍니다.")
        st.header("🏁 졸업 자격 예비진단 리포트")
        
        if is_all_pass:
            st.success("🎉 축하합니다! 현재 모든 요건을 충족했습니다."); st.balloons()
        else:
            st.error("⚠️ 아직 충족되지 않은 요건이 있습니다. 아래 내용을 확인하세요.")

        if detected_advanced:
            st.info(f"✅ **심화 판정된 강의:** {', '.join(set(detected_advanced))}")
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 취득학점", f"{int(total_sum)} / {criteria['total_credits']}", delta=int(total_sum - criteria['total_credits']))
        m2.metric("전공 합계", f"{int(maj_total_sum)} / {criteria['major_total']}")
        m3.metric("심화전공", f"{int(advanced_sum)} / {criteria['advanced_course']}")
        m4.metric("리더십(RC)", f"{leadership_count} / 2")

        if not is_all_pass:
            with st.expander("🛠️ 세부 보완 필요 사항", expanded=True):
                if not pass_major_req:
                    st.warning(f"📍 **전공필수 학점**이 {int(criteria['major_required'] - maj_req)}학점 부족합니다.")
                if not pass_advanced:
                    st.warning(f"📍 **심화전공 학점**이 {int(criteria['advanced_course'] - advanced_sum)}학점 부족합니다.")
                if req_fail:
                    st.error(f"📍 **미이수 필수 요건:** {', '.join(req_fail)}")
        
        with st.expander("📊 수강 강의 상세 통계"):
            st.dataframe(pd.DataFrame(final_courses), use_container_width=True)
    else:
        st.info("성적표 이미지를 업로드하고 분석 버튼을 눌러주세요.")
