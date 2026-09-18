# COREAD MRePath 图结构与聚合实验汇总

## 1. 实验范围

- 本表只汇总论文原有消融和后续图结构 × 通路聚合实验。
- 原有消融完成 21 个唯一配置、105 个 fold；另有 3 个病理编码器配置未运行。
- 后续完成 4 个正式配置、20 个 fold：
  `fixed_fold_graph + GCN/KAN` 和 `bernoulli_views + GCN/KAN`。
- 所有结果均使用 TCGA-COADREAD 的固定五折和随机种子 1。
- 正式实验每张 WSI 最多使用 4096 patches，最多训练 30 epochs，以验证集
  C-index 最佳 epoch 作为结果。
- 标准差为五折总体标准差（`ddof=0`）。目前尚无多随机种子和患者级配对
  bootstrap，因此不作统计显著性声明。
- 64 patches、1 epoch 的 smoke test 只验证运行流程，不纳入正式数值比较。

## 2. 公共训练配置

| 项目 | 配置 |
|---|---|
| 数据集 | TCGA-COADREAD |
| 任务 | DSS 生存分析 |
| 划分 | 仓库提供的固定五折 |
| 随机种子 | 1 |
| Patch 特征 | ResNet50 1024 维；编码器消融除外 |
| 每张 WSI 最大 patch 数 | 4096 |
| 最大 Epoch | 30 |
| Optimizer | Adam |
| Learning rate | 1e-4 |
| Weight decay | 1e-5 |
| Loss | NLL survival loss |
| 默认病理图模块 | SHGNN，Topology + Feature，k=9 |
| 默认模态权重 | Dynamic |
| 默认融合 | 完整 IFA |

## 3. 此前论文消融结果

下表按照五折平均 C-index 排序。`Δ Reference` 相对
`full_reference = 0.7265` 计算。

| 排名 | 配置 | 改变的因素 | C-index Mean ± Std | Δ Reference |
|---:|---|---|---:|---:|
| 1 | `encoder_ctranspath` | Patch 编码器改为 CTransPath | **0.7600 ± 0.1329** | **+0.0335** |
| 2 | `gene_gcn` | 基因通路聚合改为 GCN | **0.7410 ± 0.1239** | **+0.0145** |
| 3 | `graph_hgnn_both` | 病理图改为 HGNN，双超边 | **0.7269 ± 0.1266** | **+0.0004** |
| 4 | `full_reference` | 默认完整模型 | **0.7265 ± 0.1177** | +0.0000 |
| 5 | `graph_gcn` | 病理图改为 GCN | 0.7214 ± 0.1439 | -0.0051 |
| 6 | `weight_fixed_05_95` | 病理/基因固定为 5%/95% | 0.7063 ± 0.1352 | -0.0202 |
| 7 | `gene_gat` | 基因通路聚合改为 GAT | 0.7039 ± 0.1195 | -0.0226 |
| 8 | `graph_mlp` | 不使用病理图 | 0.6963 ± 0.1146 | -0.0302 |
| 9 | `weight_fixed_95_05` | 病理/基因固定为 95%/5% | 0.6926 ± 0.1379 | -0.0339 |
| 10 | `graph_k5` | 超边邻居数 k=5 | 0.6923 ± 0.1119 | -0.0342 |
| 11 | `weight_fixed_30_70` | 病理/基因固定为 30%/70% | 0.6907 ± 0.1412 | -0.0358 |
| 12 | `graph_shgnn_feature` | SHGNN 只使用特征超边 | 0.6907 ± 0.1150 | -0.0358 |
| 13 | `graph_gat` | 病理图改为 GAT | 0.6903 ± 0.1299 | -0.0362 |
| 14 | `graph_k25` | 超边邻居数 k=25 | 0.6847 ± 0.1166 | -0.0417 |
| 15 | `weight_fixed_50_50` | 病理/基因固定为 50%/50% | 0.6837 ± 0.1417 | -0.0428 |
| 16 | `graph_k49` | 超边邻居数 k=49 | 0.6832 ± 0.1267 | -0.0433 |
| 17 | `weight_fixed_70_30` | 病理/基因固定为 70%/30% | 0.6816 ± 0.1420 | -0.0449 |
| 18 | `fusion_sa_pg` | IFA 只保留 SA + PG | 0.6765 ± 0.1354 | -0.0500 |
| 19 | `graph_shgnn_topology` | SHGNN 只使用拓扑超边 | 0.6603 ± 0.1194 | -0.0662 |
| 20 | `fusion_sa_gp` | IFA 只保留 SA + GP | 0.6551 ± 0.1307 | -0.0714 |
| 21 | `fusion_pg_gp` | IFA 只保留 PG + GP | 0.6462 ± 0.1388 | -0.0803 |

尚未运行的配置为 `encoder_uni`、`encoder_conch` 和 `encoder_phikon2`。

## 4. Graph structure × pathway aggregation

| 图结构 | 聚合器 | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 | C-index Mean ± Std | IPCW C-index | IBS ↓ |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `fixed_fold_graph` | GCN | 0.9553 | 0.7455 | 0.7212 | 0.7778 | 0.6606 | **0.7721 ± 0.0993** | 0.7065 | **0.1413** |
| `fixed_fold_graph` | KAN | 0.8496 | 0.6976 | 0.7019 | 0.7615 | 0.8121 | 0.7646 ± 0.0598 | **0.7387** | 0.1414 |
| `bernoulli_views` | GCN | 0.9472 | 0.6647 | 0.7500 | 0.7073 | 0.7455 | 0.7629 ± 0.0971 | 0.7011 | 0.1436 |
| `bernoulli_views` | KAN | 0.9431 | 0.7196 | 0.8365 | 0.6667 | 0.7333 | **0.7798 ± 0.0985** | **0.7027** | **0.1397** |

配置边界：

- `fixed_fold_graph` 的结果目录记录为 `DD-KAC` 基因编码。
- `bernoulli_views` 的结果目录记录为
  `PC-CMKA-DDKAC/C4_bernoulli_views` 基因编码。
- 因此两种图结构之间不是严格的单变量比较；同一种图结构内部的 GCN/KAN
  比较成立。
- 图结构实验 Fold 2–4 的 iAUC 为空，当前不能报告有效的五折 iAUC。

## 5. 结果解读

| 问题 | 当前结论 |
|---|---|
| 此前单因素消融最高结果 | `CTransPath = 0.7600 ± 0.1329` |
| 后续图结构实验最高原始结果 | `bernoulli_views + KAN = 0.7798 ± 0.0985` |
| fixed fold 中 GCN 与 KAN | GCN 高 0.0075；KAN 的折间波动更小 |
| Bernoulli views 中 GCN 与 KAN | KAN 高 0.0169，但只在 2/5 折领先 |
| Bernoulli views 是否优于 fixed fold | 不能直接下结论，基因编码配置不一致 |
| 是否已有显著性结论 | 没有，需要多随机种子和患者级配对 bootstrap |

当前最稳妥的表述是：在本次单种子五折实验中，`bernoulli_views + KAN`
获得最高平均 C-index，但优势存在折间不一致，且跨图结构比较受到基因编码配置
不同的混杂，仍需统一配置后复验。

## 6. 结果目录

- 此前论文消融：`results/results_coadread_paper_ablations_20260726/`
- 默认完整模型：`results/results_coadread_multimodal_20260725/mrepath/`
- 图结构与聚合器：
  `results/results_pc_cmka_graph_structure_aggregation/coadread/`
- 图结构 smoke test：
  `results/results_pc_cmka_graph_structure_aggregation_smoke/coadread/`
