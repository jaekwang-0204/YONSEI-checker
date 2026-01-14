# --- 5. 최종 분석 결과 표시 (보완 가이드 기능 강화) ---
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
            # 현재 수강한 모든 과목에 대해 영역 매칭 수행
            for course in final_courses:
                course_norm = normalize_string(course['과목명'])
                for area, area_course_list in db.get("area_courses", {}).items():
                    if any(normalize_string(ac) in course_norm for ac in area_course_list):
                        passed_areas.add(area)
            
            # 부족한 영역 확인 (JSON에 정의된 필수 영역 기준)
            all_req_areas = set(gen.get("required_areas", []))
            missing_areas = sorted(list(all_req_areas - passed_areas))

            # 필수교양(단일과목) 미이수 리스트 생성
            req_fail = []
            for item in gen.get("required_courses", []):
                if item['name'] == "리더십":
                    if leadership_count < 2: req_fail.append("리더십(RC포함 2과목)")
                    continue
                if not any(normalize_string(kw) in normalize_string(search_names) for kw in item["keywords"]):
                    req_fail.append(item['name'])

            # 최종 판정 변수
            pass_total = total_sum >= criteria['total_credits']
            pass_major_total = maj_total_sum >= criteria['major_total']
            pass_major_req = maj_req >= criteria['major_required']
            pass_advanced = advanced_sum >= criteria['advanced_course']
            pass_req_courses = len(req_fail) == 0
            pass_areas = len(missing_areas) == 0

            is_all_pass = all([pass_total, pass_major_total, pass_major_req, pass_advanced, pass_req_courses, pass_areas])

            # --- 결과 출력 ---
            st.header("🏁 졸업 자격 예비진단 리포트")
            if is_all_pass: 
                st.success("🎉 축하합니다! 모든 졸업 요건을 충족했습니다."); st.balloons()
            else: 
                st.error("⚠️ 아직 충족되지 않은 요건이 있습니다. 아래 대시보드와 보완 가이드를 확인하세요.")

            # 대시보드 메트릭
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("총 취득학점", f"{int(total_sum)} / {criteria['total_credits']}", delta=int(total_sum - criteria['total_credits']))
            m2.metric("전공 합계", f"{int(maj_total_sum)} / {criteria['major_total']}")
            m3.metric("3~4000 단위(심화)", f"{int(advanced_sum)} / {criteria['advanced_course']}", delta=int(advanced_sum - criteria['advanced_course']), delta_color="normal")
            m4.metric("리더십(RC 포함)", f"{leadership_count} / 2")

            # --- [핵심 추가 기능] 부족 요건 상세 보완 가이드 ---
            if not is_all_pass:
                st.markdown("### 💡 부족 요건 보완 가이드")
                
                # 1. 심화 학점 부족 시 강의 리스트 출력
                if not pass_advanced:
                    with st.expander("🔴 3000~4000단위(심화) 추천 강의 리스트", expanded=True):
                        st.info(f"심화 학점이 **{int(criteria['advanced_course'] - advanced_sum)}학점** 부족합니다. 아래 과목 이수를 권장합니다.")
                        # 전공 필수/선택 리스트 중 심화 키워드에 해당하는 과목 추출
                        all_major_list = known.get('major_required', []) + known.get('major_elective', [])
                        adv_recs = [c for c in all_major_list if any(kw in normalize_string(c) for kw in adv_keywords)]
                        st.write(", ".join(sorted(list(set(adv_recs)))))

                # 2. 교양 영역 부족 시 해당 영역 강의 리스트 출력
                if missing_areas:
                    with st.expander("🟠 부족한 교양 이수 영역 및 추천 강의", expanded=True):
                        st.warning(f"필수 교양 영역 중 **{', '.join(missing_areas)}** 영역 이수가 필요합니다.")
                        for area in missing_areas:
                            st.subheader(f"📍 {area} 영역 추천 과목")
                            area_recs = db.get("area_courses", {}).get(area, ["등록된 정보가 없습니다."])
                            st.write(", ".join(area_recs))

                # 3. 기타 필수 요건 안내
                if not pass_major_req or req_fail:
                    with st.expander("⚪ 기타 미달 요건"):
                        if not pass_major_req:
                            st.write(f"- **전공필수 학점 부족:** {int(criteria['major_required'] - maj_req)}학점 더 수강해야 합니다.")
                        if req_fail:
                            st.write(f"- **미이수 필수 과목:** {', '.join(req_fail)}")
            
            with st.expander("📊 수강 과목 상세 통계 (수정 가능)"):
                st.dataframe(pd.DataFrame(final_courses), use_container_width=True)
        else:
            st.info("성적표 이미지를 업로드하고 분석 버튼을 눌러주세요.")
