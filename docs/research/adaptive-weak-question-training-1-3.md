# IELTS 自适应弱项回采样与题库训练研究 v1.3

日期：2026-05-10

## 0. 研究定位

这份文档回答一个新功能问题：系统如何持续遍历题库，把低分、未理解题意、或者明显薄弱的回答保存下来，并让这些题目在后续训练中更高频地出现。

结论先说在前面：

1. 这不是简单的“低分题多出几次”。
2. 这必须是一个**用户能力 - 题目难度 - 答题偏差 - 复现策略**的统计模型。
3. “弱题”应该分成**对某个用户弱**和**全局弱题候选**两层，不能把一次失误直接当成题目永久差。
4. 题目重现频率应该由**后验概率、信息增益、遗忘效应、曝光控制**共同决定，而不是手写权重表。

## 1. 目标定义

我们要解决的是三类信号：

| 信号 | 含义 | 示例 |
| --- | --- | --- |
| 低分 | 语言质量差 | band 低、句法乱、词汇重复、展开不足 |
| 没理解题意 | 相关性差 | 回答了别的话题，或者只抓住了局部关键词 |
| 薄弱题目 | 题目对用户形成稳定困难 | 同一主题 / 同一问法多次表现差，且不是偶发噪声 |

这三类信号不能混为一谈。  
一个高分但跑题的回答，和一个低分但内容相关的回答，教育意义完全不同。

## 2. 当前仓库能支持什么

当前仓库已经有：

* 题库 JSON
* 回答 attempts
* turn 级别 transcript / score / report
* 历史页和报告页

但当前没有：

* item-level difficulty 表
* user-item mastery 状态
* weak-question registry
* replay scheduler
* exposure control
* 统计置信度和后验阈值

所以这个功能的第一版应当先补“数据模型”，再补“训练策略”。

## 3. 为什么不能用玩具算法

如果只是写成：

```text
如果 score < 5 就把题目权重 +1
如果 off-topic 就把题目权重 +2
```

这会有三个问题：

1. **样本噪声会放大**：一次偶发失误会把题目错误标成弱题。
2. **反馈回路会失真**：弱题越出越多，模型以为它更弱，但其实只是被更频繁地采样。
3. **个体弱项和题目弱项混淆**：用户弱，不等于题目本身弱。

所以必须引入统计建模。

## 4. 推荐建模框架

### 4.1 观测层

对每次作答 `x_{u,q,t}`，至少记录：

* `s_{u,q,t,d}`：四维评分或估计分，`d ∈ {FC, LR, GRA, Pron}`
* `r_{u,q,t}`：相关性 / 是否理解题意
* `c_{u,q,t}`：评分置信度或 fallback 标志
* `l_{u,q,t}`：作答长度、停顿、重复等辅助特征
* `m_{u,q,t}`：模型版本、时间戳、题目版本

其中 `r` 需要单独建模，不应被总分吞掉。

### 4.2 能力 - 难度层

推荐用 IRT 或 ordinal / graded response model 来建模。

一个可执行的形式是：

```math
P(Y_{uqd} \ge k) = \sigma\left(a_{qd}\,(\theta_{ud} - b_{qdk})\right)
```

其中：

* `u` = 用户
* `q` = 题目
* `d` = 维度
* `k` = 评分阈值
* `θ` = 用户在该维度上的潜在能力
* `a` = 题目区分度
* `b` = 题目难度阈值
* `σ` = logistic function

为什么这个方向合理：

* IELTS band 是**序数尺度**，不是连续真值。
* 同一个题目对不同用户难度不同。
* 同一个用户在不同维度上的能力不同。

### 4.3 理解题意层

“没理解题目意思”不能只靠总分判断，要单独估计相关性后验：

```math
P(R_{u,q,t}=1 \mid x_{u,q,t}) = \sigma(w^\top \phi(x_{u,q,t}) + \beta_q)
```

其中 `φ(x)` 可以来自：

* prompt 与 answer 的语义相似度
* 关键词覆盖率
* off-topic 分类器
* “答非所问”人工标签

如果 `R` 很低，但语言分不一定低，这通常说明是**理解偏差**，不是纯语言薄弱。

### 4.4 用户-题目弱项层

弱项应该分成两层：

#### 4.4.1 对用户弱

```math
W_{u,q} = \alpha \cdot P(Y \le \tau \mid data) + \beta \cdot P(R=0 \mid data) + \gamma \cdot U_{u,q} + \delta \cdot D_{u,q}
```

* `P(Y ≤ τ | data)`：低分后验概率
* `P(R=0 | data)`：未理解题意的后验概率
* `U_{u,q}`：不确定性
* `D_{u,q}`：遗忘或最近一次失败的时间衰减

#### 4.4.2 全局弱题候选

只有当题目在多用户上都表现出稳定困难时，才考虑标为全局弱题候选：

```math
G_q = E_u[W_{u,q}] \quad,\quad Var_u(W_{u,q}) \text{ 需足够小}
```

这一步很关键。  
如果方差太大，说明是“某些人弱”，不是“题目本身差”。

## 5. 复现频率怎么决定

### 5.1 不是固定权重，而是后验选择

推荐把“下次出题概率”看成一个在线决策问题：

```math
Score(q,u,t) = \lambda_1 W_{u,q} + \lambda_2 I_q(u) + \lambda_3 C_q - \lambda_4 E_q(t)
```

其中：

* `W_{u,q}`：弱项后验
* `I_q(u)`：信息增益 / 训练收益
* `C_q`：题目置信度或模型确定性
* `E_q(t)`：曝光惩罚 / 最近重复惩罚

然后用 softmax 或 Thompson Sampling 做选择：

