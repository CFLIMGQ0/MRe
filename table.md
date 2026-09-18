# MRePath 全实验结果汇总（COREAD + STAD + BRCA + BLCA + HNSC）

## 新划分基线最终结果（2026-09-16）

BLCA（357 人）和 BRCA（868 人）均使用患者互斥五折、ResNet50-1024D 图像特征、DSS 终点；
前三模型共 30 折已全部完成并通过病例级预测、标签和 C-index 重算验收。均值 ± 标准差为总体标准差（ddof=0）。

| 模型 | BLCA Fold 0–4 | BLCA Mean ± SD | BRCA Fold 0–4 | BRCA Mean ± SD |
|---|---|---:|---|---:|
| 原始 MRePath | 0.625962 / 0.748460 / 0.748975 / 0.611641 / 0.647482 | **0.676504 ± 0.060056** | 0.783505 / 0.755334 / 0.707124 / 0.678414 / 0.644326 | **0.713741 ± 0.050413** |
| PIBD | 0.613462 / 0.597536 / 0.584016 / 0.583969 / 0.532374 | **0.582271 ± 0.027208** | 0.687285 / 0.681366 / 0.725594 / 0.817181 / 0.677075 | **0.717700 ± 0.052639** |
| SurvPath | 0.535577 / 0.664271 / 0.509221 / 0.553435 / 0.585612 | **0.569623 ± 0.053448** | 0.701031 / 0.576102 / 0.783113 / 0.533040 / 0.646611 | **0.647979 ± 0.088831** |

这批新结果已完成 **30/30 折**。MMP、LD-CVAE、DIMAF、SlotSPE 的另外 100 折尚未启动，
因为它们的官方 UNI/CTransPath、RNA 或原型输入尚未齐全，不能用现有结果冒充官方复现。

## 存储恢复（2026-09-15 00:03）

新划分基线已完成 **24/30 折**；09-14 21:09 的磁盘保护中断后，按用户授权改用其他可写磁盘。
旧结果保留，204 的四个剩余折重新启动调度，202 的两个 SurvPath/BRCA 折等待现有特征复制验收。
新输出使用 202 系统盘；不重跑已完成折，不重编码，不删除缓存。中断折因无完整续训状态从头重跑。
当前实时进度和完整五折成绩仍见
[新划分运行结果](results/results_author_patient_disjoint_20260914/LIVE_RESULTS.md)，
存储路径、任务唯一归属和保护规则见 [跨盘恢复记录](docs/STORAGE_RECOVERY_20260914.md)。
新增四模型 100 折仍未启动。

## 新请求执行中（2026-09-14）：新划分三基线 + 四个新增模型

请求共 130 折：原始 MRePath / PIBD / SurvPath 在 BLCA、BRCA 重跑共 30 折；
MMP / LD-CVAE / DIMAF / SlotSPE 在五个数据集共 100 折。

**当前只启动/安排前 30 折，后 100 折仍待输入协议确认和缺失依赖准备，未训练。**
204 四卡已启动首批四个训练；202 两卡在现有 BLCA 特征复制验收后自动进入十折队列。
每卡最多一个本项目任务，不中断其他项目。旧结果不覆盖，不作为新划分性能。

实时状态、逐模型完成折数和完整五折结果见
[新划分运行结果](results/results_author_patient_disjoint_20260914/LIVE_RESULTS.md)。
后四模型官方配方缺 UNI/CTransPath、部分 RNA 和原型；若改用统一 ResNet 输入，
必须明确标注为统一输入对照，而非完整官方原生协议复现。

## 当前划分更新：BLCA / BRCA（2026-09-14，尚未产生新成绩）

用户已同意采用 SurvPath / PIBD 作者原始患者互斥五折，仅过滤到现有队列，
不重新随机划分；模型和原 ResNet50 Encoder 保持不变。

| 数据集 | 保留患者 | 所需 WSI | 新五折同折患者重叠 | 新划分性能 |
|---|---:|---:|---|---|
| BLCA | 357 | 421 | 每折 0 人 | 重跑已启动，待完成五折 |
| BRCA | 868 | 926 | 每折 0 人 | 重跑已启动，待完成五折 |

现有图像特征、图与超图缓存齐全，无需重新运行 ResNet。
下方历史 BLCA / BRCA 成绩使用旧的有同折患者重叠划分，原样保留，
**不能当成新划分结果，也不能据此声称无同折患者泄漏的泛化性能**。
历史 CSV 已备份，新旧结果必须使用独立目录。患者名单、每折人数、来源提交及边界见
[划分变更记录](splits/author_patient_disjoint_20260914/README.md)。

## 原始模型与多模态基线补齐（2026-09-13 晚，进行中）

新增原始结构 MRePath 的 BLCA/HNSC 各 5 折，PIBD/SurvPath 的
BLCA/HNSC/COREAD/STAD 各 5 折，共 **50 个新折**；两个基线的 BRCA
已有完整五折并通过患者、DSS 标签、病例级 C-index 重算核验，直接复用。
本节不混入 AES 或 Bernoulli + KAN。启动不等于跑完，不用部分折均值代替五折成绩。

**持续更新的逐折结果与完整五折成绩：
[本轮结果表](results/results_requested_baselines_5fold_20260913/LIVE_RESULTS.md)**。
详细代码版本、配置、调度、证据及口径差异见
[本轮运行记录](results/results_requested_baselines_5fold_20260913/RUN_STATUS.md)。

| 模型 | BLCA | HNSC | COREAD | STAD | BRCA（历史复用） |
|---|---|---|---|---|---|
| 原始 MRePath 结构 | **0.7225 ± 0.0408** | 本轮补齐中 | 历史结果见正文 | 历史结果见正文 | 历史结果见正文 |
| PIBD | 本轮排队/训练 | 本轮排队/训练 | 本轮排队/训练 | 本轮排队/训练 | 0.6628 ± 0.0800 |
| SurvPath | 本轮排队/训练 | 本轮排队/训练 | 本轮排队/训练 | 本轮排队/训练 | 0.6331 ± 0.0560 |

本轮已完成的原始结构 MRePath（BLCA，五折全部结束）：

| Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 | Mean ± Std（ddof=0） |
|---:|---:|---:|---:|---:|---:|
| 0.715707 | 0.658349 | 0.707198 | 0.755130 | 0.776119 | **0.722501 ± 0.040830** |

原始汇总与检查点入口：
[BLCA aggregate.json](results/results_requested_baselines_5fold_20260913/mrepath/blca/aggregate.json)。

