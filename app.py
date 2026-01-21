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

    # 1. RC 특별 처리 (리더십으로 분류)
    if "RC" in norm_name or "리더십" in norm_name:
        return "교양(리더십)"

    if year not in db or dept not in db[year]:
        return "교양/기타"

    dept_db = db[year][dept]
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

def ocr_image_parsing(image_file, year, dept):
    """이미지 전처리 및 OCR 파싱"""
    try:
        # 이미지 로드 및 이진화
        img = Image.open(image_file).convert('L')

        # 이미지 리사이징: 1500px
        if img.width > 1500:
            ratio = 1500 / float(img.width)
            new_height = int(float(img.height) * ratio)
            img = img.resize((1500, new_height), Image.Resampling.LANCZOS)

        # 이미지 전처리
        img = ImageEnhance.Sharpness(img).enhance(2.0) #선명도 상향
        img = ImageOps.autocontrast(img)
        img = ImageEnhance.Contrast(img).enhance(2.5) #대비 상향

        # OCR 설정 최적화
        # [최적화] 인식 범위를 화이트리스트로 제한하여 속도 향상
        custom_config = '--psm 6 --oem 3'
        text = pytesseract.image_to_string(img, lang='kor+eng', config=custom_config)

        parsed_data = []
        for line in text.split('\n'):
            # 패턴: (강의명) (학점) 순서
            match = re.search(r'^(.*?)\s+(\d+(?:\.\d+)?)(?:\s+.*)?$', line.strip())
            if match:
                raw_name = match.group(1).strip()
                credit = float(match.group(2))

                # 노이즈 필터링 (너무 짧거나 숫자만 있는 경우 제외)
                if credit < 0 or credit > 5.0: continue
                if len(raw_name) < 2 or raw_name.isdigit(): continue

                ftype = classify_course_logic(raw_name, year, dept)
                parsed_data.append({"강의명": raw_name, "학점": credit, "이수구분": ftype})
        return parsed_data
    except: return []

# --- 3. 사이드바 구성 ---
with st.sidebar:
    st.header("⚙️ 설정")
    
    if db:
        # 1. 'area_courses'를 제외한 JSON의 모든 원본 키를 가져옵니다.
        # 예: ["2019(졸업요건 기준)", "2019(진단세포학 임시삭제)", "2020(졸업요건 기준)", ...]
        all_origin_keys = [k for k in db.keys() if k != "area_courses"]
            
        # 2. 1단계: 화면에 보여줄 '숫자 학번'만 추출하여 정렬합니다.
        years_display = sorted(list(set([k.split('(')[0] for k in all_origin_keys])), reverse=True)
            
        # [위젯 1] 입학년도 선택 (예: 2020)
        selected_year_num = st.selectbox("1️⃣ 입학년도 선택", years_display, key="v_year_num")
        
        # 3. 2단계: 선택된 숫자(예: 2020)로 시작하는 '원본 키'들만 필터링합니다.
        # 여기서 ["2020(졸업요건 기준)", "2020(진단세포학 임시삭제)"]가 정확히 추출됩니다.
        available_versions = sorted([k for k in all_origin_keys if k.startswith(selected_year_num)])
        
        # [위젯 2] 세부 판정 기준 선택
        # 필터링된 원본 키 리스트를 그대로 사용하므로 '숫자'만 뜨는 현상이 해결됩니다.
        selected_full_key = st.selectbox(
            "2️⃣ 세부 판정 기준", 
            available_versions,
            key="v_full_key"
        )
        
        # 분석 로직에서 사용할 최종 키값 확정
        selected_year = selected_full_key
        
        # 4. 3단계: 전공 선택 (2차원 매핑: db[버전키][전공키])
        if selected_year in db:
            dept_options = list(db[selected_year].keys())
            selected_dept = st.selectbox("3️⃣ 전공 선택", dept_options, key="v_dept")
        else:
            selected_dept = "-"
            
    else:
        st.error("requirements.json 로드 실패")
        selected_year, selected_dept = "2025", "-"

    st.divider()
    if st.button("🔄 모든 데이터 초기화"):
        st.session_state.ocr_results = []
        st.rerun()

    if st.button("🐛 버그 신고"):
        show_bug_report_dialog(selected_year, selected_dept)

# --- 4. 메인 UI ---
st.title("🎓 연세대 임상병리학과 졸업요건 예비진단")
st.info("에브리타임 학점계산기(성적 화면) 캡쳐본을 업로드해주세요. 여러 장 업로드 시 모든 학기를 통합 분석합니다.")

