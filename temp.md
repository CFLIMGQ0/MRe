# MRePath 与本项目改进模型：逐模块、逐数据流、逐训练目标的差异说明

> 编写日期：2026-09-13。
> 用途：可把本文件整体交给另一个 GPT，分析“我们究竟修改了哪些模块、哪些只是原模型的保留、现有实验能否支持改进归因”。
> 本文件是代码与结果记录审计，不是新实验报告；本次没有修改模型实现或启动正式训练。

## 0. 给接收本文的 GPT：请先遵守这些分析边界

1. 请区分论文模型、作者发布代码、本项目复现基线、本项目基础改进、后续创新变体、当前 YAML 六个对象，不要混称为一个“原模型/新模型”。
2. 请把“代码可直接确认”“历史报告记载”“由计算图推导”“仍需实验验证”分开。
3. 不要因为类名包含 KAN，就认为每个子模块都是同一种标准 B-spline KAN。
4. 不要把 Bernoulli 组内基因图、六功能组之间的聚合、病理 patch 超图当作同一张图。
5. 不要把编码器内部的 `fusion` 一致性损失误认为病理–基因 IFA 融合损失。
6. 不要把 COREAD 的某个变体最高值与 STAD 的另一个变体最高值拼成“同一个模型”的结果。
7. 请优先判断真实前向流程与梯度路径，再评价命名、创新性及消融是否充分。没有实验或文献依据时，不要直接宣称稳定 SOTA、统计显著、首次提出或可发表。
8. 本文已经包含主要公式、配置和伪代码；你若无法访问仓库，不要假装看过本文之外的文件。

## 1. 最简结论

我们前面讨论的基础模型是：

**在 MRePath 的病理 SHGNN、动态模态加权、IFA 和生存预测头基本保持原架构的前提下，替换基因组编码器，引入组内基因关系图及 Bernoulli 双视图一致性训练，并在编码后的六组特征上增加独立 KAN 聚合器。**

更精确的程序身份是：

```text
MRePath(
    genomic_encoder = pc_cmka_ddkac,
    pc_cmka_experiment = C4_bernoulli_views,
    gene_aggregation = kan,
    graph_type = shgnn,
    hyperedge_mode = both,
    weighting_mode = dynamic,
    fusion_variant = ifa,
    rebalance_variant = original
)
```

需要特别修正两种容易产生的理解：

- 不是“把病理 SHGNN 换成 Bernoulli 图”。Bernoulli 作用于基因组分支。
- 也不是“只把原始 MLP 换成一个 KAN 层”。组内编码器、图算子、随机视图、辅助损失、组间聚合均需要分别计入改动。

“Bernoulli Views + KAN”是组合简称，不足以完整描述实现。

## 2. 六个比较对象不能混淆

| 标识 | 对象 | 本文中的含义 |
|---|---|---|
| P | 论文 MRePath | 《Multimodal Cancer Survival Analysis via Hypergraph Learning with Cross-Modality Rebalance》，本地 `Sheaf超图.pdf`，方法章节与 Table 1 |
| R | 作者发布仓库 | 项目复现协议记录的 `MCPathology/MRePath`，参考提交 `e3c133b0beb5ded80426afbe49ab41f1003a4ed5`；这是协议记录，不代表本次重新联网审计了该提交 |
| L | 本项目原始复现基线 | 本地 `MRePath`，`genomic_encoder=original`、`gene_aggregation=default`、SHGNN + Dynamic + IFA |
| B | 本项目基础改进 | `pc_cmka_ddkac / C4_bernoulli_views` + 外部 `KANGeneAggregator`，即本文重点 |
| I | 后续 BK_Ixx 变体 | 例如 `mask2spline_hyperkan`、Jensen 去偏、Jacobian 一致性等，有另外的内部 KAN/辅助损失机制 |
| Y | 当前 `model.yaml` | 描述 `pc_cmka_full_graph + dd_kac + pathway_aggregation:none`，与 B 不一致；且现有入口不自动读取该文件 |

本文主要比较 **L → B** 的实际程序结构，并注明它们与 P/R 的数据和复现差异。不能把所有 L 与 R 的修复都算作 B 的模型创新。

## 3. 把整个模型拆成七个网络模块

下表“保留”指本项目基线与基础改进之间保留该模块的架构和选择，不代表训练后的参数、输出、关注区域和模态权重数值完全不变。

| 模块 | 原始复现基线 L | 基础改进 B | 变化性质 |
|---|---|---|---|
| M1：病理特征提取及投影 | 20×、256×256 patch、ResNet50 1024 维缓存特征；投影到 256 维 | 同一类输入和投影模块 | 保留 |
| M2：病理超图编码 | 空间/特征双超边，SHGNN，默认三层 | 同一 SHGNN 与双超边 | 保留 |
| M3：六个功能组的基因编码 | 每组独立 MLP/SNN，输出六个 256 维 token | 每组使用值域分支 + 图结构分支 + 门控残差融合；C4 训练时增加 Bernoulli 双视图 | 替换并扩展 |
| M4：独立跨组聚合 | `gene_aggregation=default`，此位置是直接返回输入 | `gene_aggregation=kan`，新增特征维 KAN 与组维 KAN | 新增 |
| M5：模态动态加权 | 原始 `DynamicWeighting` | 仍然使用该模块，但基因输入已经改变 | 保留架构，输入改变 |
| M6：交互对齐融合 | 原始完整 IFA：SA + PG + GP | 仍然使用完整 IFA | 保留 |
| M7：池化与生存预测 | 双分支平均池化、拼接、MLP、四时间区间 logits | 同一预测头 | 保留 |

另有一个非网络模块的变化：**训练目标增加了基因编码器辅助损失**，不是只更换网络层后继续使用完全相同的优化目标。

## 4. 输入、输出和前向顺序

### 4.1 主要张量约定

按当前 small 配置说明，不将这些维度泛化为所有可选模型配置：

| 张量 | 形状 | 含义 |
|---|---|---|
| `X_path` | `[N, 1024]`，或带单病例 batch 维 | 一例病例采样的病理 patch 特征，正式设置通常最多 4096 个 patch |
| `P` | `[1, N, 256]` | 病理投影后的特征，尚未经过 SHGNN |
| `P_h` | `[1, N, 256]` | SHGNN 后的病理特征 |
| `x_g` | `[1, n_g]` | 第 g 个功能组的基因表达，g=1…6，各组基因数可以不同 |
| `G_base` | `[1, 6, 256]` | 六个功能组各自编码后堆叠的表示 |
| `G_kan` | `[1, 6, 256]` | 经过外部 KAN 聚合器的表示 |
| 模态权重 | `[1, 2]` | 病理权重与基因组权重 |
| 融合后池化向量 | 两个 `[1, 256]` | 分别对病理和基因 token 求均值 |
| 最终 logits | `[1, 4]` | 四个离散生存时间区间的 logits |