新结果统一展示总体标准差 ddof=0。BLCA 原划分每折有 11–13 名训练/验证
重叠患者；本轮只读审计另确认 BRCA 历史划分每折重叠 14、11、22、21、15 名。
两者均不得解释为无泄漏泛化性能。BRCA 当前可用元数据/RNA 交集是 868 名，
与历史两个基线的实际验证患者完全匹配；旧文档“871 名”保留为历史记录而不再
作为本轮已核验人数。模型原生 batch、抽样与时间分箱有差异，详见运行记录。

## 历史启动记录（2026-09-13，以下保留各记录时点的状态）

已启动 HNSC、BLCA 的基础 `C4_bernoulli_views + 外部 KAN` 实验流水线，
保留原始 Dynamic weighting + IFA，不加入 Quality + Conflict；各计划 5 折、
seed=1、30 epochs。启动时处于 WSI 特征提取阶段，不计入已完成实验。

BLCA 原划分每折存在 11–13 名有效患者同时位于训练和验证集。
经用户明确要求，保留仓库原始划分继续运行；后续结果须标注患者重叠/数据泄漏，
不能作为无泄漏泛化性能。HNSC 原划分无同折患者重叠。

配置、病例审计、主机、日志与状态入口见
[本轮运行记录](results/results_bernoulli_kan_hnsc_blca_5fold_20260913/RUN_STATUS.md)。

2026-09-13 08:37 调度更新：已切换为可用 GPU 动态分折队列，缓存就绪后每卡
一折、完成即接下一折；204 预处理使用 0/1/3 卡，202 使用 0/1 卡，CPU 解码
worker 从每进程 2 个增至 8 个。训练会跳过其他任务占用的卡，各折结果独立
保存，父进程统一汇总。模型、seed、batch size、30 epochs 及原始划分未变。

2026-09-13 16:41 修复续跑：此前 HNSC/BLCA 在特征提取阶段因文件句柄累积耗尽
中断，保留缓存分别为 174/415、199/455，均尚无正式训练折结果。已修复逐切片
DataLoader worker、OpenSlide/HDF5 的资源释放，未提高生产句柄上限，未改模型
和原始划分。两端各通过 120 次连续合成小样本提取压力测试（结束句柄始终 34）
以及真实切片三次重复提取比对（特征最大差值 0）。两条原 parallel 服务已从
原缓存续跑；完成特征、图和超图缓存后自动进入五折训练。具体证据及后续状态见
上述本轮运行记录，暂不填入 C-index。

16:44 续跑实查：BLCA 特征已完成 **205/455**，HNSC **183/415**；之前卡住的
五张切片均已成功通过，204 三个、202 两个特征进程正常运行。仍为预处理阶段，
不是正式五折性能结果。

## 0. 汇总口径与去重说明

- 本文件以原 `table.md` 为主体，已整合 `COREAD.md` 和
  `STAD_ALL_EXPERIMENTS_SUMMARY_ZH.md` 中的正式结果、实验边界、分析结论与
  证据入口。
- 三个文件中完全重复的实验只保留一次。例如，`COREAD.md` 中的 21 组论文
  消融已由本文件第 3–10 节完整收录，因此不再复制第二张相同排名表。
- 名称相近但配置、结果目录、评价批次或实现边界不同的结果不做强行合并，均
  分表保留。尤其是 STAD 的 `bernoulli_views` 图结构筛选、10 组
  `BK_Ixx` 组合，以及独立的 `Bernoulli views + GCN/KAN` 正式实验不是同一组
  结果；COREAD 的相应实验也按各自配置保留。
- 各实验沿用原始汇总的标准差口径：第 1–16 节为总体标准差（`ddof=0`），
  第 17–24 节为样本标准差（`ddof=1`），第 25–28 节为总体标准差
  （`ddof=0`），第 29 节以后 STAD 独立汇总为样本标准差。不同口径的数值不
  重新换算。

## 1. COREAD 论文消融实验范围

- 论文消融矩阵共有 24 个唯一配置，每个配置运行 5 折，共 120 折。
- 当前完成 21 个唯一配置，共 105 折。
  - 本轮新运行 20 个配置，共 100 折。
  - `full_reference` 复用此前已经完成的 5 折结果。
- 尚未运行的 3 个配置为 `encoder_uni`、`encoder_conch` 和
  `encoder_phikon2`，共 15 折。
- 所有消融均为单因素实验：每次只改变一个模块，其余模块保持
  `full_reference` 配置不变；这里没有把所有模块进行笛卡尔积组合。
- 表中的标准差是 5 折 C-index 的总体标准差（`ddof=0`）。
- `Δ Reference` 表示相对 `full_reference=0.7265` 的绝对变化。

## 2. COREAD 论文消融公共训练配置

| 项目 | 配置 |
|---|---|
| 数据集 | TCGA-COADREAD |
| 任务 | DSS 生存分析 |
| 划分 | 仓库提供的固定五折 |
| 随机种子 | 1 |
| 每张 WSI 最大 patch 数 | 4096 |
| Patch 特征 | 默认 ResNet50，1024 维 |
| 最大 Epoch | 30 |
| 模型选择 | 验证集最佳 C-index Epoch |
| Optimizer | Adam |
| Learning rate | 1e-4 |
| Weight decay | 1e-5 |
| Loss | NLL survival loss |
| 默认图模块 | SHGNN，拓扑与特征双超边 |
| 默认超边邻居数 | k=9 |
| 默认模态加权 | Dynamic |
| 默认融合 | 完整 IFA |
| 默认基因聚合 | Default |

## 3. 默认完整模型

| 配置 | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 | Mean ± Std |
|---|---:|---:|---:|---:|---:|---:|
| `full_reference` | 0.8984 | 0.7804 | 0.7596 | 0.5637 | 0.6303 | **0.7265 ± 0.1177** |

## 4. 图与超图模块组合

这一组只替换病理图建模模块；编码器、k、动态加权、IFA 和基因聚合均保持默认。

