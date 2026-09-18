# MRePath 实验结果总表与迁移清单

> 更新时间：2026-08-10  
> 主要终点：DSS；主要指标：五折 Harrell C-index  
> 本文统一将本机五折结果写为 `Mean ± Std`，其中 Std 为五折总体标准差（`ddof=0`）。此前聊天中个别结果采用样本标准差（`ddof=1`），因此“±”可能略大，但均值和排序不变。

## 1. 当前 15 个图结构实验

公共配置为 ResNet50 病理特征、SHGNN、动态模态加权、完整 IFA、30 epochs、seed 1、每折验证 C-index 最佳 checkpoint。这里的 15 项是 `genomics.graph_structure` 的选择，不是 15 个基因编码器。

### 1.1 COREAD：15/15 项完成

| 排名 | Graph structure | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 | Mean ± Std |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `fixed_fold_graph` | 0.9634 | 0.7066 | 0.8654 | 0.7805 | 0.6848 | **0.8001 ± 0.1033** |
| 2 | `effective_resistance_views` | 0.9472 | 0.7325 | 0.7212 | 0.6612 | 0.7939 | **0.7712 ± 0.0975** |
| 3 | `pc_cmka_full_graph` | 0.9390 | 0.6946 | 0.7500 | 0.6612 | 0.7697 | **0.7629 ± 0.0962** |
| 4 | `bernoulli_views` | 0.9350 | 0.7066 | 0.7308 | 0.6558 | 0.7576 | **0.7571 ± 0.0950** |
| 5 | `hessian_antithetic` | 0.9309 | 0.7006 | 0.7596 | 0.6369 | 0.7576 | **0.7571 ± 0.0978** |
| 6 | `patient_degree_edge_gate` | 0.9553 | 0.6926 | 0.7115 | 0.6518 | 0.7697 | 0.7562 ± 0.1065 |
| 7 | `reference_operator` | 0.9431 | 0.7006 | 0.6923 | 0.6423 | 0.8000 | 0.7557 ± 0.1068 |
| 8 | `inverse_calibration` | 0.9390 | 0.6926 | 0.6731 | 0.6640 | 0.8000 | 0.7537 ± 0.1047 |
| 9 | `inverse_random_probe` | 0.9512 | 0.7146 | 0.7212 | 0.5962 | 0.7697 | 0.7506 ± 0.1154 |
| 10 | `isotropic_antithetic` | 0.9390 | 0.7345 | 0.6827 | 0.6260 | 0.7697 | 0.7504 ± 0.1061 |
| 11 | `inverse_fixed_rho` | 0.9350 | 0.6986 | 0.7500 | 0.5854 | 0.7697 | 0.7477 ± 0.1134 |
| 12 | `direct_low_rank` | 0.9431 | 0.7026 | 0.6827 | 0.6355 | 0.7697 | 0.7467 ± 0.1072 |
| 13 | `direct_edge_gate` | 0.9472 | 0.6766 | 0.7115 | 0.6328 | 0.7515 | 0.7439 ± 0.1089 |
| 14 | `reference_degree_edge_gate` | 0.9553 | 0.6806 | 0.7019 | 0.6233 | 0.7455 | 0.7413 ± 0.1140 |
| 15 | `independent_views` | 0.9512 | 0.6886 | 0.7115 | 0.6016 | 0.7333 | 0.7373 ± 0.1159 |

### 1.2 STAD：指定的 COREAD 前五名已完成

| 排名 | Graph structure | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 | Mean ± Std |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `bernoulli_views` | 0.5629 | 0.6012 | 0.6113 | 0.7192 | 0.6647 | **0.6319 ± 0.0545** |
| 2 | `pc_cmka_full_graph` | 0.5331 | 0.6194 | 0.6054 | 0.7115 | 0.6754 | **0.6290 ± 0.0613** |
| 3 | `effective_resistance_views` | 0.5430 | 0.5992 | 0.5783 | 0.7115 | 0.6626 | **0.6189 ± 0.0605** |
| 4 | `fixed_fold_graph` | 0.5629 | 0.5607 | 0.6019 | 0.7385 | 0.6169 | **0.6162 ± 0.0649** |
| 5 | `hessian_antithetic` | 0.4967 | 0.6113 | 0.5819 | 0.7154 | 0.6700 | **0.6151 ± 0.0751** |

注意：在 COREAD 上最高的 `fixed_fold_graph` 到 STAD 仅排第 4，说明 COREAD 上的排序不能直接外推到 STAD。STAD 其余 10 个图结构尚未运行。