这里的“六通路”是项目对六个基因功能组/签名的简称，不应理解为只有六个基因，或者六条指定的 KEGG 通路。

### 4.2 复现基线 L 的主预测路径

```text
病理输入 → ResNet50 缓存 → 病理投影 P → SHGNN → P_h
基因输入 → 六组各自 MLP/SNN → G

weights = DynamicWeighting(P, G)     # 使用 SHGNN 之前的 P
P_w = pathology_weight × P_h        # 权重应用于 SHGNN 之后的 P_h
G_w = genomics_weight × G

(P_f, G_f) = IFA(P_w, G_w)
z = concat(mean(G_f), mean(P_f))
logits = Linear_128_to_4(ReLU(Linear_512_to_128(z)))
```

动态权重的计算位置很重要：不能简单描述为“先把两路全部编码结束，再只根据 P_h 与 G 算权重”。本地代码按其论文对齐设计，使用 P 与 G 计算权重，再把病理权重应用到 P_h。

### 4.3 基础改进 B 的主预测路径及训练旁路

```text
病理输入 → 与 L 相同的投影和 SHGNN → P_h

六组基因输入
  └─ 每组 PC-CMKA/DD-KAC 风格编码器
       ├─ 固定基准图 + 值域/结构域编码 → base_fused_g ────┐
       ├─ Bernoulli view 1 → structure_1, fused_1         │
       └─ Bernoulli view 2 → structure_2, fused_2         │
                └─ 训练旁路：结构/组内融合一致性损失       │
                                                        ↓
                   stack(base_fused_1…base_fused_6) = G_base
                                                        ↓
                           外部 KANGeneAggregator → G_kan

weights = DynamicWeighting(P, G_kan)
(P_f, G_f) = IFA(pathology_weight × P_h, genomics_weight × G_kan)
与 L 相同的池化及生存预测头
```

**重要：当前基础 C4 编码器返回的是基准图得到的 `fused`。两个随机视图主要参与辅助损失，没有作为两路 token 直接送入外部 KAN。**

这一点区别于部分后续 BK_Ixx 变体：后者会显式读取 `runtime_views`，再调用编码器内部的 `BernoulliKANInnovation`。

## 5. 未改变模块的具体结构

### 5.1 M1：病理投影

small 配置的投影为：

```text
1024 → Linear → 256 → ReLU6 → Dropout(0.25)
 256 → Linear → 256 → ReLU6 → Dropout(0.25)
```

ResNet50 特征是预先提取的缓存，不应把本轮基因分支改动描述为重新训练了一个新的切片特征提取器。CTransPath 等编码器实验属于另外的消融，不是 B 的组成部分。

### 5.2 M2：病理超图

- 节点是病理 patch。
- 使用空间邻近与特征相似两类超边，默认 `hyperedge_mode=both`。
- 默认 k=9 来自当前复现实验配置；它与后面基因相关性图的 top-8 不是同一个参数。
- 本地 SHGNN 使用 `SheafBuilderGeneral` 和三层 `HyperDiffusionGeneralSheafConv(256,256,d=1)`。
- 存在图/超图缓存读取与在线构造的不同工程路径，但 B 没有把病理 SHGNN 替换成 GCN、HGNN 或 Bernoulli 图。

### 5.3 M5：动态模态加权

本地 `DynamicWeighting` 根据病理 P 与基因 G（B 中是 G_kan）得到两路 mono-confidence，再构造 holo-confidence：

```text
c_p, c_g ∈ (0,1)，数值上裁剪到 [1e-4, 1-1e-4]
h_p = log(c_p) / (log(c_p) + log(c_g))
h_g = log(c_g) / (log(c_p) + log(c_g))
(w_p, w_g) = softmax(c_p + h_p, c_g + h_g)
```

病理支路先将每个 token 投影为标量，再在固定 patch 数维度上计算置信度；基因支路展平六个 256 维 token。若病理 token 数不等于设置值，代码有均值回退路径。

基础 B 的 `rebalance_variant=original`，没有使用 `QualityConflictWeighting`。因此不能把 Quality + Conflict 列为该基础模型已启用的创新。

### 5.4 M6：完整 IFA

本地实现按以下顺序工作，省略 attention 内部线性投影：

```text
G_s = LayerNorm(G_w + Attention(Q=G_w, K=G_w, V=G_w))
G_f = LayerNorm(G_s + Attention(Q=G_s, K=P_w, V=P_w))
P_f = LayerNorm(P_w + Attention(Q=P_w, K=G_f, V=G_f))
```

这分别对应基因自注意力、病理引导基因、更新后的基因引导病理。默认 4 个注意力头。

所以原模型本来就在 IFA 中存在六组之间的自注意力；新增 KAN 的准确说法是“在动态加权及 IFA 之前增加显式非线性组间聚合”，不是“首次让六组发生交互”。

### 5.5 M7：预测与风险计算

- IFA 输出的两路 token 分别平均池化。
- 拼接为 512 维，经 `Linear(512,128) + ReLU + Linear(128,4)` 输出 logits。
- `MRePath.forward()` 本身返回 logits；后续损失/评价代码计算：

```text
hazard_t = sigmoid(logit_t)
survival_t = product_{j≤t}(1 - hazard_j)
risk = -sum_t survival_t
```

四个离散时间区间不是四种癌症类别。B 没有把任务换成分类或直接回归生存月数。

## 6. 改动一：M3 的组内基因编码器

### 6.1 原始编码器到底是什么

`genomic_encoder=original` 时，每个功能组各有一个独立网络。small 配置为：

```text
n_g → Linear → 1024 → ELU → AlphaDropout(0.25)
1024 → Linear → 256 → ELU → AlphaDropout(0.25)
```

六组输出堆叠为 `[B,6,256]`。本地函数叫 `SNN_Block`，但实际激活是 `ELU`，不能因其名称就写成 `SELU`。论文用 MLP 描述这一基因嵌入步骤；应区分论文概念与本地精确层实现。

原始这一位置没有 PC-CMKA 组内基因图，没有 Bernoulli 双视图，也没有后述图校准字典。

### 6.2 新增的组内基因图来自哪里

`build_fold_pc_cmka_priors()` 使用训练折的 RNA 矩阵，为每个功能组分别构图。当前没有指定外部边文件，使用如下相关性回退：

