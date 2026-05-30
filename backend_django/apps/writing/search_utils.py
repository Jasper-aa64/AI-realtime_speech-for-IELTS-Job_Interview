import re


SEARCH_ALIASES = {
    "computers": "computer",
    "children": "child",
    "childrens": "child",
    "childs": "child",
    "schools": "school",
    "teachers": "teacher",
    "education": "study",
    "educational": "study",
    "learning": "study",
    "learn": "study",
    "important": "important",
    "essential": "important",
    "effective": "important",
    "effectively": "important",
    "charts": "graph",
    "chart": "graph",
    "graphs": "graph",
    "maps": "map",
    "processes": "process",
    "advantages": "advantage",
    "disadvantages": "disadvantage",
    "wasting": "waste",
    "wasted": "waste",
    "wasteful": "waste",
    "recycled": "recycle",
    "recycling": "recycle",
    "freshwater": "water",
    "fees": "fee",
    "charges": "charge",
    "charged": "charge",
    "cities": "city",
    "families": "family",
    "museums": "museum",
    "musem": "museum",
    "museumes": "museum",
    "admision": "admission",
    "admisson": "admission",
    "governments": "government",
    "goverment": "government",
    "controll": "control",
    "controlling": "control",
}
SEARCH_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "does", "for", "from", "have", "in", "is", "it", "of", "on", "or", "should", "that", "the", "their", "they", "to", "with",
}
QUERY_EXPANSIONS = {
    "water": [
        "water", "clean water", "water supply", "fresh water", "freshwater", "drinking water", "tap water",
        "水", "供水", "用水", "饮用水", "淡水", "净水", "清洁水", "自来水", "水资源",
    ],
    "free_charge": [
        "free", "free of charge", "without charge", "provided free", "charge", "fee", "cost",
        "免费", "不收费", "无偿", "费用", "收费", "付费",
    ],
    "waste": [
        "waste", "wasting", "wasted", "wasteful", "rubbish", "garbage", "trash",
        "浪费", "垃圾", "废弃物", "废物",
    ],
    "recycling": [
        "recycle", "recycling", "recycled", "reuse", "reusing",
        "回收", "循环利用", "再利用",
    ],
    "technology": [
        "computer", "internet", "technology", "technological", "digital", "online", "device", "smartphone", "phone", "robot", "ai",
        "电脑", "计算机", "互联网", "网络", "科技", "技术", "线上", "在线", "电子", "手机", "设备", "人工智能", "机器人",
    ],
    "education": [
        "education", "educational", "school", "teacher", "student", "study", "studying", "learning", "learn", "classroom", "university",
        "教育", "学习", "学校", "老师", "教师", "学生", "课堂", "课程", "大学", "校园",
    ],
    "children": [
        "child", "children", "kid", "young", "teenager", "youth", "parent",
        "孩子", "儿童", "小孩", "青少年", "年轻人", "父母", "家长",
    ],
    "importance": [
        "important", "essential", "valuable", "necessary", "benefit", "effective", "useful", "priority",
        "重要", "必要", "有用", "有效", "价值", "好处", "优先",
    ],
    "environment": [
        "environment", "environmental", "pollution", "climate", "energy", "resource", "plastic",
        "环境", "污染", "气候", "能源", "资源", "塑料",
    ],
    "health": [
        "health", "healthy", "medical", "medicine", "hospital", "doctor", "exercise", "fitness", "diet", "food", "disease",
        "健康", "医疗", "医院", "医生", "运动", "饮食", "食物", "疾病",
    ],
    "government": [
        "government", "public", "policy", "law", "tax", "fund", "funding", "responsibility",
        "政府", "公共", "政策", "法律", "税", "税收", "资金", "责任",
    ],
    "work": [
        "work", "job", "career", "employer", "employee", "company", "business", "salary", "profession",
        "工作", "职业", "雇主", "员工", "公司", "企业", "商业", "工资", "薪水", "薪资", "收入",
    ],
    "transport": [
        "transport", "traffic", "car", "road", "railway", "train", "flight", "travel",
        "交通", "汽车", "道路", "铁路", "火车", "飞机", "旅行", "旅游",
    ],
    "society": [
        "society", "social", "community", "people", "individual", "family", "culture", "global",
        "社会", "社区", "个人", "人们", "家庭", "文化", "全球",
    ],
    "crime": [
        "crime", "criminal", "punishment", "prison", "police", "lawbreaking", "robbery",
        "犯罪", "罪犯", "惩罚", "监狱", "警察",
    ],
    "media": [
        "media", "advertising", "advertisement", "television", "tv", "news", "newspaper", "social media",
        "媒体", "广告", "电视", "新闻", "报纸", "社交媒体",
    ],
    "population": [
        "population", "people", "resident", "residents", "inhabitant", "inhabitants",
        "人口", "居民",
    ],
    "task1_change": [
        "increase", "decrease", "rise", "fall", "trend", "compare", "comparison", "proportion", "percentage",
        "上升", "下降", "趋势", "对比", "比例", "百分比",
    ],
    "task1_visual": [
        "graph", "chart", "table", "map", "process", "diagram", "bar", "line", "pie",
        "图表", "表格", "地图", "流程", "柱状图", "折线图", "饼图",
    ],
    "museum": [
        "museum", "museums", "gallery", "galleries", "visitor", "visitors",
        "博物馆", "美术馆", "游客", "参观者",
    ],
}
QUERY_EXPANSION_LIMIT = 48
CHINESE_SINGLE_TERM_BLOCKS = {
    "水": ["薪水"],
}


