# Bernoulli Views + KAN 后续改进：五个高新颖度模块方案

> 形成日期：2026-08-11
> 基础模型：TCGA-STAD Bernoulli views + KAN，seed 1
> 当前结果：Harrell C-index **66.15% ± 3.59%**
> 研究目标：建立 Bernoulli graph views 与 KAN 之间的直接、可解释联系，而不是继续简单串联模块

## 1. 当前实现的关键缺口

当前代码中的信息流为：

```text
基因图
  └─ Bernoulli 双视图
       └─ PC-CMKA 六个通路表示
            └─ KAN 六通路聚合
                 └─ WSI/RNA 融合与生存预测
```

Bernoulli 双视图目前只在每个 PC-CMKA pathway 内产生结构与融合一致性损失。pathway encoder 最终返回原始图的 `fused` 表示，后续 `KANGeneAggregator` 没有直接看到：

- 两个 view 的表示；
- Bernoulli edge mask；
- 两个 view 的分歧或不确定性；
- KAN 对不同 view 的样条响应变化。

因此，当前的 Bernoulli views 和 KAN 本质上只是前后串联。后续改进的核心应是建立以下一种或多种直接联系：

1. `view representation → KAN`；
2. `view mask → KAN parameters`；
3. `KAN sensitivity → Bernoulli probability`；
4. `view uncertainty → KAN complexity`；
5. `mask set algebra → KAN interaction decomposition`。

## 2. 五个方案总览

| 优先级 | 模块名称 | Bernoulli 与 KAN 的直接联系 | 主要目标 | 新颖度判断 | 实现难度 |
|---:|---|---|---|---:|---:|
| 1 | **BV-JetKAN** | 双视图进入共享 KAN，并约束 KAN 样条导数 | 提高扰动鲁棒性、抑制样条过拟合 | 高 | 中低 |
| 2 | **UVR-KAN** | 视图分歧控制粗/细 KAN 的使用比例 | 改善校准和折间稳定性 | 高 | 中 |
| 3 | **Mask2Spline HyperKAN** | Bernoulli mask 直接调制 KAN 样条系数 | 学习结构条件化非线性 | 很高 | 中高 |
| 4 | **KAN2Bern Controller** | KAN 的样条敏感性反向生成边保留概率 | 形成 KAN 与视图采样闭环 | 很高 | 高 |
| 5 | **BML-KAN** | mask 交集/并集通过 KAN 做集合分解 | 学习稳定、独有和协同结构 | 极高 | 高 |

## 3. Idea 1：BV-JetKAN

### 3.1 名称

**Bernoulli View–Jet Consistent KAN，简称 BV-JetKAN。**

这里的 `Jet` 指函数在某一点的输出及局部导数信息。

### 3.2 模块结构

让 Bernoulli 正负双视图产生的六通路表示都通过同一个 KAN：

\[
z^+=E(G\odot M^+),\qquad z^-=E(G\odot M^-)
\]

\[
h^+=KAN(z^+),\qquad h^-=KAN(z^-)
\]

在现有表示一致性之外，加入 KAN 层的一阶导数一致性：

\[
\mathcal L_{jet}
=\|h^+-h^-\|_2^2
+\lambda_J\|J_{KAN}(z^+)-J_{KAN}(z^-)\|_F^2
\]

其中 `J_KAN` 是 KAN 输出对六通路输入的 Jacobian。由于当前 KAN 使用三次 B-spline，可以通过自动微分或解析样条导数计算。

### 3.3 核心创新

普通对比学习只要求两个 view 的表示或预测接近。BV-JetKAN 进一步要求：

- 两个 view 的输出接近；
- KAN 在两个 view 附近的局部响应方向接近；
- 对同一患者的轻微图扰动，不应产生完全不同的样条斜率。

这让 Bernoulli views 直接约束 KAN 的函数几何，而不是只约束 KAN 之前的 encoder。

### 3.4 为什么适合当前结果

当前 KAN 的 Harrell C-index 较高，但 IPCW C-index、IBS、iAUC 和 validation loss 没有同步改善，可能存在排序导向的局部过拟合。导数一致性能够限制 KAN 学出过陡或高度 view-sensitive 的样条。

### 3.5 最小实验

建议采用递进消融：