1. 从训练折中取该功能组的基因表达列。
2. 计算基因两两相关系数，取绝对值；NaN/Inf 置零。
3. 对角置零。
4. 每个基因保留最多 8 个相关邻居，选中边的权重下限为 0.001。
5. 用 `max(A,Aᵀ)` 对称化，因此对称化后的节点度可能大于 8。
6. 每折重新构建训练折图；验证病例复用该折图，不用验证 RNA 重新估计相关性。

后续谱算子只取无向边的上三角支持，不保留自环。无可用边时算子有确定性链式回退；当前正常多基因组不应把这个回退当成预期主方法。

由此可直接确认：

- 这是“组内基因关系图”，不是患者之间的图，也不是病理 patch 图。
- 这是训练数据导出的统计关系，不是已经装载的 PPI/Reactome/KEGG/GO 生物学先验。
- 取绝对相关后不再保留正相关/负相关符号；可能有什么影响需要消融验证。
- top-k 中很弱甚至零相关的候选仍可能被下限抬为 0.001；这也是实现细节，不能描述成所有边均具有强生物学证据。

### 6.3 C4 的基准图不做患者自适应逆校准

虽然程序类叫 `PCCMKADDKACPathway`，但 C4 明确设置：

```text
calibration_mode = fixed
```

因此每个患者的基准边权都是该折的 `w0`；`coefficients=0`。不能把完整 A0 中的“患者目标矩逆求解、最小信任半径图校准”作为 C4 已启用的机制。

仍然存在患者自适应的是后述频率路由和域融合门控，它们由患者表达统计量驱动。**固定图不等于整个基因编码器对所有患者使用相同特征混合系数。**

### 6.4 固定参考谱算子

对当前 C4，以基准图的度矩阵 D0 固定归一化。设 B_inc 为有向关联矩阵（只是表示无向边所需的任意方向），则：

```text
S(w) = D0^(-1/2) B_incᵀ diag(w) B_inc D0^(-1/2)
S_hat(w) = 2 S(w) / Lambda - I
```

代码用边上的 scatter 运算实现，不在正式传播中显式构造完整关联矩阵。

默认 `rho_max=0.5`，当未手动给定谱上界时：

```text
Lambda = 2 × exp(0.5) ≈ 3.2974
```

C4 沿用这个谱尺度，即使它关闭了逆校准。这一点与旧 `dd_kac` 的拉普拉斯缩放并不相同。

### 6.5 值域分支：不是外部聚合器的三次 B-spline KAN

每个功能组使用 8 个固定 RBF 中心，均匀分布在 [-1,1]。其标量变换可写为：

```text
phi(x_i) = a × x_i + sum_{k=1…8} c_k × exp(-(x_i-mu_k)^2 / (2 sigma^2))
sigma = 2 / 7
V = Linear_n_g_to_256(phi(x))
```

- 每个功能组有自己的 a 与 8 个 c_k。
- 在该功能组内，这些非线性标量系数对不同基因位置共享，然后经线性投影区分各基因。
- 这是一种 KAN-like 值域非线性实现，不是把每个 `n_g→256` 连接都替换成独立可学习三次 B-spline。
- 下文 M4 才是真正调用本项目 `KANLinear` 的独立跨组聚合器。

### 6.6 图结构分支：二阶 Chebyshev 响应与患者路由

先按患者在组内中心化表达 `x_c = x - mean(x)`，默认阶数 R=2：

```text
r0 = x_c
r1 = S_hat(w) × x_c
r2 = 2 S_hat(w) × r1 - r0
```

路由器输入五个患者统计量：

1. 组内表达均值；
2. 组内表达标准差（`unbiased=False`）；
3. `abs(x)<1e-6` 的比例；
4. 图能量 `x_cᵀ S(w) x_c / (||x_c||² + 数值保护)`；
5. `abs(x)>0.5` 的比例。

```text
route_logits = Linear_32_to_3(GELU(Linear_5_to_32(stats)))
alpha = softmax(route_logits)
Z = Linear_n_g_to_256(alpha0*r0 + alpha1*r1 + alpha2*r2)
```

这里的路由表示对不同阶图响应的加权，不是改变六个功能组数量，也不是病理–基因动态权重。

### 6.7 组内值域/结构域融合

```text
gate = sigmoid(Linear_5_to_1(stats))
U = LayerNorm(gate*V + (1-gate)*Z + Linear_n_g_to_256(x))
```

这里有门控、残差投影和 LayerNorm。它们位于单个基因功能组内部。

不要与外面的 `DynamicWeighting` 混淆：

- 这里的 gate 平衡“值域特征/图结构特征”。
- 外面的动态权重平衡“病理模态/基因模态”。

六个 U 堆叠后仍为 `[B,6,256]`，所以能接回原始 MRePath 下游接口。

## 7. 改动二：组内图上的 Bernoulli 双视图

### 7.1 采样规则

基础 C4 默认保留概率 p=0.8。两次独立采样对应边掩码：

```text
m_e^(1), m_e^(2) ~ Bernoulli(0.8)
w_e^(1) = w0_e * m_e^(1) / 0.8
w_e^(2) = w0_e * m_e^(2) / 0.8
```

在忽略数值下限时，重标定使每条边权的期望仍为 w0_e。代码最终对权重 `clamp_min(1e-8)`，所以“删边”在数值实现中是接近零的小边权，并非从 edge_index 真正删除该边。

因此不能把它描述成“每次严格删除 20% 的边”；是每条边独立保留，实际删除比例会波动。

### 7.2 两个视图之间共享什么

- 共享同一个编码器参数。
- 共享基准图计算出的 `base_logits` 频率路由（`shared_route=true`）。
- 值域分支 V 在该次前向中共享。
- 结构特征根据各视图边权分别计算。
- 域融合门控根据各视图图统计量重新计算，因此两个视图的门控值不必相同。

这比“所有参数和所有门控都固定，只做 DropEdge”更具体。

### 7.3 训练与验证

- 训练：计算基准表示，同时计算两个视图的结构表示 Z1/Z2 和组内融合表示 U1/U2，用于一致性损失。
- 验证：`train_only=true`，不随机采样双视图；C4 使用固定基准图的表示。
- 基础版本不是测试时多次随机采样再平均的 ensemble。
- 基础版本也不是同时做两次病理 SHGNN 前向，或两次完整 IFA 前向。

### 7.4 必须明确：双视图没有直接进入外部 KAN

实际调用关系是：

```python
# PCCMKADDKACPathway.forward 的末尾
return fused  # 基准图的组内融合表示

# PCCMKADDKACEncoder.forward；基础 C4 的内部 innovation 为 off
stacked = stack([group(x_g) for each group], dim=1)
return stacked

# MRePath.forward
G = self.genomic_encoder(x_omic)
G = self.gene_aggregator(G)  # 此处才调用外部 KANGeneAggregator
```

