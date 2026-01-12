import streamlit as st
import pytesseract
from pdf2image import convert_from_bytes
import re
import pandas as pd
from PIL import Image

st.set_page_config(page_title="졸업요건 진단기 (OCR Final)", page_icon="🎓")

st.title("🎓 연세대학교 졸업요건 진단 (최종)")
st.markdown("""
**[시스템 상태]** OCR(광학 문자 인식) 엔진이 가동 중입니다.
이미지나 스캔된 PDF에서도 글자를 강제로 읽어냅니다.
""")

st.divider()

uploaded_file = st.file_uploader("PDF 파일을 업로드하세요", type=["pdf", "png", "jpg", "jpeg"])

if uploaded_file is not None:
    with st.spinner('문서를 정밀 분석 중입니다...'):
        try:
            full_text = ""
            
            # 1. 이미지 변환 및 OCR
            images = []
            if uploaded_file.name.lower().endswith('.pdf'):
                images = convert_from_bytes(uploaded_file.read())
            else:
                images = [Image.open(uploaded_file)]

            # OCR 수행 (한글/영어 혼합)
            for img in images:
                text = pytesseract.image_to_string(img, lang='kor+eng')
                full_text += text + "\n"
            
            # --- [핵심 수정 구간] 데이터 분석 로직 ---
            
            # 1. 성명 추출 (OCR 오타 보정)
            # 패턴: "명" 글자 뒤에 특수문자(|, !, 1)나 공백이 오고 그 뒤에 한글 2~4자
            # 예: "4 명 | 이재광" -> "이재광" 추출
            name_match = re.search(r'명\s*[:\|\!1l\s]*([가-힣]{2,4})', full_text)
            name = name_match.group(1) if name_match else "인식 실패"

            # 2. 학점 추출 (195점 오류 해결)
            # 모든 숫자 추출
            all_numbers = re.findall(r'취득[:\.\s]*(\d{2,3})', full_text)
            
            valid_credits = []
            if all_numbers:
                for num_str in all_numbers:
                    val = float(num_str)
                    # [중요] 160학점 이상은 '19.5'에서 점이 빠진 오타로 간주하고 제외
                    if val < 160: 
                        valid_credits.append(val)
            
            # 유효한 숫자 중 최대값이 진짜 누계 학점 (보통 130~150 사이)
            total_credit = max(valid_credits) if valid_credits else 0.0

            # 3. 인증 확인 (검색 조건 완화)
            # 공백을 모두 제거한 텍스트에서 키워드 검색
            clean_text_for_cert = full_text.replace(" ", "").replace("\n", "")
            
            # "외국어" 또는 "TOEIC" 등이 보이면 인정
            has_english = any(x in clean_text_for_cert for x in ["외국어", "영어", "TOEIC", "토익"])
            # "정보" 또는 "MOS" 등이 보이면 인정
            has_info = any(x in clean_text_for_cert for x in ["정보", "컴퓨터", "MOS"])

            # --- 결과 출력 ---
            col1, col2 = st.columns(2)
            with col1:
                st.metric("이름", name)
            with col2:
                st.metric("총 취득 학점", f"{total_credit} 학점")

            st.write("---")
            
            # 디버깅용 (텍스트 원본 확인)
            with st.expander("🔍 OCR이 읽어낸 텍스트 원본 보기"):
                st.text(full_text)

            # 상세 표
            rows = []
            rows.append(["총 취득학점 (130)", "✅ 충족" if total_credit >= 130 else "❌ 미충족", f"{total_credit}점"])
            rows.append(["외국어 인증", "✅ 확인됨" if has_english else "❌ 미확인", "키워드: 외국어/영어"])
            rows.append(["정보 인증", "✅ 확인됨" if has_info else "❓ 미확인", "키워드: 정보/컴퓨터"])
            
            df = pd.DataFrame(rows, columns=["항목", "상태", "비고"])
            st.table(df)
            
            if total_credit >= 130:
                st.success("🎉 OCR 분석 결과, 졸업 학점을 충족한 것으로 보입니다!")
            else:
                st.warning("⚠️ 학점이 부족하거나 OCR 인식이 부정확할 수 있습니다.")

        except Exception as e:
            st.error(f"오류 발생: {e}")