tab1, tab2 = st.tabs(["📸 이미지 분석", "✏️ 강의 수정 및 최종 진단"])

with tab1:
    img_files = st.file_uploader("에브리타임 학점계산기 캡쳐 이미지 (PNG, JPG)", type=['png','jpg','jpeg'], accept_multiple_files=True)
    if img_files and st.button("🔍 성적 이미지지 분석 실행"):
        all_results = []

        with st.spinner(f"총 {len(img_files)}장의 이미지를 분석 중입니다..."):
            for img in img_files: 
                result = ocr_image_parsing(img, selected_year, selected_dept)
                all_results.extend(result)

            # 강의명 기준 중복 제거 및 세션 상태 저장
            if all_results:
                df_all = pd.DataFrame(all_results)

                # 1. "채플"이 포함된 행들만 따로 추출 (중복 제거 제외 대상)
                # normalize_string을 사용하여 '채플', '채플(1)' 등을 모두 잡습니다.
                is_chapel = df_all['강의명'].apply(lambda x: "채플" in x)
                df_chapel = df_all[is_chapel]

                # 2. 채플이 아닌 나머지 강의들만 추출하여 중복 제거 수행
                df_others = df_all[~is_chapel].drop_duplicates(subset=['강의명'])

                # 3. 두 데이터프레임을 다시 합치기
                df_final = pd.concat([df_chapel, df_others], ignore_index=True)

                # 세션 상태에 저장
                st.session_state.ocr_results = df_final.to_dict('records')
                st.success(f"분석 완료! 총 {len(st.session_state.ocr_results)}개의 강의을 인식했습니다. (채플 포함)")                