所以基础组合中的协同是：双视图训练约束改变基因编码器学到的表示，KAN 再处理其基准表示。**不能据此宣称已经实现了“两个 Bernoulli 视图上的 KAN 输出一致性”“掩码条件化 KAN 样条”或“KAN 控制采边”。**这些需要另外的损失/数据流，有些属于 BK_Ixx。

## 8. 改动三：M4 独立 KAN 跨组聚合器

### 8.1 插入位置与原始对照

位置是：

```text
六组基因编码输出 → GeneGraphAggregator → DynamicWeighting → IFA
```

`GeneGraphAggregator(method='default')` 在此位置直接返回输入。

`method='gcn'/'gat'` 则使用六组 token 组成的全连接有向边集（排除显式自连，共 30 条边；底层层实现可能另行处理自环）。

`method='kan'` 使用 `KANGeneAggregator`，不消费这个 `edge_index`，也不重新构建相关性图。

这说明“基因组内相关性图”和“六组之间 GCN 的全连接图”是两个不同层级。

### 8.2 KANLinear 的具体参数化

本项目本地实现：

```text
y_j = sum_i W_base[j,i] * SiLU(x_i)
    + sum_i sum_k W_spline[j,i,k] * B_k(x_i)
```

- B_k 为三次 B-spline 基函数。
- `grid_size=5`，`spline_order=3`，每个输入–输出连接有 8 个样条系数。
- 默认内部网格区间为 [-1,1]，有为三次样条扩展的边界节点。
- base 分支与 spline 分支相加。
- 当前基础聚合器没有调用自适应网格更新、掩码条件化系数或 Jacobian 专用方法。
- 网格参数是 buffer，不是默认会自动更新的可训练节点；`KANLinear` 中存在额外方法不代表每次 forward 都会调用。

### 8.3 完整聚合器的两级结构

```text
输入 G：[B,6,256]

第一级：特征维非线性变换，对六组共享这套参数
KANLinear(256,128)
Dropout(0.25)
KANLinear(128,256)
输出：[B,6,256]

转置：[B,256,6]

第二级：六组之间的非线性混合，对 256 个特征位置共享这套参数
KANLinear(6,12)
Dropout(0.25)
KANLinear(12,6)
输出：[B,256,6]

转置回：[B,6,256]
LayerNorm(256)
```

精确实现注意：

- 外部 `KANGeneAggregator` 的输出是 `LayerNorm(mixed)`，没有额外的 `+ 输入G` 残差。
- 组内编码器有残差，不代表外部 KAN 聚合器也有残差。
- 六个功能组有固定语义顺序，KAN 的六维映射与该顺序绑定；不应自动声称它像图消息传递一样对任意组置换等变。
- 这里的两级作用是“特征维变换 + 功能组维混合”，不是对病理 patch 做 KAN。

### 8.4 参数量和成本

默认外部 KAN 聚合器共有 **591,632 个可训练参数**，本次用 CPU 实例化后实际统计确认：

```text
256→128 与 128→256 两层：589,824
6→12 与 12→6 两层：1,296
LayerNorm(256)：512
合计：591,632
```

这只是外部聚合器本身，不是整个 B 相比 L 的净增参数量；M3 同时被替换，完整参数差还依赖六组基因数量和图边数。

比原来直接返回输入，KAN 必然增加此位置的计算与参数。相比旧 MLP 的整个基因分支总成本，需要实测，不应仅凭名称断言更轻量。

## 9. 改动四：训练损失和实际梯度路径

### 9.1 主生存损失不变

当前正式设置通常采用四时间区间的 `nll_surv`，Adam、学习率 1e-4、weight decay 1e-5、30 epochs、seed 1、batch size 1。

这些是本项目记录的训练设置；“每个历史批次全部完全相同”仍需逐目录参数确认。

### 9.2 基础 C4 并非只有一个 SSL 损失

配置由公共 JSON 与 C4 overrides 深度合并。C4 没有把所有公共损失权重清零。每个功能组的辅助损失为：

```text
L_aux,g = 0.01   * L_moment,g
        + 0.001  * L_trust,g
        + 0.01   * L_ssl,g
        + 0.001  * L_identifiability,g
        + 0.0001 * L_dictionary,g

L_total = L_survival + mean_g(L_aux,g)
```

基础配置下原始动态加权模块没有额外 Quality/Conflict 损失。

各项是否实际起作用，要根据运行模式判断，不能只看权重非零：

| 损失项 | 当前 C4 状态 | 准确含义 |
|---|---|---|
| Moment | 仍计算，权重 0.01 | 基准矩与目标矩的精度加权误差 |
| Trust | fixed 模式通常为 0 | 基准边权未改变，`rho=max(abs(log(w/w0)))=0` |
| SSL | 训练时启用，权重 0.01 | 两个视图的结构/组内融合表示一致性 |
| Identifiability | 明确关闭，返回 0 | 虽然公共 `lambda_id` 仍为 0.001，但 `mode=off` |
| Dictionary | 仍计算，权重 0.0001 | 低秩边形变字典的加权正交性惩罚 |

### 9.3 SSL 到底比较什么

基础 C4：`ssl.mode=structure_fusion`。

```text
L_ssl = 1.0 * C(Z1,Z2) + 0.5 * C(U1,U2)
```

其中 Z 为组内图结构分支特征，U 为组内值域/结构域融合特征。这里没有把 IFA 输出 P_f/G_f 代入 C。

`C(a,b)` 的实现是：

```text
1 - cosine_similarity(a,b)
+ 防止表示方差过小的惩罚，variance_floor=0.5
```

当 batch size>1 时，方差项沿病例 batch 计算；正式 batch size=1 时，代码改为沿该病例的特征维计算离散程度。因此不能原样宣称这是标准大 batch 对比学习、包含患者负样本，或已经等价实现完整 VICReg。

`structure_fusion` 不包含 gate 一致性项；只有 `structure_fusion_gate` 才把该项加入 SSL。

### 9.4 fixed 模式仍保留目标网络/字典的含义

校准器先计算目标网络，然后再判断 `calibration_mode`。所以 C4 中：

```text
target = baseline_moments + predicted_offset
actual = baseline_moments
moment_loss = mean(precision * predicted_offset²)
```

这是从当前计算图得到的推导：该项可以约束目标网络，但固定模式下目标网络并不通过图校准改变主预测图。字典正交项也仍存在，而 fixed 主表示并不靠学习到的字典去变形基准边权。

因此应把它们看作需要审视的遗留/辅助计算，而不能仅因非零损失权重就宣称“逆校准是基础 C4 性能提升的原因”。这些项对主输出有无间接优化影响、能否删除，需要控制随机性和训练轨迹后验证；本次没有修改它们。