## 2. 论文消融实验（COREAD）

以下是 24 个唯一配置中的 21 个已完成配置；每次只改变一个因素。每折明细和配置解释仍保留在 `table.md`。

### 2.1 图/超图模块

| 配置 | Mean ± Std |
|---|---:|
| HGNN，Topology + Feature | **0.7269 ± 0.1266** |
| 默认 SHGNN，Topology + Feature | 0.7265 ± 0.1177 |
| GCN，Topology + Feature | 0.7214 ± 0.1439 |
| MLP，无图 | 0.6963 ± 0.1146 |
| GAT，Topology + Feature | 0.6903 ± 0.1299 |
| SHGNN，Feature only | 0.6907 ± 0.1150 |
| SHGNN，Topology only | 0.6603 ± 0.1194 |

### 2.2 超边邻居数

| k | Mean ± Std |
|---:|---:|
| 9 | **0.7265 ± 0.1177** |
| 0（无图 MLP） | 0.6963 ± 0.1146 |
| 5 | 0.6923 ± 0.1119 |
| 25 | 0.6847 ± 0.1166 |
| 49 | 0.6832 ± 0.1267 |

### 2.3 病理/基因模态权重

| 权重方式（Pathology : Genomics） | Mean ± Std |
|---|---:|
| Dynamic | **0.7265 ± 0.1177** |
| 5% : 95% | 0.7063 ± 0.1352 |
| 95% : 5% | 0.6926 ± 0.1379 |
| 30% : 70% | 0.6907 ± 0.1412 |
| 50% : 50% | 0.6837 ± 0.1417 |
| 70% : 30% | 0.6816 ± 0.1420 |

### 2.4 IFA 融合组件

| 融合组件 | Mean ± Std |
|---|---:|
| 完整 IFA（SA + PG + GP） | **0.7265 ± 0.1177** |
| SA + PG | 0.6765 ± 0.1354 |
| SA + GP | 0.6551 ± 0.1307 |
| PG + GP | 0.6462 ± 0.1388 |

### 2.5 病理编码器与基因通路聚合

| 类别 | 配置 | Mean ± Std | 状态 |
|---|---|---:|---|
| 病理编码器 | CTransPath | **0.7600 ± 0.1329** | 完成 |
| 病理编码器 | ResNet50 | 0.7265 ± 0.1177 | 完成 |
| 病理编码器 | UNI / CONCH / Phikon2 | — | 未运行 |
| 基因聚合 | GCN | **0.7410 ± 0.1239** | 完成 |
| 基因聚合 | Default | 0.7265 ± 0.1177 | 完成 |
| 基因聚合 | GAT | 0.7039 ± 0.1195 | 完成 |

## 3. 基础图模块 × 基因编码器

### 3.1 COREAD

| 组合 | Mean ± Std | 说明 |
|---|---:|---|
| SHGNN + MLP | 0.7265 ± 0.1177 | MRePath public/default reference |
| SHGNN + GCN | 0.7273 ± 0.1432 | 一次重复运行 |
| SHGNN + GCN（strict repeat） | 0.7179 ± 0.1447 | 严格重跑 |
| SHGNN + KAN | 0.6870 ± 0.1400 | 完成 |
| HGNN + GCN | 0.6889 ± 0.1168 | 完成 |
| HGNN + KAN | 0.6842 ± 0.1681 | 完成 |
| HGNN + MLP | 0.7269 ± 0.1266 | 论文图模块消融 |

历史 `gene_gcn=0.7410 ± 0.1239` 来自论文单因素消融目录；它与后续 SHGNN+GCN 重跑不是同一份输出目录，不能仅凭 seed 相同认定训练轨迹完全相同。

### 3.2 STAD

| 组合 | Mean ± Std |
|---|---:|
| SHGNN + GCN | **0.6824 ± 0.0502** |
| HGNN + GCN | 0.6670 ± 0.0610 |
| SHGNN + KAN | 0.6561 ± 0.0323 |
| HGNN + KAN | 0.6421 ± 0.0328 |
| SHGNN + MLP | 0.6411 ± 0.0563 |
| HGNN + MLP | 0.6363 ± 0.0389 |

## 4. KAN 五变体与 Quality + Conflict

### 4.1 COREAD

