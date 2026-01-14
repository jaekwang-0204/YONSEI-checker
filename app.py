import streamlit as st
import pdfplumber
import re
import pandas as pd
import json
import pytesseract
from PIL import Image, ImageOps
import io

# --- Tesseract 경로 설정 (필요 시 주석 해제) ---
# 로컬 윈도우 사용 시:
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
# 리눅스/스트림릿 클라우드: 보통 자동 인식됨

st.set_page_config(page_title="졸업요건 진단기 (Ultimate)", page_icon="🎓")

# --- 세션 상태 초기화 ---
if 'manual_courses' not in st.session_state:
    st.session_state.manual_courses = []

# --- 1. 졸업요건 DB 로드 ---
@st.cache_data
def load_requirements():
    try:
        with open('requirements.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

db = load_requirements()

# --- 2. 헬퍼 함수들 ---

def clean_ocr_text(text):
    """
    OCR 결과에서 흔히 발생하는 오타를 수정하고 노이즈를 제거합니다.
    """
    # 1. 등급 오타 수정 (At -> A+, Poy -> P 등)
    corrections = {
        r'At': 'A+', r'Bt': 'B+', r'Ct': 'C+', r'Dt': 'D+',
        r'Ap': 'A+', r'Bp': 'B+', # p로 인식되는 경우
        r'Poy': 'P', r'Pay': 'P', r'Pass': 'P',
        r'NP': 'NP', r'F': 'F'
    }
    
    cleaned_lines = []
    for line in text.split('\n'):
        # 너무 짧은 줄(노이즈) 제거
        if len(line.strip()) < 2:
            continue
            
        # 오타 치환
        for err, corr in corrections.items():
            line = re.sub(err, corr, line)
        
        # 특수문자 노이즈 제거 (한글, 영문, 숫자, 공백, +, - 만 남김)
        # 단, 과목명에 괄호()가 있을 수 있으므로 포함
        line = re.sub(r'[^가-힣a-zA-Z0-9\s\+\-\(\)\.]', '', line)
        
        cleaned_lines.append(line)
        
    return "\n".join(cleaned_lines)

def filter_failed_courses(full_text):
    """F/NP 학점 제거"""
    lines = full_text.split('\n')
    filtered_lines = []
    for line in lines:
        if re.search(r'\sF\s|\sF$|\sNP\s|\sNP$', line):
            continue 
        filtered_lines.append(line)
    return "\n".join(filtered_lines)

def ocr_image(image_file):
    try:
        # 이미지 전처리: 흑백 변환 및 대비 강화 (인식률 향상)
        image = Image.open(image_file).convert('L') # Grayscale
        image = ImageOps.autocontrast(image) # 대비 최적화
        
        # OCR 실행 (한글+영어)
        text = pytesseract.image_to_string(image, lang='kor+eng')
        return clean_ocr_text(text)
    except Exception as e:
        return f"Error reading image: {e}"

# --- [팝업] 버그 신고 ---
@st.dialog("🐛 버그 신고 및 문의")
def show_bug_report_dialog(year, dept):
    st.write("오류 내용을 복사해서 메일을 보내주세요.")
    st.divider()
    
    st.caption("1. 이메일 주소")
    st.code("jaekwang1164@gmail.com", language="text")
    
    st.caption("2. 메일 제목")
    st.code(f"[졸업진단기 버그신고] {year}학번 {dept}", language="text")
    
    st.caption("3. 본문 양식")
    st.code("""1. 오류 내용: 
2. 기대했던 결과: 
3. 첨부파일: 성적표 캡쳐 등""", language="text")


# --- 3. 사이드바 ---
with st.sidebar:
    st.header("⚙️ 설정")
    
    if db:
        available_years = sorted([k for k in db.keys() if k != "area_courses"])
    else:
        available_years = ["2022", "2023"]
    selected_year = st.selectbox("입학년도", available_years)
    
    if selected_year in db:
        dept_list = list(db[selected_year].keys())
        selected_dept = st.selectbox("전공", dept_list)
    else:
        selected_dept = st.selectbox("전공", ["지원되는 학과 없음"])

    st.divider()

    # 수동 과목 추가
    st.markdown("### ➕ 과목 수동 추가")
    st.caption("인식되지 않은 과목을 직접 추가하세요.")
    
    with st.form("add_course_form", clear_on_submit=True):
        m_name = st.text_input("과목명 (예: 글쓰기)")
        m_credit = st.number_input("학점", min_value=0.5, max_value=10.0, step=0.5, value=3.0)
        m_type = st.selectbox("이수 구분", ["전공필수", "전공선택", "교양/기타"])
        m_add = st.form_submit_button("추가하기")
        
        if m_add and m_name:
            st.session_state.manual_courses.append({
                "name": m_name, "credit": m_credit, "type": m_type
            })
            st.success(f"'{m_name}' 추가됨!")

    if st.session_state.manual_courses:
        st.markdown("---")
        for i, c in enumerate(st.session_state.manual_courses):
            col1, col2 = st.columns([4, 1])
            col1.text(f"{c['name']} ({c['credit']}학점)")
            if col2.button("❌", key=f"del_{i}"):
                del st.session_state.manual_courses[i]
                st.rerun()

    st.divider()
    if st.button("📧 개발자에게 메일 보내기"):
        show_bug_report_dialog(selected_year, selected_dept)


# --- 메인 화면 ---
st.title("🎓 연세대 졸업요건 정밀 진단")
st.markdown(f"**{selected_year}학번 {selected_dept}** 기준")

# 수동 인증
col1, col2 = st.columns(2)
is_eng = col1.checkbox("외국어 인증 완료", value=False)
is_info = col2.checkbox("정보/산학 인증 완료", value=False)

st.divider()

# --- 4. 데이터 입력 (탭) ---
tab1, tab2, tab3 = st.tabs(["📂 PDF 업로드", "🖼️ 이미지(캡쳐) 업로드", "📝 텍스트 입력"])
extracted_text = ""
ocr_credits_sum = 0.0 # 이미지에서 추출된 학점 합계

with tab1:
    uploaded_pdf = st.file_uploader("성적증명서 PDF", type="pdf")
    if uploaded_pdf:
        with pdfplumber.open(uploaded_pdf) as pdf:
            for page in pdf.pages:
                extracted_text += (page.extract_text() or "") + "\n"

with tab2:
    st.info("에브리타임 시간표나 성적표 스크린샷을 업로드하세요. (최대 10장)")
    # [수정] 여러 장 업로드 허용
    uploaded_imgs = st.file_uploader("이미지 파일", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
    
    if uploaded_imgs:
        with st.spinner(f"{len(uploaded_imgs)}장의 이미지를 분석 중입니다..."):
            for img_file in uploaded_imgs:
                ocr_result = ocr_image(img_file)
                extracted_text += ocr_result + "\n"
                
                # [NEW] 이미지에서 숫자(학점) 추정하여 합산 시도
                # 패턴: "과목명 3 A+" 형태에서 가운데 숫자 추출
                # 예: "미래설계 3 P" -> 3 추출
                # (주의: OCR은 불안정하므로 보조 수단으로 사용)
                matches = re.findall(r'\s([1-9](?:\.5)?)\s+[A-Z]', ocr_result)
                for m in matches:
                    try:
                        ocr_credits_sum += float(m)
                    except:
                        pass

with tab3:
    manual_input = st.text_area("텍스트 붙여넣기", height=150)
    if manual_input: extracted_text += manual_input

# --- 5. 분석 로직 ---
# 수동 추가된 과목 텍스트로 합치기 (키워드 검색용)
manual_text_block = "\n".join([f"{c['name']} {c['credit']}" for c in st.session_state.manual_courses])
full_text = extracted_text + "\n" + manual_text_block

if full_text.strip():
    if selected_year not in db:
        st.error("지원되지 않는 학번입니다.")
        st.stop()
        
    criteria = db[selected_year][selected_dept]
    gen_rule = criteria.get("general_education", {})
    clean_text = filter_failed_courses(full_text)
    
    # --- 학점 계산 (PDF 자동 + OCR 추정 + 수동 입력) ---
    
    # 1. PDF 등에서 "취득학점: 130" 패턴 찾기
    pdf_total_match = re.search(r'(?:취득학점|학점계)[:\s]*(\d{2,3})', clean_text)
    pdf_total = float(pdf_total_match.group(1)) if pdf_total_match else 0.0
    
    # 2. 전공 학점 추출 (PDF 패턴)
    pdf_maj_req = float((re.search(r'전공필수[:\s]*(\d{1,3})', clean_text) or [0,0])[1])
    pdf_maj_sel = float((re.search(r'전공선택[:\s]*(\d{1,3})', clean_text) or [0,0])[1])
    
    # 3. 수동 입력 합산
    manual_sum = sum(c['credit'] for c in st.session_state.manual_courses)
    manual_req = sum(c['credit'] for c in st.session_state.manual_courses if c['type'] == '전공필수')
    manual_sel = sum(c['credit'] for c in st.session_state.manual_courses if c['type'] == '전공선택')

    # [중요] 최종 학점 결정 전략
    # PDF에서 총점을 찾았으면 그게 가장 정확함.
    # 못 찾았으면(이미지만 올린 경우) OCR 추정치 + 수동입력치를 사용.
    if pdf_total > 0:
        final_total = pdf_total + manual_sum # PDF가 있으면 수동만 더함
    else:
        # PDF 총점이 없으면 OCR 합산값 + 수동값 사용
        final_total = ocr_credits_sum + manual_sum

    final_maj_req = pdf_maj_req + manual_req
    final_maj_sel = pdf_maj_sel + manual_sel
    final_maj_total = final_maj_req + final_maj_sel
    
    # 3000단위 (PDF에서만 신뢰 가능, 이미지는 식별 불가하므로 0)
    final_upper = float((re.search(r'3~4천단위[:\s]*(\d{1,3})', clean_text) or [0,0])[1])

    # --- 교양 체크 ---
    req_fail = []
    for item in gen_rule.get("required_courses", []):
        if not any(kw in clean_text for kw in item["keywords"]):
            req_fail.append(item['name'])

    all_req = set(gen_rule.get("required_areas", []))
    all_elec = set(gen_rule.get("elective_areas", []))
    
    my_req = [a for a in all_req if a in clean_text]
    my_elec = [a for a in all_elec if a in clean_text]
    
    missing_req = all_req - set(my_req)
    missing_elec_cnt = gen_rule["elective_min_count"] - len(my_elec)
    unused_elec = all_elec - set(my_elec)

    # --- 판정 ---
    pass_total = final_total >= criteria['total_credits']
    pass_maj = final_maj_total >= criteria['major_total']
    pass_req = len(req_fail) == 0
    pass_area_req = len(missing_req) == 0
    pass_area_elec = missing_elec_cnt <= 0
    
    # 최종 패스 조건
    final_pass = all([pass_total, pass_maj, pass_req, pass_area_req, pass_area_elec, is_eng, is_info])

    # --- 결과 표시 ---
    st.divider()
    st.header("🏁 진단 결과")
    
    if final_pass:
        st.success("🎉 **졸업 가능!** 고생하셨습니다.")
        st.balloons()
    else:
        st.error("⚠️ **졸업 요건 미충족**")
        
    c1, c2, c3 = st.columns(3)
    c1.metric("총 학점", f"{int(final_total)} / {criteria['total_credits']}")
    c2.metric("전공 학점", f"{int(final_maj_total)} / {criteria['major_total']}")
    c3.metric("필수 교양", "완료" if pass_req else "미완료")

    if not final_pass:
        st.subheader("🛠️ 보완 사항")
        if not pass_total: st.warning(f"총 학점 {int(criteria['total_credits'] - final_total)}점 부족")
        if not pass_maj: st.warning(f"전공 학점 {int(criteria['major_total'] - final_maj_total)}점 부족")
        if not pass_req: st.error(f"필수 과목 미이수: {', '.join(req_fail)}")
        if not pass_area_req: st.error(f"필수 영역 미이수: {', '.join(missing_req)}")
        if not pass_area_elec: 
            st.error(f"선택 영역 {missing_elec_cnt}개 부족")
            with st.expander("💡 추천 강의 보기"):
                rec_map = gen_rule.get("area_courses", {}) or db.get("area_courses", {})
                for a in unused_elec:
                    st.write(f"**[{a}]**", ", ".join(rec_map.get(a, ["정보 없음"])))
                    
        if not is_eng: st.warning("외국어 인증 필요")
        if not is_info: st.warning("정보 인증 필요")
        
    with st.expander("🔍 분석된 텍스트 확인 (OCR 결과)"):
        st.text(clean_text)

else:
    st.info("👆 성적표(PDF)나 에브리타임 캡쳐본을 올려주세요.")