### 9.5 外部 KAN 是否直接收到 SSL 梯度

**当前基础组合中，编码器的辅助损失不直接依赖外部 KAN 参数。**

- 生存损失经过预测头、IFA、动态加权、外部 KAN，回传到组内编码器。
- 基因编码器内部 SSL 回传到其结构/融合等相关参数。
- SSL 计算发生在外部 KAN 之前，且没有把外部 KAN 输出代入一致性项。

本次 CPU 小型合成输入验证也确认了这一点，见第 17 节。这里的“没有直接 SSL 梯度”不等于“二者完全互不影响”：它们仍通过共享主预测链路联合训练，编码器学到的变化会影响 KAN 的输入。

## 10. `fixed_fold_graph` 与 `bernoulli_views` 不是严格只差一种增强

图结构选择名称容易掩盖实现差异。runner 映射为：

```text
fixed_fold_graph → C0_original_ddkac → encoder=dd_kac
bernoulli_views  → C4_bernoulli_views → encoder=pc_cmka_ddkac
```

直接检查两套代码可见：

| 项目 | 旧 `DDKACEncoder` | C4 `PCCMKADDKACEncoder` |
|---|---|---|
| 图准备 | 训练折相关性图，显式加自环 | PC-CMKA prior 构图，选中边权有 0.001 下限，谱支持去掉自环 |
| 归一化算子 | 含自环邻接得到 `L=I-D^-1/2 A D^-1/2` | 固定参考度的关联矩阵拉普拉斯 `S(w)` |
| Chebyshev 缩放 | `scaled_laplacian=L-I` | `2S/Lambda-I`，默认 Lambda≈3.2974 |
| 主表示 | 值域 + 结构域门控融合 | 相似的双域思想，但算子和辅助框架不同 |
| 辅助目标 | `1e-4 × (1-cos(value,structure))` | moment、trust、双视图 SSL、identifiability、dictionary 的模式化组合 |
| 随机双视图 | 无 C4 这一套 | 有 Bernoulli 两视图 |

所以 `fixed_fold_graph+KAN` 对 `bernoulli_views+KAN` 的差值，不是“只加了 Bernoulli 就提升多少”的严格证据。

同一 C4 编码器内的 `aggregation=gcn` 与 `aggregation=kan` 更接近对聚合器的局部对照，但还应核对其他参数、数据、fold、checkpoint 规则确实一致。

## 11. 当前 YAML、完整 PC-CMKA 与基础 Bernoulli 版本的区别

### 11.1 当前 `model.yaml` 的关键内容

```yaml
pathology:
  enabled: true
  patch_encoder: resnet50
  graph_encoder: shgnn
  hyperedges: both
genomics:
  enabled: true
  functional_groups: 6
  graph_structure: pc_cmka_full_graph
  encoder: dd_kac
  pathway_aggregation: none
  bernoulli_kan_innovation: none
fusion:
  enabled: true
  weighting: dynamic
  method: ifa
  rebalance: original
prediction:
  head: discrete_survival
```

这是本次读取的配置快照，本文件没有修改它。

### 11.2 完整 A0 与 C4 的模式对照

如果按现有 runner 的预设映射，`pc_cmka_full_graph` 对应 `A0_full`，它与 C4 的区别如下：

| 开关 | A0_full | C4_bernoulli_views |
|---|---|---|
| 图校准 | inverse，目标矩驱动的固定步数可微求解 | fixed，基准边权不作患者逆校准 |
| 视图 | Hessian antithetic | 独立 Bernoulli 边掩码 |
| Krylov 安全缩放 | 开启 | 关闭 |
| SSL 模式 | structure_fusion_gate | structure_fusion |
| 切空间 identifiability | randomized | off |
| 外部 KAN | 由另外的 aggregation 参数决定 | 同样由另外的 aggregation 参数决定 |

公共 inverse 配置中，字典 rank=4，moment_order=2，目标网络 hidden_dim=32，offset 上限 0.25，precision 下限 0.1；求解器默认 3 次更新、步长 0.05、rho_max=0.5。A0 使用这些逆校准/不确定性机制，C4 不应被描述为使用了同样的完整机制。

一个额外工程细节：C4 关闭的是 Krylov 约束缩放，但当前增强代码仍调用 `_krylov_error` 做部分诊断；“开关关闭”不等于相应诊断计算成本全部为零。

### 11.3 现有入口没有自动读取 model.yaml

本次检查 `main.py`、`utils/process_args.py` 及项目 Python 中的 YAML/model.yaml 引用：

- `main.py` 通过 argparse 获取实际参数。
- PC-CMKA 数值配置来自 JSON 与指定 experiment 的深度合并。
- runner 中有从“图结构名称”到“JSON 预设”的映射，但不是自动读取 YAML。
- 未发现现有训练入口把 `model.yaml` 加载后转成实际训练参数的逻辑。
- 因而 `model.yaml` 更接近当前的模块选择说明，不足以单独证明某次训练启用了什么。

此外，现有 `run_pc_cmka_word_ablations.py` 生成命令时把 `--mrepath_gene_aggregation` 固定为 `default`。仅运行该脚本的 `--graph-structures bernoulli_views` 不会自动打开外部 KAN。

该 runner 还保留旧主机 Python 绝对路径，内置数据集只有 COREAD/STAD；它不能未经适配就被当作当前 BRCA 的直接启动命令。

### 11.4 精确的运行身份应看参数与保存记录

下列是辨识模型身份的参数片段，不是完整启动命令，本次没有执行训练：

```bash
# L：原始复现基线
--mrepath_genomic_encoder original
--mrepath_gene_aggregation default
--mrepath_rebalance_variant original

# C4 编码器，但尚未增加外部 KAN
--mrepath_genomic_encoder pc_cmka_ddkac
--pc_cmka_config configs/pc_cmka_ddkac_word.json
--pc_cmka_experiment C4_bernoulli_views
--mrepath_gene_aggregation default

# B：基础 Bernoulli Views + 外部 KAN
--mrepath_genomic_encoder pc_cmka_ddkac
--pc_cmka_config configs/pc_cmka_ddkac_word.json
--pc_cmka_experiment C4_bernoulli_views
--mrepath_gene_aggregation kan
--mrepath_rebalance_variant original
```

注意 `genomic_encoder=dd_kac` 与 `pc_cmka_ddkac` 是两个不同的实际编码器选项；不能因为 YAML 用了泛称 dd_kac，就在 C4 命令里误传成旧编码器。

基础 B 的 JSON 中应保持 `bernoulli_kan.mode=off`；“外部 aggregation=kan”和“内部 bernoulli_kan.mode”是两个独立开关。

## 12. BK_Ixx 为什么不能混入基础组合

