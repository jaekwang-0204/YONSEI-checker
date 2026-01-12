import streamlit as st
import pdfplumber
import re
import pandas as pd

st.set_page_config(page_title="졸업요건 진단기 (사정용)", page_icon="🎓")

st.title("🎓 연세대 졸업요건 진단 (사정용 성적표)")
st.markdown("""
**[안내]**
**'제1전공 사정용 성적표'** PDF를 업로드하거나 텍스트를 붙여넣으세요.
총 취득학점과 전공(필수/선택) 이수 현황을 분석합니다.
""")

st.divider()

# 탭 구성
tab1, tab2 = st.tabs(["📂 파일 업로드", "📝 직접 붙여넣기"])

full_text = ""

# --- 탭 1: 파일 업로드 ---
with tab1:
    uploaded_file = st.file_uploader("PDF 파일을 업로드하세요", type="pdf")
    if uploaded_file is not None:
        with st.spinner('문서 분석 중...'):
            try:
                with pdfplumber.open(uploaded_file) as pdf:
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text: full_text += text + "\n"
            except Exception as e:
                st.error(f"오류 발생: {e}")

# --- 탭 2: 직접 붙여넣기 ---
with tab2:
    st.caption("PDF 내용을 전체 복사(Ctrl+A, C)해서 여기에 붙여넣으세요.")
    manual_text = st.text_area("텍스트 입력", height=200)
    if manual_text:
        full_text = manual_text

# --- 분석 로직 ---
if full_text:
    st.divider()
    
    # 1. 공백 제거 버전 생성 (검색 용이성)
    clean_text = full_text.replace(" ", "").replace("\n", "").replace("\t", "")

    # 2. 성명 추출
    # "성명: 이재광" 패턴
    name_match = re.search(r'성명[:\s]*([가-힣]{2,4})', full_text)
    name = name_match.group(1) if name_match else "확인 불가"

    # 3. 학점 추출 로직 (사정용 성적표 특화)
    
    # (1) 총 취득학점 ("취득학점: 141" 또는 "학점계: 141")
    total_match = re.search(r'(?:취득학점|학점계)[:\s]*(\d{2,3})', full_text)
    total_credit = float(total_match.group(1)) if total_match else 0.0

    # (2) 전공필수 ("전공필수 39")
    major_req_match = re.search(r'전공필수[:\s]*(\d{1,3})', full_text)
    major_req_credit = float(major_req_match.group(1)) if major_req_match else 0.0

    # (3) 전공선택 ("전공선택 46")
    major_sel_match = re.search(r'전공선택[:\s]*(\d{1,3})', full_text)
    major_sel_credit = float(major_sel_match.group(1)) if major_sel_match else 0.0
    
    # (4) 3~4천단위 ("3~4천단위: 68") -> 졸업요건에 중요한 경우 많음
    upper_level_match = re.search(r'3~4천단위[:\s]*(\d{1,3})', full_text)
    upper_level_credit = float(upper_level_match.group(1)) if upper_level_match else 0.0

    # --- 결과 출력 ---
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("이름", name)
    with col2:
        st.metric("총 취득 학점", f"{int(total_credit)} 학점")
    with col3:
        st.metric("전공 총 학점", f"{int(major_req_credit + major_sel_credit)} 학점")

    st.write("---")

    # 상세 분석 리포트
    st.subheader("📋 이수 현황 상세")
    
    rows = []
    
    # 1. 총 학점
    status_total = "✅ 충족" if total_credit >= 130 else "❌ 미충족" # 기준 130 가정
    rows.append(["총 취득학점 (기준: 130)", status_total, f"{int(total_credit)}점"])
    
    # 2. 전공 필수
    # 학과마다 기준이 다르므로 점수만 표시
    rows.append(["전공필수", "ℹ️ 확인 필요", f"{int(major_req_credit)}점"])
    
    # 3. 전공 선택
    rows.append(["전공선택", "ℹ️ 확인 필요", f"{int(major_sel_credit)}점"])
    
    # 4. 3~4천단위 (심화과목)
    rows.append(["3~4천단위 과목", "-", f"{int(upper_level_credit)}점"])

    df = pd.DataFrame(rows, columns=["구분", "상태", "취득 학점"])
    st.table(df)

    # 안내 메시지
    if total_credit >= 130:
        st.success(f"🎉 {name}님, 총 {int(total_credit)}학점으로 졸업 기준 학점(130)을 넘으셨습니다!")
        st.info("※ 전공 필수/선택 세부 요건은 학과 규정에 따라 다를 수 있으니 위 표를 참고하세요.")
    elif total_credit == 0:
        st.warning("⚠️ 학점 정보를 찾지 못했습니다. 텍스트 복사가 잘 되었는지 확인해주세요.")
    else:
        st.error(f"⚠️ 총 학점이 {130 - int(total_credit)}점 부족합니다.")

    # 디버깅용 (원본 텍스트 확인)
    with st.expander("개발자용: 원본 텍스트 보기"):
        st.text(full_text)
