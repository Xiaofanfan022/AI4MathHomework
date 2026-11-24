# CRP-Agent

自动发现图不变量不等式的研究型智能体。课程作业"人工智能与数学"的代码部分。

## 目录

```
crp_agent/
  config.py            路径、不变量列表、随机种子等全局配置
  build_dataset.py     构造图数据集（完全枚举 + 采样 + 结构化族）
  validate_dataset.py  用已知结论检验数据集与不变量计算的正确性
  run_baseline.py      阶段二基线：形式搜索 + 系数求解 + 统计筛选（不调用模型）
  ablation.py          消融实验：模型提议与随机提议的对照（需要 API Key）
  fdr_check.py         筛选的对照实验：安慰剂数据上的假发现计数
  ceiling.py           穷举上界：完整形式空间逐条求解，给出同口径下的上限
  injection.py         注入难例：在已知为假的命题上测量反例搜索的检出率
  longrun.py           长期运行：断点续跑、记账本、出日报、形式空间自动扩张
  analyze_longrun.py   长跑结果分析：读账本生成报告，并在完整数据上复验候选
  core/
    invariants.py      九个不变量的精确算法（位掩码实现）
    graphgen.py        图的枚举与采样
    forms.py           候选形式与线性规划求解
    features.py        乘积型派生特征（n2 / aD / wD / cD / aO / nD）
    counterexample.py  反例搜索（随机 / 结构化 / 局部修改）
    stats.py           置换检验与 BH 多重检验校正
    split.py           发现集 / 验证集 / 测试集的划分
    informativeness.py 恒真式识别：候选是否被定义或已知界直接支配
  agent/
    llm.py             模型客户端（兼容 OpenAI 接口）
    mock.py            假模型：只用于验证工程件，不能评价智能体质量
    prompts.py         四处调用的提示词
    trace.py           JSONL 轨迹记录
    loop.py            智能体主循环
  viz/
    style.py           绘图样式与中文字体
    stage1_plots.py    阶段一图表（数据与已知结论）
    stage2_plots.py    阶段二图表（搜索与筛选）
    stage3_plots.py    阶段三图表（智能体轨迹与消融）
  data/                数据集 CSV
  figures/             图表 PNG
  runs/                每次运行的轨迹与结果
```

## 运行

```powershell
# 1. 构造数据集（首次约 1 分钟，n=8 的 12346 张图需要去重）
python -m crp_agent.build_dataset

# 2. 校验数据集与不变量
python -m crp_agent.validate_dataset

# 3. 阶段一图表
python -m crp_agent.viz.stage1_plots

# 4. 阶段二基线（不调用模型）
python -m crp_agent.run_baseline --max-pred 2 --top-k 80 --min-tight 0.0002

# 5. 阶段二图表
python -m crp_agent.viz.stage2_plots

# 6. 智能体（需要 API Key）
python -m crp_agent.agent --rounds 5

# 7. 消融实验：模型提议 vs 随机提议（需要 API Key）
python -m crp_agent.ablation --seeds 3 --rounds 4

# 8. 阶段三图表
python -m crp_agent.viz.stage3_plots

# 9. 筛选的对照实验（安慰剂数据，不调用模型）
python -m crp_agent.fdr_check --seeds 3

# 10. 穷举上界（约 3 分钟，不调用模型）
python -m crp_agent.ceiling --max-pred 2 --n-perm 200

# 11. 注入难例：反例搜索的检出率（约 5 分钟，不调用模型）
python -m crp_agent.injection
```

## 长期运行

短跑几轮之后，形式空间会成为瓶颈：基础档只有 2304 条（9 个基础量、
至多 2 个预测子），智能体五轮就能提掉二十多个互异形式。长跑模式在
时间维度上展开，并在形式空间接近枯竭时自动升级档位。

```powershell
# 跑 24 小时（断点续跑：中途杀掉后用同一条命令重启即可）
python -m crp_agent.longrun --hours 24 --run-dir crp_agent/runs/longrun_week

# 只跑 10 轮，用于估计单轮耗时
python -m crp_agent.longrun --hours 1 --max-rounds 10

# 不调用模型的冒烟测试
python -m crp_agent.longrun --mock --max-rounds 5
```

运行目录里的四个文件：

| 文件 | 内容 |
|---|---|
| `state.json` | 断点：轮次、已提形式键、累计词元、档位、失败计数 |
| `ledger.jsonl` | 追加式账本：每轮一行，另有 retained / refuted / escalate / error 记录 |
| `trace.jsonl` | 逐步轨迹，供汇报时引用"智能体做了什么决定" |
| `daily/YYYY-MM-DD.md` | 每日自动生成的日报 |

