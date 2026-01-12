# ... (상단 import 및 설정 코드는 동일) ...

# --- 3. UI 구성 (사이드바) ---
with st.sidebar:
    st.header("⚙️ 설정 및 신고")
    st.info("입학년도와 전공을 선택하세요.")
    
    # [수정 1] 드롭다운 연도 목록 생성 시 'area_courses' 키 제외하기
    if db:
        # db의 키 중 "area_courses"가 아닌 것만 숫자로 정렬해서 가져옴
        available_years = sorted([k for k in db.keys() if k != "area_courses"])
    else:
        available_years = ["2022", "2023"]
        
    selected_year = st.selectbox("입학년도", available_years)
    
    # ... (전공 선택 및 나머지 사이드바 코드는 동일) ...

# ... (메인 화면 및 분석 로직 부분 동일) ...

        if not pass_gen_area_elec:
            st.error(f"**[선택 교양영역 부족]** {missing_elec_count}개 영역에서 추가 수강이 필요합니다.")
            
            # [수정 2] 추천 강의 데이터 가져오기 (전역 설정 우선 사용)
            st.markdown("---")
            st.markdown("##### 💡 수강 추천 영역 및 강의")
            
            # 1순위: 해당 학과 설정에 'area_courses'가 있는지 확인
            rec_courses_map = gen_rule.get("area_courses", {})
            
            # 2순위: 없다면 JSON 최상위의 공통 'area_courses' 사용
            if not rec_courses_map:
                rec_courses_map = db.get("area_courses", {})
            
            # 아직 안 들은 영역 중에서 추천
            for area in unused_elec_areas:
                if area in rec_courses_map:
                    courses_str = ", ".join(rec_courses_map[area])
                    st.info(f"**[{area}]** 영역 추천 강의: {courses_str}")
                else:
                    st.info(f"**[{area}]** 영역의 강의를 찾아보세요.") # 데이터 없을 경우 안내
            
            st.caption("※ 위 추천 강의는 JSON 데이터 기반 예시이며, 실제 개설 여부는 포털을 확인하세요.")

# ... (나머지 하단 코드 동일) ...