`PCCMKADDKACEncoder` 有一个可选内部 `BernoulliKANInnovation`。仅当对应 mode 不是 off 时才创建并执行。

它会读取：

- 六组基准表示；
- 六组 positive/negative 视图表示；
- 掩码重叠、并集/交集及其他结构摘要。

因此 BK_I03 的“掩码摘要条件化样条系数”、BK_I06 的“Jensen 去偏”等，是基础 C4+外部 KAN 没有的额外机制。

常见误报需要避免：

1. 把 BK_I03 的结果写成普通 C4 + KAN 的结果。
2. 把外部 `KANGeneAggregator` 与内部 `BernoulliKANInnovation` 当作同一个开关。
3. 在内部已有 KAN 的 BK 变体外面再打开外部 KAN，却仍沿用原变体名称而不记录额外堆叠。
4. 把研究过的 Quality + Conflict 自动写进所有“我们模型”的结构图。

## 13. 数据和训练协议：不是网络创新，但会影响比较

### 13.1 原始数据下载不等于论文多组学条件已经补齐

目前下载任务针对项目固定五折病例对应的公开原始诊断 SVS。

- BLCA、COREAD、HNSC、STAD 的清单文件已经下载完整。
- BRCA 原始 SVS 在下载。
- 这不等于取得五个 TCGA 队列的全部病例和全部模态。
- 也不等于重新提取了全部 ResNet50 特征或重建了训练队列。

论文方法描述 RNA-seq、CNV、SNV；本项目当前公开复现主要使用 RNA/pathway 输入。必须把这种输入条件差异单列，不算成 KAN 或 Bernoulli 的模型贡献。

### 13.2 病例数和终点

本项目记录：BRCA 实际训练 871 例，论文正文报告 968 例；STAD 的独立汇总为 316 个公开 RNA 可用病例。下载清单的病例/切片数量不是实际模型训练病例数。

COREAD 复现协议记录了 298 metadata、297 固定划分病例、其中 295 有发布 RNA 的数据限制。该记录用于说明公开数据边界；每个新实验仍应从实际 dataset manifest 重新核对有效病例，不能机械套用历史数量。

本地主要终点是 DSS。论文概述文字使用 overall survival 的描述，精确终点对齐仍应核对作者数据与划分，不在本文武断断言二者已完全对齐或一定不同。

### 13.3 RNA 归一化与图估计

当前数据加载器在训练折拟合 `MinMaxScaler(feature_range=(-1,1))`，验证折使用训练 scaler。

另外，代码把原始 RNA 中为零的位置在变换后重新设为零。相关性图是在训练 split 的处理后 RNA 上构建，因此不能不加区分地说它直接使用完全未经处理的原始 RNA。

### 13.4 生存时间分箱开关

`--fold_survival_bins` 控制是否每折仅用训练病例拟合离散时间分箱。PC-CMKA runner 显式传入该开关，但通用 argparse 默认是 false。

因此“同 seed、同五折文件”并不能自动保证历史原始模型和新模型的时间分箱完全一致。正式对照需要核对该开关及实际 bins。

### 13.5 模型选择和统计口径

- 现有主要结果使用每折最佳验证 C-index checkpoint。
- 同一验证折既用于选择 epoch，又用于报告该最优 checkpoint 的指标；这不是额外独立的最终测试集。
- 如果还在这些折上筛选大量结构，报告“挑选后的最佳模型”会有选择乐观偏差，需要独立评估/嵌套选择等设计来约束结论。
- COREAD 基础组合和 BRCA 表使用总体标准差 ddof=0；STAD 独立报告和部分 BK 表使用样本标准差 ddof=1。
- 相同 seed 不保证不同网络构建顺序下所有参数初始化和后续随机流完全一致；更不能拼接不同运行的最好 fold。

这些不是“新增模型模块”，但会影响我们是否能够公平归因。

## 14. 相对作者发布代码的修复，不能算成本次创新

项目的 `docs/REPRODUCTION_CONTRACT.md` 记录了论文与发布代码之间的差异，包括：

- 发布训练脚本的优化器、weight decay、alpha 和采样设置与论文文字存在冲突，本地选择论文 profile。
- 发布实现中动态权重计算/应用及 holo-confidence 公式的差异。
- 病理节点采样后边与特征行的重映射问题。
- 本地按论文解释修复权重应用、梯度路径和图索引对齐。

本次没有重新拉取作者仓库逐行审查这些历史修复；上述是项目复现协议的记载。讨论创新时，应把它们列为 **R → L 的复现修正**，而不是 **L → B 的 Bernoulli/KAN 贡献**。

同样，日志、缓存、资源记录、失败恢复、下载直连等属于工程改进，不是生存模型结构创新。

## 15. 已有性能：可支持什么，不能支持什么

### 15.1 主比较记录

单位为 C-index（%），均值 ± 原报告标准差；未统一重新计算所有标准差。

| 数据集 | 原始复现 MRePath | 基础 Bernoulli Views + KAN | 均值差（百分点） | 论文 MRePath |
|---|---:|---:|---:|---:|
| COREAD | 72.65 ± 11.77 | 77.98 ± 9.85 | +5.33 | 80.8 ± 5.8 |
| STAD | 62.88 ± 5.08 | 66.15 ± 3.59 | +3.27 | 67.5 ± 3.3 |
| BRCA | 74.53 ± 8.29 | 本次未找到该基础组合的完整正式结果 | — | 72.9 ± 1.9 |

注意：这些是来源报告的历史比较，不是本次新跑或重新逐病例计算的结果，也不证明历史两套基础组合与今天代码在每个细节上完全一致。

STAD 另一个批次的 `SHGNN+MLP` 记录为 64.11 ± 5.63，不能覆盖上述与 Bernoulli 对照配套的 62.88 ± 5.08。

### 15.2 比较 KAN 与 GCN

| 数据集 | Bernoulli + GCN | Bernoulli + KAN | KAN 均值增加 | KAN 获胜折数 |
|---|---:|---:|---:|---:|
| COREAD | 76.29 ± 9.71 | 77.98 ± 9.85 | +1.69 pp | 2/5 |
| STAD | 63.38 ± 5.29 | 66.15 ± 3.59 | +2.77 pp | 3/5 |

这支持“这些单种子五折记录中，KAN 的平均 Harrell C-index 较高”，不支持“所有 fold、所有 seed 都提升”。

### 15.3 其他指标没有同步改善

STAD 独立报告：

| 模型 | Harrell C-index ↑ | IPCW C-index ↑ | IBS ↓ | iAUC ↑ |
|---|---:|---:|---:|---:|
| 原始 MRePath | 0.6288 | 0.6115 | 0.2802 | 0.4558 |
| Bernoulli + KAN | 0.6615 | 0.6063 | 0.5746 | 0.4029 |