**自动扩张。** 两个判据任一满足即升档：已提形式占形式空间的比例超过
35%，或最近 6 轮平均每轮新增互异形式少于 2 个。档位与形式空间：

| 档位 | 预测子 | 特征数 | 形式空间（max_pred=2） | max_pred=3 |
|---|---|---|---|---|
| 0 基础 | 9 个基础量 | 9 | 2304 | 10368 |
| 1 乘积项 | 加 6 个乘积 | 15 | 7056 | 59472 |
| 2 三点预测子 | 同档 1 | 15 | — | 59472 |

乘积项只取整数乘积（如 `n·n`、`α·Δ`），不取比值——比值是小数，
取等比例会塌到零，置换检验随即失去分辨力。

**单轮耗时**（实测，`--budget 1000 --n-perm 200`）：约 66 秒，21 次调用、
约 1 万词元。跑满一周约 9000 轮，接近第 2 档 59472 条的容量。

**跑完之后：**

```powershell
python -m crp_agent.analyze_longrun --run-dir crp_agent/runs/longrun_week
```

生成的 `analysis.md` 含六节：总体统计、异常、逐轮走势与转化率、被保留
候选（**在完整 27810 张图上重新复验**，不依赖当时的划分）、被推翻候选
的反例阶数分布、以及把数字翻成结论的判读。脚本只读，可反复运行。

## 配置 API Key

复制 `.env.example` 为 `.env`，填入：

```
OPENAI_API_KEY=...        # 兼容 OpenAI 接口的服务均可
OPENAI_BASE_URL=...       # 例如 https://aihubmix.com/v1
MODEL_NAME=...            # 例如 coding-glm-5.1-free
```

`.env` 已被 `.gitignore` 排除，不会进入版本库。
第 6、7、12 步需要 Key，其余步骤完全离线。

## 设计要点

**系数不由模型给出。** 模型只决定"用哪些不变量、什么符号、哪个方向"，
具体系数由线性规划在数据上求解。这样做的好处是模型不会编造数值，
且每条候选都能被精确复现。

**每条候选都留下轨迹。** `runs/<时间戳>/trace.jsonl` 每行一步，
记录输入摘要、模型输出、策略选择、预算消耗与结果。
汇报时可以直接引用轨迹说明智能体"做了什么决定"。

**搜索预算要记账。** "搜了 30 张图没找到"与"搜了 30 万张没找到"
提供的证据强度不同，因此每次搜索都记录实际评估的图数。

**假阳性要控制。** 同时检验上百条候选时，总有一些仅因偶然在数据上成立。
系统用置换检验给出 p 值，再用 Benjamini-Hochberg 控制错误发现率。

**恒真式要先剔除。** 不变量之间存在由定义直接给出的序关系
（例如 $\omega \leq \chi$、$\delta \leq \Delta$）。这类形式在任何图上都成立，
必然通过置换检验，却没有信息量。若不加区分，随机抽样反而会"胜出"——
消融实验中随机组一度全面超过模型组，原因正是如此。
`core/informativeness.py` 用 35 条基本事实识别被支配的候选，
智能体把它们连同理由一起反馈给模型，要求换方向。

注意**同一不等式的对称写法**：$n \geq 2\nu$ 与 $\nu \leq n/2$ 是移项关系，
若只比较目标与方向都相同的写法，后者在表中、前者却会被误判为有信息量。
这一漏洞曾使上界多出 3 条（37 而非 34），补上后 $n \geq 2\nu$ 被正确剔除。

## 已知结论

数据集上已核对以下结论（`validate_dataset.py`，违反数均为 0）：

| 结论 | 违反 | 取等 |
|---|---|---|
| $\chi + \alpha \leq n+1$ | 0 / 27810 | 478 |
| Reed: $\chi \leq \lceil(\omega+\Delta+1)/2\rceil$ | 0 / 27810 | 365 |
| Brooks: $\chi \leq \Delta+1$ | 0 / 27810 | — |
| $\alpha + \omega \leq n+1$ | 0 / 27810 | 478 |

## 一个值得注意的观察

$\chi \leq \omega+1$ 在全部 13598 张 $n \leq 8$ 的图上成立，
却在 $n=11$ 失效，反例是 Grötzsch 图（无三角形但色数为 4）。

这说明"在小图上验证通过"不能作为"普遍成立"的证据，
也正是本课题要处理的核心困难。
