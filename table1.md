# TCGA-STAD 全部已完成实验结果总表与综合分析

> 汇总日期：2026-08-11  
> 数据条件：TCGA-STAD，DSS，316 个公开 RNA 可用病例，官方五折  
> 正式协议：每折 30 epochs，best-validation-C-index checkpoint  
> 统计口径：五折 Harrell C-index 算术均值 ± 样本标准差

## 1. 结论摘要

截至目前，共得到 **10 行正式结果**，其中包含 8 组独立训练结果和 2 组病例级后期融合结果。所有正式结果均覆盖相同的 316 个病例和 5 个验证折；smoke、dry-run 与预检不参与排名。

1. **当前 seed 1 的最高单分支结果是 RNA-only SNN：66.99% ± 5.41%。** 这说明当前公开队列中 RNA 分支具有较强信号，但 SNN 在 seed 42 降至 63.54%，尚不能据此认定 RNA-only 稳定优于多模态方法。
2. **当前表现最好的多模态改进是 Bernoulli views + KAN：66.15% ± 3.59%。** 相对本地 MRePath 基线提高 3.27 个百分点，相对 Bernoulli views + GCN 提高 2.77 个百分点，并且折间标准差更低。
3. KAN 的提升不是五折一致：相对 GCN 在 Fold 0/1/2 获胜，在 Fold 3/4 下降。因此当前证据是“有希望的 seed 1 结果”，不是稳定提升结论。
4. **SNN+CLAM 对随机种子较敏感。** seed 1 为 65.27% ± 9.26%，seed 42 为 61.76% ± 8.62%；均值下降 3.51 个百分点，相同 fold 平均绝对变化 5.20 个百分点。
5. **不能只根据普通 C-index 宣称 KAN 全面优于基线。** KAN 的 IPCW C-index、IBS、iAUC 和 validation loss 没有同步改善，提示其当前优势主要体现在 Harrell 风险排序，概率校准和删失稳健性仍需处理。

## 2. 正式实验总表

“训练”表示单独优化过模型参数；“融合”表示使用已经训练好的 SNN/CLAM 病例风险进行算术平均，没有再训练一套融合网络。论文值仅作量级背景，不代表严格同条件复现。

| 实验结果 | 类型 | Seed | 输入模态 | 本地五折 C-index | 最小–最大 | 相对本地 MRePath seed 1 | 论文 STAD 参考 |
|---|---|---:|---|---:|---:|---:|---:|
| MRePath（SHGNN + MLP） | 训练 | 1 | WSI + RNA | **62.88% ± 5.08%** | 57.89%–70.38% | 基线 | 67.50% ± 3.30% |
| Porpoise | 训练 | 1 | WSI + RNA | **62.15% ± 6.95%** | 53.31%–71.92% | −0.73 pp | 66.00% ± 10.60% |
| SNN component | 训练 | 1 | RNA-only | **66.99% ± 5.41%** | 60.42%–75.38% | +4.11 pp | 48.50% ± 4.70%（仅背景） |
| CLAM component | 训练 | 1 | WSI-only | **58.95% ± 5.16%** | 54.66%–64.90% | −3.93 pp | 61.60% ± 7.80%（CLAM-SB，仅背景） |
| SNN+CLAM | 融合 | 1 | WSI + RNA | **65.27% ± 9.26%** | 54.44%–78.85% | +2.39 pp | 62.90% ± 6.50% |
| SNN component | 训练 | 42 | RNA-only | **63.54% ± 6.90%** | 57.60%–74.42% | 不作跨 seed 配对 | 48.50% ± 4.70%（仅背景） |
| CLAM component | 训练 | 42 | WSI-only | **59.77% ± 2.80%** | 55.67%–63.46% | 不作跨 seed 配对 | 61.60% ± 7.80%（仅背景） |
| SNN+CLAM | 融合 | 42 | WSI + RNA | **61.76% ± 8.62%** | 52.53%–75.00% | 不作跨 seed 配对 | 62.90% ± 6.50% |
| Bernoulli views + GCN | 训练 | 1 | WSI + RNA | **63.38% ± 5.29%** | 57.95%–71.15% | +0.50 pp | 无直接对应值 |
| Bernoulli views + KAN | 训练 | 1 | WSI + RNA | **66.15% ± 3.59%** | 62.58%–70.79% | **+3.27 pp** | 无直接对应值 |

