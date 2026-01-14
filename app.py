# --- 5. 최종 분석 결과 표시 (심화학점 및 교양 리스트 포함) ---
        st.divider()
        final_courses = edited_df.to_dict('records')
        
        if final_courses:
            criteria = db[selected_year][selected_dept]
            gen = criteria.get("general_education", {})
            known = criteria.get("known_courses", {})
            
            # 1. 학점 계산
            total_sum = sum(c['학점'] for c in final_courses)
            maj_req = sum(c['학점'] for c in final_courses if c['이수구분'] == "전공필수")
            maj_sel = sum(c['학점'] for c in final_courses if c['이수구분'] == "전공선택")
            maj_total_sum = maj_req + maj_sel

            # 2. 심화 학점 계산
            adv_keywords = known.get("advanced_keywords", [])
            advanced_sum = sum(c['학점'] for c in final_courses if any(kw in normalize_string(c['과목명']) for kw in adv_keywords))
            
            # 3. 리더십 및 필수교양 체크
            leadership_count = len([c for c in final_courses if "리더십" in str(c['이수구분']) or "RC" in normalize_string(c['과목명'])])
            search_names = " ".join([c['과목명'] for c in final_courses])
            
            # 4. 교양 영역 이수 현황 분석
            passed_areas = set()
            for area, area_course_list in db.get("area_courses", {}).items():
                for course in final_courses:
                    if any(normalize_string(ac) in normalize_string(course['과목명']) for ac in area_course_list):
                        passed_areas.add(area)
            
            # 부족한 영역 확인
            all_req_areas = set(gen.get("required_areas", []))
            missing_areas = all_req_areas - passed_areas

            # --- 결과 출력 ---
            st.header("🏁 졸업 자격 예비진단 리포트")
            
            pass_advanced = advanced_sum >= criteria['advanced_course']
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("총 취득학점", f"{int(total_sum)} / {criteria['total_credits']}")
            col2.metric("전공 합계", f"{int(maj_total_sum)} / {criteria['major_total']}")
            col3.metric("3~4천단위(심화)", f"{int(advanced_sum)} / {criteria['advanced_course']}", delta=int(advanced_sum - criteria['advanced_course']))
            col4.metric("리더십(RC)", f"{leadership_count} / 2")

            # --- [추가 기능] 부족 항목 상세 가이드 ---
            if not pass_advanced or missing_areas:
                st.markdown("### 💡 부족 요건 보완 가이드")
                
                # 심화 학점 부족 시 강의 리스트 출력
                if not pass_advanced:
                    with st.expander("🔴 3000~4000단위(심화) 추천 강의 리스트", expanded=True):
                        st.info(f"심화 학점이 {int(criteria['advanced_course'] - advanced_sum)}학점 부족합니다. 아래 강의들을 확인하세요.")
                        # JSON의 major_required와 elective 중 심화 키워드에 해당하는 것들 필터링
                        adv_list = [c for c in known['major_required'] + known['major_elective'] if any(kw in normalize_string(c) for kw in adv_keywords)]
                        st.write(", ".join(sorted(list(set(adv_list)))))

                # 교양 영역 부족 시 강의 리스트 출력
                if missing_areas:
                    with st.expander("🟠 부족한 교양 이수 영역 추천 강의", expanded=True):
                        st.warning(f"필수 교양 영역 중 **{', '.join(missing_areas)}** 영역 이수가 필요합니다.")
                        for area in missing_areas:
                            st.subheader(f"📍 {area} 영역")
                            area_recs = db.get("area_courses", {}).get(area, ["등록된 강의 없음"])
                            st.write(", ".join(area_recs))
            
            if all([total_sum >= criteria['total_credits'], pass_advanced, len(missing_areas) == 0]):
                st.success("✅ 현재까지 모든 요건을 충족하고 있습니다!")
                st.balloons()