所以不能把 Harrell 排序均值提升写成生存概率质量、删失稳健性、时间依赖判别等全面提升。跨指标的具体原因仍待检查时间网格、评价口径与校准，不凭这个表直接断言根因。

### 15.4 后续变体的结果单独保留

例如 `BK_I03_mask2spline_hyperkan` 为 COREAD 80.32 ± 9.68、STAD 60.66 ± 4.06；`BK_I06_bernoulli_jensen_debiased` 的 STAD 为 64.20 ± 4.71。

它们不是基础组合的 77.98/66.15，也不能挑选其中一个数据集最好值拼成同一个方法的跨数据集结果。

### 15.5 证据完整性限制

本次主机能直接检查当前源代码，以及图结构筛选 C4 的配置快照；该快照的核心 fixed/Bernoulli/SSL 配置与本文一致，但其结果目录是 `ga-default`，不是外部 KAN 组合的完整证据。

基础组合的 77.98/66.15 来源主要是 `COREAD.md`、`STAD_ALL_EXPERIMENTS_SUMMARY_ZH.md` 及合并后的 `table.md`。

本次在当前主机未找到以下基础组合原始目录：

```text
results/results_pc_cmka_graph_structure_aggregation/coadread/
results/results_pc_cmka_graph_structure_aggregation/stad/
results_pc_cmka_graph_structure_aggregation/coadread/
results_pc_cmka_graph_structure_aggregation/stad/
```

STAD 报告指向原机器的 `/mnt/f/Sheaf-TCGA/results/stad_project10/bernoulli_views_gcn_kan_seed1/formal_30e_4096p/`。

因此，本文对“当前代码怎样实现基础组合”的描述是直接代码证据；对“历史基础组合是否用的完全同版实现”的确认仍需拿到当时的命令、resolved config、模型结构文本、代码版本和逐病例预测。

## 16. 怎样设计实验才能知道到底是哪一块有效

以下是建议的后续实验设计，不是已启动或已完成清单。

### 16.1 首先做严格受控的最小矩阵

| 实验 | 组内编码器 | Bernoulli/一致性 | 外部聚合器 | 想回答的问题 |
|---|---|---|---|---|
| E0 | 原始 MLP/SNN | 无 | default | 原始基线 |
| E1 | 同一 PC-CMKA fixed 实现 | 关闭双视图及 SSL | default | 替换组内编码器本身的作用 |
| E2 | 与 E1 相同 | 开启 C4 双视图及 SSL | default | 双视图一致性训练的增量 |
| E3 | 与 E1 相同 | 关闭双视图及 SSL | KAN | KAN 在固定组内编码器上的增量 |
| E4 | 与 E1 相同 | 开启 C4 双视图及 SSL | KAN | 两个机制组合的效果 |

E1–E4 应保持同一图构建、同一谱尺度、同一编码器类、相同其他损失设置和训练协议，不能用旧 `DDKACEncoder` 替代 E1 后声称只比较 Bernoulli。

对 moment/dictionary 等辅助项，应明确选择“所有这几组均保留”或“所有均关闭”，并单独记录，不要只在某一组悄悄清零。

E0 与 E1 是整套编码器替换，仍不是所有子机制的单变量实验；若要解释组内编码器，还需分别拆值域、图结构域、门控和残差。

### 16.2 进一步区分聚合收益来自哪里

- 在同一组内编码器下比较 default、参数量相近的 MLP mixer、GCN、GAT、KAN。
- 对 KAN 分别测试“仅特征维变换”“仅组维混合”“两级均启用”。
- 比较是否添加外部残差，以及不同 grid_size、dropout。
- 检查输入特征落在样条有效区间的比例，但不要使用验证标签选择网格。
- 报告参数量、峰值显存、单 epoch 时间和推理时间。

### 16.3 进一步区分双视图收益来自哪里

- 同一实现下比较不增强、单视图、双视图和不同保留概率。
- 区分 structure-only、fusion-only、structure+fusion 的 SSL。
- 比较共享与独立的频率路由。
- 若声称“Bernoulli 与 KAN 显式耦合”，需要另加外部 KAN 输出的一致性等可观测机制，再与目前松耦合基础组合比较。

注意：当前主预测只用基准表示。如果只计算随机视图但把相关损失完全关掉，就没有新增的视图监督梯度路径；即使数值轨迹仍可能因消耗随机数而变化，也不能把这种变化称为视图学习收益。

### 16.4 公平比较底线

- 固定病例交集、WSI/RNA 输入、fold、终点、时间分箱与评价器。
- 多个随机种子，保留逐病例预测及逐折配对差值。
- 不把五个交叉验证折简单当成五个独立临床样本做过度显著性推断。
- 同时关注 Harrell、IPCW、IBS、iAUC 与概率校准。
- 最终结论需要与模型选择过程分离的评估设计。

## 17. 本次实际做了哪些验证

### 17.1 静态源代码检查

检查了主模型、KAN、PC-CMKA 编码器、图增强、图校准、谱算子、损失、配置解析、训练 loop、数据归一化、图构建和 runner 参数。

没有修改上述文件。对论文的描述使用本地 PDF；对作者发布代码历史修复的说明使用项目复现协议，未假装本次重新联网核验作者仓库。

### 17.2 CPU 合成数据计算图检查

为验证最容易混淆的数据流，使用当前 PyTorch，在 CPU 上构造六个各有四基因的简单图，实例化真实 `PCCMKADDKACEncoder(C4)` 与真实 `KANGeneAggregator`。没有使用真实病例，没有 optimizer step，没有生成正式实验输出。

当前默认 Python 缺少 pandas，直接导入配置工具失败；随后仅从原文件 AST 提取其两个纯配置函数 `deep_update`/`load_pc_cmka_config` 执行，避免导入 pandas。没有安装或修改环境，也没有把这个小检查当作完整训练环境验收。

实际输出：

```text
encoded_shape = (1, 6, 256)
aggregated_shape = (1, 6, 256)
KAN_parameters = 591632
encoder_aux_has_outer_KAN_grad = False
prediction_path_has_outer_KAN_grad = True
C4_base_output_unchanged_across_view_samples = True
```

解释：

- 外部 KAN 保持六 token 接口。
- 编码器辅助损失对外部 KAN 参数的梯度为 unused/None。
- 以聚合后特征的一项作为主预测链路代理，能向外部 KAN 传递非零梯度；这不是完整生存损失端到端验证。
- 固定输入、参数和基准图时，C4 编码器的基准输出不随两次随机视图采样改变。这不表示外部 KAN 在 train 模式下也完全确定，因为它有 Dropout。
- 此检查不能证明真实队列性能，也不能替代完整训练的依赖、数据和资源检查。