| 配置 | 图模块 | 使用的边/超边 | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 | Mean ± Std | Δ Reference |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| `full_reference` | SHGNN | Topology + Feature | 0.8984 | 0.7804 | 0.7596 | 0.5637 | 0.6303 | 0.7265 ± 0.1177 | +0.0000 |
| `graph_mlp` | MLP，无图 | None | 0.8943 | 0.6367 | 0.6731 | 0.5501 | 0.7273 | 0.6963 ± 0.1146 | -0.0302 |
| `graph_gat` | GAT | Topology + Feature | 0.9187 | 0.7405 | 0.6058 | 0.5501 | 0.6364 | 0.6903 ± 0.1299 | -0.0362 |
| `graph_gcn` | GCN | Topology + Feature | 0.8943 | 0.6387 | 0.8942 | 0.5556 | 0.6242 | 0.7214 ± 0.1439 | -0.0051 |
| `graph_hgnn_both` | HGNN | Topology + Feature | 0.8943 | 0.8104 | 0.7212 | 0.5176 | 0.6909 | **0.7269 ± 0.1266** | **+0.0004** |
| `graph_shgnn_topology` | SHGNN | Topology only | 0.8943 | 0.5828 | 0.6250 | 0.5691 | 0.6303 | 0.6603 ± 0.1194 | -0.0662 |
| `graph_shgnn_feature` | SHGNN | Feature only | 0.8943 | 0.5828 | 0.7019 | 0.5772 | 0.6970 | 0.6907 ± 0.1150 | -0.0358 |

本组最高为 `graph_hgnn_both=0.7269`，但仅比默认 SHGNN 高 0.0004，
差异可以视为非常小。

## 5. 超边邻居数 k

这一组只改变拓扑和特征超边的邻居数。`k=0` 与无图 MLP 是同一配置，
`k=9` 与完整默认模型是同一配置。

| 配置 | k | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 | Mean ± Std | Δ Reference |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `graph_mlp`（k=0 别名） | 0 | 0.8943 | 0.6367 | 0.6731 | 0.5501 | 0.7273 | 0.6963 ± 0.1146 | -0.0302 |
| `graph_k5` | 5 | 0.8984 | 0.5948 | 0.7115 | 0.5962 | 0.6606 | 0.6923 ± 0.1119 | -0.0342 |
| `full_reference`（k=9 别名） | 9 | 0.8984 | 0.7804 | 0.7596 | 0.5637 | 0.6303 | **0.7265 ± 0.1177** | +0.0000 |
| `graph_k25` | 25 | 0.8984 | 0.5968 | 0.7115 | 0.5745 | 0.6424 | 0.6847 ± 0.1166 | -0.0417 |
| `graph_k49` | 49 | 0.9187 | 0.5888 | 0.6250 | 0.5745 | 0.7091 | 0.6832 ± 0.1267 | -0.0433 |

本组最优为默认的 `k=9`。

## 6. 病理与基因模态权重

这一组只把动态模态权重替换为固定权重。权重顺序为
`Pathology : Genomics`。

| 配置 | Pathology : Genomics | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 | Mean ± Std | Δ Reference |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `full_reference` | Dynamic | 0.8984 | 0.7804 | 0.7596 | 0.5637 | 0.6303 | **0.7265 ± 0.1177** | +0.0000 |
| `weight_fixed_50_50` | 50% : 50% | 0.9390 | 0.5749 | 0.6827 | 0.5312 | 0.6909 | 0.6837 ± 0.1417 | -0.0428 |
| `weight_fixed_70_30` | 70% : 30% | 0.9309 | 0.5709 | 0.6827 | 0.5203 | 0.7030 | 0.6816 ± 0.1420 | -0.0449 |
| `weight_fixed_30_70` | 30% : 70% | 0.9431 | 0.5808 | 0.7019 | 0.5366 | 0.6909 | 0.6907 ± 0.1412 | -0.0358 |
| `weight_fixed_95_05` | 95% : 5% | 0.9390 | 0.5828 | 0.7115 | 0.5447 | 0.6848 | 0.6926 ± 0.1379 | -0.0339 |
| `weight_fixed_05_95` | 5% : 95% | 0.9431 | 0.6188 | 0.7308 | 0.5420 | 0.6970 | **0.7063 ± 0.1352** | -0.0202 |

动态模态权重优于全部固定权重；固定权重中最好的是
`5% Pathology + 95% Genomics`。

## 7. IFA 融合组件

这一组只改变 IFA 中保留的交互组件。

| 配置 | 融合组件 | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 | Mean ± Std | Δ Reference |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `full_reference` | 完整 IFA（SA + PG + GP） | 0.8984 | 0.7804 | 0.7596 | 0.5637 | 0.6303 | **0.7265 ± 0.1177** | +0.0000 |
| `fusion_pg_gp` | PG + GP | 0.9146 | 0.5679 | 0.5865 | 0.5257 | 0.6364 | 0.6462 ± 0.1388 | -0.0803 |
| `fusion_sa_pg` | SA + PG | 0.9187 | 0.6307 | 0.6442 | 0.5041 | 0.6848 | **0.6765 ± 0.1354** | -0.0500 |
| `fusion_sa_gp` | SA + GP | 0.9146 | 0.6028 | 0.5769 | 0.5691 | 0.6121 | 0.6551 ± 0.1307 | -0.0714 |

完整 IFA 明显优于三个删减组合。

## 8. 病理特征编码器

这一组只替换病理 patch 特征编码器。

| 配置 | 编码器 | 特征维度 | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 | Mean ± Std | Δ Reference | 状态 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `full_reference` | ResNet50 | 1024 | 0.8984 | 0.7804 | 0.7596 | 0.5637 | 0.6303 | 0.7265 ± 0.1177 | +0.0000 | 完成 |
| `encoder_ctranspath` | CTransPath | 768 | 0.9065 | 0.7725 | 0.9038 | 0.5989 | 0.6182 | **0.7600 ± 0.1329** | **+0.0335** | 完成 |
| `encoder_uni` | UNI | 1024 | — | — | — | — | — | — | — | 未运行：需要授权权重和特征缓存 |
| `encoder_conch` | CONCH | 512 | — | — | — | — | — | — | — | 未运行：需要授权权重和特征缓存 |
| `encoder_phikon2` | Phikon2 | 1024 | — | — | — | — | — | — | — | 未运行：尚未提取特征 |

当前已完成编码器中，CTransPath 最好，比 ResNet50 提高 0.0335。

## 9. 基因通路聚合

这一组只改变六个基因通路节点之间的聚合器。

| 配置 | 基因聚合 | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 | Mean ± Std | Δ Reference |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `full_reference` | Default | 0.8984 | 0.7804 | 0.7596 | 0.5637 | 0.6303 | 0.7265 ± 0.1177 | +0.0000 |
| `gene_gcn` | GCN | 0.9146 | 0.7445 | 0.8365 | 0.6152 | 0.5939 | **0.7410 ± 0.1239** | **+0.0145** |
| `gene_gat` | GAT | 0.9106 | 0.6587 | 0.7596 | 0.5908 | 0.6000 | 0.7039 ± 0.1195 | -0.0226 |