| 模型/组合 | Mean ± Std |
|---|---:|
| DD-KAC | **0.7796 ± 0.0929** |
| JC-MOA | 0.7734 ± 0.0877 |
| TC-RBF-KAN | 0.7636 ± 0.0838 |
| DO-LA | 0.7625 ± 0.1202 |
| JC-MOA + Quality + Conflict | 0.7553 ± 0.0717 |
| DD-KAC + Quality + Conflict | 0.7429 ± 0.1112 |
| Quality + Conflict（基础 KAN 队列） | 0.7357 ± 0.1114 |
| PB-TAMLU | 0.7208 ± 0.0877 |
| MLP + Quality + Conflict | 0.7039 ± 0.0884 |
| Conflict only | 0.5495 ± 0.1757 |

### 4.2 STAD：首次正式运行

| 模型/组合 | Mean ± Std |
|---|---:|
| JC-MOA + Quality + Conflict | **0.6379 ± 0.0477** |
| DD-KAC + Quality + Conflict | 0.6364 ± 0.0368 |
| PB-TAMLU | 0.6214 ± 0.0363 |
| TC-RBF-KAN | 0.6168 ± 0.0501 |
| JC-MOA | 0.6149 ± 0.0418 |
| DD-KAC | 0.6138 ± 0.0349 |
| DO-LA | 0.6085 ± 0.0417 |
| KAN + Quality + Conflict | 0.6080 ± 0.0462 |
| MLP + Quality + Conflict | 0.6073 ± 0.0576 |

### 4.3 STAD：完整重跑及 DD-KAC+Q+C 追加重跑

| 实验 | Mean ± Std |
|---|---:|
| DD-KAC + Q+C，完整重跑 | **0.6473 ± 0.0489** |
| DD-KAC + Q+C，repeat 4 | 0.6449 ± 0.0588 |
| JC-MOA + Q+C，完整重跑 | 0.6398 ± 0.0361 |
| DD-KAC + Q+C，repeat 3 | 0.6355 ± 0.0465 |
| DO-LA，完整重跑 | 0.6246 ± 0.0490 |
| PB-TAMLU，完整重跑 | 0.6238 ± 0.0412 |
| MLP + Q+C，完整重跑 | 0.6219 ± 0.0560 |
| TC-RBF-KAN，完整重跑 | 0.6179 ± 0.0375 |
| JC-MOA，完整重跑 | 0.6156 ± 0.0529 |
| KAN + Q+C，完整重跑 | 0.6015 ± 0.0595 |
| DD-KAC，完整重跑 | 0.5912 ± 0.0336 |

同一名称的多次运行保留为不同重复，不取逐折最大值拼成新的五折结果。若只比较“完整五折运行的最高观测均值”，STAD 的 DD-KAC+Q+C 当前最高为 0.6473。

## 5. COREAD 多模态基线与历史复现

不同目录可能使用不同实现、病理特征或严格程度，因此此表用于追溯，不应直接当作完全受控的消融。

| 模型/运行 | Mean ± Std |
|---|---:|
| PIBD official + CTransPath | **0.7573 ± 0.1183** |
| SurvPath | 0.7384 ± 0.1135 |
| PIBD（多模型套件） | 0.7381 ± 0.0876 |
| MRePath public/default | 0.7265 ± 0.1177 |
| MRePath `results_coadread_v2` | 0.7235 ± 0.0752 |
| MRePath paper 配置历史运行 | 0.7183 ± 0.0982 |
| MRePath released 配置历史运行 | 0.7169 ± 0.0871 |
| PIBD + ResNet50 | 0.7147 ± 0.0737 |
| SNN + CLAM | 0.6941 ± 0.0693 |
| MCAT | 0.6539 ± 0.0940 |
| MRePath paper-strict 历史运行 | 0.6386 ± 0.1167 |
| MOTCat | 0.6035 ± 0.0823 |

## 6. 较早的 PC-CMKA/DD-KAC 图结构实现

这批结果来自较早的 13 项/模块实现，现已由第 1 节的 15 个 `graph_structure` 正式实验取代。保留它们是为了实验追溯，不应和当前 15 项视作同一实现的重复。

| 历史配置 | Mean ± Std |
|---|---:|
| `original_ddkac_fixed_graph` | **0.7724 ± 0.1151** |
| `moment_random_drop` | 0.7702 ± 0.0844 |
| `direct_patient_edge_gate` | 0.7574 ± 0.1026 |
| `moment_hessian_antithetic` | 0.7563 ± 0.1005 |
| `moment_independent_random_views` | 0.7551 ± 0.0950 |
| `moment_hessian_krylov` | 0.7497 ± 0.1030 |
| `moment_shared_route_structure_ssl` | 0.7500 ± 0.0877 |
| `moment_hessian_krylov_shared_route` | 0.7457 ± 0.0959 |
| `moment_shared_route_ssl_identifiability` | 0.7443 ± 0.0994 |
| `moment_inverse_calibration` | 0.7438 ± 0.1074 |
| `reference_operator_fixed_graph` | 0.7389 ± 0.1076 |