## 3. 五折完整结果

| 实验结果 | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 | 五折均值 ± SD |
|---|---:|---:|---:|---:|---:|---:|
| SNN component, seed 1 | 65.23% | 67.41% | 60.42% | 75.38% | 66.50% | **66.99% ± 5.41%** |
| Bernoulli views + KAN, seed 1 | 62.58% | 64.98% | 70.79% | 69.04% | 63.37% | **66.15% ± 3.59%** |
| SNN+CLAM, seed 1 | 65.56% | 68.02% | 59.48% | 78.85% | 54.44% | **65.27% ± 9.26%** |
| SNN component, seed 42 | 57.62% | 64.78% | 57.60% | 74.42% | 63.31% | **63.54% ± 6.90%** |
| Bernoulli views + GCN, seed 1 | 57.95% | 61.13% | 60.42% | 71.15% | 66.26% | **63.38% ± 5.29%** |
| MRePath（SHGNN + MLP）, seed 1 | 59.93% | 57.89% | 60.54% | 70.38% | 65.66% | **62.88% ± 5.08%** |
| Porpoise, seed 1 | 53.31% | 61.13% | 59.13% | 71.92% | 65.26% | **62.15% ± 6.95%** |
| SNN+CLAM, seed 42 | 57.62% | 64.98% | 52.53% | 75.00% | 58.67% | **61.76% ± 8.62%** |
| CLAM component, seed 42 | 59.27% | 55.67% | 59.84% | 63.46% | 60.62% | **59.77% ± 2.80%** |
| CLAM component, seed 1 | 64.90% | 54.66% | 56.07% | 64.23% | 54.91% | **58.95% ± 5.16%** |

## 4. 同折配对比较

相同 seed 1、相同官方 fold 的差值比只比较两个均值更有解释力。由于这里只有 5 个固定验证折且训练随机种子有限，本节不进行显著性宣称。

| 比较 | 平均差值 | 获胜折数 | Fold 0/1/2/3/4 差值（pp） | 结论 |
|---|---:|---:|---|---|
| Bernoulli KAN − MRePath | **+3.27 pp** | 3/5 | +2.65 / +7.09 / +10.25 / −1.35 / −2.28 | 均值明显提高，但并非五折一致 |
| Bernoulli GCN − MRePath | +0.50 pp | 3/5 | −1.99 / +3.24 / −0.12 / +0.77 / +0.60 | 基本接近基线，改进幅度较小 |
| Bernoulli KAN − GCN | **+2.77 pp** | 3/5 | +4.64 / +3.85 / +10.37 / −2.12 / −2.89 | KAN 主要改善 Fold 0–2 |
| SNN+CLAM − MRePath（seed 1） | +2.39 pp | 3/5 | +5.63 / +10.12 / −1.06 / +8.46 / −11.22 | 平均提高，但折间波动很大 |
| Porpoise − MRePath | −0.73 pp | 2/5 | −6.62 / +3.24 / −1.41 / +1.54 / −0.40 | 整体与基线接近但略低 |
| SNN+CLAM seed 42 − seed 1 | −3.51 pp | 1/5 | −7.95 / −3.04 / −6.95 / −3.85 / +4.23 | 随机种子敏感性明显 |

## 5. 可共同计算的生存指标

Porpoise、SNN 和 CLAM 的第三方保存结果没有完整时间点生存概率，因此不能可靠补算 IPCW C-index、IBS 和 iAUC。下表只比较本地 MRePath 与两组 Bernoulli 改进，并使用相同评价代码。

| 模型 | Harrell C-index ↑ | IPCW C-index ↑ | IBS ↓ | iAUC ↑ | Validation loss ↓ |
|---|---:|---:|---:|---:|---:|
| MRePath（SHGNN + MLP） | 0.6288 | 0.6115 | **0.2802** | **0.4558** | **1.6263** |
| Bernoulli views + GCN | 0.6338 | **0.6244** | 0.5680 | 0.3814 | 1.9017 |
| Bernoulli views + KAN | **0.6615** | 0.6063 | 0.5746 | 0.4029 | 3.0141 |