本组最优为 GCN 基因聚合器。

## 10. 已完成组合总排名

| 排名 | 配置 | 五折 C-index | Δ Reference |
|---:|---|---:|---:|
| 1 | `encoder_ctranspath` | **0.7600 ± 0.1329** | **+0.0335** |
| 2 | `gene_gcn` | **0.7410 ± 0.1239** | **+0.0145** |
| 3 | `graph_hgnn_both` | **0.7269 ± 0.1266** | **+0.0004** |
| 4 | `full_reference` | **0.7265 ± 0.1177** | +0.0000 |
| 5 | `graph_gcn` | 0.7214 ± 0.1439 | -0.0051 |
| 6 | `weight_fixed_05_95` | 0.7063 ± 0.1352 | -0.0202 |
| 7 | `gene_gat` | 0.7039 ± 0.1195 | -0.0226 |
| 8 | `graph_mlp` | 0.6963 ± 0.1146 | -0.0302 |
| 9 | `weight_fixed_95_05` | 0.6926 ± 0.1379 | -0.0339 |
| 10 | `graph_k5` | 0.6923 ± 0.1119 | -0.0342 |
| 11 | `weight_fixed_30_70` | 0.6907 ± 0.1412 | -0.0358 |
| 12 | `graph_shgnn_feature` | 0.6907 ± 0.1150 | -0.0358 |
| 13 | `graph_gat` | 0.6903 ± 0.1299 | -0.0362 |
| 14 | `graph_k25` | 0.6847 ± 0.1166 | -0.0417 |
| 15 | `weight_fixed_50_50` | 0.6837 ± 0.1417 | -0.0428 |
| 16 | `graph_k49` | 0.6832 ± 0.1267 | -0.0433 |
| 17 | `weight_fixed_70_30` | 0.6816 ± 0.1420 | -0.0449 |
| 18 | `fusion_sa_pg` | 0.6765 ± 0.1354 | -0.0500 |
| 19 | `graph_shgnn_topology` | 0.6603 ± 0.1194 | -0.0662 |
| 20 | `fusion_sa_gp` | 0.6551 ± 0.1307 | -0.0714 |
| 21 | `fusion_pg_gp` | 0.6462 ± 0.1388 | -0.0803 |

## 11. 下一轮候选组合

本轮是单因素消融，尚未验证多个最优模块同时启用时的效果。根据当前结果，
下一轮优先级最高的组合为：

1. `CTransPath + gene GCN + SHGNN + k=9 + Dynamic + 完整 IFA`
2. `CTransPath + gene GCN + HGNN + k=9 + Dynamic + 完整 IFA`

这两个是根据各模块独立五折结果提出的新候选组合，不能把单因素提升直接相加，
仍需各自重新运行五折验证。

## 12. 结果目录

- 本轮消融结果：`results/results_coadread_paper_ablations_20260726/`
- 默认完整模型：
  `results/results_coadread_multimodal_20260725/mrepath/`

---

# TCGA-BRCA 多模态模型五折结果

## 13. BRCA 实验状态与公共配置

- BRCA 多模态实验套件已于 2026-08-19 11:06 完成，任务正常退出，8 个正式模型均完成 5 折。
- 数据集为 TCGA-BRCA，共 871 例；任务终点为 DSS。
- 使用仓库固定五折、随机种子 1、30 Epoch、batch size 1。
- 病理输入为 ResNet50 1024 维特征，每例最多使用 4096 个 patch；分子输入为当前公开数据条件下的 RNA/pathway 特征。
- 表中使用每折保存的最佳验证 C-index，并按总体标准差（`ddof=0`）汇总。

## 14. BRCA 正式模型总排名

| 排名 | 模型 | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 | Mean ± Std |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | CMTA | 0.7257 | 0.8050 | 0.8152 | 0.7430 | 0.7633 | **0.7704 ± 0.0347** |
| 2 | MRePath | 0.7287 | 0.7403 | 0.9026 | 0.6729 | 0.6817 | **0.7453 ± 0.0829** |
| 3 | Porpoise | 0.8219 | 0.8436 | 0.6654 | 0.6906 | 0.6659 | **0.7375 ± 0.0786** |
| 4 | SNN+CLAM | 0.7196 | 0.7925 | 0.7740 | 0.5286 | 0.5978 | **0.6825 ± 0.1027** |
| 5 | PIBD | 0.6599 | 0.5569 | 0.8015 | 0.6241 | 0.6714 | **0.6628 ± 0.0800** |
| 6 | MCAT | 0.7176 | 0.6467 | 0.6642 | 0.5431 | 0.6382 | **0.6420 ± 0.0566** |
| 7 | SurvPath | 0.7277 | 0.6380 | 0.5581 | 0.6012 | 0.6405 | **0.6331 ± 0.0560** |
| 8 | MOTCat | 0.7399 | 0.5676 | 0.5281 | 0.5379 | 0.6120 | **0.5971 ± 0.0771** |

BRCA 上当前表现最好的是 CMTA（0.7704 ± 0.0347）；MRePath 排名第二，
比 CMTA 低 0.0251，但 MRePath 的折间波动更大。

## 15. SNN+CLAM 组件诊断结果

| 模型/组件 | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 | Mean ± Std |
|---|---:|---:|---:|---:|---:|---:|
| SNN component | 0.6842 | 0.7905 | 0.6829 | 0.6552 | 0.5938 | **0.6813 ± 0.0637** |
| CLAM component | 0.7551 | 0.5705 | 0.7690 | 0.5493 | 0.5344 | **0.6357 ± 0.1039** |
| SNN+CLAM 融合 | 0.7196 | 0.7925 | 0.7740 | 0.5286 | 0.5978 | **0.6825 ± 0.1027** |

这里的 CLAM component 使用 `PorpoiseAMIL` 病理头，是融合实验的组件诊断结果，
不应当视为对独立 CLAM-SB 实现的严格复现，也不重复计入上面的正式模型排名。

## 16. BRCA 结果目录