## 7. 学弟提供的 STAD 基线（外部结果）

这些值来自学弟提供的报告，不是本机结果目录重新计算的结果；报告口径原样保留。

| 模型 | STAD C-index | 条件 |
|---|---:|---|
| SNN component | **0.6699 ± 0.0541** | RNA-only |
| SNN + CLAM | 0.6527 ± 0.0926 | 病例级两路风险算术平均 |
| MRePath（SHGNN + MLP） | 0.6288 ± 0.0508 | 学弟报告中的本地对照 |
| Porpoise | 0.6215 ± 0.0695 | WSI + RNA-only |
| CLAM component | 0.5895 ± 0.0516 | WSI-only component |

这组外部结果里 SNN component 最高；与本机实验合并比较时，本机 `SHGNN + GCN=0.6824` 的均值更高，但二者并非完全相同实现和输入条件。

## 8. 新主机迁移清单

迁移目标按“继续 COREAD/STAD 图结构与编码器实验，并允许在 BRCA 上运行同类图实验；不复制原始 SVS、patch 和 H5”制定。

### 8.1 必须迁移

| 内容 | 路径 | 文件数/说明 | 大小 |
|---|---|---:|---:|
| COREAD WSI 图 | `data/tcga_coadread/clam_20x_resnet50_paper_k9/graph_files/` | 301 个 `.pt` | 13,398,608,367 B（12.48 GiB） |
| COREAD 超图缓存 | `data/tcga_coadread/clam_20x_resnet50_paper_k9/hypergraph_cache/` | 301 个 `.pt` | 935,161,865 B（0.87 GiB） |
| STAD WSI 图 | `data/tcga_stad/clam_20x_resnet50_paper_k9/graph_files/` | 343 个 `.pt` | 16,190,836,742 B（15.08 GiB） |
| STAD 超图缓存 | `data/tcga_stad/clam_20x_resnet50_paper_k9/hypergraph_cache/` | 343 个 `.pt` | 1,129,983,531 B（1.05 GiB） |
| RNA、临床、metadata、pathway 文件 | `datasets_csv/` | 整目录 | 187,457,893 B（0.17 GiB） |
| 固定五折 | `splits/` | 整目录 | 206,309 B |
| 当前代码与配置 | Git 仓库、`model.yaml`、`configs/` | Git 跟踪源码约 4.1 MiB | 约 4.3 MB |

必须项合计约 **31,846,509,606 B = 31.85 GB = 29.66 GiB**。实际复制时还需预留文件系统元数据和临时空间，建议目标盘至少准备 **35 GiB** 可用空间。

`hypergraph_cache` 的校验记录包含源 `graph_files` 的大小和 `mtime_ns`，所以两者必须一起迁移并保留时间戳。建议使用 `rsync -a` 或 tar 归档；如果时间戳改变，缓存可能被判定失效，但可在新主机从 `graph_files` 重建，不需要原始 WSI。

### 8.2 BRCA 缩小迁移包

BRCA 原始 SVS 当前为 **970,057,767,688 B = 970.06 GB = 903.44 GiB**。本机已经完成 ResNet50 特征、WSI 图和离线超图缓存构建，不需要再做一次缓存：

| BRCA 内容 | 文件数 | 大小 | 是否需要迁移 |
|---|---:|---:|---|
| `graph_files/*.pt` | 929 | 40,035,642,144 B（37.29 GiB） | MRePath/15 个图结构实验必需 |
| `hypergraph_cache/*.pt` | 929 | 2,794,403,565 B（2.60 GiB） | 离线超图训练必需 |
| `pt_files/*.pt` | 929 | 37,610,044,956 B（35.03 GiB） | 仅旧多模态基线需要 |
| `h5_files/*.h5` | 929 | 37,932,228,280 B（35.33 GiB） | 不迁移，已有图和 pt 后可省略 |
| `patches/*.h5` | 929 | 590,119,280 B（0.55 GiB） | 不迁移 |
| `masks/` | 929 | 1,924,408,201 B（1.79 GiB） | 不迁移 |
| `raw_svs/` | 1,858 个文件 | 970,057,767,688 B（903.44 GiB） | 不迁移 |

