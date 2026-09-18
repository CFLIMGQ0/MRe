# Bernoulli Views × KAN：五个候选创新模块

## 1. 当前实现与真正的问题

当前项目中的 `bernoulli_views + KAN` 不是一个深度耦合模块，而是前后串联：

1. 在六个功能组各自的基因图内部，以固定保留率生成两个独立 Bernoulli
   删边视图，并使用 `mask / p` 对边权重进行重标定；
2. 在 PC-CMKA-DDKAC 编码器内部，对两个视图的结构表示和融合表示施加
   一致性损失；
3. 编码器最终只返回完整图的六个通路 token；
4. KAN 随后对每个通路进行特征变换，再跨六个通路进行非线性混合。

因此，当前 Bernoulli views 与 KAN 之间没有直接交换以下信息：

- 哪些边被删除；
- 两个 mask 的重合程度；
- 删边引起的通路特征方差；
- KAN 样条曲率和导数；
- 哪些跨通路 KAN 关系对删边稳定。

现有实验中，`bernoulli_views + KAN` 的五折平均 C-index 为
`0.7798 ± 0.0985`，高于对应 GCN 的 `0.7629 ± 0.0971`，但 KAN 只在
2/5 折上领先。因此下一步应优先解决稳定性和训练—测试偏差，而不是继续增加
普通模型容量。

## 2. 新颖性边界

简单的“Bernoulli 删边 + KAN”不能作为创新点：