该表表明：

- GCN 的普通 C-index 和 IPCW C-index 略高于 MRePath，但 IBS、iAUC 和 loss 变差；
- KAN 的普通 C-index 提高最明显，但 IPCW C-index 略低于 MRePath，IBS 与 loss 明显更高；
- Bernoulli 两组在 Fold 3/4 出现很高的 IBS，说明风险排序提高并没有转化为更好的生存概率校准；
- 当前最稳妥的表述是“**KAN 改善了 seed 1 下的 Harrell 排序性能**”，不能写成“所有生存指标全面提升”。

## 6. 分方向综合分析

### 6.1 Bernoulli views + KAN 是当前最值得继续验证的改进

KAN 是当前 seed 1 最强的多模态结果，并具有正式结果中较低的折间标准差。它相对 MRePath 和 GCN 的均值优势分别为 3.27 和 2.77 个百分点，说明六通路聚合器的表达能力可能比单纯换成 GCN 更重要。

但 KAN 的提升集中在 Fold 0–2，Fold 3/4 反而低于 GCN；同时校准相关指标没有改善。下一步应优先补种子和校准约束，而不是直接继续堆叠更多模块。

### 6.2 当前队列中的基因组信号很强，但 SNN 稳定性不足

SNN seed 1 达到全部结果中的最高均值 66.99%，且高于同 seed 的 SNN+CLAM 1.72 个百分点。seed 42 中 SNN 也比融合高 1.78 个百分点。这说明当前直接风险平均没有稳定利用 CLAM 分支，甚至可能因风险尺度不一致而稀释 RNA 信号。

不过 SNN 从 seed 1 到 seed 42 下降 3.45 个百分点，因此不能只依据 seed 1 排名认定其为最终最佳模型。其与论文 SNN 数值差距很大，也提示实现、分子输入和 checkpoint 规则并非严格同条件。

### 6.3 SNN+CLAM 的主要问题是融合波动

SNN+CLAM seed 1 的最高 fold 达 78.85%，最低仅 54.44%；seed 42 的范围同样很宽。两次实验相同 fold 的平均绝对变化达到 5.20 个百分点。当前算术平均融合容易受到两路风险尺度影响，后续可在训练折内做风险标准化或学习式融合，但不能使用验证标签调权。

### 6.4 Porpoise 没有超过本地 MRePath

Porpoise 为 62.15% ± 6.95%，相对 MRePath 低 0.73 个百分点，仅在 2/5 个 fold 获胜。在当前 RNA-only 条件下，没有证据表明 bilinear fusion 比 MRePath 的 SHGNN + IFA 更有效。

### 6.5 病理单分支当前较弱

CLAM component 两个 seed 分别为 58.95% 和 59.77%，都低于对应 SNN 分支。seed 42 的 CLAM 标准差只有 2.80%，说明它较稳定但判别力有限。该组件使用 Porpoise 发布代码中的 `PorpoiseAMIL` 生存头，与论文 CLAM-SB 只能作背景参考。

## 7. 非正式门禁实验

以下任务用于验证数据、代码和显存链路，不进入正式结果排名：

| 门禁任务 | 范围 | 状态 | 用途 |
|---|---|---|---|
| MRePath smoke | seed 1，Fold 0，1 epoch | PASS | 验证 4096-patch 正式路径可执行 |
| Porpoise/SNN/CLAM smoke | 小规模单折 | PASS | 验证第三方 baseline 数据适配与训练链路 |
| SNN/CLAM seed 42 smoke | 小规模单折 | PASS | 验证独立 seed 目录和不覆盖策略 |
| Bernoulli GCN/KAN dry-run | Fold 0，1 epoch，16 patches，仅打印/门禁 | PASS | 验证命令、目录和配置解析 |
| Bernoulli GCN/KAN smoke | Fold 0，1 epoch，16 patches | PASS | 验证 Bernoulli 双视图与两种聚合器可训练 |

## 8. 当前结论与下一步优先级

### 可对外表述的当前结论