1. 当前 Bernoulli + KAN；
2. 双 view 经过共享 KAN，只加输出一致性；
3. 输出一致性 + 一阶 Jacobian 一致性；
4. 若训练稳定，再尝试较弱的二阶曲率正则。

初始建议只跑 Fold 0、2、4，`lambda_J ∈ {1e-4, 5e-4, 1e-3}`。

### 3.6 风险

- 过强的一致性可能抹掉真正有意义的结构差异；
- 二阶导数计算成本较高，首轮不应直接加入；
- 需要确认 view-specific pathway token 能够从 PC-CMKA encoder 返回。

## 4. Idea 2：UVR-KAN

### 4.1 名称

**Uncertainty-gated View-Resolution KAN，简称 UVR-KAN。**

### 4.2 模块结构

利用两个 Bernoulli view 的通路表示差异，估计患者级、通路级结构不确定性：

\[
u_g=\|z_g^+-z_g^-\|_2^2
\]

设置两个复杂度不同的 KAN 分支：

- `KAN_coarse`：较小 grid size，例如 3，曲线更平滑；
- `KAN_fine`：较大 grid size，例如 7，表达能力更强。

使用不确定性进行患者级动态组合：

\[
\alpha_g=\exp(-\tau u_g)
\]

\[
h_g=(1-\alpha_g)KAN_{coarse}(z_g)
+\alpha_g KAN_{fine}(z_g)
\]

含义是：

- view 稳定时，使用精细样条捕获复杂关系；
- view 分歧较大时，自动退回平滑 KAN，避免拟合不可靠结构。

### 4.3 核心创新

KAN 已有 grid update、grid extension 和动态样条研究，但 UVR-KAN 的分辨率不是由统一训练阶段或普通输入范围决定，而是由 **Bernoulli 图视图产生的患者级结构不确定性**决定。

### 4.4 为什么适合当前结果

当前 Bernoulli + KAN 的 C-index 提升主要集中在 Fold 0–2，Fold 3/4 没有超过 GCN，并且 Fold 3/4 的 IBS 很高。UVR-KAN 可以在不可靠病例上主动降低模型自由度，重点解决校准和跨 fold 稳定性。

### 4.5 最小实验

1. `grid 3 + grid 7` 双分支；
2. 首轮固定 `alpha=exp(-tau*u)`，不增加额外 gate 网络；
3. 比较固定 coarse、固定 fine、uncertainty-gated 三组；
4. 主指标同时报告 C-index、IPCW C-index、IBS 和 iAUC。

### 4.6 风险

- 双 KAN 会增加参数量；
- 不确定性尺度可能因通路不同而不一致，需要训练折内标准化；
- 如果 view 差异主要来自随机噪声而非结构可靠性，gate 可能学习不到有效规律。

## 5. Idea 3：Mask2Spline HyperKAN

### 5.1 名称

**Bernoulli Mask-conditioned Spline Hypernetwork，简称 Mask2Spline HyperKAN。**

### 5.2 模块结构

先将高维 Bernoulli edge mask 压缩成低维结构描述：

\[
s(M)=[
keep\ ratio,
degree\ change,
spectral\ shift,
edge\ weight\ loss,
view\ overlap]
\]

使用一个小型 hypernetwork 为 KAN 样条系数生成低秩偏移：

\[
\Delta C(M)=U\,\mathrm{diag}(H(s(M)))\,V
\]

\[
C_M=C_0+\Delta C(M)
\]

不同 Bernoulli view 因此使用不同但共享主体的 KAN 函数：

\[
h_M=KAN_{C_M}(z_M)
\]

加入期望对齐和偏移正则：

\[
\mathbb E_M[h_M]\approx h_{base},
\qquad
\lambda_C\|\Delta C(M)\|_2^2
\]

### 5.3 核心创新

Bernoulli mask 不再只是数据增强，而成为 KAN 函数本身的条件变量。模块能够学习类似以下关系：

- 某类边缺失时，应当平滑哪一段 spline；
- 哪个通路的非线性响应需要增强；
- 不同结构完整度下，六通路之间应如何重新组合。

已有 MetaKAN 使用元网络提高 KAN 的参数效率，但没有发现使用患者级 Bernoulli gene-graph mask 生成 KAN spline adapter 的公开方案。

### 5.4 最小实验