- [IRGL-RRI](https://pmc.ncbi.nlm.nih.gov/articles/PMC12178140/) 已经在植物
  RNA 图中结合 Bernoulli masking、图编码器和 KAN 解码器；
- [Khan-GCL](https://ojs.aaai.org/index.php/AAAI/article/view/39890) 已经将
  KAN 用于图对比学习，并利用 KAN 系数生成 hard negatives；
- [GKAN](https://arxiv.org/abs/2406.06470) 已经研究 KAN 与图聚合的结合；
- [AD-GCL](https://arxiv.org/abs/2106.05819) 已经研究可学习的图删边增强。

截至 2026-08-11，未检索到以下五个具体模块的直接同构先例。但这只能表述为
“未检索到直接先例”，不能声称绝对无人研究过。

## 3. Idea 1：Bernoulli-Jensen Debiased KAN

### 3.1 问题

Bernoulli 视图使用 `mask / p`，使删边后的边权重在期望上等于原边权重。但
经过非线性 KAN 后，一般存在：

\[
\mathbb{E}[\phi(h_{view})] \neq \phi(\mathbb{E}[h_{view}])
\]

即使 Bernoulli 采样在输入边权重层面无偏，KAN 的样条曲率仍会重新引入
二阶偏差。这会形成训练时随机图与测试时完整图之间的系统性偏移。

### 3.2 模块

让两个 Bernoulli 视图都经过共享 KAN。对于两个视图的通路表示：

\[
\mu=\frac{h_1+h_2}{2},\qquad
v=\frac{(h_1-h_2)^2}{4}
\]

利用 KAN 三次 B-spline 可解析的二阶导数，对双视图 KAN 输出进行局部
Jensen 偏差修正：

\[
z_{BJ}=\frac{\phi(h_1)+\phi(h_2)}{2}
-\frac{1}{2}\phi''(\mu)v
\]

还可以增加完整图锚定损失：

\[
\mathcal{L}_{anchor}=\left\|z_{BJ}-\phi(h_{base})\right\|_2^2
\]

### 3.3 Bernoulli 与 KAN 的联系

- Bernoulli 双视图提供局部结构扰动的方差；
- KAN 提供输入位置相关的样条曲率；
- 只有同时拥有两者，才能估计并修正非线性期望偏差。

### 3.4 预期价值

- 减少随机视图训练与完整图推理之间的偏差；
- 降低高曲率样条对随机删边的过度放大；
- 可能改善当前不同 fold 之间不稳定的问题；
- 在线性聚合器中 `phi''=0`，可形成非常干净的机制消融。

### 3.5 必要消融

- 原始 `bernoulli_views + KAN`；
- 只让双视图经过 KAN，但不做修正；
- 修正项中的 `phi''` 停止梯度；
- 用常数曲率替代真实 KAN 曲率；
- `bernoulli_views + GCN`。

## 4. Idea 2：Overlap-Calibrated Spline Jacobian Consistency

### 4.1 问题

普通一致性只要求两个视图的输出相似。KAN 可能通过两组完全不同的通路样条
关系获得相同输出，从而出现“预测一致但内部机制不一致”。

### 4.2 模块

对于第 `g` 个功能组，计算两个 Bernoulli mask 的边重合率：

\[
r_g=\frac{|M_g^{(1)}\cap M_g^{(2)}|}
{|M_g^{(1)}\cup M_g^{(2)}|}
\]

两个视图经过共享 KAN 后，计算 KAN 对第 `g` 个通路输入的 Jacobian：

\[
J_g^{(v)}=\frac{\partial z^{(v)}}{\partial h_g^{(v)}}
\]

使用 mask 重合率校准导数一致性强度：

\[
\mathcal{L}_{Jac}=
\sum_g r_g\left\|J_g^{(1)}-J_g^{(2)}\right\|_2^2
\]

重合率高的视图应使用相近的通路响应函数；重合率低时不强制完全一致。

### 4.3 Bernoulli 与 KAN 的联系

- Bernoulli mask 决定两个图在结构上有多相似；
- KAN Jacobian 表示模型在两个图中是否使用了相同的通路机制；
- mask overlap 决定 KAN 导数一致性应该有多强。

### 4.4 预期价值

- 抑制 KAN 在小样本上用不稳定样条关系记忆训练病例；
- 比只对齐最终 embedding 提供更强的函数级约束；
- 可以输出各通路 Jacobian 稳定性，增强生物解释。

## 5. Idea 3：Bernoulli-Barycentric Grid KAN

### 5.1 问题

当前 KAN 使用固定 `[-1,1]` 三次 B-spline 网格。Bernoulli 删边会改变通路
特征分布，使完整图和两个视图落入不同样条区间，甚至离开有效网格范围。
KAN 此时可能学习删边造成的数值漂移，而不是稳定的通路关系。

### 5.2 模块

在每个训练 fold 内，分别估计完整图和两个视图的通路特征分位点：

\[
Q_{base}(u),\quad Q_1(u),\quad Q_2(u)
\]

构造三者的一维 Wasserstein barycenter：

\[
\bar{Q}(u)=w_0Q_{base}(u)+w_1Q_1(u)+w_2Q_2(u)
\]

将 `bar_Q` 的等间隔分位点作为三个分支共享的 KAN spline knots，并通过
EMA 缓慢更新。验证集和测试集不得参与结点估计。

### 5.3 Bernoulli 与 KAN 的联系

- Bernoulli 视图提供结构扰动后的输入分布；
- KAN 的样条结点根据完整图与扰动图的公共重心分布确定；
- KAN 的表达分辨率被放在跨视图稳定的区域，而不是固定数值区间。

### 5.4 预期价值

- 减少视图之间的 spline-bin switching；
- 降低固定网格与真实通路特征尺度不匹配的问题；
- 改动和计算成本相对较低，适合快速筛选。

## 6. Idea 4：Bernoulli-Stable Cross-Pathway Spline Gate

### 6.1 问题

KAN 的 pathway mixer 中，每条样条边可以理解为“输入通路 `g` 对输出通路
`r` 的非线性影响”。如果一条跨通路关系在轻微基因图删边后大幅波动，它更
可能是偶然相关，而不是稳定生物关系。

### 6.2 模块

让两个 Bernoulli 视图经过共享 pathway KAN。对于每条跨通路样条边，计算
其视图贡献方差：

\[
V_{r,g}=\operatorname{Var}_{v}
[\phi_{r,g}(h_g^{(v)})]
\]

构造稳定性门：

\[
a_{r,g}=\exp(-V_{r,g}/\tau)
\]

最终聚合为：

\[
z_r=\sum_g a_{r,g}\phi_{r,g}(h_g)
\]

稳定性门可以使用 batch 内估计与训练集 EMA 的组合，并对方差统计停止梯度，
防止模型通过缩小所有样条输出作弊。

### 6.3 Bernoulli 与 KAN 的联系

- 局部基因图 Bernoulli 删边产生结构稳定性证据；
- 该证据直接控制六通路 KAN 中每条跨通路样条边；
- 不是给整个模态一个可靠性分数，而是筛选具体的通路到通路非线性关系。

### 6.4 预期价值

- 抑制由少数训练病例产生的虚假跨通路关系；
- 输出可解释的 `6 × 6` 稳定通路关系矩阵；
- 同时具备性能提升和生物解释潜力。

## 7. Idea 5：KAN-Sensitivity Correlated Bernoulli Views

### 7.1 问题

当前两个 Bernoulli mask 相互独立，可能同时删除风险关键边，也可能在大量
无关边上高度重合，导致正样本对质量不稳定。

### 7.2 模块

利用下游 KAN 的样条导数和通路编码器对基因边的敏感度，计算边的重要性：

\[
s_e=\left\|
\frac{\partial z_{KAN}}{\partial h_g}
\frac{\partial h_g}{\partial w_e}
\right\|
\]

不再独立采样两个 mask，而是学习每条边的联合 Bernoulli 分布：

\[
P(m_e^{(1)},m_e^{(2)}\mid s_e)
\]

- 高敏感边：提高边保留概率，并让两个视图更倾向共同保留；
- 低敏感边：降低保留概率，并让两个视图尽量互补；
- 所有边的平均保留率仍约束为 0.8；
- 敏感度使用 `stop-gradient`；
- 加入熵约束，防止采样退化为固定图。

### 7.3 Bernoulli 与 KAN 的联系

形成闭环：

\[
Bernoulli\ views
\rightarrow KAN
\rightarrow spline\ sensitivity
\rightarrow Bernoulli\ pair
\]

与普通自适应删边不同，这里不仅学习单个 mask 的保留概率，还由下游 KAN
敏感度控制两个 Bernoulli mask 的联合相关性。

### 7.4 预期价值与风险

优点：

- 保护 KAN 高敏感的风险关键结构；
- 在低敏感结构上产生更有差异的双视图；
- 可能同时提高正样本质量和视图信息量。

风险：

- 与自适应图增强、Khan-GCL 的距离比前四个 idea 更近；
- 计算基因边到 KAN 输出的链式敏感度成本较高；
- 必须防止采样器利用标签形成捷径。

## 8. 推荐优先级

| 优先级 | 模块 | 新颖性边界 | 实现成本 | 推荐理由 |
|---:|---|---|---|---|
| 1 | Bernoulli-Jensen Debiased KAN | 高 | 中 | 数学问题最明确，二者缺一不可 |
| 2 | Overlap-Calibrated Jacobian Consistency | 高 | 中 | 直接约束 KAN 函数稳定性 |
| 3 | Bernoulli-Barycentric Grid KAN | 中高 | 低到中 | 最适合快速验证 |
| 4 | Stable Cross-Pathway Spline Gate | 高 | 中 | 性能和通路解释兼顾 |
| 5 | Sensitivity-Correlated Bernoulli Views | 中高 | 高 | 高风险、高收益，近邻工作较多 |

## 9. 第一轮实验建议

五个模块第一轮不要叠加。每个候选分别与以下基线比较：

1. `bernoulli_views + GCN`；
2. 当前 `bernoulli_views + KAN`；
3. 候选模块去掉关键联系后的消融；
4. 完整候选模块。

第一轮保持随机种子 1、原固定五折、4096 patches、30 epochs 和相同 checkpoint
规则。主指标为 C-index，同时报告 IPCW C-index 和 IBS。

候选模块只有满足以下条件才进入三随机种子复验：

- 五折平均 C-index 比当前 KAN 至少提高 0.01；
- 至少 4/5 折方向一致；
- 五折标准差不高于当前 KAN；
- IBS 不变差；
- 去掉 Bernoulli–KAN 联系后提升明显消失，证明增益不是单纯增加参数。

## 10. 最推荐的论文主线

优先实现 `Bernoulli-Jensen Debiased KAN`。它对应一个明确且只在二者结合时
出现的问题：Bernoulli 重标定只能保证线性层面的无偏性，而 KAN 样条曲率会
在聚合后产生 Jensen 偏差。通过双视图方差和 KAN 二阶导数进行修正，可以把
贡献限定为：

> 利用 Bernoulli 图视图估计结构扰动方差，并通过 KAN 样条曲率消除非线性
> 通路聚合中的二阶采样偏差。

这一表述比“把 Bernoulli views 与 KAN 组合”更具体，也更容易通过公式、消融
和压力测试证明模块的必要性。