- 总目录：`results_brca_multimodal_5fold/`
- CMTA：`results_brca_multimodal_5fold/cmta/fold_metrics.csv`
- MRePath：`results_brca_multimodal_5fold/mrepath/*/summary.csv`
- Porpoise：`results_brca_multimodal_5fold/porpoise/*/*/*/summary_latest.csv`
- SNN+CLAM：`results_brca_multimodal_5fold/snn_clam/summary.csv`
- PIBD：`results_brca_multimodal_5fold/pibd/*/summary.csv`
- MCAT：`results_brca_multimodal_5fold/mcat/*/summary.csv`
- MOTCat：`results_brca_multimodal_5fold/motcat/*/summary.csv`
- SurvPath：`results_brca_multimodal_5fold/survpath/*/summary.csv`

---

# PC-CMKA-DDKAC 图结构支持实验

## 17. 实验完成情况

- COREAD：15 个图结构配置全部完成，每个配置 5 折，共 75 折。
- STAD：按此前筛选要求运行 COREAD 排名前五的配置，共 25 折。
- 汇总采用验证集最佳 C-index；标准差为五折样本标准差（`ddof=1`）。

## 18. COREAD 图结构配置排名

| 排名 | 配置 | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 | Mean ± Std |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `fixed_fold_graph` | 0.9634 | 0.7066 | 0.8654 | 0.7805 | 0.6848 | **0.8001 ± 0.1155** |
| 2 | `effective_resistance_views` | 0.9472 | 0.7325 | 0.7212 | 0.6612 | 0.7939 | **0.7712 ± 0.1090** |
| 3 | `pc_cmka_full_graph` | 0.9390 | 0.6946 | 0.7500 | 0.6612 | 0.7697 | **0.7629 ± 0.1075** |
| 4 | `bernoulli_views` | 0.9350 | 0.7066 | 0.7308 | 0.6558 | 0.7576 | **0.7571 ± 0.1062** |
| 5 | `hessian_antithetic` | 0.9309 | 0.7006 | 0.7596 | 0.6369 | 0.7576 | **0.7571 ± 0.1094** |
| 6 | `patient_degree_edge_gate` | 0.9553 | 0.6926 | 0.7115 | 0.6518 | 0.7697 | 0.7562 ± 0.1191 |
| 7 | `reference_operator` | 0.9431 | 0.7006 | 0.6923 | 0.6423 | 0.8000 | 0.7557 ± 0.1194 |
| 8 | `inverse_calibration` | 0.9390 | 0.6926 | 0.6731 | 0.6640 | 0.8000 | 0.7537 ± 0.1170 |
| 9 | `inverse_random_probe` | 0.9512 | 0.7146 | 0.7212 | 0.5962 | 0.7697 | 0.7506 ± 0.1290 |
| 10 | `isotropic_antithetic` | 0.9390 | 0.7345 | 0.6827 | 0.6260 | 0.7697 | 0.7504 ± 0.1186 |
| 11 | `inverse_fixed_rho` | 0.9350 | 0.6986 | 0.7500 | 0.5854 | 0.7697 | 0.7477 ± 0.1268 |
| 12 | `direct_low_rank` | 0.9431 | 0.7026 | 0.6827 | 0.6355 | 0.7697 | 0.7467 ± 0.1199 |
| 13 | `direct_edge_gate` | 0.9472 | 0.6766 | 0.7115 | 0.6328 | 0.7515 | 0.7439 ± 0.1217 |
| 14 | `reference_degree_edge_gate` | 0.9553 | 0.6806 | 0.7019 | 0.6233 | 0.7455 | 0.7413 ± 0.1274 |
| 15 | `independent_views` | 0.9512 | 0.6886 | 0.7115 | 0.6016 | 0.7333 | 0.7373 ± 0.1296 |

## 19. STAD 已筛选图结构配置排名

| 排名 | 配置 | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 | Mean ± Std |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `bernoulli_views` | 0.5629 | 0.6012 | 0.6113 | 0.7192 | 0.6647 | **0.6319 ± 0.0609** |
| 2 | `pc_cmka_full_graph` | 0.5331 | 0.6194 | 0.6054 | 0.7115 | 0.6754 | 0.6290 ± 0.0686 |
| 3 | `effective_resistance_views` | 0.5430 | 0.5992 | 0.5783 | 0.7115 | 0.6626 | 0.6189 ± 0.0676 |
| 4 | `fixed_fold_graph` | 0.5629 | 0.5607 | 0.6019 | 0.7385 | 0.6169 | 0.6162 ± 0.0726 |
| 5 | `hessian_antithetic` | 0.4967 | 0.6113 | 0.5819 | 0.7154 | 0.6700 | 0.6151 ± 0.0840 |

## 20. 图结构结果目录

- `results/results_graph_structure_15x2_5fold/`

---

# Bernoulli Views + KAN 组合创新实验

## 21. 实验完成情况

- COREAD 与 STAD 均完成 10 个配置 × 5 折，共 100 折。
- 汇总采用验证集最佳 C-index；标准差为五折样本标准差（`ddof=1`）。

## 22. COREAD 组合排名

| 排名 | 配置 | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 | Mean ± Std |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `BK_I03_mask2spline_hyperkan` | 0.8984 | 0.7745 | 0.8173 | 0.6531 | 0.8727 | **0.8032 ± 0.0968** |
| 2 | `BK_I04_kan2bern_controller` | 0.9431 | 0.8204 | 0.7692 | 0.7073 | 0.7394 | **0.7959 ± 0.0922** |
| 3 | `BK_I02_uvr_kan` | 0.9472 | 0.7764 | 0.7500 | 0.7520 | 0.7030 | **0.7857 ± 0.0941** |
| 4 | `BK_I09_stable_cross_pathway_gate` | 0.9350 | 0.7365 | 0.8173 | 0.6287 | 0.7818 | 0.7799 ± 0.1120 |
| 5 | `BK_I08_bernoulli_barycentric_grid` | 0.8862 | 0.7455 | 0.7885 | 0.6558 | 0.8000 | 0.7752 ± 0.0840 |
| 6 | `BK_I05_bml_kan` | 0.9350 | 0.7505 | 0.7981 | 0.6396 | 0.7091 | 0.7664 ± 0.1107 |
| 7 | `BK_I07_overlap_calibrated_jacobian` | 0.9187 | 0.7176 | 0.7981 | 0.6734 | 0.7030 | 0.7622 ± 0.0989 |
| 8 | `BK_I10_sensitivity_correlated_views` | 0.9350 | 0.7555 | 0.7212 | 0.6640 | 0.6727 | 0.7497 ± 0.1101 |
| 9 | `BK_I06_bernoulli_jensen_debiased` | 0.9228 | 0.6796 | 0.7212 | 0.6748 | 0.7455 | 0.7488 ± 0.1016 |
| 10 | `BK_I01_bv_jetkan` | 0.9187 | 0.7086 | 0.7692 | 0.6396 | 0.6970 | 0.7466 ± 0.1066 |

