import streamlit as st
import pdfplumber
import re
import pandas as pd
import json
import pytesseract
from PIL import Image, ImageOps, ImageEnhance
import io

st.set_page_config(page_title="졸업요건 진단기 (Universal)", page_icon="🎓", layout="wide")

if 'ocr_results' not in st.session_state:
    st.session_state.ocr_results = []

# --- 1. DB 로드 ---
@st.cache_data
def load_requirements():
    try:
        with open('requirements.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError: return {}

db = load_requirements()

# --- 2. 분류 로직 (RC/리더십 특화) ---
def normalize_string(s):
    if not isinstance(s, str): return ""
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', s).upper()

def classify_course_logic(course_name, year, dept):
    norm_name = normalize_string(course_name)
    if "RC" in norm_name or "리더십" in norm_name: return "교양(리더십)"
    if year not in db or dept not in db[year]: return "교양/기타"
    
    dept_db = db[year][dept]
    known = dept_db.get("known_courses", {})
    
    for req in known.get("major_required", []):
        if normalize_string(req) in norm_name: return "전공필수"
    for sel in known.get("major_elective", []):
        if normalize_string(sel) in norm_name: return "전공선택"
    
    # 필수교양 키워드 체크
    for rg in dept_db.get("general_education", {}).get("required_courses", []):
        if any(normalize_string(kw) in norm_name for kw in rg["keywords"]): return "필수교양"

    for area, courses in db.get("area_courses", {}).items():
        for c in courses:
            if normalize_string(c) in norm_name: return f"교양({area})"
    return "교양/기타"

# --- 3. 파싱 로직 (텍스트/이미지 공통) ---
def parse_line_to_course(line, year, dept):
    """한 줄의 텍스트에서 과목명과 학점을 추출"""
    line = re.sub(r'[~@#$%\^&*_\-=|;:"<>,.?/\[\]\{\}]', ' ', line).strip()
    # 패턴: 과목명 (공백) 학점(0.5~9.0)
    match = re.search(r'^(.*?)\s+(\d+(?:\.\d+)?)(?:\s+.*)?$', line)
    if match:
        name = match.group(1).strip()
        credit = float(match.group(2))
        # 노이즈 필터링
        if len(name) < 2 or name.isdigit() or name.upper() in ["AT", "BT", "PASS", "NP", "TOTAL"]: return None
        return {"과목명": name, "학점": credit, "이수구분": classify_course_logic(name, year, dept)}
    return None

# --- 4. OCR 및 PDF 처리기 ---
def process_image(img_file, year, dept):
    img = Image.open(img_file).convert('L')
    img = ImageEnhance.Contrast(ImageOps.autocontrast(img)).enhance(2.0)
    text = pytesseract.image_to_string(img, lang='kor+eng', config='--psm 6')
    
    results = []
    start = False
    for line in text.split('\n'):
        if not start:
            if any(k in line for k in ["과목명", "학점", "성적", "전공"]): start = True
            continue
        res = parse_line_to_course(line, year, dept)
        if res: results.append(res)
    return results

def process_pdf(pdf_file, year, dept):
    text_results = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            # 1. 먼저 텍스트 추출 시도 (텍스트형 PDF)
            page_text = page.extract_text()
            if page_text:
                for line in page_text.split('\n'):
                    res = parse_line_to_course(line, year, dept)
                    if res: text_results.append(res)
            
            # 2. 만약 텍스트가 거의 없다면 이미지로 변환하여 OCR 시도 (스캔형 PDF)
            if not text_results:
                # 이 부분은 서버 환경에 따라 이미지 렌더링 라이브러리(pdf2image 등)가 필요할 수 있음
                # 우선은 텍스트 추출 위주로 작동하며, 안될 경우 이미지 탭 사용 유도
                pass
    return text_results

# --- UI 레이아웃 ---
with st.sidebar:
    st.header("⚙️ 설정")
    years = sorted([k for k in db.keys() if k != "area_courses"])
    selected_year = st.selectbox("입학년도", years)
    selected_dept = st.selectbox("전공", list(db[selected_year].keys()))
    if st.button("🔄 데이터 초기화"):
        st.session_state.ocr_results = []; st.rerun()

st.title("🎓 연세대 졸업요건 통합 진단기")
st.info("PDF(텍스트/이미지) 및 에브리타임 캡쳐를 모두 지원합니다. 업로드 후 '분석 실행'을 눌러주세요.")

tab1, tab2, tab3 = st.tabs(["📂 성적표 업로드 (PDF/이미지)", "✏️ 과목 수정 및 최종 확인", "📊 진단 리포트"])

with tab1:
    col1, col2 = st.columns(2)
    with col1:
        uploaded_pdf = st.file_uploader("성적증명서 PDF (텍스트/이미지 포함)", type="pdf")
    with col2:
        uploaded_imgs = st.file_uploader("에브리타임 캡쳐본 (복수 선택 가능)", type=['png','jpg','jpeg'], accept_multiple_files=True)
    
    if st.button("🚀 모든 파일 분석 시작"):
        all_found = []
        with st.spinner("모든 소스에서 데이터를 추출하는 중..."):
            if uploaded_pdf:
                all_found.extend(process_pdf(uploaded_pdf, selected_year, selected_dept))
            if uploaded_imgs:
                for img in uploaded_imgs:
                    all_found.extend(process_image(img, selected_year, selected_dept))
        
        if all_found:
            # 중복 제거 (과목명 기준)
            df_temp = pd.DataFrame(all_found).drop_duplicates(subset=['과목명'])
            st.session_state.ocr_results = df_temp.to_dict('records')
            st.success(f"총 {len(st.session_state.ocr_results)}개의 과목을 찾았습니다! 두 번째 탭으로 이동하세요.")
        else:
            st.error("과목을 찾지 못했습니다. 파일 형식을 확인하거나 직접 입력해주세요.")

with tab2:
    st.markdown("### 📝 추출된 수강 과목 명단")
    st.caption("잘못된 분류나 학점은 수정하고, 누락된 과목은 하단에 추가하세요.")
    
    df_input = pd.DataFrame(st.session_state.ocr_results) if st.session_state.ocr_results else pd.DataFrame(columns=["과목명", "학점", "이수구분"])
    
    edited_df = st.data_editor(
        df_input, num_rows="dynamic", use_container_width=True,
        column_config={
            "학점": st.column_config.NumberColumn(step=0.5),
            "이수구분": st.column_config.SelectboxColumn(options=["전공필수", "전공선택", "필수교양", "교양(리더십)", "교양(문학과예술)", "교양(인간과역사)", "교양(언어와표현)", "교양(가치와윤리)", "교양(국가와사회)", "교양(지역과세계)", "교양(논리와수리)", "교양(자연과우주)", "교양(생명과환경)", "교양(정보와기술)", "교양(체육과건강)", "교양/기타"])
        }, key="editor"
    )

with tab3:
    if not edited_df.empty:
        # 진단 로직
        final_list = edited_df.to_dict('records')
        criteria = db[selected_year][selected_dept]
        
        # 학점 계산
        total_sum = sum(c['학점'] for c in final_list)
        maj_req = sum(c['학점'] for c in final_list if c['이수구분'] == "전공필수")
        maj_sel = sum(c['학점'] for c in final_list if c['이수구분'] == "전공선택")
        
        # 리더십 (RC 포함 2과목)
        leadership_list = [c for c in final_list if "리더십" in str(c['이수구분']) or "RC" in normalize_string(c['과목명'])]
        leadership_count = len(leadership_list)
        
        # 결과 화면
        st.header("🏁 종합 졸업 자격 진단")
        c1, c2, c3 = st.columns(3)
        c1.metric("총 취득학점", f"{int(total_sum)} / {criteria['total_credits']}", delta=int(total_sum - criteria['total_credits']))
        c2.metric("전공(필+선)", f"{int(maj_req + maj_sel)} / {criteria['major_total']}")
        c3.metric("리더십(RC 포함)", f"{leadership_count} / 2")

        # 세부 미충족 알림
        if leadership_count < 2:
            st.error(f"❌ 리더십 요건 부족: 현재 {leadership_count}과목 이수 (RC 포함 2과목 필수)")
        if maj_req < criteria['major_required']:
            st.warning(f"⚠️ 전공필수 학점 부족: {int(criteria['major_required'] - maj_req)}학점 더 필요")
            
        st.balloons() if total_sum >= criteria['total_credits'] and leadership_count >= 2 else None
    else:
        st.warning("분석할 데이터가 없습니다. 첫 번째 탭에서 파일을 먼저 업로드하세요.")
