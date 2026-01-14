import streamlit as st
import pdfplumber
import re
import pandas as pd
import json
import pytesseract
from PIL import Image, ImageOps, ImageEnhance
import numpy as np

# Tesseract 경로 (필요시 설정)
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

st.set_page_config(page_title="졸업요건 진단기 (Ultimate)", page_icon="🎓")

if 'manual_courses' not in st.session_state:
    st.session_state.manual_courses = []

# --- 1. DB 로드 ---
@st.cache_data
def load_requirements():
    try:
        with open('requirements.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

db = load_requirements()

# --- 2. 강력해진 헬퍼 함수들 ---

def preprocess_image_for_ocr(image):
    """
    OCR 인식률을 높이기 위해 이미지를 흑백으로 변환하고, 크기를 키우고, 선명하게 만듭니다.
    """
    # 1. 흑백 변환
    image = image.convert('L')
    
    # 2. 이미지 확대 (작은 글씨 인식용, 2배)
    new_size = tuple(2 * x for x in image.size)
    image = image.resize(new_size, Image.Resampling.LANCZOS)
    
    # 3. 대비(Contrast) 증가
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.0)
    
    # 4. 이진화 (Thresholding) - 글자를 진하게, 배경을 날림
    # 128보다 어두우면 0(검정), 밝으면 255(흰색)
    image = image.point(lambda x: 0 if x < 140 else 255)
    
    return image

def normalize_string(s):
    """비교를 위해 공백, 특수문자 제거"""
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', s)

def find_course_in_db(ocr_line, year, dept):
    """
    OCR된 텍스트 한 줄이 DB에 있는 전공 과목인지 확인합니다.
    (OCR이 불안정해도 DB에 있는 정확한 명칭을 매칭하기 위함)
    """
    if year not in db or dept not in db[year]:
        return None, "교양/기타"
    
    known = db[year][dept].get("known_courses", {})
    clean_line = normalize_string(ocr_line)
    
    # 전공 필수 리스트와 대조
    for req in known.get("major_required", []):
        if normalize_string(req) in clean_line:
            return req, "전공필수" # 정확한 과목명, 타입 반환
            
    # 전공 선택 리스트와 대조
    for sel in known.get("major_elective", []):
        if normalize_string(sel) in clean_line:
            return sel, "전공선택"
            
    return None, "교양/기타"

def ocr_image_and_parse(image_file, year, dept):
    try:
        # 1. 이미지 전처리
        origin_image = Image.open(image_file)
        processed_image = preprocess_image_for_ocr(origin_image)
        
        # 2. OCR 실행 (psm 6: 단일 텍스트 블록으로 가정)
        config_options = '--psm 6' 
        text = pytesseract.image_to_string(processed_image, lang='kor+eng', config=config_options)
        
        parsed_courses = []
        
        # 3. 라인별 분석 (Reverse Matching 전략)
        # 에브리타임 캡쳐는 보통 "과목명 ... 학점 ... 성적" 순서임
        # 하지만 OCR은 이를 섞어서 읽을 수 있음.
        # 전략: 라인에서 'DB에 있는 전공과목명'이 발견되면 그 줄(혹은 주변)에서 학점을 찾는다.
        
        lines = text.split('\n')
        for line in lines:
            if len(line) < 2: continue
            
            # (1) 이 줄에 전공 과목 이름이 있는가?
            found_name, found_type = find_course_in_db(line, year, dept)
            
            # 전공 과목을 찾았다면
            if found_name:
                # 학점 찾기 (숫자 1~9)
                credit_match = re.search(r'\b([1-9])(?:\.0)?\b', line)
                credit = float(credit_match.group(1)) if credit_match else 3.0 # 기본값 3.0
                
                # 이미 리스트에 없으면 추가
                if not any(c['name'] == found_name for c in parsed_courses):
                    parsed_courses.append({
                        "name": found_name, # OCR된 텍스트 대신 DB의 정확한 명칭 사용
                        "credit": credit,
                        "type": found_type
                    })
            
            # (2) 전공은 아니지만 "교양" 처럼 학점/성적 패턴이 명확한 경우
            else:
                # 패턴: 한글/영어(2자이상) + 공백 + 숫자 + 공백 + 알파벳성적
                # 예: "미래설계리빙랩 3 P"
                match = re.search(r'([가-힣a-zA-Z\s]+)\s+(\d)\s+([A-Z]\+?|P)', line)
                if match:
                    c_name = match.group(1).strip()
                    c_credit = float(match.group(2))
                    # 이미 등록된 게 아닐 때만
                    if not any(normalize_string(c['name']) in normalize_string(c_name) for c in parsed_courses):
                        parsed_courses.append({
                            "name": c_name,
                            "credit": c_credit,
                            "type": "교양/기타" # 전공 DB에 없으므로 교양으로 가정
                        })

        return text, parsed_courses
        
    except Exception as e:
        return f"Error: {e}", []