## 23. STAD 组合排名

| 排名 | 配置 | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 | Mean ± Std |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `BK_I06_bernoulli_jensen_debiased` | 0.5993 | 0.6012 | 0.6784 | 0.7038 | 0.6270 | **0.6420 ± 0.0471** |
| 2 | `BK_I08_bernoulli_barycentric_grid` | 0.6358 | 0.6285 | 0.5854 | 0.6731 | 0.6606 | **0.6367 ± 0.0339** |
| 3 | `BK_I07_overlap_calibrated_jacobian` | 0.5795 | 0.6093 | 0.6160 | 0.7404 | 0.6310 | **0.6352 ± 0.0617** |
| 4 | `BK_I04_kan2bern_controller` | 0.5960 | 0.6296 | 0.6572 | 0.6808 | 0.5769 | 0.6281 ± 0.0426 |
| 5 | `BK_I10_sensitivity_correlated_views` | 0.6093 | 0.6397 | 0.5854 | 0.6808 | 0.6001 | 0.6230 ± 0.0379 |
| 6 | `BK_I09_stable_cross_pathway_gate` | 0.5828 | 0.6377 | 0.6137 | 0.6577 | 0.6048 | 0.6193 ± 0.0291 |
| 7 | `BK_I02_uvr_kan` | 0.5215 | 0.6093 | 0.6278 | 0.6462 | 0.6566 | 0.6123 ± 0.0538 |
| 8 | `BK_I01_bv_jetkan` | 0.5464 | 0.5891 | 0.6160 | 0.7038 | 0.6022 | 0.6115 ± 0.0578 |
| 9 | `BK_I05_bml_kan` | 0.5099 | 0.5992 | 0.6137 | 0.7000 | 0.6183 | 0.6082 ± 0.0676 |
| 10 | `BK_I03_mask2spline_hyperkan` | 0.5596 | 0.6235 | 0.5677 | 0.6308 | 0.6515 | 0.6066 ± 0.0406 |

## 24. Bernoulli Views + KAN 结果目录

- `results/results_bernoulli_kan_5fold/`

---

# COREAD 图结构 × 通路聚合补充实验

## 25. 实验范围与口径

- 本组来自原 `COREAD.md`，新增 4 个正式配置、20 个 fold：
  `fixed_fold_graph + GCN/KAN` 和 `bernoulli_views + GCN/KAN`。
- 使用 TCGA-COADREAD 固定五折、随机种子 1、DSS 终点、ResNet50 1024 维
  patch 特征、每张 WSI 最多 4096 patches、最多 30 epochs，并选择验证集
  C-index 最佳 epoch。其余公共训练项见第 2 节。
- 标准差为五折总体标准差（`ddof=0`）。目前没有多随机种子和患者级配对
  bootstrap，不作统计显著性声明。
- 64 patches、1 epoch 的 smoke test 仅验证运行链路，不纳入正式数值比较。

## 26. COREAD 图结构 × 通路聚合正式结果

| 图结构 | 聚合器 | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 | C-index Mean ± Std | IPCW C-index | IBS ↓ |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `fixed_fold_graph` | GCN | 0.9553 | 0.7455 | 0.7212 | 0.7778 | 0.6606 | **0.7721 ± 0.0993** | 0.7065 | **0.1413** |
| `fixed_fold_graph` | KAN | 0.8496 | 0.6976 | 0.7019 | 0.7615 | 0.8121 | 0.7646 ± 0.0598 | **0.7387** | 0.1414 |
| `bernoulli_views` | GCN | 0.9472 | 0.6647 | 0.7500 | 0.7073 | 0.7455 | 0.7629 ± 0.0971 | 0.7011 | 0.1436 |
| `bernoulli_views` | KAN | 0.9431 | 0.7196 | 0.8365 | 0.6667 | 0.7333 | **0.7798 ± 0.0985** | **0.7027** | **0.1397** |

配置与评价边界：

- `fixed_fold_graph` 的结果目录记录为 `DD-KAC` 基因编码。
- `bernoulli_views` 的结果目录记录为
  `PC-CMKA-DDKAC/C4_bernoulli_views` 基因编码。
- 因此两种图结构之间不是严格的单变量比较；只支持在同一种图结构内部比较
  GCN 与 KAN。
- 图结构实验 Fold 2–4 的 iAUC 为空，目前不能报告有效的五折 iAUC。

## 27. COREAD 补充实验解读

| 问题 | 当前结论 |
|---|---|
| 此前单因素消融最高结果 | `CTransPath = 0.7600 ± 0.1329` |
| 本组图结构 × 聚合实验最高结果 | `bernoulli_views + KAN = 0.7798 ± 0.0985` |
| fixed fold 中 GCN 与 KAN | GCN 高 0.0075；KAN 的折间波动更小 |
| Bernoulli views 中 GCN 与 KAN | KAN 高 0.0169，但只在 2/5 折领先 |
| Bernoulli views 是否优于 fixed fold | 不能直接下结论，基因编码配置不一致 |
| 是否已有显著性结论 | 没有，需要多随机种子和患者级配对 bootstrap |

当前最稳妥的表述是：在本次单种子五折实验中，`bernoulli_views + KAN`
获得最高平均 C-index，但优势存在折间不一致，且跨图结构比较受到基因编码配置
不同的混杂，仍需统一配置后复验。该结果与第 22 节的 10 组 `BK_Ixx` 组合是
不同实验批次，二者均保留。

## 28. COREAD 补充实验结果目录

- 图结构与聚合器：
  `results/results_pc_cmka_graph_structure_aggregation/coadread/`
- 图结构 smoke test：
  `results/results_pc_cmka_graph_structure_aggregation_smoke/coadread/`
- 论文消融和默认完整模型目录已在第 12 节列出，不再重复。

---

# TCGA-STAD 全部已完成实验结果与综合分析

## 29. STAD 独立汇总范围、协议与冲突保留说明

> 原汇总日期：2026-08-11  
> 数据条件：TCGA-STAD，DSS，316 个公开 RNA 可用病例，官方五折  
> 正式协议：每折 30 epochs，best-validation-C-index checkpoint  
> 统计口径：五折 Harrell C-index 算术均值 ± 样本标准差

