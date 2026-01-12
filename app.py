import streamlit as st
import pdfplumber
import re
import pandas as pd

# 페이지 설정
st.set_page_config(page_title="졸업요건 진단기", page_icon="🎓")

st.title("🎓 연세대학교 졸업요건 진단")
st.markdown("""
**[사용 방법]**
1. **'파일 업로드'** 탭에서 PDF를 넣어보세요.
2. 만약 분석이 안 되면 **'직접 붙여넣기'** 탭을 클릭해서 텍스트를 복사해 넣으세요.
""")

st.divider()

# 탭 나누기 (자동 vs 수동)
tab1, tab2 = st.tabs(["📂 파일 업로드 (자동)", "📝 직접 붙여넣기 (수동)"])

full_text = ""

# --- 탭 1: 파일 업로드 ---
with tab1:
    uploaded_file = st.file_uploader("PDF 파일을 여기에 업로드하세요.", type="pdf")
    if uploaded_file is not None:
        with st.spinner('성적표를 분석하고 있습니다...'):
            try:
                with pdfplumber.open(uploaded_file) as pdf:
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text:
                            full_text += text + "\n"
                
                if not full_text.strip():
                    st.error("⚠️ 이 PDF는 텍스트를 추출할 수 없는 보안 문서이거나 이미지입니다.")
                    st.info("👉 옆에 있는 **'직접 붙여넣기'** 탭을 이용해 주세요!")
            except Exception as e:
                st.error(f"오류 발생: {e}")

# --- 탭 2: 직접 붙여넣기 ---
with tab2:
    st.markdown("""
    **PDF 텍스트가 자동으로 안 읽힐 때 사용하세요.**
    1. 성적표 PDF를 내 컴퓨터에서 엽니다.
    2. **Ctrl + A** (전체 선택) → **Ctrl + C** (복사) 합니다.
    3. 아래 칸에 **Ctrl + V** (붙여넣기) 하고 **Ctrl + Enter**를 누르세요.
    """)
    manual_text = st.text_area("여기에 텍스트를 붙여넣으세요", height=300)
    if manual_text:
        full_text = manual_text

# --- 공통 분석 로직 (텍스트가 있을 때만 실행) ---
if full_text:
    st.divider()
    st.subheader("🔍 분석 결과")
    
    # 1. 데이터 정제 (모든 공백 제거)
    clean_text = full_text.replace(" ", "").replace("\n", "").replace("\t", "")

    # 2. 성명 추출
    name_match = re.search(r'(?:성명|명성)[:\.]*([가-힣]{2,4})', clean_text)
    name = name_match.group(1) if name_match else "확인 불가"

    # 3. 총 취득 학점 추출 (최대값 찾기)
    # "취득" 뒤에 오는 숫자들을 모두 찾아서 가장 큰 값을 선택
    credit_matches = re.findall(r'취득[:\.]*(\d{2,3}(?:\.\d+)?)', clean_text)
    
    total_credit = 0.0
    if credit_matches:
        float_credits = [float(c) for c in credit_matches]
        total_credit = max(float_credits)

    # 4. 졸업 인증 확인
    has_english = "외국어인증취득" in clean_text
    has_info = "정보인증취득" in clean_text

    # --- 결과 화면 출력 ---
    col1, col2 = st.columns(2)
    with col1:
        st.metric("이름", name)
    with col2:
        st.metric("총 취득 학점", f"{total_credit} 학점")

    # 상세 분석 결과 표
    rows = []
    
    # (1) 학점
    status_credit = "✅ 충족" if total_credit >= 130 else "❌ 미충족"
    note_credit = f"현재 {total_credit}학점" if total_credit >= 130 else f"{round(130 - total_credit, 2)}학점 부족"
    rows.append(["총 취득학점 (130학점)", status_credit, note_credit])
    
    # (2) 외국어
    status_eng = "✅ 취득 완료" if has_english else "❌ 미취득"
    rows.append(["외국어 인증", status_eng, "-" if has_english else "졸업 필수"])
    
    # (3) 정보
    status_info = "✅ 취득 완료" if has_info else "❓ 미취득"
    rows.append(["정보 인증", status_info, "-" if has_info else "학과 요건 확인 필요"])

    df_result = pd.DataFrame(rows, columns=["항목", "상태", "비고"])
    st.table(df_result)

    # 최종 판정 메시지
    if total_credit >= 130 and has_english:
        st.success("🎉 축하합니다! 졸업 요건을 모두 충족했습니다!")
        st.balloons()
    elif total_credit == 0:
        st.warning("⚠️ 텍스트에서 '학점' 정보를 찾지 못했습니다. 복사한 내용에 '취득'이라는 단어가 포함되어 있는지 확인해주세요.")
        with st.expander("내가 입력한 텍스트 확인하기"):
            st.text(full_text)
    else:
        st.error("⚠️ 졸업 요건이 부족합니다. 상세 내용을 확인하세요.")
