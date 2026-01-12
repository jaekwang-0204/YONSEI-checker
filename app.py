import streamlit as st
import pdfplumber
import re
import pandas as pd

st.set_page_config(page_title="졸업요건 진단기", page_icon="🎓")

st.title("🎓 연세대학교 졸업요건 진단 (Fast Ver.)")
st.markdown("""
**[안내]**
텍스트 복사가 가능한 **'원본 PDF 파일'**을 업로드해주세요.
이미지로 된 파일은 인식이 안 될 수 있습니다.
""")

st.divider()

# 탭 구성 (혹시 모를 상황 대비 수동 입력 유지)
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
                
                # 텍스트가 안 뽑히면 경고
                if not full_text.strip():
                    st.error("⚠️ 텍스트를 읽을 수 없습니다. (이미지 파일이거나 보안 문서)")
                    st.info("👉 옆의 '직접 붙여넣기' 탭을 이용해보세요.")
            except Exception as e:
                st.error(f"오류 발생: {e}")

# --- 탭 2: 직접 붙여넣기 ---
with tab2:
    st.caption("PDF 내용을 전체 복사(Ctrl+A, C)해서 여기에 붙여넣으세요.")
    manual_text = st.text_area("텍스트 입력", height=200)
    if manual_text:
        full_text = manual_text

# --- 공통 분석 로직 ---
if full_text:
    st.divider()
    
    # 1. 성명 추출 (파이프 '|' 기호 처리 추가)
    # 패턴: "성명" 또는 "명성" 뒤에 공백이나 특수문자(|, :)가 있고 그 뒤에 한글
    name_match = re.search(r'(?:성\s*명|명\s*성)[\s:\|]*([가-힣]{2,4})', full_text)
    name = name_match.group(1) if name_match else "확인 불가"

    # 2. 학점 추출 (숫자 수집 후 최대값)
    # "취득" 뒤에 오는 숫자들을 모두 찾음 (공백/콜론 무시)
    # 예: "취득: 130", "취득 18.5" 등
    credit_matches = re.findall(r'취득[:\s]*(\d{2,3}(?:\.\d+)?)', full_text)
    
    total_credit = 0.0
    if credit_matches:
        # 160학점 이상은 오타로 간주하고 제외 (OCR 잔재가 혹시 남을까봐 안전장치)
        valid_credits = [float(c) for c in credit_matches if float(c) < 160]
        if valid_credits:
            total_credit = max(valid_credits)

    # 3. 인증 확인 (공백 제거 후 검색)
    clean_text = full_text.replace(" ", "").replace("\n", "")
    # "외국어" + "취득" 또는 "영어" 등의 키워드 조합
    has_english = any(x in clean_text for x in ["외국어인증취득", "외국어인증:취득", "영어인증취득"])
    has_info = any(x in clean_text for x in ["정보인증취득", "정보인증:취득", "컴퓨터인증취득"])

    # --- 결과 출력 ---
    col1, col2 = st.columns(2)
    with col1:
        st.metric("이름", name)
    with col2:
        st.metric("총 취득 학점", f"{total_credit} 학점")

    # 상세 표
    st.subheader("📋 분석 리포트")
    rows = []
    
    # 학점 상태
    status_credit = "✅ 충족" if total_credit >= 130 else "❌ 미충족"
    rows.append(["총 취득학점 (130)", status_credit, f"{total_credit}점"])
    
    # 외국어 상태
    status_eng = "✅ 취득 완료" if has_english else "❌ 미취득"
    rows.append(["외국어 인증", status_eng, "졸업 필수"])
    
    # 정보 상태
    status_info = "✅ 취득 완료" if has_info else "❓ 미취득"
    rows.append(["정보 인증", status_info, "학과 요건 확인"])
    
    df = pd.DataFrame(rows, columns=["항목", "상태", "비고"])
    st.table(df)

    # 최종 메시지
    if total_credit >= 130 and has_english:
        st.success("🎉 축하합니다! 졸업 요건을 충족했습니다.")
        st.balloons()
    elif total_credit == 0:
        st.warning("⚠️ 학점 정보를 찾지 못했습니다. 텍스트 복사가 잘 되었는지 확인해주세요.")
    else:
        st.error("⚠️ 졸업 요건이 부족합니다. 부족한 항목을 채워주세요.")
        
    # 디버깅용 (텍스트 원본 확인 - 필요 없으면 주석 처리)
    with st.expander("개발자용: 텍스트 원본 보기"):
        st.text(full_text)
