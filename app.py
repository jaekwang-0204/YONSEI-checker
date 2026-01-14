def classify_course_logic(course_name, year, dept):
    """
    최적화된 분류 로직:
    1. RC 포함 -> 교양(리더십)
    2. 필수 교양 키워드 매칭 -> 필수교양
    3. 전공 키워드 매칭 -> 전공필수/선택
    4. 교양 영역 키워드 매칭 -> 선택교양(영역명)
    """
    norm_input = normalize_string(course_name) # 공백/특수문자 제거된 대문자 텍스트
    
    # [1] RC 및 리더십 특별 처리
    if "RC" in norm_input or "리더십" in norm_input:
        return "교양(리더십)"

    if year not in db or dept not in db[year]:
        return "기타"
    
    criteria_dept = db[year][dept]
    
    # [2] 필수 교양 과목 매칭 (채플, 글쓰기, 기독교 등)
    req_gen = criteria_dept.get("general_education", {}).get("required_courses", [])
    for rg in req_gen:
        for kw in rg["keywords"]:
            if normalize_string(kw) in norm_input:
                return "필수교양"

    # [3] 전공 과목 매칭
    known = criteria_dept.get("known_courses", {})
    for req in known.get("major_required", []):
        if normalize_string(req) in norm_input:
            return "전공필수"
    for sel in known.get("major_elective", []):
        if normalize_string(sel) in norm_input:
            return "전공선택"

    # [4] 선택 교양 영역별 매칭 (area_courses)
    for area, courses in db.get("area_courses", {}).items():
        for c in courses:
            if normalize_string(c) in norm_input:
                return f"교양({area})"

    return "선택교양" # 아무것도 해당 안 되면 일반 선택교양으로 분류
