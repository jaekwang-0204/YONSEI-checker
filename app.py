import streamlit as st
import pdfplumber
import re
import pandas as pd
import json

st.set_page_config(page_title="졸업요건 진단기 (Pro)", page_icon="🎓")

# --- 1. 졸업요건 DB 로드 ---
@st.cache_data
def load_requirements():
    try:
        with open('requirements.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

db = load_requirements()

# --- 2. F학점 제거 함수 ---
def filter_failed_courses(full_text):
    lines = full_text.split('\n')
    filtered_lines = []
    for line in lines:
        # F 또는 NP가 포함된 줄은 제외 (단순 F 글자가 아니라 등급 위치에 있는 경우)
        if re.search(r'\sF\s|\sF$|\sNP\s|\sNP$', line):
            continue 
        filtered_lines.append(line)
    return "\n".join(filtered_lines)

# --- 3. UI 구성 (사이드바) ---
with st.sidebar:
    st.header("⚙️ 설정 및 신고")
    st.info("입학년도와 전공을 선택하세요.")
    
    # 드롭다운: 학번 선택 (area_courses 키 제외)
    if db:
        available_years = sorted([k for k in db.keys() if k != "area_courses"])
    else:
        available_years = ["2022", "2023"]
        
    selected_year = st.selectbox("입학년도", available_years)
    
    # 드롭다운: 전공 선택
    if selected_year in db:
        dept_list = list(db[selected_year].keys())
        selected_dept = st.selectbox("전공", dept_list)
    else:
        selected_dept = st.selectbox("전공", ["지원되는 학과 없음"])

    st.divider()
    
    # [기능] 버그 신고
    st.markdown("### 🐛 버그 신고")
    st.caption("오류 발생 시 개발자에게 메일을 보냅니다.")
    email_subject = f"[졸업진단기 버그신고] {selected_year}학번 {selected_dept} 오류 제보"
    email_body = "1. 오류 내용:\n2. 기대했던 결과:\n3. 첨부(선택):"
    mailto_link = f"mailto:jaekwang1164@gmail.com?subject={email_subject}&body={email_body}"
    
    st.markdown(f'<a href="{mailto_link}" target="_blank" style="text-decoration:none; background-color:#FF4B4B; color:white; padding:10px 20px; border-radius:5px; display:block; text-align:center;">📧 메일 보내기</a>', unsafe_allow_html=True)


# --- 메인 화면 ---
st.title("🎓 연세대 졸업요건 정밀 진단")
st.markdown(f"**{selected_year}학번 {selected_dept}** 기준으로 분석합니다.")

# 수동 인증 체크
col1, col2 = st.columns(2)
is_eng = col1.checkbox("외국어 인증 완료", value=False)
is_info = col2.checkbox("정보/산학 인증 완료", value=False)

st.divider()

# --- 4. 데이터 입력 ---
tab1, tab2 = st.tabs(["📂 PDF 업로드", "📝 텍스트 붙여넣기"])
full_text = ""

with tab1:
    uploaded_file = st.file_uploader("성적증명서 PDF", type="pdf")
    if uploaded_file:
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text: full_text += text + "\n"

with tab2:
    manual_input = st.text_area("텍스트 붙여넣기", height=150)
    if manual_input: full_text = manual_input

# --- 5. 분석 로직 ---
if full_text:
    # 학과 데이터 확인
    if selected_year not in db or selected_dept not in db[selected_year]:
        st.error("지원되지 않는 학번/학과입니다. 사이드바 설정을 확인해주세요.")
        st.stop()

    criteria = db[selected_year][selected_dept]
    gen_rule = criteria.get("general_education", {})
    
    # F학점 제거
    clean_text = filter_failed_courses(full_text)
    
    # --- 데이터 추출 및 계산 ---
    
    # 1) 학점 계산
    total_match = re.search(r'(?:취득학점|학점계)[:\s]*(\d{2,3})', clean_text)
    my_total = float(total_match.group(1)) if total_match else 0.0
    
    maj_req = float((re.search(r'전공필수[:\s]*(\d{1,3})', clean_text) or [0,0])[1])
    maj_sel = float((re.search(r'전공선택[:\s]*(\d{1,3})', clean_text) or [0,0])[1])
    my_maj_total = maj_req + maj_sel
    my_upper = float((re.search(r'3~4천단위[:\s]*(\d{1,3})', clean_text) or [0,0])[1])

    # 2) 교양 필수과목 체크
    req_courses_fail_list = [] 
    for item in gen_rule.get("required_courses", []):
        count = 0
        for kw in item["keywords"]:
            count += clean_text.count(kw)
        if count < 1: 
            req_courses_fail_list.append(item['name'])

    # 3) 교양 영역 체크
    all_req_areas = set(gen_rule.get("required_areas", []))
    all_elec_areas = set(gen_rule.get("elective_areas", []))
    
    my_req_areas = [a for a in all_req_areas if a in clean_text]
    my_elec_areas = [a for a in all_elec_areas if a in clean_text]
    
    missing_req_areas = all_req_areas - set(my_req_areas) # 필수 중 안 들은 것
    missing_elec_count = gen_rule["elective_min_count"] - len(my_elec_areas) # 선택 중 부족한 개수
    unused_elec_areas = all_elec_areas - set(my_elec_areas) # 아직 안 들은 선택 영역 목록

    # --- 판정 로직 ---
    pass_total = my_total >= criteria['total_credits']
    pass_maj_tot = my_maj_total >= criteria['major_total']
    pass_maj_req = maj_req >= criteria['major_required']
    pass_upper = my_upper >= criteria['advanced_course']
    pass_eng = is_eng
    pass_info = is_info
    pass_gen_req_course = len(req_courses_fail_list) == 0
    pass_gen_area_req = len(missing_req_areas) == 0
    pass_gen_area_elec = missing_elec_count <= 0

    final_pass = all([pass_total, pass_maj_tot, pass_maj_req, pass_upper, pass_eng, pass_info, pass_gen_req_course, pass_gen_area_req, pass_gen_area_elec])

    # --- 결과 화면 출력 ---
    st.divider()
    st.header("🏁 종합 판정 결과")
    
    # 1. 최초 판정 결과
    if final_pass:
        st.success("🎉 **졸업 가능합니다!** 모든 요건을 충족했습니다.")
        st.balloons()
    else:
        st.error("⚠️ **졸업 불가능** (아래 보완 사항을 확인하세요)")

    # 2. 요약 정보
    col_s1, col_s2, col_s3 = st.columns(3)
    col_s1.metric("총 학점", f"{int(my_total)} / {criteria['total_credits']}")
    col_s2.metric("전공 학점", f"{int(my_maj_total)} / {criteria['major_total']}")
    col_s3.metric("필수 교양", "이수" if pass_gen_req_course else "미이수")

    # 3. 상세 성적표 (라벨 변경됨)
    with st.expander("📄 상세 성적표 (추출된 데이터 확인)", expanded=False):
        st.text(clean_text)
        st.caption("※ F/NP 학점 과목은 제외된 데이터입니다.")

    # 4. 보완 가이드 (불합격 시 표시)
    if not final_pass:
        st.subheader("🛠️ 졸업을 위한 보완 가이드")
        
        # 학점 관련
        if not pass_total:
            st.warning(f"**[총 학점]** {int(criteria['total_credits'] - my_total)}학점 부족")
        if not pass_maj_tot:
            st.warning(f"**[전공 전체]** {int(criteria['major_total'] - my_maj_total)}학점 부족")
        if not pass_maj_req:
            st.warning(f"**[전공 필수]** {int(criteria['major_required'] - maj_req)}학점 부족")
        if not pass_upper:
            st.warning(f"**[3000단위 이상]** {int(criteria['advanced_course'] - my_upper)}학점 부족")

        # 필수 교양 과목
        if not pass_gen_req_course:
            st.error(f"**[필수 교양 미이수]** 수강 필요: {', '.join(req_courses_fail_list)}")

        # 교양 영역
        if not pass_gen_area_req:
            st.error(f"**[필수 영역 미이수]** 수강 필요: {', '.join(missing_req_areas)}")
        
        if not pass_gen_area_elec:
            st.error(f"**[선택 영역 부족]** {missing_elec_count}개 영역 추가 이수 필요")
            
            # --- 추천 강의 로직 (공통 데이터 연동) ---
            st.markdown("---")
            st.markdown("##### 💡 부족한 영역 추천 강의")
            
            # 1순위: 학과별 설정, 2순위: 공통 설정(root)
            rec_courses_map = gen_rule.get("area_courses", {})
            if not rec_courses_map:
                rec_courses_map = db.get("area_courses", {})
            
            for area in unused_elec_areas:
                if area in rec_courses_map:
                    st.info(f"**[{area}]** 추천: {', '.join(rec_courses_map[area])}")
                else:
                    st.info(f"**[{area}]** 포털에서 해당 영역 강의를 검색하세요.")

        # 인증
        if not pass_eng:
            st.warning("**[외국어 인증]** 미완료")
        if not pass_info:
            st.warning("**[정보/산학 인증]** 미완료")