def filter_failed_courses(full_text):
    lines = full_text.split('\n')
    filtered = []
    for line in lines:
        if re.search(r'\sF\s|\sF$|\sNP\s|\sNP$', line): continue
        filtered.append(line)
    return "\n".join(filtered)

# --- 팝업 ---
@st.dialog("🐛 버그 신고")
def show_bug_report_dialog(year, dept):
    st.write("오류 내용을 복사해서 메일을 보내주세요.")
    st.code(f"받는사람: jaekwang1164@gmail.com\n제목: [버그] {year} {dept}\n내용: 오류 설명", language="text")

# --- UI 시작 ---
with st.sidebar:
    st.header("⚙️ 설정")
    if db:
        years = sorted([k for k in db.keys() if k != "area_courses"])
    else:
        years = ["2022"]
    selected_year = st.selectbox("입학년도", years)
    
    if selected_year in db:
        depts = list(db[selected_year].keys())
        selected_dept = st.selectbox("전공", depts)
    else:
        selected_dept = st.selectbox("전공", ["-"])
    
    st.divider()
    
    st.markdown("### ➕ 과목 수동 추가")
    with st.form("add_form", clear_on_submit=True):
        m_name = st.text_input("과목명")
        m_credit = st.number_input("학점", 1.0, 10.0, 3.0)
        m_add = st.form_submit_button("추가")
        
        if m_add and m_name:
            # 수동 입력 시에도 DB 매칭 시도
            fname, ftype = find_course_in_db(m_name, selected_year, selected_dept)
            final_name = fname if fname else m_name
            
            st.session_state.manual_courses.append({
                "name": final_name, "credit": m_credit, "type": ftype
            })
            st.success(f"{final_name} ({ftype}) 추가됨")

    if st.session_state.manual_courses:
        st.markdown("---")
        for i, c in enumerate(st.session_state.manual_courses):
            c1, c2 = st.columns([4,1])
            c1.text(f"{c['name']} ({c['type']})")
            if c2.button("x", key=f"d{i}"):
                del st.session_state.manual_courses[i]
                st.rerun()

    st.divider()
    if st.button("📧 신고"): show_bug_report_dialog(selected_year, selected_dept)

# --- 메인 ---
st.title("🎓 연세대 졸업요건 진단기")
st.caption(f"{selected_year}학번 {selected_dept}")

c1, c2 = st.columns(2)
is_eng = c1.checkbox("외국어 인증", False)
is_info = c2.checkbox("정보 인증", False)

tab1, tab2, tab3 = st.tabs(["📄 PDF", "📸 캡쳐/이미지", "⌨️ 텍스트"])
extracted_text = ""
ocr_courses = []

with tab1:
    pdf_file = st.file_uploader("PDF 업로드", type="pdf")
    if pdf_file:
        with pdfplumber.open(pdf_file) as pdf:
            for p in pdf.pages: extracted_text += (p.extract_text() or "") + "\n"

with tab2:
    st.info("에브리타임, 포털 성적 캡쳐 (여러장 가능)")
    img_files = st.file_uploader("이미지", type=['png','jpg'], accept_multiple_files=True)
    if img_files:
        with st.spinner("이미지 정밀 분석 중... (흑백 변환 & DB 대조)"):
            for img in img_files:
                txt, parsed = ocr_image_and_parse(img, selected_year, selected_dept)
                extracted_text += txt + "\n"
                ocr_courses.extend(parsed)

with tab3:
    txt_input = st.text_area("텍스트 붙여넣기")
    if txt_input: extracted_text += txt_input

# --- 분석 ---
manual_txt = "\n".join([c['name'] for c in st.session_state.manual_courses])
full_text = extracted_text + "\n" + manual_txt