1. 只调制 `pathway_mixer`，暂不调制高维 `feature_encoder`；
2. adapter rank 从 2 或 4 开始；
3. mask summary 使用 5–10 个结构统计量，避免直接输入完整 mask；
4. 加入 `delta coefficient norm` 和 base-view expectation loss。

### 5.5 风险

- STAD 样本量有限，完整 hypernetwork 容易过拟合；
- 样条系数和 pathway token 同时变化可能产生不可辨识性；
- 必须保留 `C_0` 主体和低秩、小幅度 adapter。

## 6. Idea 4：KAN2Bern Controller

### 6.1 名称

**Spline-guided Bernoulli Feedback Controller，简称 KAN2Bern。**

### 6.2 模块结构

前三个方案是 `Bernoulli → KAN`。KAN2Bern 增加反向联系：

```text
Bernoulli view → KAN → spline sensitivity → 下一轮 Bernoulli probability
```

根据 KAN 的 spline slope 和生存风险梯度计算每条基因边的重要性：

\[
s_e=
\left|
\frac{\partial r}{\partial z_g}
\frac{\partial z_g}{\partial w_e}
\right|
\]

构造两类非均匀 Bernoulli view：

\[
p_e^{safe}=\operatorname{clip}(p_0+\beta s_e)
\]

\[
p_e^{hard}=\operatorname{clip}(p_0-\gamma s_e)
\]

- `safe view`：高敏感边更容易保留，用于语义保持一致性；
- `hard view`：在固定扰动预算下挑战高敏感边，用于鲁棒性训练。

继续使用逆概率缩放，尽量保持期望边权不变：

\[
\widetilde w_e=w_e\frac{M_e}{p_e}
\]

### 6.3 核心创新

该模块形成真正的闭环：

- Bernoulli mask 决定 KAN 看到什么；
- KAN 样条的任务敏感性决定下一轮 mask 如何采样。

已有 Khan-GCL 会使用 KAN 系数寻找关键特征并在表示空间构造 hard negative；KAN2Bern 的区别是：

1. 在原始患者基因图边上生成 Bernoulli 概率；
2. 使用生存任务梯度与 KAN spline slope 联合定义敏感性；
3. 同时生成语义保持 view 与预算约束的挑战 view；
4. 验证阶段仍使用未增强原图。

### 6.4 最小实验

1. 冻结已经训练好的 KAN，离线统计 edge sensitivity；
2. 先生成固定的非均匀概率表，不立即端到端更新 controller；
3. 比较 uniform Bernoulli、safe-only、safe+hard；
4. 确认有效后再进行每若干 epoch 更新一次的闭环训练。

### 6.5 风险

- 与 KAN-based graph contrastive hard negative 文献距离最近，投稿前需要重点做新颖性检索；
- 完全端到端更新可能出现采样器与预测器相互追逐；
- hard view 过强可能破坏生物语义，应限制图连通性和扰动预算。

## 7. Idea 5：BML-KAN

### 7.1 名称

**Bernoulli Mask-Lattice KAN，简称 BML-KAN。**

### 7.2 模块结构

对两个 Bernoulli mask 不只计算独立 view，还构造 mask 的交集和并集：

\[
M^\cap=M^+\cap M^- ,
\qquad
M^\cup=M^+\cup M^-
\]

由此得到：

- `z_intersection`：两个 view 都保留的稳定结构；
- `z_unique+`：仅正 view 保留的结构；
- `z_unique-`：仅负 view 保留的结构；
- `z_union`：两个 view 覆盖的全部结构。

使用专门的 `LatticeKAN` 学习：

\[
h=KAN_{lattice}
(z^\cap,z^{+\setminus-},z^{-\setminus+},z^\cup)
\]

加入软性的集合估值关系：

\[
F(M^+)+F(M^-)
\approx
F(M^\cap)+F(M^\cup)+\delta_{KAN}
\]

`delta_KAN` 不强制为零，而是由 KAN 学习非加性生物交互。

### 7.3 核心创新

普通双视图只学习“两个随机扰动应当相似”。BML-KAN 进一步把边集合拆为：

- 稳定共有连接；
- 单视图特有连接；
- 冗余连接；
- 只有在组合下才出现的非线性协同作用。