with tab2:
    st.markdown("### 📝 수강 강의 관리")

    # --- 교과과정 이미지 출력 로직 추가 ---
    img_path = f"images/{selected_year}_{selected_dept}.png"

    try:
        # 이미지를 불러와서 가이드로 표시
        guide_img = Image.open(img_path)
        st.image(guide_img, caption=f"📖 {selected_year}학번 {selected_dept} 교과과정 (전공 가이드)", use_container_width=True)    
    except FileNotFoundError:
        st.caption(f"ℹ️ {selected_year}학번 교과과정 이미지가 images 폴더에 없습니다. (파일명 예시: {selected_year}_{selected_dept}.png)")
    except Exception as e:
        st.caption("ℹ️ 교과과정(전공 가이드) 이미지를 불러오는 중 오류가 발생했습니다.")

    st.divider()
    st.caption("OCR 인식 결과(강의명, 학점, 이수구분 등)가 정확하지 않을 경우 수동으로 수정이 가능합니다. 행 왼쪽(체크박스)을 클릭하여 삭제하거나 하단에서 추가할 수 있습니다.")

    # 에디터용 데이터프레임 생성
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

    # --- 5. 최종 분석 결과 표시 (심화학점 포함) ---
    st.divider()
    final_courses = edited_df.to_dict('records')

    if final_courses:
        criteria = db[selected_year][selected_dept]
        gen = criteria.get("general_education", {})
        known = criteria.get("known_courses", {})

        # 1. 일반 학점 계산
        total_sum = sum(c['학점'] for c in final_courses)
        maj_req = sum(c['학점'] for c in final_courses if c['이수구분'] == "전공필수")
        maj_sel = sum(c['학점'] for c in final_courses if c['이수구분'] == "전공선택")
        maj_total_sum = maj_req + maj_sel

        # 2. [NEW] 3000~4000단위(심화) 학점 계산
        adv_keywords_raw = known.get("advanced_keywords", [])
        norm_adv_keywords = sorted(list(set([normalize_string(kw) for kw in adv_keywords_raw])), key=len)

        advanced_sum = 0.0
        detected_advanced = [] # 어떤 강의이 심화로 판정됐는지 기록

        # st.data_editor의 결과인 edited_df를 직접 한 행씩 분석
        for index, row in edited_df.iterrows():
            c_name = str(row['강의명']).strip()
            c_type = str(row['이수구분']).strip()

            # 학점 데이터를 float으로 안전하게 변환
            try:
                c_credit = float(row['학점'])
            except:
                c_credit = 0.0

            norm_name = normalize_string(c_name)

            # [핵심 3] 매칭 검사 (키워드가 강의명 안에 포함되어 있는가?)
            is_advanced_by_key = False
            if norm_name:
                for kw in norm_adv_keywords:
                    if kw in norm_name: # 예: "분자진단" in "분자진단학및실험"
                        is_advanced_by_key = True
                        break

            # [판정 로직 2] 이수구분 기반 매칭 (전공이면서 기초강의이 아닌 경우)
            # 임상병리학과 1학년 강의(해부, 조직)은 심화에서 제외하는 방어 로직          
            is_major = "전공" in c_type
            basic_list = ["인체해부학", "의학용어", "해부학", "세포생물학", "병리학", "미생물학"]
            is_exactly_basic = any(c_name == basic for basic in basic_list) or (c_name == "조직학")

            #진단조직학 심화전공 판정 기준 강화
            is_advanced_work = any(word in c_name for word in ["진단", "종합설계"])

            is_basic = is_exactly_basic and not is_advanced_work

            if is_advanced_by_key or (is_major and not is_basic):
                advanced_sum += c_credit
                detected_advanced.append(c_name)

        # 3. 리더십 및 필수교양 체크
        leadership_count = len([c for c in final_courses if "리더십" in str(c['이수구분']) or "RC" in normalize_string(c['강의명'])])

        search_names = " ".join([c['강의명'] for c in final_courses])
        req_fail = []
        for item in gen.get("required_courses", []):
            if item['name'] == "리더십":
                if leadership_count < 2: req_fail.append("리더십(RC) 2강의)")
                continue
            if not any(normalize_string(kw) in normalize_string(search_names) for kw in item["keywords"]):
                req_fail.append(item['name'])
        # 전공필수 체크
        for mr_course in known.get("major_required", []):
            norm_mr = normalize_string(mr_course)
            if not any(norm_mr in normalize_string(c['강의명']) for c in final_courses):
                req_fail.append(f"전공필수({mr_course})")

        # 최종 판정 로직
        pass_total = total_sum >= criteria['total_credits']
        pass_major_total = maj_total_sum >= criteria['major_total']
        pass_major_req = maj_req >= criteria['major_required']
        pass_advanced = advanced_sum >= criteria['advanced_course']
        pass_req_courses = len(req_fail) == 0

        is_all_pass = all([pass_total, pass_major_total, pass_major_req, pass_advanced, pass_req_courses])

        st.info("ℹ️ 본 진단 결과는 참고용이며, 정확한 졸업 여부는 학과 사무실을 통해 최종확인하시기 바랍니다.")
        st.header("🏁 졸업 자격 예비진단 리포트")
        if is_all_pass: 
            st.success("🎉 축하합니다! 모든 졸업 요건을 충족했습니다."); st.balloons()
        else: 
            st.error("⚠️ 아직 충족되지 않은 요건이 있습니다. 아래 대시보드와 보완 사항을 확인하세요.")

        # --- 메시지 출력 위치 ---
        # ⚠️ Metric 대시보드보다 위에 출력되도록 위치 조정
        if detected_advanced:
            st.info(f"✅ **심화 판정된 강의:** {', '.join(detected_advanced)}")
        else:
            st.warning("⚠️ **심화로 인식된 강의이 없습니다.** 테이블의 강의명에 '임상화학', '분자진단' 등이 포함되어 있는지 확인해주세요.")

        # 대시보드 레이아웃 (4열 구성)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 취득학점", f"{int(total_sum)} / {criteria['total_credits']}", delta=int(total_sum - criteria['total_credits']))
        m2.metric("전공 합계", f"{int(maj_total_sum)} / {criteria['major_total']}")
        m3.metric("3~4000단위(심화전공)", f"{int(advanced_sum)} / {criteria['advanced_course']}", delta=int(advanced_sum - criteria['advanced_course']), delta_color="normal")
        m4.metric("리더십(RC강의)", f"{leadership_count} / 2")

        # 세부 보완 사항 안내
        if not is_all_pass:
            with st.expander("🛠️ 세부 보완 필요 사항", expanded=True):
                if not pass_major_req:
                    st.warning(f"📍 **전공필수 학점**이 {int(criteria['major_required'] - maj_req)}학점 부족합니다.")
                if not pass_advanced:
                    st.warning(f"📍 **3000~4000단위(심화전) 학점**이 {int(criteria['advanced_course'] - advanced_sum)}학점 부족합니다.")
                if req_fail:
                    st.error(f"📍 **미이수 필수 요건:** {', '.join(req_fail)}")

        with st.expander("📊 수강 강의 상세 통계"):
            st.dataframe(pd.DataFrame(final_courses), use_container_width=True)
    else:
        st.info("성적표 이미지를 업로드하고 분석 버튼을 눌러주세요.")