```math
P(q \mid u,t) = \frac{\exp(Score(q,u,t)/T)}{\sum_j \exp(Score(j,u,t)/T)}
```

这比“权重+1”更稳，因为它天然支持探索与利用平衡。

### 5.2 为什么需要 Thompson Sampling

Thompson Sampling 适合在线决策：每次从后验里抽样，再选当前最可能带来收益的题目。  
它的优点是：

* 对不确定题目保留探索
* 不会过早锁死某几个弱题
* 便于控制重复曝光

对于题库训练，这是比纯贪心更合适的策略。

### 5.3 为什么要加 spaced repetition

单次低分不应该马上高频重复；更合理的是结合遗忘曲线。

一个可实现的时间更新形式：

```math
next\_due(q,u) = now + base(q) \cdot \exp(-\gamma \cdot mastery(u,q))
```

或者更经验化：

* 失败后短期重现
* 连续成功后拉长间隔
* 多次失败后回到更短间隔

这和分布式练习 / spacing effect 是一致的。

## 6. 弱题与低分答案怎么保存

建议把每次作答存成“训练样本”，而不是只存一个最终分数。

### 6.1 建议字段

```json
{
  "attempt_id": "...",
  "turn_id": "...",
  "question_id": "...",
  "user_id": "...",
  "transcript": "...",
  "audio_path": "...",
  "score": {
    "fc": 4.5,
    "lr": 4.0,
    "gra": 4.5,
    "pron": null,
    "overall": 4.5
  },
  "relevance": 0.18,
  "weak_item_flag": true,
  "weak_reason": ["off_topic", "low_band", "high_uncertainty"],
  "model_version": "..."
}
```

### 6.2 标签建议

至少区分：

* `low_band`
* `off_topic`
* `partial_understanding`
* `short_answer`
* `repetition_heavy`
* `grammar_sparse`
* `pronunciation_unreliable`
* `weak_for_user`
* `global_weak_candidate`

不要把所有问题都塞进一个“bad”标签。

## 7. 如何避免误标

必须有统计门槛，而不是单次判定。

推荐规则：

1. **单次答案只进候选池，不直接定性。**
2. **同一题至少累积足够样本后再判全局弱题。**
3. **使用后验概率或置信区间，而不是单点分数。**
4. **做 shrinkage / hierarchical Bayes，避免小样本过拟合。**

一个可操作的标准是：

```math
P(G_q > \tau \mid data) > 0.8
```

才进入“弱题候选”；  
若要正式标记成弱题，最好再加人工复核或更高阈值。

## 8. 评估指标

这个系统上线后，不能只看“用户觉得有用”。

至少要看：

* 弱题检测的 precision / recall
* off-topic 检测的 AUC / F1
* replay 后的分数提升
* exposure entropy（题库覆盖均匀性）
* calibration error（概率是否可信）
* information gain per replay
* 误标率：普通题被错标成弱题的比例

如果这些指标没有，算法就还是玩具。

## 9. 对当前仓库的落地建议

### 第一阶段

先在当前 `reports/attempts/` 基础上增加：

* item stats 表
* turn-level relevance label
* weak-item 候选表
* replay queue

### 第二阶段

在 `web/ielts_server.py` 里把随机采样替换成：

* `sample_for_practice(user_id, mode)`
* `rank_weak_items(user_id)`
* `enqueue_replay(question_id, reason)`

### 第三阶段

前端在 History 或 Settings 里显示：

* `weak_for_user`
* `global_weak_candidate`
* `off_topic`
* `low_band`
* `next_due`

### 第四阶段

做离线回放验证：

* 用历史 attempts 回放模型
* 看弱题标记是否稳定
* 看 replay 是否真的提升后续 score

### 当前仓库映射

* [web/ielts_server.py](C:/Users/liangjunming/Desktop/AI_Project/web/ielts_server.py:183) 现在负责题库抽样与 history 持久化，是弱题调度的后端入口。
* [web/ielts_server.py](C:/Users/liangjunming/Desktop/AI_Project/web/ielts_server.py:550) 这里的 Part 1 抽题逻辑目前还是随机抽样，后续可替换为自适应采样。
* [web/static/app.js](C:/Users/liangjunming/Desktop/AI_Project/web/static/app.js:611) 这里渲染 History 和 report，适合承接弱题标签、next_due、off-topic 等训练解释。
* [tests/test_ielts_web_server.py](C:/Users/liangjunming/Desktop/AI_Project/tests/test_ielts_web_server.py:81) 这里已有 history / score / fallback 的测试骨架，可扩展到弱题回采样测试。

## 10. 参考来源

* [Knowledge tracing: Modeling the acquisition of procedural knowledge](https://link.springer.com/article/10.1007/BF01099821)
* [Learning meets Assessment: On the relation between Item Response Theory and Bayesian Knowledge Tracing](https://arxiv.org/abs/1803.05926)
* [Item Response Theory -- A Statistical Framework for Educational and Psychological Measurement](https://arxiv.org/abs/2108.08604)
* [Knowledge tracing: Modeling the acquisition of procedural knowledge](https://doi.org/10.1007/BF01099821)
* [A Tutorial on Thompson Sampling](https://arxiv.org/abs/1707.02038)
* [Distributed practice in verbal recall tasks: A review and quantitative synthesis](https://pubmed.ncbi.nlm.nih.gov/16719566/)

## 11. 结论

如果要把“弱题回采样”做严谨，最佳路径不是先做复杂 UI，而是先把：

1. 观测数据规范化
2. 题目难度 / 用户能力分离
3. 相关性与语言质量分开建模
4. 复现策略做成概率决策
5. 用统计置信度控制弱题标签

这样系统才会越用越准，而不是越采样越偏。
