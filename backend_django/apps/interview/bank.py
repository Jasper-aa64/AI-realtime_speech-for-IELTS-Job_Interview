"""Curated practice material, independent of AI availability and IELTS seeds."""

CATEGORIES = [
    {"id": "cpp", "label": "C++ 基础与进阶"},
    {"id": "low_latency", "label": "低延迟与性能"},
    {"id": "systems", "label": "系统与并发"},
    {"id": "projects", "label": "项目深挖"},
    {"id": "behavioral", "label": "行为与沟通"},
]

_PROMPTS = {
    "cpp": [
        "解释 RAII 如何保证异常路径上的资源释放。请用你实际写过的 C++ 代码举例。",
        "unique_ptr、shared_ptr 和 weak_ptr 的所有权与成本有什么区别？何时避免 shared_ptr？",
        "vector 扩容时会发生什么？引用和迭代器何时失效，如何避免延迟尖峰？",
        "解释移动语义、完美转发及生命周期陷阱。给一个容易发生悬空引用的例子。",
        "C++ 原子操作的 relaxed、acquire 和 release 有什么区别？如何证明一条 SPSC 队列正确？",
        "什么时候选择虚函数，什么时候选择模板或静态多态？请说明代码大小与运行成本的取舍。",
    ],
    "low_latency": [
        "你会怎样定位 P99 延迟尖峰？请区分应用排队、操作系统调度、网络和业务处理时间。",
        "如果实时音频按 200 ms 成批上传，你如何降低延迟，同时证明没有丢音或降低识别质量？",
        "解释缓存行、false sharing 和内存布局如何影响吞吐与尾延迟。你会如何测量？",
        "热路径中预分配、对象池和零拷贝分别解决什么问题？什么时候优化反而增加复杂度或延迟？",
        "一个有界队列满了应该怎样处理？比较背压、拒绝、丢弃与无限缓冲对正确性和延迟的影响。",
        "怎样设计公平的性能对照实验？请说明预热、样本量、分位数、时钟和测量本身的开销。",
    ],
    "systems": [
        "如何设计可取消的工作线程？停止、解除阻塞、join 与资源销毁的顺序有什么风险？",
        "TCP、TLS 和 WebSocket 分别提供什么保证？为什么发送成功不等于对方完成处理？",
        "解释锁、无锁和无等待的区别。如何判断无锁实现是否适合你的实际工作负载？",
        "如何排查死锁和数据竞争？请说明 sanitizer 能证明什么、不能证明什么。",
        "网络断开后怎样恢复一个实时会话，防止旧回合回复或音频在新会话重播？",
        "多个线程需要向同一连接写数据时，你如何保证消息顺序、payload 生命周期和关闭安全？",
    ],
    "projects": [
        "选一个你投入最多的项目，用目标、约束、架构、个人贡献和结果五个部分介绍。",
        "讲一个项目中最难复现的问题。你如何收集证据、缩小范围并验证修复？",
        "你的项目最关键的设计取舍是什么？如果重做一次，会改变什么，为什么？",
        "如果面试官要求证明你的性能提升，你会展示什么基线、数据、配置和复现步骤？",
        "哪些功能已经真实落地，哪些仍是原型？你怎样诚实地解释限制和下一步？",
        "如果这个项目的用户增加十倍，最先遇到的瓶颈与故障模式是什么？",
    ],
    "behavioral": [
        "讲一次你与同事对技术方案意见不同的经历。如何用事实推动决定？",
        "用 STAR 结构讲一次你犯错并修复问题的经历，说明你如何防止再次发生。",
        "面对紧迫期限和不明确需求，你如何安排优先级并与相关人沟通？",
        "当你不知道面试问题的答案时，你会如何解释已知信息并推进分析？",
        "讲一次你主动学习陌生技术并完成交付的经历。如何验证自己真正理解？",
        "你为什么选择 C++ 和低延迟岗位？哪些项目证据能支持你的兴趣和能力？",
    ],
}

QUESTIONS = [
    {"id": f"{category}-{index}", "category": category, "prompt": prompt,
     "difficulty": "advanced" if category in {"low_latency", "systems"} else "intermediate", "source": "curated"}
    for category, prompts in _PROMPTS.items() for index, prompt in enumerate(prompts, 1)
]

BY_ID = {question["id"]: question for question in QUESTIONS}