- 本组共 10 行正式结果，包括 8 组独立训练结果和 2 组病例级后期融合结果。
  所有正式结果覆盖相同的 316 个病例和 5 个验证折；smoke、dry-run 与预检不
  参与排名。
- “训练”表示单独优化过模型参数；“融合”表示对已经训练好的 SNN/CLAM
  病例风险作算术平均，没有另行训练融合网络。
- 论文值只用于量级背景，不代表严格同条件复现。
- 本节的 `Bernoulli views + GCN/KAN` 来自独立正式实验目录，不覆盖第 19 节
  的 STAD 图结构筛选结果，也不覆盖第 23 节的 10 组 `BK_Ixx` 结果。它们虽然
  名称相近，但配置和实验批次不同，故按用户要求全部保留。

## 30. STAD 结论摘要

1. 当前 seed 1 的最高单分支结果是 RNA-only SNN：
   **66.99% ± 5.41%**。这说明当前公开队列中 RNA 分支具有较强信号，但 SNN
   在 seed 42 降至 63.54%，尚不能据此认定 RNA-only 稳定优于多模态方法。
2. 本组表现最好的多模态改进是 Bernoulli views + KAN：
   **66.15% ± 3.59%**。相对本地 MRePath 基线提高 3.27 个百分点，相对
   Bernoulli views + GCN 提高 2.77 个百分点，并且折间标准差更低。
3. KAN 的提升不是五折一致：相对 GCN 在 Fold 0/1/2 获胜，在 Fold 3/4
   下降。因此当前证据是“有希望的 seed 1 结果”，不是稳定提升结论。
4. SNN+CLAM 对随机种子较敏感。seed 1 为 65.27% ± 9.26%，seed 42 为
   61.76% ± 8.62%；均值下降 3.51 个百分点，相同 fold 平均绝对变化 5.20
   个百分点。
5. 不能只根据普通 C-index 宣称 KAN 全面优于基线。KAN 的 IPCW C-index、
   IBS、iAUC 和 validation loss 没有同步改善，提示其优势主要体现在 Harrell
   风险排序，概率校准和删失稳健性仍需处理。

## 31. STAD 正式实验总表

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

## 32. STAD 五折完整结果

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

## 33. STAD 同折配对比较

以下比较使用相同 seed 1 和相同官方 fold。由于只有 5 个固定验证折且训练随机
种子有限，不进行统计显著性宣称。

| 比较 | 平均差值 | 获胜折数 | Fold 0/1/2/3/4 差值（pp） | 结论 |
|---|---:|---:|---|---|
| Bernoulli KAN − MRePath | **+3.27 pp** | 3/5 | +2.65 / +7.09 / +10.25 / −1.35 / −2.28 | 均值明显提高，但并非五折一致 |
| Bernoulli GCN − MRePath | +0.50 pp | 3/5 | −1.99 / +3.24 / −0.12 / +0.77 / +0.60 | 基本接近基线，改进幅度较小 |
| Bernoulli KAN − GCN | **+2.77 pp** | 3/5 | +4.64 / +3.85 / +10.37 / −2.12 / −2.89 | KAN 主要改善 Fold 0–2 |
| SNN+CLAM − MRePath（seed 1） | +2.39 pp | 3/5 | +5.63 / +10.12 / −1.06 / +8.46 / −11.22 | 平均提高，但折间波动很大 |
| Porpoise − MRePath | −0.73 pp | 2/5 | −6.62 / +3.24 / −1.41 / +1.54 / −0.40 | 整体与基线接近但略低 |
| SNN+CLAM seed 42 − seed 1 | −3.51 pp | 1/5 | −7.95 / −3.04 / −6.95 / −3.85 / +4.23 | 随机种子敏感性明显 |

## 34. STAD 可共同计算的生存指标

Porpoise、SNN 和 CLAM 的第三方保存结果没有完整时间点生存概率，因此不能可靠
补算 IPCW C-index、IBS 和 iAUC。下表只比较本地 MRePath 与两组 Bernoulli
改进，并使用相同评价代码。

| 模型 | Harrell C-index ↑ | IPCW C-index ↑ | IBS ↓ | iAUC ↑ | Validation loss ↓ |
|---|---:|---:|---:|---:|---:|
| MRePath（SHGNN + MLP） | 0.6288 | 0.6115 | **0.2802** | **0.4558** | **1.6263** |
| Bernoulli views + GCN | 0.6338 | **0.6244** | 0.5680 | 0.3814 | 1.9017 |
| Bernoulli views + KAN | **0.6615** | 0.6063 | 0.5746 | 0.4029 | 3.0141 |

该表表明：

- GCN 的普通 C-index 和 IPCW C-index 略高于 MRePath，但 IBS、iAUC 和 loss
  变差。
- KAN 的普通 C-index 提高最明显，但 IPCW C-index 略低于 MRePath，IBS 与
  loss 明显更高。
- Bernoulli 两组在 Fold 3/4 出现很高的 IBS，说明风险排序提高没有转化为更好
  的生存概率校准。
- 当前最稳妥的表述是“KAN 改善了 seed 1 下的 Harrell 排序性能”，不能写成
  “所有生存指标全面提升”。

## 35. STAD 分方向综合分析

### 35.1 Bernoulli views + KAN

KAN 是本组 seed 1 最强的多模态结果，并具有较低的折间标准差。它相对 MRePath
和 GCN 的均值优势分别为 3.27 和 2.77 个百分点，说明六通路聚合器的表达能力
可能比单纯换成 GCN 更重要。

但 KAN 的提升集中在 Fold 0–2，Fold 3/4 反而低于 GCN；同时校准相关指标没有
改善。下一步应优先补种子和校准约束，而不是直接继续叠加更多模块。

### 35.2 RNA-only SNN 与基因组信号

SNN seed 1 达到本组全部结果中的最高均值 66.99%，且高于同 seed 的
SNN+CLAM 1.72 个百分点；seed 42 中 SNN 也比融合高 1.78 个百分点。这说明
当前直接风险平均没有稳定利用 CLAM 分支，甚至可能因风险尺度不一致而稀释 RNA
信号。

不过 SNN 从 seed 1 到 seed 42 下降 3.45 个百分点，因此不能只依据 seed 1
排名认定其为最终最佳模型。其与论文 SNN 数值差距很大，也提示实现、分子输入和
checkpoint 规则并非严格同条件。

### 35.3 SNN+CLAM 融合波动