if full_text.strip():
    if selected_year not in db: st.stop()
    criteria = db[selected_year][selected_dept]
    gen_rule = criteria.get("general_education", {})
    clean_text = filter_failed_courses(full_text)
    
    # 1. PDF 자동 추출 (우선순위 높음)
    pdf_total = float((re.search(r'(?:취득학점|학점계)[:\s]*(\d{2,3})', clean_text) or [0,0])[1])
    pdf_maj_req = float((re.search(r'전공필수[:\s]*(\d{1,3})', clean_text) or [0,0])[1])
    pdf_maj_sel = float((re.search(r'전공선택[:\s]*(\d{1,3})', clean_text) or [0,0])[1])
    pdf_upper = float((re.search(r'3~4천단위[:\s]*(\d{1,3})', clean_text) or [0,0])[1])

    # 2. OCR + 수동 추출 합산
    all_added = st.session_state.manual_courses + ocr_courses
    # 중복 제거 (이름이 같은 과목이 여러번 찍혔을 수 있음)
    unique_added = {v['name']:v for v in all_added}.values()
    
    added_total = sum(c['credit'] for c in unique_added)
    added_req = sum(c['credit'] for c in unique_added if c['type'] == '전공필수')
    added_sel = sum(c['credit'] for c in unique_added if c['type'] == '전공선택')
    
    # 최종 합산 로직
    if pdf_total > 0:
        # PDF가 있으면 PDF값 + 수동값 (OCR은 PDF에 이미 있을테니 무시하거나 보조)
        final_total = pdf_total + sum(c['credit'] for c in st.session_state.manual_courses)
        final_req = pdf_maj_req + sum(c['credit'] for c in st.session_state.manual_courses if c['type'] == '전공필수')
        final_sel = pdf_maj_sel + sum(c['credit'] for c in st.session_state.manual_courses if c['type'] == '전공선택')
    else:
        # 이미지만 있으면 OCR + 수동값 사용
        final_total = added_total
        final_req = added_req
        final_sel = added_sel
    
    final_maj = final_req + final_sel

    # 교양 체크
    req_fail = []
    for item in gen_rule.get("required_courses", []):
        if not any(kw in clean_text for kw in item["keywords"]):
            req_fail.append(item['name'])

    all_area = set(gen_rule.get("required_areas", []) + gen_rule.get("elective_areas", []))
    my_area = [a for a in all_area if a in clean_text] # OCR 텍스트 안에서 교양영역 키워드 찾기
    
    miss_req_area = set(gen_rule.get("required_areas", [])) - set(my_area)
    elec_fail_cnt = max(0, gen_rule["elective_min_count"] - len([a for a in my_area if a in gen_rule.get("elective_areas", [])]))

    # 판정
    final_pass = all([
        final_total >= criteria['total_credits'],
        final_maj >= criteria['major_total'],
        final_req >= criteria['major_required'],
        # 3000단위는 OCR로 힘들어서 PDF일때만 체크 (이미지일 땐 0>=50 False 뜨므로 조건 완화 필요하나 일단 유지)
        (pdf_upper >= criteria['advanced_course'] if pdf_total > 0 else True), 
        not req_fail, not miss_req_area, elec_fail_cnt == 0,
        is_eng, is_info
    ])
    
    st.divider()
    if final_pass: st.balloons(); st.success("졸업 가능!")
    else: st.error("졸업 요건 부족")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("총 학점", f"{int(final_total)}/{criteria['total_credits']}")
    c2.metric("전공(필+선)", f"{int(final_maj)}/{criteria['major_total']}")
    c3.metric("전공필수", f"{int(final_req)}/{criteria['major_required']}")
    
    if not final_pass:
        st.subheader("🛠️ 보완 필요")
        if final_total < criteria['total_credits']: st.warning(f"총점 {int(criteria['total_credits']-final_total)} 부족")
        if final_req < criteria['major_required']: st.warning(f"전필 {int(criteria['major_required']-final_req)} 부족")
        if req_fail: st.error(f"필수교양 미이수: {req_fail}")
        if miss_req_area: st.error(f"필수영역 미이수: {miss_req_area}")
        if elec_fail_cnt: 
            st.error(f"선택영역 {elec_fail_cnt}개 부족")
            with st.expander("추천 강의"):
                rmap = gen_rule.get("area_courses", {}) or db.get("area_courses", {})
                for a in (set(gen_rule.get("elective_areas", [])) - set(my_area)):
                    st.write(f"[{a}]", ", ".join(rmap.get(a, [])))

    with st.expander("📸 OCR 인식된 과목 목록 확인"):
        if ocr_courses:
            df = pd.DataFrame(ocr_courses)
            # 중복 제거해서 보여주기
            df = df.drop_duplicates(subset=['name'])
            st.dataframe(df)
        else:
            st.info("이미지에서 인식된 과목이 없습니다.")
            
    with st.expander("📄 전체 텍스트"):
        st.text(clean_text)

else:
    st.info("성적표를 업로드해주세요.")