## 18. 供 GPT 回答的具体问题

请基于上面的实际实现回答，而不是只根据“Bernoulli + KAN”这个名字评价：

1. 相比原始 MRePath，哪些是架构替换，哪些是训练正则，哪些只是复现修复或工程改进？
2. M3 的值域/图结构域双分支、门控、频率路由各自承担什么功能？是否存在冗余或归因不清？
3. M4 的两级 KAN 与常规 MLP mixer、GCN、IFA 自注意力的区别是什么？哪些区别已有代码证据，哪些必须实验才能确定？
4. 基础 C4 中双视图未直接经过外部 KAN，应该称为模块串联、松耦合联合训练，还是有更精确的术语？不能仅凭名称声称显式协同。
5. fixed 模式下仍保留 moment target/dictionary 损失是否有必要？若去除，如何做不改变其他条件的验证？
6. 旧 `dd_kac` 与 `pc_cmka_ddkac` 的谱算子和目标不同，现有 fixed-vs-Bernoulli 对照能支持多强的因果结论？
7. batch size=1 时的特征维方差惩罚，与 batch 维的防塌缩约束有哪些不同？
8. KAN 所用固定样条网格、输入分布、没有外部残差等，有哪些应检查但尚不能下结论的风险？
9. 当前 C-index 均值提高但 IBS/IPCW/iAUC 未同步改善，后续应怎样排查和设计评价？
10. 在不堆更多模块的前提下，最小消融矩阵应该是什么？目前缺少哪些运行原始证据？
11. 若评价论文创新性，需要补充检索哪些已有方向（图随机增强、一致性正则、图谱滤波、KAN mixer、跨模态生存分析）？请不要未经检索就宣称首创。
12. 请给出一份可以真实对应当前代码的模型描述，并指出哪些宣传性说法应删除或改弱。

## 19. 源文件索引

下面路径以 `/xmlg/Lim/Project1` 为项目根目录。将本文复制给外部 GPT 后，即使其无法打开这些链接，前文也已包含主要实现信息。

| 内容 | 源文件 |
|---|---|
| 论文原文 | [Sheaf超图.pdf](/xmlg/Lim/Project1/Sheaf超图.pdf) |
| 复现合同与已知公开数据限制 | [REPRODUCTION_CONTRACT.md](/xmlg/Lim/Project1/docs/REPRODUCTION_CONTRACT.md) |
| 论文 COREAD 本地 profile | [paper_coadread.json](/xmlg/Lim/Project1/configs/paper_coadread.json) |
| 当前模块选择说明 | [model.yaml](/xmlg/Lim/Project1/model.yaml) |
| 主模型、原始基因编码、独立聚合、权重和头 | [model_HGNN.py](/xmlg/Lim/Project1/models/model_HGNN.py:66) |
| 原始 SNN_Block 的实际 ELU 实现 | [models/util.py](/xmlg/Lim/Project1/models/util.py:116) |
| IFA 的 SA/PG/GP 前向 | [fusion.py](/xmlg/Lim/Project1/models/layers/fusion.py:60) |
| KANLinear 与外部 KANGeneAggregator | [kan.py](/xmlg/Lim/Project1/models/layers/kan.py:208) |
| 旧 DDKACEncoder | [genomic_encoders.py](/xmlg/Lim/Project1/models/layers/genomic_encoders.py:426) |
| PC-CMKA 组内编码器与内部 BK 分支入口 | [encoder.py](/xmlg/Lim/Project1/models/layers/pc_cmka/encoder.py:27) |
| 校准模式、fixed 行为、目标网络和字典 | [calibration.py](/xmlg/Lim/Project1/models/layers/pc_cmka/calibration.py:222) |
| 固定参考谱算子与 Chebyshev 响应 | [spectral.py](/xmlg/Lim/Project1/models/layers/pc_cmka/spectral.py:11) |
| Bernoulli 采样和 train_only | [augmentation.py](/xmlg/Lim/Project1/models/layers/pc_cmka/augmentation.py:246) |
| 一致性损失及 batch=1 分支 | [losses.py](/xmlg/Lim/Project1/models/layers/pc_cmka/losses.py:9) |
| 后续 BK_Ixx 内部 KAN 机制 | [bernoulli_kan.py](/xmlg/Lim/Project1/models/layers/pc_cmka/bernoulli_kan.py) |
| JSON 合并、训练折 prior 构建 | [utils/pc_cmka.py](/xmlg/Lim/Project1/utils/pc_cmka.py:28) |
| 公共数值配置和 C4/BK overrides | [pc_cmka_ddkac_word.json](/xmlg/Lim/Project1/configs/pc_cmka_ddkac_word.json) |
| 图结构名称到 preset 的映射、默认聚合参数 | [run_pc_cmka_word_ablations.py](/xmlg/Lim/Project1/scripts/run_pc_cmka_word_ablations.py:29) |
| 实际命令行开关 | [process_args.py](/xmlg/Lim/Project1/utils/process_args.py:115) |
| 辅助损失进入训练的实际位置 | [core_utils.py](/xmlg/Lim/Project1/utils/core_utils.py:529) |
| 分箱、归一化、训练/验证 scaler | [dataset_survival.py](/xmlg/Lim/Project1/datasets/dataset_survival.py:422) |
| 合并后的历史结果总表 | [table.md](/xmlg/Lim/Project1/table.md) |
| COREAD 基础组合报告 | [COREAD.md](/xmlg/Lim/Project1/COREAD.md) |
| STAD 独立报告 | [STAD_ALL_EXPERIMENTS_SUMMARY_ZH.md](/xmlg/Lim/Project1/STAD_ALL_EXPERIMENTS_SUMMARY_ZH.md) |

## 20. 可直接复制到对外讨论中的保守表述

> 我们以本地复现的 MRePath 为基线，保留其病理 SHGNN、动态模态加权、交互对齐融合和离散生存预测头，重点改造基因组分支。原始六功能组 MLP 编码被替换为结合表达值域与训练折基因图谱响应的双域编码器；训练时通过 Bernoulli 边采样构造双视图，对组内结构表示及值域–结构融合表示施加一致性约束。随后在六组基准编码表示上增加由特征维变换和组维混合组成的 KAN 聚合器。基础实现中随机视图用于编码器辅助训练，未直接送入外部 KAN，也没有启用掩码条件化样条、KAN 反馈采边或 Quality + Conflict。已有单种子五折记录显示部分队列的平均 Harrell C-index 提高，但尚不能将提升归因于单一模块，也未证明跨种子稳定性或各类生存指标全面改善。
