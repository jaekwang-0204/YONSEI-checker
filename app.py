import streamlit as st
import pdfplumber
import re
import pandas as pd

# 페이지 설정
st.set_page_config(page_title="졸업요건 진단기", page_icon="🎓")

st.title("🎓 연세대학교 졸업요건 자동 진단")
st.markdown("""
**[사용 안내]**
1. 학교 포털에서 내려받은 **성적증명서(PDF)**를 업로드하세요.
2. 이 서비스는 파일을 서버에 저장하지 않으며, 분석 후 즉시 메모리에서 삭제합니다.
""")

st.divider()

uploaded_file = st.file_uploader("PDF 파일을 여기에 업로드하세요.", type="pdf")

if uploaded_file is not None:
    with st.spinner('성적표를 정밀 분석하고 있습니다...'):
        try:
            # 1. 텍스트 추출 (pdfplumber 활용)
            full_text = ""
            with pdfplumber.open(uploaded_file) as pdf:
                for page in pdf.pages:
                    # extract_text가 None일 경우 대비
                    page_text = page.extract_text()
                    if page_text:
                        full_text += page_text + "\n"

            # ---------------------------------------------------------
            # [디버깅 기능] 추출된 텍스트가 비어있거나 이상한지 눈으로 확인하는 창
            # 만약 결과가 안 나오면 이 탭을 열어서 글자가 잘 읽혔는지 확인하세요.
            with st.expander("🔍 (개발자용) 텍스트 추출 결과 보기"):
                if not full_text.strip():
                    st.error("텍스트가 추출되지 않았습니다! (이미지 스캔본이거나 암호화된 파일일 수 있습니다)")
                else:
                    st.text(full_text)
            # ---------------------------------------------------------

            # 2. 데이터 정제 (핵심: 모든 공백과 줄바꿈 제거)
            # "취 득 : 1 3 0" -> "취득:130"으로 만들어서 검색 성공률을 높임
            clean_text = full_text.replace(" ", "").replace("\n", "").replace("\t", "")

            # 3. 성명 추출
            # 공백 없는 상태에서 '성명' 또는 '명성' 뒤에 오는 한글 찾기
            name_match = re.search(r'(?:성명|명성)[:\.]*([가-힣]{2,4})', clean_text)
            name = name_match.group(1) if name_match else "확인 불가"

            # 4. 총 취득 학점 추출 (강력한 로직)
            # 공백 없는 상태에서 '취득'이라는 글자 뒤에 나오는 숫자들을 모두 수집
            # 예: "취득:130", "취득18.5" 등
            credit_matches = re.findall(r'취득[:\.]*(\d{2,3}(?:\.\d+)?)', clean_text)
            
            total_credit = 0.0
            if credit_matches:
                # 찾은 숫자들 중 가장 큰 값을 총 학점으로 선택 (누계 학점은 항상 최대값이므로)
                float_credits = [float(c) for c in credit_matches]
                total_credit = max(float_credits)

            # 5. 졸업 인증 확인
            has_english = "외국어인증취득" in clean_text
            has_info = "정보인증취득" in clean_text

            # --- 결과 화면 출력 ---
            col1, col2 = st.columns(2)
            with col1:
                st.metric("이름", name)
            with col2:
                st.metric("총 취득 학점", f"{total_credit} 학점")

            st.write("---")

            # 상세 분석 결과 표
            st.subheader("📋 상세 분석 결과")
            
            # 데이터프레임 생성
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
                st.warning("⚠️ 학점을 읽지 못했습니다. 위의 '텍스트 추출 결과 보기'를 눌러 내용이 비어있는지 확인해주세요.")
            else:
                st.error("⚠️ 졸업 요건이 부족합니다. 상세 내용을 확인하세요.")

        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")