它把 Bernoulli mask 的布尔格结构和 KAN 的可解释单变量函数结合起来。目前没有检索到使用 KAN 对 Bernoulli 图 mask 的交、并和 Möbius/估值残差进行建模的公开工作。

### 7.4 最小实验

1. 每个样本只使用一对 mask；
2. 先计算 `intersection` 和 `union` 两个额外 view；
3. 使用共享 PC-CMKA encoder，避免四套参数；
4. 比较无 lattice loss、硬 valuation loss、KAN residual 三种方案。

### 7.5 风险

- 每次训练最多需要四个图 view，计算成本最高；
- 严格的集合加法关系可能不适合真实生物网络，因此必须使用软约束和可学习残差；
- 在 316 例队列上可能需要更强正则或先进行跨队列预训练。

## 8. 新颖性检索边界

以下宽泛方向已经存在，不能单独作为创新点：

| 已有方向 | 代表工作 | 对本方案的约束 |
|---|---|---|
| KAN 替换图网络中的 MLP | [KAGNNs](https://openreview.net/forum?id=03UB1MCAMr)、[GraphKAN](https://arxiv.org/abs/2406.13597) | 不能只写“将 KAN 用于图学习” |
| KAN + 图对比学习 | [Khan-GCL](https://ojs.aaai.org/index.php/AAAI/article/view/39890) | 不能只写“KAN 编码双视图” |
| 自适应 edge-drop | [GCA](https://arxiv.org/abs/2010.14945)、[AD-GCL](https://arxiv.org/abs/2106.05819) | KAN2Bern 必须突出 spline sensitivity 与生存任务闭环 |
| 元网络生成 KAN 参数 | [MetaKAN](https://openreview.net/forum?id=9biCmI3Mnd) | Mask2Spline 必须突出患者级 graph mask 条件化 |
| KAN 生存模型 | [CoxKAN](https://arxiv.org/abs/2409.04290)、[SurvKAN](https://arxiv.org/abs/2602.02179) | 不能只把生存预测头换成 KAN |
| KAN 动态 grid/系数 | [原始 KAN](https://openreview.net/forum?id=Ozo7qJ5vZi)、[UKAN](https://openreview.net/forum?id=wj4Az2454x) | UVR-KAN 必须突出 view uncertainty 控制患者级复杂度 |

截至 2026-08-11 的公开检索中，没有发现与上述五个模块完全同构的方法。但“没有检索到”不等于能够绝对证明从未提出；正式投稿前仍需补充 Google Scholar、Web of Science、专利数据库和最新预印本检索。

## 9. 推荐实验顺序

### 第一阶段：最低成本验证直接联系

1. **BV-JetKAN**；
2. 先做 view-level KAN output consistency；
3. 再增加一阶 Jacobian consistency；
4. 只跑 Fold 0、2、4 做门禁。

### 第二阶段：解决当前校准问题

1. **UVR-KAN**；
2. 使用 coarse/fine 双分支；
3. 同时考察 C-index、IPCW C-index、IBS、iAUC 和 loss；
4. 不以单一 Harrell C-index 选择最终方向。

### 第三阶段：论文主创新候选

1. **Mask2Spline HyperKAN**；
2. **KAN2Bern Controller**；
3. 若两者分别有效，可形成双向闭环，但必须保留单模块消融。

### 第四阶段：高风险探索

1. **BML-KAN**；
2. 先在单 fold 检查集合分解是否产生稳定信号；
3. 只有在 lattice residual 有清晰解释时再投入完整五折。

## 10. 建议的主线选择

如果目标是尽快得到可验证结果，推荐主线为：

```text
Bernoulli view-specific pathway tokens
        ↓
Shared KAN
        ↓
Output + Jacobian consistency
        ↓
View uncertainty gated coarse/fine spline
        ↓
Survival prediction
```

可以将这一组合暂命名为：

> **Uncertainty-aware Jet-Consistent Bernoulli KAN（UJ-BKAN）**

其论文假设可以写为：

> Bernoulli 图扰动不仅用于约束通路编码器，还应直接约束 KAN 的函数几何；同时，图视图分歧应控制样条模型的患者级复杂度，从而在保持风险排序能力的同时改善生存概率校准。

该主线与当前结果暴露的问题直接对应，改动范围也比完整的 mask-conditioned hypernetwork 或闭环采样器更可控。
