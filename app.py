import streamlit as st
import pdfplumber
from pypdf import PdfReader
import re
import pandas as pd

st.set_page_config(page_title="졸업요건 진단기", page_icon="🎓")

st.title("🎓 연세대학교 졸업요건 진단 (고성능)")
st.markdown("""
**[사용 방법]**
1. **파일 업로드**: PDF를 올리면 두 가지 엔진(Plumber, PyPDF)으로 분석을 시도합니다.
2. **직접 입력**: 파일 인식이 안 되면, 메모장에 먼저 붙여넣어 본 뒤 복사해서 넣어보세요.
""")

st.divider()

# 탭 구성
tab1, tab2 = st.tabs(["📂 파일 업로드", "📝 직접 붙여넣기"])

full_text = ""

# --- [엔진 1] 파일 업로드 처리 ---
with tab1:
    uploaded_file = st.file_uploader("PDF 파일을 업로드하세요", type="pdf")
    
    if uploaded_file is not None:
        with st.spinner('1차 시도 (pdfplumber) 중...'):
            try:
                # 방법 A: pdfplumber
                with pdfplumber.open(uploaded_file) as pdf:
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text: full_text += text + "\n"
            except:
                pass

        # 1차 실패 시 2차 시도
        if not full_text.strip():
            with st.spinner('1차 실패.. 2차 시도 (pypdf) 중...'):
                try:
                    # 방법 B: pypdf (다른 방식의 엔진)
                    reader = PdfReader(uploaded_file)
                    full_text = "" # 리셋
                    for page in reader.pages:
                        text = page.extract_text()
                        if text: full_text += text + "\n"
                except Exception as e:
                    st.error(f"2차 시도도 실패했습니다: {e}")

        # 디버깅용 텍스트 확인 (개발자 모드)
        with st.expander("🔍 추출된 텍스트 원본 확인하기 (클릭)"):
            if full_text.strip():
                st.text(full_text)
            else:
                st.warning("텍스트가 추출되지 않았습니다.")

# --- [엔진 2] 직접 붙여넣기 처리 ---
with tab2:
    st.info("💡 팁: PDF에서 복사가 안 되면 메모장에 먼저 붙여넣어 보세요. 메모장에서도 깨지면 '이미지'로 된 문서입니다.")
    manual_text = st.text_area("여기에 텍스트를 붙여넣고 Ctrl+Enter를 누르세요", height=300)
    if manual_text:
        full_text = manual_text

# --- 공통 분석 로직 ---
if full_text.strip():
    st.divider()
    
    # 1. 데이터 정제 (공백/줄바꿈 제거하여 검색 확률 높임)
    clean_text = full_text.replace(" ", "").replace("\n", "").replace("\t", "")
    
    # 2. 성명 추출 (이름이 2~4글자 한글)
    name_match = re.search(r'(?:성명|명성)[:\.]*([가-힣]{2,4})', clean_text)
    name = name_match.group(1) if name_match else "확인 불가"

    # 3. 학점 추출 (숫자 찾기)
    # "취득" 뒤에 오는 숫자들을 모두 찾음
    credit_matches = re.findall(r'취득[:\.]*(\d{2,3}(?:\.\d+)?)', clean_text)
    
    total_credit = 0.0
    if credit_matches:
        # 찾은 숫자 중 가장 큰 값 선택
        total_credit = max([float(c) for c in credit_matches])

    # 4. 인증 확인
    has_english = "외국어인증취득" in clean_text
    has_info = "정보인증취득" in clean_text

    # 결과 출력
    col1, col2 = st.columns(2)
    with col1:
        st.metric("이름", name)
    with col2:
        st.metric("총 취득 학점", f"{total_credit} 학점")

    # 상세 표
    st.subheader("📋 상세 결과")
    rows = []
    
    rows.append([
        "총 취득학점 (130)", 
        "✅ 충족" if total_credit >= 130 else "❌ 미충족", 
        f"{total_credit}점"
    ])
    rows.append([
        "외국어 인증", 
        "✅ 취득" if has_english else "❌ 미취득", 
        "-"
    ])
    rows.append([
        "정보 인증", 
        "✅ 취득" if has_info else "❓ 미취득", 
        "-"
    ])
    
    df = pd.DataFrame(rows, columns=["항목", "상태", "비고"])
    st.table(df)
    
    if total_credit == 0:
        st.error("⚠️ 텍스트는 읽었으나 '학점' 숫자를 찾지 못했습니다. 위의 '추출된 텍스트 원본 확인하기'를 눌러 내용을 확인해주세요.")