缓存验收结果为 `graphs=929, caches=929, valid=929, invalid=0, errors=0`。

- 只跑 MRePath 和当前 15 个图结构：BRCA 只需 **39.89 GiB** 的 `graph_files + hypergraph_cache`，约为原始 SVS 的 4.42%，缩小约 22.6 倍。
- 还要跑 MCAT、MOTCat、SurvPath、PIBD 等旧基线：额外带上 `pt_files`，BRCA 模型输入合计约 **74.92 GiB**。
- COREAD + STAD + BRCA 三个数据集的图实验必需包：**74,676,555,315 B = 74.68 GB = 69.55 GiB**。

### 8.3 模型权重

当前 15×2 图结构结果目录实际完成了 COREAD 15 项和 STAD 5 项，共 20 个五折实验。

| 权重方案 | 文件数 | 大小 |
|---|---:|---:|
| 只保留每折 best checkpoint | 100 | **31,823,872,684 B（29.64 GiB）** |
| 每折最终 checkpoint | 100 | 31,823,682,012 B（约 29.64 GiB） |
| best + 最终 checkpoint 全部保留 | 200 | 63,647,554,696 B（59.28 GiB） |
| 只保留两个数据集共同的前五项 best | 50 | 15,916,396,954 B（14.82 GiB） |

推荐只迁移 **100 个 best checkpoint**，不迁移同一折的最终 checkpoint。这样“必须数据 + 当前正式实验 best 权重”总计约 **63.67 GB = 59.30 GiB**，建议准备至少 **65 GiB** 可用空间。

如果新主机只负责从头训练，不需要加载旧模型，则权重不是运行必需品，迁移量可降回约 **29.66 GiB**。

加入 BRCA 后：

- 三个数据集图实验必需包 + 当前 100 个 best checkpoint：**106,500,427,999 B = 106.50 GB = 99.19 GiB**；建议至少预留 110 GiB。
- 如果 BRCA 还要运行依赖 `pt_files` 的旧基线，再增加 35.03 GiB，总迁移量约 **134.21 GiB**；建议至少预留 145 GiB。

### 8.4 可选结果审计文件

当前图结构结果目录中，排除 checkpoint 后约 **2.23 GiB**，其中 JSON 诊断约 1.42 GiB、病例预测 PKL 约 0.81 GiB，而 CSV/TXT 配置与汇总只有数 MiB。推荐迁移 CSV、TXT、配置和 `result.md`；只有需要逐病例复算或诊断时再迁移 JSON/PKL。

### 8.5 不迁移

- `raw_svs/`、`patches/`、`masks/`、`h5_files/`；
- COREAD/STAD 的原始数据下载目录；
- COREAD/STAD 的 `pt_files/`；BRCA 的 `pt_files/` 仅在需要运行旧基线时迁移；
- `__pycache__/`、`.pytest_cache/`、日志缓存；
- 每折非 best 的最终 checkpoint；
- 整个历史 `results*` 目录。历史所有权重约 264.64 GiB，没有必要全部搬迁。

## 9. 证据目录

- 当前 15 项图结构：`results/results_graph_structure_15x2_5fold/`
- 论文消融：`results/results_coadread_paper_ablations_20260726/` 和 `table.md`
- COREAD KAN：`results/results_coadread_improved_kan_5fold_20260801/`
- COREAD Q+C：`results/results_coadread_quality_conflict_matrix_5fold_20260805/`
- STAD 六基础组合：`results/results_stad_base_six_5fold_20260805/`、`results/results_stad_mlp_base_kan_5fold_20260802/`
- STAD KAN/Q+C：`results/results_stad_improved_kan_5fold_20260801/`、`results/results_stad_improved_kan_quality_conflict_5fold_20260802/`、`results/results_stad_requested_repeat_5fold_20260804/`
- STAD DD-KAC+Q+C 追加重跑：`results/results_stad_dd_kac_quality_conflict_repeat3_20260804/`、`results/results_stad_dd_kac_quality_conflict_repeat4_20260804/`

## 10. 环境迁移提醒

仓库当前没有 `environment.yml` 或 `requirements.txt`，而部分运行脚本硬编码了 `/home/administrator/miniconda3/envs/mrepath-train/bin/python`。因此复制数据后仍需在新主机重建 Conda 环境，或在迁移前导出环境文件，并把脚本中的 Python 路径改成新主机实际路径。仅复制缓存和权重并不能替代运行环境。
