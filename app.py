# --- [기존 분석 로직 내부 - Tab 3 부분] ---

with tab3:
    final_courses = edited_df.to_dict('records')
    if final_courses:
        criteria = db[selected_year][selected_dept]
        known = criteria.get("known_courses", {})
        
        # 1. 일반 학점 계산
        total_sum = sum(c['학점'] for c in final_courses)
        maj_sum = sum(c['학점'] for c in final_courses if c['이수구분'] in ["전공필수", "전공선택"])
        
        # 2. [NEW] 3000~4000단위 학점 계산
        adv_keywords = known.get("advanced_keywords", [])
        advanced_sum = sum(c['학점'] for c in final_courses if any(kw in normalize_string(c['과목명']) for kw in adv_keywords))
        
        # 3. 리더십 및 필수교양 체크
        leadership_count = len([c for c in final_courses if "리더십" in str(c['이수구분']) or "RC" in normalize_string(c['과목명'])])
        
        # --- 결과 출력 ---
        st.header("🏁 졸업 자격 정밀 진단")
        
        # 판정 로직 보강
        pass_adv = advanced_sum >= criteria['advanced_course']
        pass_total = total_sum >= criteria['total_credits']
        pass_major = maj_sum >= criteria['major_total']
        
        is_pass = all([pass_total, pass_major, pass_adv, leadership_count >= 2])

        if is_pass: st.success("🎉 모든 졸업 요건을 충족했습니다!"); st.balloons()
        else: st.error("⚠️ 미충족된 졸업 요건이 있습니다.")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("총 취득학점", f"{int(total_sum)} / {criteria['total_credits']}")
        col2.metric("전공 합계", f"{int(maj_sum)} / {criteria['major_total']}")
        col3.metric("3~4천단위", f"{int(advanced_sum)} / {criteria['advanced_course']}")
        col4.metric("리더십(RC)", f"{leadership_count} / 2")

        # 상세 경고 메시지
        if not pass_adv:
            st.warning(f"💡 **3000~4000단위(심화) 학점**이 {int(criteria['advanced_course'] - advanced_sum)}학점 부족합니다.")
