import streamlit as st
import pdfplumber
import re
import pandas as pd

# 페이지 기본 설정
st.set_page_config(
    page_title="졸업요건 진단기",
    page_icon="🎓",
    layout="centered"
)

# 제목 및 안내
st.title("🎓 연세대학교 졸업요건 자동 진단")
st.markdown("""
학교 포털에서 내려받은 **성적증명서(PDF)**를 업로드하세요.  
이 서비스는 파일을 서버에 저장하지 않으며, 분석 후 즉시 메모리에서 삭제합니다.
""")

st.divider()

# 파일 업로드 위젯
uploaded_file = st.file_uploader("여기에 PDF 파일을 드래그하거나 클릭해서 업로드하세요.", type="pdf")

if uploaded_file is not None:
    # 분석 중임을 표시
    with st.spinner('성적표를 분석하고 있습니다...'):
        try:
            full_text = ""
            # pdfplumber를 사용하여 텍스트 추출 (한글 폰트 문제 해결)
            with pdfplumber.open(uploaded_file) as pdf:
                for page in pdf.pages:
                    full_text += page.extract_text() + "\n"
            
            # --- 데이터 분석 로직 ---
            
            # 1. 공백 제거 버전 (키워드 검색용)
            clean_text = full_text.replace(" ", "").replace("\n", "")
            
            # 2. 성명 추출
            # "성 명" 또는 "명 성" 패턴 찾기
            name_match = re.search(r'(?:성\s*명|명\s*성)[\s:]*([가-힣]{2,4})', full_text)
            name = name_match.group(1) if name_match else "확인 불가"
            
            # 3. 총 취득 학점 추출 (최대값 찾기 전략)
            # 문서 내 "취득" 주변의 숫자를 모두 찾아 가장 큰 값을 총점으로 간주
            credit_matches = re.findall(r'취득[:\s]*(\d{2,3}(?:\.\d+)?)', full_text)
            total_credit = 0.0
            if credit_matches:
                total_credit = max([float(c) for c in credit_matches])
            
            # 4. 졸업 인증 여부 확인
            has_english = "외국어인증취득" in clean_text
            has_info = "정보인증취득" in clean_text
            
            # --- 결과 화면 출력 ---
            
            # 요약 정보 표시
            col1, col2 = st.columns(2)
            with col1:
                st.metric(label="이름", value=name)
            with col2:
                st.metric(label="총 취득 학점", value=f"{total_credit} 학점")
            
            st.write("---")
            
            # 상세 상태판
            st.subheader("📋 상세 분석 결과")
            
            result_data = {
                "항목": ["총 취득학점 (130학점 기준)", "외국어 인증", "정보 인증"],
                "상태": [],
                "비고": []
            }
            
            # 학점 판정
            if total_credit >= 130:
                result_data["상태"].append("✅ 충족")
                result_data["비고"].append(f"현재 {total_credit}학점")
            else:
                result_data["상태"].append("❌ 미충족")
                result_data["비고"].append(f"{130 - total_credit}학점 부족")
                
            # 외국어 판정
            if has_english:
                result_data["상태"].append("✅ 취득 완료")
                result_data["비고"].append("-")
            else:
                result_data["상태"].append("❌ 미취득")
                result_data["비고"].append("졸업 필수")
                
            # 정보인증 판정
            if has_info:
                result_data["상태"].append("✅ 취득 완료")
                result_data["비고"].append("-")
            else:
                result_data["상태"].append("❓ 미취득")
                result_data["비고"].append("학과 요건 확인 필요")

            # 표 그리기
            df = pd.DataFrame(result_data)
            st.table(df)
            
            # 최종 메시지
            if total_credit >= 130 and has_english:
                st.success("🎉 축하합니다! 졸업 요건을 충족할 가능성이 매우 높습니다.")
                st.balloons()
            else:
                st.warning("⚠️ 아직 졸업 요건이 부족합니다. 위의 부족한 항목을 확인해주세요.")
                
        except Exception as e:
            st.error("파일을 읽는 도중 오류가 발생했습니다.")
            st.error(f"에러 메시지: {e}")