def search_base_tokens(value: str | None) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", str(value or "").lower())
    normalized: list[str] = []
    for token in tokens:
        if token in SEARCH_STOPWORDS:
            continue
        replacement = SEARCH_ALIASES.get(token)
        if replacement:
            normalized.append(replacement)
        elif len(token) > 3 and token.endswith("s"):
            normalized.append(token[:-1])
        else:
            normalized.append(token)
    return normalized


def search_normalize(value: str | None) -> str:
    return " ".join(search_base_tokens(value))


def unique_terms(terms: list[str], limit: int = QUERY_EXPANSION_LIMIT) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for raw_term in terms:
        term = re.sub(r"\s+", " ", str(raw_term or "").strip().lower())
        if not term or term in seen:
            continue
        seen.add(term)
        unique.append(term)
        if len(unique) >= limit:
            break
    return unique


def chinese_term_matches(term: str, text: str) -> bool:
    if term not in text:
        return False
    if len(term) == 1 and any(blocked in text for blocked in CHINESE_SINGLE_TERM_BLOCKS.get(term, [])):
        return False
    return True


def expanded_search_terms(query: str | None) -> list[str]:
    text = str(query or "").lower()
    terms: list[str] = search_base_tokens(text)
    for concept_terms in QUERY_EXPANSIONS.values():
        matched = False
        for term in concept_terms:
            normalized_term = str(term).lower()
            if re.search(r"[\u4e00-\u9fff]", normalized_term):
                matched = chinese_term_matches(normalized_term, text)
            elif " " in normalized_term:
                matched = normalized_term in f" {search_normalize(text)} "
            else:
                matched = normalized_term in terms
            if matched:
                break
        if matched:
            for term in concept_terms:
                if not re.search(r"[\u4e00-\u9fff]", term):
                    terms.extend(search_base_tokens(term))
    return unique_terms(terms)


def query_concepts(query: str | None) -> list[str]:
    text = str(query or "").lower()
    base_terms = search_base_tokens(text)
    concepts: list[str] = []
    for concept, concept_terms in QUERY_EXPANSIONS.items():
        for term in concept_terms:
            normalized_term = str(term).lower()
            if re.search(r"[\u4e00-\u9fff]", normalized_term):
                matched = chinese_term_matches(normalized_term, text)
            elif " " in normalized_term:
                matched = search_normalize(normalized_term) in f" {search_normalize(text)} "
            else:
                matched = normalized_term in base_terms
            if matched:
                concepts.append(concept)
                break
    return unique_terms(concepts, limit=16)