> 在 TCGA-STAD 公开 WSI + RNA-only、316 例、官方五折、seed 1 条件下，Bernoulli views + KAN 的 Harrell C-index 为 66.15% ± 3.59%，相对本地 MRePath 基线提高 3.27 个百分点；但该提升尚未在 IPCW C-index、IBS 和 iAUC 上同步出现，也尚未经过多 seed 验证。

### 建议顺序

1. 给 Bernoulli views + KAN 和对应 GCN/MRePath 对照补相同的 seed 42，随后扩展到至少 3 个 seed；
2. 针对 Fold 3/4 高 IBS 检查离散生存概率、删失权重和 checkpoint 选择，加入校准/早停约束；
3. 对 SNN+CLAM 使用训练折内风险标准化，验证直接平均是否是融合退化来源；
4. 保持病例、五折、ResNet50 特征、epoch 和评价器不变，每次只改变一个主因素；
5. 在多 seed 与多指标证据完成前，不把 seed 1 的单次最高均值写成稳定 SOTA。

## 9. 独立报告与证据入口

| 工作 | Markdown | HTML |
|---|---|---|
| MRePath seed 1 | [中文报告](../../../2026-08-03_stad_mrepath_validation/02_mrepath_seed1/L1_deliverables/STAD_MREPATH_FINAL_COMPARISON_ZH.md) | [离线 HTML](../../../2026-08-03_stad_mrepath_validation/02_mrepath_seed1/L1_deliverables/STAD_MRePath_offline_report.html) |
| Porpoise seed 1 | [中文报告](../../../2026-08-04_multimodal_baselines/01_porpoise_seed1/L1_deliverables/STAD_Porpoise_FINAL_COMPARISON_ZH.md) | [离线 HTML](../../../2026-08-04_multimodal_baselines/01_porpoise_seed1/L1_deliverables/STAD_Porpoise_offline_report.html) |
| SNN+CLAM seed 1 | [中文报告](../../../2026-08-04_multimodal_baselines/02_snn_clam_seed1/L1_deliverables/STAD_SNN_CLAM_FINAL_COMPARISON_ZH.md) | [离线 HTML](../../../2026-08-04_multimodal_baselines/02_snn_clam_seed1/L1_deliverables/STAD_SNN_CLAM_offline_report.html) |
| SNN+CLAM seed 42 | [中文报告](../../../2026-08-04_multimodal_baselines/04_snn_clam_seed42/L1_deliverables/STAD_SNN_CLAM_seed42_FINAL_COMPARISON_ZH.md) | [离线 HTML](../../../2026-08-04_multimodal_baselines/04_snn_clam_seed42/L1_deliverables/STAD_SNN_CLAM_seed42_offline_report.html) |
| seed 复现性 | [对比报告](../../../2026-08-04_multimodal_baselines/05_seed_reproducibility/L1_deliverables/STAD_SNN_CLAM_seed1_vs_seed42_reproducibility.md) | [离线 HTML](../../../2026-08-04_multimodal_baselines/05_seed_reproducibility/L1_deliverables/STAD_SNN_CLAM_seed1_vs_seed42_reproducibility_offline.html) |
| Bernoulli GCN/KAN | [中文报告](../../../2026-08-10_stad_bernoulli_views/01_seed1_formal/L1_deliverables/STAD_BERNOULLI_GCN_KAN_FINAL_REPORT_ZH.md) | [离线 HTML](../../../2026-08-10_stad_bernoulli_views/01_seed1_formal/L1_deliverables/STAD_BERNOULLI_GCN_KAN_offline_report.html) |

## 10. 原始结果位置

- MRePath：`/mnt/f/Sheaf-TCGA/results/stad_project10/paper_original_5fold_seed1/`
- Porpoise、SNN、CLAM seed 1：`/mnt/f/Sheaf-TCGA/results/stad_porpoise_snn_clam/`
- SNN、CLAM seed 42：`/mnt/f/Sheaf-TCGA/results/stad_snn_clam_seed42/`
- Bernoulli GCN/KAN：`/mnt/f/Sheaf-TCGA/results/stad_project10/bernoulli_views_gcn_kan_seed1/formal_30e_4096p/`

所有原始结果、checkpoint、病例级预测和日志继续保存在 F 盘；本报告只做只读汇总，没有移动或覆盖任何实验产物。