SNN+CLAM seed 1 的最高 fold 达 78.85%，最低仅 54.44%；seed 42 的范围同样
很宽。两次实验相同 fold 的平均绝对变化达到 5.20 个百分点。当前算术平均融合
容易受到两路风险尺度影响，后续可在训练折内做风险标准化或学习式融合，但不能
使用验证标签调权。

### 35.4 Porpoise

Porpoise 为 62.15% ± 6.95%，相对 MRePath 低 0.73 个百分点，仅在 2/5 个
fold 获胜。在当前 RNA-only 条件下，没有证据表明 bilinear fusion 比 MRePath
的 SHGNN + IFA 更有效。

### 35.5 病理单分支

CLAM component 两个 seed 分别为 58.95% 和 59.77%，都低于对应 SNN 分支。
seed 42 的 CLAM 标准差只有 2.80%，说明它较稳定但判别力有限。该组件使用
Porpoise 发布代码中的 `PorpoiseAMIL` 生存头，与论文 CLAM-SB 只能作背景参考。

## 36. STAD 非正式门禁实验

以下任务只用于验证数据、代码和显存链路，不进入正式结果排名：

| 门禁任务 | 范围 | 状态 | 用途 |
|---|---|---|---|
| MRePath smoke | seed 1，Fold 0，1 epoch | PASS | 验证 4096-patch 正式路径可执行 |
| Porpoise/SNN/CLAM smoke | 小规模单折 | PASS | 验证第三方 baseline 数据适配与训练链路 |
| SNN/CLAM seed 42 smoke | 小规模单折 | PASS | 验证独立 seed 目录和不覆盖策略 |
| Bernoulli GCN/KAN dry-run | Fold 0，1 epoch，16 patches，仅打印/门禁 | PASS | 验证命令、目录和配置解析 |
| Bernoulli GCN/KAN smoke | Fold 0，1 epoch，16 patches | PASS | 验证 Bernoulli 双视图与两种聚合器可训练 |

## 37. STAD 当前可表述结论与下一步

当前可对外表述为：

> 在 TCGA-STAD 公开 WSI + RNA-only、316 例、官方五折、seed 1 条件下，
> Bernoulli views + KAN 的 Harrell C-index 为 66.15% ± 3.59%，相对本地
> MRePath 基线提高 3.27 个百分点；但该提升尚未在 IPCW C-index、IBS 和
> iAUC 上同步出现，也尚未经过多 seed 验证。

建议顺序：

1. 给 Bernoulli views + KAN 和对应 GCN/MRePath 对照补相同的 seed 42，随后
   扩展到至少 3 个 seed。
2. 针对 Fold 3/4 高 IBS 检查离散生存概率、删失权重和 checkpoint 选择，加入
   校准/早停约束。
3. 对 SNN+CLAM 使用训练折内风险标准化，验证直接平均是否是融合退化来源。
4. 保持病例、五折、ResNet50 特征、epoch 和评价器不变，每次只改变一个主因素。
5. 在多 seed 与多指标证据完成前，不把 seed 1 的单次最高均值写成稳定 SOTA。

## 38. STAD 独立报告与证据入口

以下相对路径按原 STAD 汇总文件原样保留：

| 工作 | Markdown | HTML |
|---|---|---|
| MRePath seed 1 | [中文报告](../../../2026-08-03_stad_mrepath_validation/02_mrepath_seed1/L1_deliverables/STAD_MREPATH_FINAL_COMPARISON_ZH.md) | [离线 HTML](../../../2026-08-03_stad_mrepath_validation/02_mrepath_seed1/L1_deliverables/STAD_MRePath_offline_report.html) |
| Porpoise seed 1 | [中文报告](../../../2026-08-04_multimodal_baselines/01_porpoise_seed1/L1_deliverables/STAD_Porpoise_FINAL_COMPARISON_ZH.md) | [离线 HTML](../../../2026-08-04_multimodal_baselines/01_porpoise_seed1/L1_deliverables/STAD_Porpoise_offline_report.html) |
| SNN+CLAM seed 1 | [中文报告](../../../2026-08-04_multimodal_baselines/02_snn_clam_seed1/L1_deliverables/STAD_SNN_CLAM_FINAL_COMPARISON_ZH.md) | [离线 HTML](../../../2026-08-04_multimodal_baselines/02_snn_clam_seed1/L1_deliverables/STAD_SNN_CLAM_offline_report.html) |
| SNN+CLAM seed 42 | [中文报告](../../../2026-08-04_multimodal_baselines/04_snn_clam_seed42/L1_deliverables/STAD_SNN_CLAM_seed42_FINAL_COMPARISON_ZH.md) | [离线 HTML](../../../2026-08-04_multimodal_baselines/04_snn_clam_seed42/L1_deliverables/STAD_SNN_CLAM_seed42_offline_report.html) |
| seed 复现性 | [对比报告](../../../2026-08-04_multimodal_baselines/05_seed_reproducibility/L1_deliverables/STAD_SNN_CLAM_seed1_vs_seed42_reproducibility.md) | [离线 HTML](../../../2026-08-04_multimodal_baselines/05_seed_reproducibility/L1_deliverables/STAD_SNN_CLAM_seed1_vs_seed42_reproducibility_offline.html) |
| Bernoulli GCN/KAN | [中文报告](../../../2026-08-10_stad_bernoulli_views/01_seed1_formal/L1_deliverables/STAD_BERNOULLI_GCN_KAN_FINAL_REPORT_ZH.md) | [离线 HTML](../../../2026-08-10_stad_bernoulli_views/01_seed1_formal/L1_deliverables/STAD_BERNOULLI_GCN_KAN_offline_report.html) |

## 39. STAD 原始结果位置

- MRePath：`/mnt/f/Sheaf-TCGA/results/stad_project10/paper_original_5fold_seed1/`
- Porpoise、SNN、CLAM seed 1：
  `/mnt/f/Sheaf-TCGA/results/stad_porpoise_snn_clam/`
- SNN、CLAM seed 42：`/mnt/f/Sheaf-TCGA/results/stad_snn_clam_seed42/`
- Bernoulli GCN/KAN：
  `/mnt/f/Sheaf-TCGA/results/stad_project10/bernoulli_views_gcn_kan_seed1/formal_30e_4096p/`

这些是原始报告记录的原主机 F 盘位置。原始结果、checkpoint、病例级预测和日志
当时保存在 F 盘；本文件只整合汇总信息，没有移动或覆盖实验产物。
