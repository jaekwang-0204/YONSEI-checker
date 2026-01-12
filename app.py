import streamlit as st
import pytesseract
from pdf2image import convert_from_bytes
import re
import pandas as pd
from PIL import Image

st.set_page_config(page_title="졸업요건 진단기 (OCR)", page_icon="🎓")

st.title("🎓 연세대학교 졸업요건 진단 (OCR 버전)")
st.markdown("""
**[필독]**
이 PDF는 텍스트 복사가 안 되는 **'이미지형 문서'**입니다.
서버가 문서를 그림으로 변환해서 글자를 읽어내므로 **분석 시간이 조금 더 걸릴 수 있습니다.**
""")

st.divider()

uploaded_file = st.file_uploader("PDF 파일을 업로드하세요", type=["pdf", "png", "jpg", "jpeg"])

if uploaded_file is not None:
    with st.spinner('문서를 스캔하여 글자를 읽고 있습니다... (약 10~30초 소요)'):
        try:
            full_text = ""
            
            # 1. 파일 형식에 따라 이미지 변환
            images = []
            if uploaded_file.name.lower().endswith('.pdf'):
                # PDF를 이미지로 변환
                images = convert_from_bytes(uploaded_file.read())
            else:
                # 이미 이미지 파일인 경우
                images = [Image.open(uploaded_file)]

            # 2. OCR (글자 인식) 수행
            progress_bar = st.progress(0)
            for i, img in enumerate(images):
                # 한글+영어 모드로 읽기
                text = pytesseract.image_to_string(img, lang='kor+eng')
                full_text += text + "\n"
                progress_bar.progress((i + 1) / len(images))
            
            # --- 분석 로직 ---
            st.success("스캔 완료! 분석을 시작합니다.")
            
            # 공백 제거
            clean_text = full_text.replace(" ", "").replace("\n", "").replace("\t", "")
            
            # [디버깅] 인식된 텍스트 확인
            with st.expander("🔍 OCR이 읽어낸 텍스트 원본 보기"):
                st.text(full_text)

            # 1. 성명 추출
            name_match = re.search(r'(?:성명|명성)[:\.]*([가-힣]{2,4})', clean_text)
            name = name_match.group(1) if name_match else "인식 실패"

            # 2. 학점 추출 (숫자 찾기)
            # OCR은 오타가 날 수 있으므로 숫자 패턴을 더 유연하게 검색
            # 예: '취득' 뒤에 오는 숫자
            credit_matches = re.findall(r'취득[:\.]*.*?(\d{2,3}(?:\.\d+)?)', full_text.replace(" ", ""))
            
            total_credit = 0.0
            if credit_matches:
                # 가장 큰 숫자를 총점으로 간주
                total_credit = max([float(c) for c in credit_matches])

            # 3. 인증 확인
            has_english = "외국어인증취득" in clean_text
            has_info = "정보인증취득" in clean_text

            # --- 결과 출력 ---
            col1, col2 = st.columns(2)
            with col1:
                st.metric("이름 (OCR)", name)
            with col2:
                st.metric("총 취득 학점", f"{total_credit} 학점")

            st.write("---")
            
            # 상세 표
            rows = []
            rows.append(["총 취득학점 (130)", "✅ 충족" if total_credit >= 130 else "❌ 미충족", f"{total_credit}점"])
            rows.append(["외국어 인증", "✅ 인식됨" if has_english else "❌ 미인식", "-"])
            rows.append(["정보 인증", "✅ 인식됨" if has_info else "❓ 미인식", "-"])
            
            df = pd.DataFrame(rows, columns=["항목", "상태", "비고"])
            st.table(df)
            
            if total_credit == 0:
                st.warning("⚠️ 숫자를 찾지 못했습니다. 위의 '텍스트 원본 보기'를 눌러 '취득' 글자가 잘 인식되었는지 확인해주세요.")
                
        except Exception as e:
            st.error(f"오류 발생: {e}")
            st.error("혹시 Streamlit 설정을 재부팅 하셨나요? 'Reboot app'이 필요할 수 있습니다.")
