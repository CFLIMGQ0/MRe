# Bernoulli Views + KAN 组合创新：十个候选方法与新颖性核查

> 合并来源：`BERNOULLI_KAN_FIVE_NOVEL_IDEAS_ZH.md`、`bernoulli_kan_ideas.md`
> 合并与检索日期：2026-08-11
> 适用项目：MRePath，多模态 WSI + RNA 生存预测
> 基础方案：六个功能组基因图上的 Bernoulli 双视图 + PC-CMKA 编码 + KAN 通路聚合

## 1. 结论先行

这十个方法都不是“所有组成部分均由本项目首次提出”。Bernoulli 图掩码、双视图学习、KAN、Jacobian 正则、超网络、可学习删边、Wasserstein 重心、混合专家和不确定性门控均有既有研究。

特别需要避免宣称“首次将 Bernoulli 与 KAN 结合”：生物图任务中的 [MKAN-MMI](https://pubmed.ncbi.nlm.nih.gov/39512819/) 已使用 Bernoulli 随机掩码、图编码器和 KAN；[IRGL-RRI](https://pmc.ncbi.nlm.nih.gov/articles/PMC12178140/) 也明确结合 Bernoulli 图 masking、GNN 与 KAN 多尺度融合。它们没有实现本文十个方案中的完整耦合机制，但足以否定宽泛的“Bernoulli + KAN 首创”表述。

截至本次针对性公开检索，没有发现与十个方案中任一方案在以下四个层面全部相同的论文：

1. 患者级六功能组加权基因图；
2. Bernoulli 双图视图；
3. KAN 样条的导数、曲率、系数、网格或跨通路边被视图信息直接控制；
4. 与 WSI 联合的监督生存预测。

但是，“未发现完全同构先例”不等于能证明“从未有人做过”。正式投稿前仍应补充 Google Scholar、Web of Science、Scopus、CNKI、专利数据库以及投稿日前最新预印本检索。

## 2. 当前基础实现与创新边界

当前信息流是：

```text
六个功能组基因图
  -> 两个独立 Bernoulli 删边视图（mask / p）
  -> PC-CMKA 内部结构与融合一致性
  -> 完整图的六个 pathway token
  -> KAN 特征变换和跨通路混合
  -> WSI/RNA 融合与生存预测
```

当前 Bernoulli Views 与 KAN 仍然主要是前后串联：KAN 不直接接收两个视图、mask、视图分歧或结构不确定性。因此十个候选的共同目标，是建立以下直接联系之一：

- `view representation -> KAN function geometry`；
- `view uncertainty -> KAN complexity or interaction gate`；
- `mask -> KAN spline parameters/grid`；
- `KAN sensitivity -> Bernoulli probability/correlation`；
- `mask set algebra -> KAN nonlinear interaction decomposition`。

不能单独作为创新点的已有方向包括：

- 随机 Bernoulli edge drop：[DropEdge](https://arxiv.org/abs/1907.10903)、[GraphCL](https://proceedings.neurips.cc/paper/2020/file/3fe230348e9a12c13120749e3f9fa4cd-Paper.pdf)；
- 自适应或可学习图增强：[GCA](https://arxiv.org/abs/2010.14945)、[AD-GCL](https://arxiv.org/abs/2106.05819)、[AutoGCL](https://ojs.aaai.org/index.php/AAAI/article/view/20871)；
- KAN 用于图学习：[GKAN](https://arxiv.org/abs/2406.06470)、[Kolmogorov-Arnold Graph Neural Networks](https://arxiv.org/abs/2406.18354)；
- KAN 与图对比学习：[Khan-GCL](https://ojs.aaai.org/index.php/AAAI/article/view/39890)；
- KAN 生存分析：[CoxKAN](https://arxiv.org/abs/2409.04290)；
- 元网络生成 KAN 参数：[MetaKAN](https://arxiv.org/abs/2506.07549)。

## 3. 十个方法总览与核查结论

判定等级定义：

- **A：暂未发现高度相似方法**——基础组件已有，但完整机制差异明显；
- **B：存在较强近邻**——核心组合有区别，但审稿时必须正面对比；
- **C：高度相似风险**——主要思想已有，当前差异可能只够构成任务化扩展；
- **D：基本相同**——不宜作为方法创新。

| 编号 | 方法 | 最相近的已有方向 | 判定 | 核心结论 |
|---:|---|---|---|---|
| 1 | BV-JetKAN | Jacobian matching、TangentProp、双视图一致性 | B | “视图输出一致”已有；双视图 KAN 样条 Jacobian 一致性未发现完全同构实现 |
| 2 | UVR-KAN | uncertainty-gated MoE、KAN 动态网格/容量 | B | 不确定性控制专家已有；由 Bernoulli 图分歧控制患者级粗/细 KAN 未发现相同实现 |
| 3 | Mask2Spline HyperKAN | HyperNetworks、MetaKAN、内容自适应 KAN 系数 | C | 生成/调制 KAN 系数已有；mask 结构统计条件化低秩 spline adapter 是主要差异 |
| 4 | KAN2Bern Controller | GCA、AD-GCL、图对比显著性、Khan-GCL | C | 任务/显著性指导图增强已有；KAN spline slope + 生存梯度生成 safe/hard edge views 是具体差异 |
| 5 | BML-KAN | 集合格、Möbius/估值分解、子图组合 | A | 交并集数学不新，但未发现用 KAN 学习 Bernoulli mask 格上的非加性生物交互 |
| 6 | Bernoulli-Jensen Debiased KAN | expectation-linear dropout、二阶 delta method | B | dropout 训练/推理期望间隙已有；用双图视图方差和 KAN 二阶样条曲率显式修正未发现相同实现 |
| 7 | Overlap-Calibrated Spline Jacobian Consistency | Jacobian matching、增广一致性、Idea 1 | C | 与 Idea 1 内部高度重叠；新内容主要是用 mask Jaccard overlap 加权 Jacobian 损失 |
| 8 | Bernoulli-Barycentric Grid KAN | KAN adaptive grid、Wasserstein barycenter | A/B | 两个组件均已有，但用 base/双视图分布重心设置共享 spline knots 未发现直接先例 |
| 9 | Bernoulli-Stable Cross-Pathway Spline Gate | 不确定性门控、augmentation variance、interaction gating | B | 以扰动方差抑制不稳定关系已有思想；逐条 KAN 通路样条边门控是具体差异 |
| 10 | KAN-Sensitivity Correlated Bernoulli Views | 可学习图增强、显著性增强、Idea 4 | C | 与 Idea 4 内部高度重叠；联合 Bernoulli 相关结构比普通逐边概率更具体，但不是全新大方向 |

当前没有发现达到 **D（基本相同）** 的直接同构方案，但第 3、4、7、10 项不能以现在的宽泛描述宣称“高新颖度”。

---

## 4. Idea 1：BV-JetKAN

### 4.1 定义

**Bernoulli View-Jet Consistent KAN（BV-JetKAN）**让两个 Bernoulli 视图产生的六通路表示经过同一个 KAN：

\[
z^+=E(G\odot M^+),\qquad z^-=E(G\odot M^-)
\]

\[
h^+=KAN(z^+),\qquad h^-=KAN(z^-)
\]

同时约束输出及一阶局部函数几何：

\[
\mathcal L_{jet}=\|h^+-h^-\|_2^2
+\lambda_J\|J_{KAN}(z^+)-J_{KAN}(z^-)\|_F^2
\]

### 4.2 相似工作

- [Knowledge Transfer with Jacobian Matching](https://proceedings.mlr.press/v80/srinivas18a.html) 已系统使用 Jacobian matching，并说明噪声增强与局部斜率匹配之间的联系；
- Tangent propagation 和 [Robust Learning with Jacobian Regularization](https://arxiv.org/abs/1908.02729) 已用导数约束提升扰动不变性；
- R-Drop 类方法和图双视图学习已要求随机子网络或增强视图输出一致；
- [Khan-GCL](https://ojs.aaai.org/index.php/AAAI/article/view/39890) 已把 KAN 放入图对比框架。

### 4.3 是否一样

**不一样，但属于已有思想的专门化组合，判定 B。** 未发现已有论文同时对 Bernoulli 加权基因图的两个视图施加共享 KAN 输出一致性和 KAN spline Jacobian 一致性，并用于多模态生存训练。真正可主张的贡献是“图结构扰动直接约束 KAN 函数几何”，而不是“首次 Jacobian regularization”。

### 4.4 风险与必要消融

- 与本文件 Idea 7 高度重叠；
- 必须比较：仅输出一致、固定权重 Jacobian 一致、overlap 加权 Jacobian 一致；
- 二阶导数成本高，首轮只做一阶；
- 若 KAN 前的 encoder 已强制两个 view 几乎相同，新增 Jacobian 项可能没有独立作用。

## 5. Idea 2：UVR-KAN

### 5.1 定义

**Uncertainty-gated View-Resolution KAN（UVR-KAN）**以两个图视图的通路分歧估计结构不确定性：

\[
u_g=\|z_g^+-z_g^-\|_2^2,\qquad \alpha_g=\exp(-\tau u_g)
\]

再动态组合低容量平滑 KAN 与高容量精细 KAN：

\[
h_g=(1-\alpha_g)KAN_{coarse}(z_g)+\alpha_g KAN_{fine}(z_g)
\]

图结构稳定时使用精细样条；分歧大时退回平滑样条。

### 5.2 相似工作

- Mixture-of-Experts 已广泛使用输入难度或预测不确定性进行专家门控；
- 原始 [KAN](https://arxiv.org/abs/2404.19756) 包含 grid extension/update；
- [Adaptive Training of Grid-Dependent PIKANs](https://arxiv.org/abs/2407.17611) 和 [Dynamic Framework for Grid Adaptation in KANs](https://arxiv.org/abs/2601.18672) 已研究动态网格和由训练几何决定分辨率；
- 图不确定性领域已经通过随机边和 Monte-Carlo edge dropout 衡量结构不确定性，例如 [Edge-variational GCN](https://arxiv.org/abs/2009.02759)。

### 5.3 是否一样

**不一样，但近邻较多，判定 B。** 已有工作分别覆盖不确定性门控、混合专家和 KAN 网格自适应；暂未发现使用“同一患者 Bernoulli 基因图双视图分歧”直接控制 coarse/fine KAN 比例的实现。

创新表述应限定为：**结构视图不确定性驱动的患者级 KAN 容量选择**。如果只用一个普通 gate 学习两个 KAN 的权重，则很容易被视为常规 MoE。

## 6. Idea 3：Mask2Spline HyperKAN

### 6.1 定义

将 Bernoulli edge mask 压缩成结构统计：

\[
s(M)=[keep\ ratio, degree\ change, spectral\ shift,
edge\ weight\ loss, view\ overlap]
\]

小型 hypernetwork 生成 KAN spline 系数的低秩偏移：

\[
\Delta C(M)=U\,\mathrm{diag}(H(s(M)))\,V,\qquad C_M=C_0+\Delta C(M)
\]

并约束偏移幅度及增强期望与完整图预测的一致性。

### 6.2 相似工作

- HyperNetworks 的基本定义就是由一个网络生成另一个网络的参数；
- [MetaKAN](https://arxiv.org/abs/2506.07549) 已使用较小 meta-learner 生成 KAN 权重；
- 内容自适应或输入条件化的 KAN 系数调制已经开始出现；
- [AutoGCL](https://ojs.aaai.org/index.php/AAAI/article/view/20871) 已学习输入条件化的图视图分布。

### 6.3 是否一样

**架构思想高度相似，但条件变量和任务不同，判定 C。** “超网络生成 KAN 参数”不是新点；当前可区分之处只有：

1. 条件不是任务 ID 或普通样本特征，而是患者 Bernoulli gene-graph mask 的结构摘要；
2. 只生成低秩、小幅的 spline adapter，而非完整 KAN；
3. 用完整图期望锚定限制随机图与推理图偏差；
4. 最终服务于 WSI/RNA 生存预测。

若没有证明 mask 条件化优于参数量匹配的普通 adapter/FiLM，本方案很可能被评为 MetaKAN 的任务化扩展。

## 7. Idea 4：KAN2Bern Controller

### 7.1 定义

利用 KAN spline slope 与生存风险梯度计算基因边敏感度：

\[
s_e=\left|\frac{\partial r}{\partial z_g}\frac{\partial z_g}{\partial w_e}\right|
\]

生成两类非均匀视图：

\[
p_e^{safe}=clip(p_0+\beta s_e),\qquad
p_e^{hard}=clip(p_0-\gamma s_e)
\]

- safe view 更常保留高敏感边；
- hard view 在扰动预算内挑战高敏感边；
- 仍使用 \(w_eM_e/p_e\) 做逆概率缩放；
- 推理阶段使用完整图。

### 7.2 相似工作

- [GCA](https://arxiv.org/abs/2010.14945) 根据图结构重要性自适应设置增强强度；
- [AD-GCL](https://arxiv.org/abs/2106.05819) 学习对抗式 edge dropping；
- [ADEdgeDrop](https://arxiv.org/abs/2403.09171) 由对抗 edge predictor 指导删边；
- Graph Contrastive Saliency 使用梯度显著性生成更保语义的图增强；
- [Khan-GCL](https://ojs.aaai.org/index.php/AAAI/article/view/39890) 已利用 KAN 系数识别关键特征并构造语义 hard negatives。

### 7.3 是否一样

**与现有自适应增强高度接近，但不是完全相同，判定 C。** KAN2Bern 的特定差异是把 KAN 样条斜率、生存任务梯度和原始患者基因图边联合起来，并成对产生 safe/hard 视图。

这里不能声称“首次任务指导的图增强”或“首次 KAN 指导的 hard sample”。可争取的表述是：**KAN spline survival sensitivity-guided paired edge augmentation**。

## 8. Idea 5：BML-KAN

### 8.1 定义

在两个 Bernoulli mask 上构造布尔格元素：

\[
M^\cap=M^+\cap M^-,\qquad M^\cup=M^+\cup M^-
\]

并区分稳定共有、正视图独有、负视图独有和并集结构。LatticeKAN 学习：

\[
h=KAN_{lattice}(z^\cap,z^{+\setminus-},z^{-\setminus+},z^\cup)
\]

使用软估值关系：

\[
F(M^+)+F(M^-)\approx F(M^\cap)+F(M^\cup)+\delta_{KAN}
\]

其中 \(\delta_{KAN}\) 表示非加性生物交互，而不是强制为零。

### 8.2 相似工作

- 集合函数、布尔格、Möbius transform 和 interaction transform 是成熟数学工具，例如 [The interaction transform for functions on lattices](https://doi.org/10.1016/j.disc.2008.12.007)；
- 子图 GNN 和多视图图学习会组合不同子图，但通常不对随机 mask 的交、并、独有部分施加估值残差；
- KAN 已被用于显式非线性交互建模，但未检索到 KAN 与 Bernoulli mask lattice 的直接组合。

### 8.3 是否一样

**暂未发现高度相似的端到端模块，判定 A。** 交集、并集、Möbius/估值本身不能声称为新；相对独特的是把双视图 mask 的集合格分解为 KAN 可学习的非加性通路交互，并用于生存任务。

这是十项中概念差异最大的方法之一，但每个患者最多需要 base、两个独立视图、交集和并集等多次图编码，计算和过拟合风险也最高。

## 9. Idea 6：Bernoulli-Jensen Debiased KAN

### 9.1 定义

`mask / p` 只保证边权在线性层面的期望不变。经过非线性 KAN 后通常有：

\[
\mathbb E[\phi(h_{view})]\ne \phi(\mathbb E[h_{view}])
\]

由两个视图估计局部均值和方差：

\[
\mu=\frac{h_1+h_2}{2},\qquad v=\frac{(h_1-h_2)^2}{4}
\]

利用 KAN spline 二阶导数做局部二阶修正：

\[
z_{BJ}=\frac{\phi(h_1)+\phi(h_2)}{2}
-\frac{1}{2}\phi''(\mu)v
\]

并加入完整图锚定：

\[
\mathcal L_{anchor}=\|z_{BJ}-\phi(h_{base})\|_2^2
\]

### 9.2 相似工作

- [Dropout with Expectation-linear Regularization](https://arxiv.org/abs/1609.08017) 已明确研究 dropout 训练阶段与确定性推理阶段的 expectation gap，并用正则显式控制；
- 二阶 delta method/Taylor 展开使用 Hessian 与方差近似非线性期望偏差，是成熟统计思想；
- dropout 理论已经研究 Hessian 与随机扰动方差的关系，例如 [Stochastic Modified Equations and Dynamics of Dropout](https://proceedings.iclr.cc/paper_files/paper/2024/hash/bd9ea5d671ee761a69dba811348d78ba-Abstract-Conference.html)。

### 9.3 是否一样

**理论问题已有，具体估计器未发现相同实现，判定 B。** 不能声称首次发现 Jensen gap；可以主张用 Bernoulli 图双视图方差和 KAN 可解析样条曲率，对基因图增强到完整图推理的非线性偏差进行显式二阶校正。

必须验证公式符号、二阶近似范围以及两视图方差估计的偏差。只有两个 Monte-Carlo 样本时，\(v\) 方差很大；需要与 4/8 视图估计、只做 expectation-linear anchor、常数曲率等基线比较。

## 10. Idea 7：Overlap-Calibrated Spline Jacobian Consistency

### 10.1 定义

对功能组 \(g\) 计算两个 mask 的 Jaccard overlap：

\[
r_g=\frac{|M_g^{(1)}\cap M_g^{(2)}|}{|M_g^{(1)}\cup M_g^{(2)}|}
\]

再用它校准 KAN Jacobian 一致性：

\[
\mathcal L_{Jac}=\sum_g r_g
\left\|J_g^{(1)}-J_g^{(2)}\right\|_2^2
\]

结构重合高时强制局部通路机制接近；重合低时减弱约束。

### 10.2 相似工作

- Jacobian matching、TangentProp 和数据增强诱导局部导数不变性已经存在；
- 多视图学习中使用视图相似性、置信度或质量调节一致性权重是常见思想；
- 本文件 Idea 1 已经提出双视图 KAN Jacobian consistency。

### 10.3 是否一样

**对外没有发现完全相同公式，但与 Idea 1 内部高度相似，判定 C。** 它不应作为与 BV-JetKAN 平行的完整主创新，更适合作为 BV-JetKAN 的一个加权版本或消融：

```text
BV-JetKAN
  ├─ uniform Jacobian consistency
  └─ overlap-calibrated Jacobian consistency
```

此外，公式当前可能方向不合理：overlap 低往往意味着扰动更强，此时既可以“减少一致性约束以免过约束”，也可以“增加鲁棒性约束”。必须通过理论假设和消融决定，而不能仅凭直觉。

## 11. Idea 8：Bernoulli-Barycentric Grid KAN

### 11.1 定义

在每个训练 fold 内估计完整图与两个视图的通路特征分位函数：

\[
Q_{base}(u),\quad Q_1(u),\quad Q_2(u)
\]

构造一维 Wasserstein barycenter：

\[
\bar Q(u)=w_0Q_{base}(u)+w_1Q_1(u)+w_2Q_2(u)
\]

以 \(\bar Q\) 的等间隔分位点作为三个分支共享的 KAN spline knots，并通过训练集 EMA 缓慢更新。验证集和测试集不得参与 knot 估计。

### 11.2 相似工作

- 原始 KAN 和后续工作已根据输入分布更新 spline grid；
- AdaptKAN/动态 grid 工作已使用层分布、训练指标或曲率调整 knot；
- Wasserstein barycenter 已广泛用于多分布共识、域适配和模型融合；[Wasserstein Barycenter Matching](https://proceedings.mlr.press/v202/chu23a.html) 还将其用于图神经网络的图尺度泛化。

### 11.3 是否一样

**组件已有，但未发现“增强视图分布重心 -> KAN knots”的直接先例，判定 A/B。** 它与普通 KAN grid update 的关键差异不是“使用分位点”，而是训练目标明确要求 knots 同时覆盖完整图和 Bernoulli 扰动图的共同分布几何。

本方案较容易实现，但需注意：一维 Wasserstein-2 重心的分位函数加权成立需要明确的分布和权重设定；各通路、各特征维度是否分别建 grid 也要写清楚。

## 12. Idea 9：Bernoulli-Stable Cross-Pathway Spline Gate

### 12.1 定义

对 KAN pathway mixer 中每条“输入通路 \(g\) -> 输出通路 \(r\)”样条边，计算双视图贡献方差：

\[
V_{r,g}=Var_v[\phi_{r,g}(h_g^{(v)})]
\]

构造稳定性门并作用于完整图：

\[
a_{r,g}=\exp(-V_{r,g}/\tau),\qquad
z_r=\sum_g a_{r,g}\phi_{r,g}(h_g)
\]

方差统计结合样本内估计和训练集 EMA，并停止梯度，避免模型通过统一缩小输出作弊。

### 12.2 相似工作

- 数据增强理论已将增强后的特征方差解释为复杂度正则；
- 不确定性门控和 MoE 会降低不可靠专家或模态的权重；
- Monte-Carlo edge dropout 已用于量化图结构不确定性；
- feature/interaction gate 已经逐特征或逐交互选择可靠关系。

### 12.3 是否一样

**核心原则已有，但门控粒度和 KAN 位置不同，判定 B。** 暂未发现直接以 Bernoulli 基因图视图方差控制每条跨通路 KAN spline edge 的论文。可争取的贡献是“结构扰动证据驱动的通路到通路非线性关系稳定选择”，不是泛化的“不确定性门控”。

它和 UVR-KAN 的区别是：UVR 控制整个通路的模型复杂度，本文控制具体 \(6\times6\) 跨通路函数边；二者不应在第一轮叠加。

## 13. Idea 10：KAN-Sensitivity Correlated Bernoulli Views

### 13.1 定义

通过下游 KAN 与图编码器的链式敏感度定义边重要性：

\[
s_e=\left\|\frac{\partial z_{KAN}}{\partial h_g}
\frac{\partial h_g}{\partial w_e}\right\|
\]

不再独立采样两个 mask，而是为每条边学习联合 Bernoulli 分布：

\[
P(m_e^{(1)},m_e^{(2)}\mid s_e)
\]

- 高敏感边提高边际保留概率，并让两个视图更倾向共同保留；
- 低敏感边降低保留概率，并鼓励两个视图互补；
- 全图平均保留率仍约束为 0.8；
- 敏感度停止梯度，并加入熵/相关预算约束。

### 13.2 相似工作

- 自适应、可学习和显著性指导的 edge drop 已经较成熟；
- [AutoGCL](https://ojs.aaai.org/index.php/AAAI/article/view/20871) 学习条件化视图生成分布；
- Graph Contrastive Saliency 使用梯度识别语义相关子结构；
- [Khan-GCL](https://ojs.aaai.org/index.php/AAAI/article/view/39890) 根据 KAN 参数识别关键特征并生成 hard negatives；
- 本文件 Idea 4 同样使用 KAN 敏感度反向控制 Bernoulli edge sampling。

### 13.3 是否一样

**与 Idea 4 和外部自适应增强都高度接近，判定 C。** 具体差异在于它显式学习两个 mask 的联合相关结构，而不只是分别设置 \(p_e^{safe}\) 与 \(p_e^{hard}\)。这是一项有意义的机制细化，但不足以和 KAN2Bern 同时包装成两个完全独立的大创新。

建议将二者统一为：

```text
KAN-guided Bernoulli Controller
  ├─ independent safe/hard marginals（Idea 4）
  └─ sensitivity-conditioned correlated pair（Idea 10）
```

后者作为增强版，前者作为简单基线。

## 14. 十个方案之间的内部重复关系

| 方案组 | 重叠程度 | 建议处理 |
|---|---|---|
| Idea 1 BV-JetKAN vs Idea 7 Overlap-Jacobian | **高** | 合并为一个主模块；uniform/overlap-weighted 作为两个版本 |
| Idea 4 KAN2Bern vs Idea 10 Correlated Views | **很高** | 合并为一个 controller；独立 safe/hard 与联合相关采样作为递进消融 |
| Idea 2 UVR-KAN vs Idea 9 Stable Spline Gate | 中 | 保留两个模块：一个控制容量，一个控制具体跨通路关系 |
| Idea 3 Mask2Spline vs Idea 8 Barycentric Grid | 低 | 前者调系数，后者调 knots，可分别实验，但首轮不要叠加 |
| Idea 1/7 vs Idea 6 Jensen Debias | 中低 | 前者约束一阶局部几何，后者校正二阶期望偏差，理论目标不同 |
| Idea 5 BML-KAN vs 其余方案 | 低 | 独立的集合格/交互分解方向 |

因此，从论文“相互正交的方法方向”看，这十项更合理地归纳为 **8 个方向**，而不是10个完全独立的创新：

1. Jet/Overlap Jacobian consistency；
2. Uncertainty-gated resolution；
3. Mask-conditioned spline hypernetwork；
4. KAN-guided Bernoulli controller；
5. Bernoulli mask lattice decomposition；
6. Jensen debiasing；
7. Barycentric spline grid；
8. Stable cross-pathway spline gate。

## 15. 推荐优先级

| 推荐级别 | 方法 | 理由 |
|---|---|---|
| 1 | Bernoulli-Barycentric Grid KAN | 实现成本较低、机制清晰、目前直接近邻较少 |
| 2 | Bernoulli-Jensen Debiased KAN | 问题定义明确，但需严谨验证二阶估计公式 |
| 3 | BV-JetKAN（含 overlap 消融） | 容易证明 Bernoulli 与 KAN 的直接联系，但 Jacobian 思想已有 |
| 4 | Stable Cross-Pathway Spline Gate | 可输出可解释的 6×6 稳定关系，适合生物分析 |
| 5 | UVR-KAN | 可能改善折间稳定性，但需排除普通 MoE 的参数量收益 |
| 6 | BML-KAN | 概念新颖度较高，但计算量和小样本过拟合风险最大 |
| 7 | Mask2Spline HyperKAN | 与 MetaKAN/条件化系数工作距离较近，需强消融才能站住 |
| 8 | KAN-guided Bernoulli Controller | 与自适应图增强和 Khan-GCL 距离最近，创新风险最高 |

## 16. 统一实验要求

每个方向第一轮不要相互叠加，并至少比较：

1. `bernoulli_views + GCN`；
2. 当前 `bernoulli_views + KAN`；
3. 参数量匹配但切断 Bernoulli-KAN 直接联系的对照；
4. 候选模块去掉关键机制的消融；
5. 完整候选模块。

固定 seed、公开五折、epoch 数、训练样本、patch 上限、终点、checkpoint 和评价代码。除 Harrell C-index 外，同时报告 IPCW C-index、IBS、iAUC、五折标准差和逐折配对差值。

候选进入多随机种子复验前，建议满足：

- 五折平均 C-index 至少提高 0.01；
- 至少 4/5 folds 方向一致；
- 标准差不高于基础 KAN；
- IBS 不变差；
- 切断 Bernoulli-KAN 联系后增益明显下降；
- 参数量匹配的普通 MLP/KAN/MoE 不能解释全部增益。

## 17. 可用与不可用的论文表述

可以谨慎表述：

> 我们研究 Bernoulli 加权基因图视图与 KAN 样条函数之间的直接耦合，使图结构扰动能够控制或约束 KAN 的局部几何、容量、系数、网格、交互门和反向采样策略，并将其用于多模态癌症生存预测。

在完成更系统检索及充分消融前，不应表述：

- 首次把 Bernoulli masking 与 KAN 结合；
- 首次把 KAN 用于图学习或生存分析；
- 首次提出 Jacobian consistency；
- 首次提出 uncertainty-gated experts；
- 首次提出 hypernetwork-generated KAN；
- 首次提出 adaptive/saliency-guided edge drop；
- 十个方法彼此完全独立。

最终最稳妥的贡献单位不是“某个已有组件”，而是经过消融证明不可替代的、任务特定的 **Bernoulli graph perturbation-to-KAN mechanism**。
