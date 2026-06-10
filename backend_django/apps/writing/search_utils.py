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
    "parents": "parent",
    "teenagers": "teenager",
    "youths": "youth",
    "museums": "museum",
    "musem": "museum",
    "museumes": "museum",
    "admision": "admission",
    "admisson": "admission",
    "governments": "government",
    "goverment": "government",
    "controll": "control",
    "controlling": "control",
    "activities": "activity",
    "news": "news",
    "species": "species",
    "driverless": "driverless",
    "business": "business",
    "vehicles": "vehicle",
    "flights": "flight",
    "travelling": "travel",
    "traveling": "travel",
    "tourists": "tourist",
    "languages": "language",
    "cultures": "culture",
    "buildings": "building",
    "houses": "house",
    "homes": "home",
    "taxes": "tax",
    "advertisements": "advertisement",
    "criminals": "criminal",
    "residents": "resident",
    "inhabitants": "inhabitant",
    "neighbourhoods": "neighborhood",
    "neighborhoods": "neighborhood",
    "universities": "university",
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
    "leisure_holiday": [
        "weekend", "weekends", "working week", "shorter working week", "longer weekend", "holiday", "holidays",
        "summer holiday", "summer holidays", "school holiday", "school holidays", "vacation", "break", "leisure",
        "leisure time", "outdoor activities", "hiking", "climbing", "rest", "relax", "relaxing",
        "周末", "周六", "周日", "双休", "休息日", "工作周", "工作日", "假期", "暑假", "寒假", "学校假期", "放假", "休假", "休闲", "空闲时间", "户外活动",
    ],
    "decision_choice": [
        "decision", "decisions", "choice", "choices", "choose", "choosing", "difficult decision", "hard decision",
        "important decision", "too many choices",
        "决定", "选择", "抉择", "艰难的决定", "困难的决定", "重要决定", "难选",
    ],
    "lateness_delay": [
        "late", "being late", "delay", "delayed", "miss", "missed", "punctual", "punctuality", "on time",
        "迟到", "晚到", "延误", "耽误", "错过", "准时", "守时", "迟到的经历",
    ],
    "transport": [
        "transport", "transportation", "traffic", "traffic congestion", "car", "road", "railway", "train", "flight", "fly",
        "air travel", "public transport", "vehicle", "driverless", "commute", "commuting", "travel",
        "交通", "公共交通", "拥堵", "堵车", "汽车", "道路", "铁路", "火车", "飞机", "飞行", "航空", "通勤", "无人驾驶", "旅行", "旅游", "出行",
    ],
    "air_travel_pollution": [
        "air travel", "flight", "flights", "fly", "flying", "stop flying", "reduce flying", "air pollution", "fuel resources",
        "environmental benefits", "aviation", "airline",
        "航空", "飞行", "飞机", "航空旅行", "航空污染", "减少飞行", "停止飞行", "燃料", "燃料资源", "环境收益", "航班",
    ],
    "society": [
        "society", "social", "community", "individual", "public", "relationship",
        "社会", "社区", "个人", "人们", "公众", "人际关系",
    ],
    "crime": [
        "crime", "criminal", "punishment", "prison", "police", "lawbreaking", "robbery",
        "犯罪", "罪犯", "惩罚", "监狱", "警察",
    ],
    "media": [
        "media", "advertising", "advertisement", "television", "tv", "news", "newspaper", "social media", "internet news",
        "媒体", "广告", "电视", "新闻", "报纸", "社交媒体", "短视频", "网络媒体",
    ],
    "population": [
        "population", "resident", "residents", "inhabitant", "inhabitants",
        "人口", "居民",
    ],
    "city_housing": [
        "home", "owning a home", "own home", "rent", "renting", "rented", "housing", "house", "building", "apartment", "flat",
        "city", "cities", "urban", "rural", "countryside", "village", "town", "neighborhood", "neighbourhood", "living abroad", "migration", "move to cities",
        "住房", "房屋", "房子", "买房", "租房", "房租", "拥有住房", "租住", "居住", "住宅", "家", "房价", "公寓", "建筑", "城市", "城镇", "农村", "乡村", "村庄", "社区", "邻里", "搬到城市", "城市化", "移民", "住在国外",
    ],
    "money_economy": [
        "money", "save money", "saving money", "cost", "fee", "charge", "income", "salary", "tax", "taxes", "fund", "funding",
        "public money", "government spending", "price", "expensive", "afford", "economic", "economy", "financial",
        "钱", "存钱", "储蓄", "费用", "成本", "收费", "收入", "工资", "税", "税收", "资金", "政府支出", "公共资金", "价格", "昂贵", "负担", "经济", "金融",
    ],
    "public_services": [
        "public service", "public services", "healthcare", "education", "transport", "infrastructure", "museum", "library",
        "government", "law", "policy", "responsibility", "public money", "free of charge",
        "公共服务", "公共设施", "医疗服务", "教育服务", "基础设施", "博物馆", "图书馆", "政府", "政策", "责任", "公共资金", "免费服务",
    ],
    "family_age": [
        "family", "parent", "parents", "child", "children", "teenager", "young people", "old people", "elderly", "ageing", "aging",
        "retire", "retirement", "generation", "household", "family meal", "parenting",
        "家庭", "父母", "家长", "孩子", "儿童", "青少年", "年轻人", "老人", "老年人", "老龄化", "退休", "代际", "一代人", "家庭聚餐", "育儿",
    ],
    "ageing_population": [
        "ageing population", "aging population", "elderly people", "older people", "living longer", "retire", "retirement",
        "老龄化", "人口老龄化", "老龄社会", "老年人口", "老年人", "老人", "养老", "退休", "长寿",
    ],
    "culture_language": [
        "culture", "cultural", "language", "foreign language", "languages die out", "fewer languages", "music", "art", "museum", "gallery",
        "tradition", "traditional", "national", "local culture", "global culture",
        "文化", "语言", "外语", "语言消亡", "少数语言", "语言灭绝", "音乐", "艺术", "博物馆", "美术馆", "传统", "国家", "本地文化", "全球文化",
    ],
    "tourism_globalization": [
        "tourism", "tourist", "tourists", "travel", "foreign", "international", "global", "globalisation", "globalization",
        "global fashion", "global food", "imported food", "supermarket", "abroad", "countries", "world",
        "旅游", "游客", "旅行", "外国", "国际", "全球", "全球化", "全球时尚", "进口食物", "进口食品", "超市", "国外", "世界",
    ],
    "sports_outdoors": [
        "sport", "sports", "exercise", "fitness", "outdoor", "outdoor activities", "hiking", "climbing", "team sport",
        "physical activity", "athlete", "competition",
        "运动", "体育", "锻炼", "健身", "户外", "户外活动", "徒步", "爬山", "登山", "团队运动", "身体活动", "运动员", "比赛",
    ],
    "animals_nature": [
        "species", "loss of species", "extinction", "extinct", "endangered", "animal", "animals", "wildlife", "natural environment", "nature", "zoo", "plant", "plants", "forest",
        "物种", "物种灭绝", "灭绝", "濒危", "动物", "野生动物", "自然环境", "自然", "动物园", "植物", "森林", "动植物",
    ],
    "shopping_consumption": [
        "shopping", "consumer", "consumers", "buy", "purchase", "product", "products", "goods", "supermarket", "fashion",
        "advertising", "brand", "new products",
        "购物", "消费者", "消费", "购买", "产品", "商品", "超市", "时尚", "广告", "品牌", "新产品",
    ],
    "science_information": [
        "science", "aim of science", "scientific", "scientific research", "research", "information", "knowledge", "share information",
        "knowledge sharing", "academic", "business information", "technology research",
        "科学", "科学目标", "科学目的", "科研", "科学研究", "研究", "信息", "知识", "信息共享", "知识共享", "学术", "商业信息", "科研信息",
    ],
    "science_aim": [
        "aim of science", "important aim of science", "science should improve people's lives", "improve people's lives",
        "科学目标", "科学目的", "科学的目标", "科学的目的", "科学改善生活", "科学改善人们生活",
    ],
    "reading_books": [
        "read", "reading", "write", "writing", "book", "books", "printed book", "printed books", "newspaper", "newspapers",
        "literacy", "illiterate", "illiteracy", "adult education", "digital era", "electronically",
        "阅读", "读书", "写作", "书", "书籍", "纸质书", "印刷书", "报纸", "读写", "读写能力", "文盲", "扫盲", "成人教育", "电子书", "数字时代",
    ],
    "competition_cooperation": [
        "competition", "compete", "competing", "cooperate", "cooperation", "collaboration", "teamwork", "competitive",
        "university places", "major competitions",
        "竞争", "合作", "协作", "团队合作", "互相竞争", "大学名额竞争", "比赛竞争", "竞争合作",
    ],
    "building_history": [
        "history of the house", "history of the building", "house history", "building history", "old building", "historic building", "historical building",
        "房屋历史", "建筑历史", "老建筑", "历史建筑", "房子历史", "建筑物历史", "古建筑", "历史遗迹",
    ],
    "relationship_communication": [
        "relationship", "relationships", "communication", "communicate", "face-to-face", "face to face", "contact",
        "social problems", "practical problems", "meeting", "meetings",
        "人际关系", "关系", "沟通", "交流", "面对面", "面对面交流", "联系", "社交问题", "实际问题", "会议", "见面",
    ],
    "gender_equality": [
        "gender", "men", "women", "male", "female", "equality", "equal", "girls", "boys",
        "性别", "男女", "男性", "女性", "男人", "女人", "男孩", "女孩", "男女平等", "性别平等", "性别差异",
    ],
    "medical_treatment": [
        "medicine", "medical", "doctor", "treatment", "treatments", "alternative medicine", "alternative medicines",
        "hospital", "health problems", "therapy", "therapies",
        "医疗", "药物", "医生", "治疗", "替代疗法", "替代医疗", "医院", "健康问题", "疗法", "看医生",
    ],
    "driverless_vehicle": [
        "driverless", "driverless vehicle", "driverless vehicles", "driverless car", "driverless cars", "buses and trucks", "passenger", "passengers",
        "无人驾驶", "自动驾驶", "无人车", "无人驾驶汽车", "无人驾驶车辆", "乘客", "公交车", "卡车",
    ],
    "sugar_obesity": [
        "sugar", "sugary", "sugary products", "food and drink", "drink products", "obesity", "overweight", "diet",
        "processed food", "consume less sugar",
        "糖", "含糖", "含糖食品", "含糖饮料", "食品饮料", "肥胖", "超重", "饮食", "加工食品", "少吃糖",
    ],
    "community_charity": [
        "community", "community service", "charity", "volunteer", "voluntary", "unpaid", "neighbourhood", "neighborhood",
        "public property", "cleaning parks",
        "社区", "社区服务", "公益", "慈善", "志愿者", "义工", "无偿", "邻里", "公共财产", "清理公园",
    ],
    "reading_writing_task1": [
        "rent", "weekly rent", "apartment", "apartments", "international students", "students", "production", "consumption",
        "water consumption", "energy use", "waste disposal", "exports",
        "房租", "租金", "周租金", "公寓", "国际学生", "学生人数", "产量", "消费量", "用水量", "能源使用", "废物处理", "出口",
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
QUERY_EXPANSION_LIMIT = 96
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
