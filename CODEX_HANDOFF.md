# MRePath 项目 Codex 交接说明

## 2026-09-16 22:22：无人值守至 19 日的容错、全盘和健康监控已启用

详细策略与返回后的检查入口见 `docs/UNATTENDED_RUNBOOK_20260916.md`。关键状态：

- 三个 enabled user services 均 active，`Linger=yes`；GPU 每 20 秒、健康每 60 秒轮询。
- AES CPU 构建器在 204 限制一个并发（202 HNSC 一个），并以 idle I/O priority + nice 10
  运行，避免与 GPU 训练争抢特征盘吞吐。
- 每卡最多一个本轮任务；18,000 MiB 启动阈值。失败任务独立做最多 12 次指数退避重试，
  8 小时无日志进展会终止该精确任务并重试；控制器崩溃由 systemd 恢复。
- 监控两机四个物理数据文件系统。写盘使用 204 `/xmlg`（约 308.5 GiB 可用）和 202 `/`
  （约 83.1 GiB 可用）；204 `/` 与 202 `/new_data` 只余约 24.7/34.0 GiB，不写新大文件。
  训练/AES 分别设 60 GiB、80/60 GiB 安全线，原缓存不删除。
- 75 个外部模型输入组合、2,402 张入组 slide、202 HNSC 415 个 graph 全通过预检；
  40 tests + 15 subtests 通过。受控重启后四个 GPU 任务和三项 AES 缓存均正常续跑。

## 2026-09-16 22:02：三外部模型 + M3 + AES 的 22 项动态队列已启动

当前用户明确要求 LD-CVAE、DIMAF、SlotSPE 使用现有 ResNet50 特征跑五队列，
M3（`BK_I03_mask2spline_hyperkan`）补跑 BLCA/HNSC，AES 跑五队列。共 22 个
“模型×队列”任务，每项内部为五折。动态队列状态：
`results/requested_full_20260916/scheduler/pipeline_status.json`。

- 204 GPU0/1 被其他用户占至只余约 0.4/1.8 GiB；启动时实际使用 4 卡：204 GPU2/3、
  202 GPU0/1。控制器持续轮询；任一候选卡空闲显存达到 18 GiB 会自动补任务，
  每卡同一时刻最多一个本轮任务，不停止他人进程。
- 服务 `mrepath-requested-six-gpu-20260916.service`；204 结果根
  `results/requested_full_20260916/`，202 结果根
  `/home/Lim/MRePath_runs/requested_full_20260916/`。
- 首批任务：M3-BLCA、SlotSPE-BLCA、M3-HNSC、SlotSPE-BRCA；两项 M3 已有真实
  batch loss，外部模型 smoke 在两机真实缓存上通过。
- 首次 SlotSPE 进程曾因多进程 DataLoader 的文件描述符传递错误退出；适配器已只对
  LD-CVAE/DIMAF/SlotSPE 强制 `num_workers=0`（不改模型、数据、损失或随机种子），
  并重新启动。旧 traceback 追加保留在同一 `task.log`；判断当前状态应以最新
  `invocation.json` / `manifest.json`、存活 PID 和调度状态为准。重启时发现并清理了
  SSH 遗留的重复远端进程；调度器现会识别既有本轮 PID，防止再次叠加。
- 外部适配入口 `scripts/run_resnet50_repository_model.py`：导入 pinned 官方模型/损失，
  只读现有 PT/HDF5/graph.x，不修改或转换原缓存；统一 active split、DSS、RNA、
  ResNet50-1024D、最多 4096 patches。其结果口径是“官方结构 + 统一 ResNet 输入”，
  不是论文 UNI/CTransPath 原生成绩。
- 智普审计见 `docs/ZHIPU_AND_INPUT_AUDIT_20260916.md`：原始特征当天修改数为 0；
  08:30 的外部模型/M3 未训练成功；`p=.8,T=.2` 的部分 AES 缓存保留但不使用。
- 正式 AES 首轮登记 `p=.8,T=.001`，只含 p/T，无隐藏 Top-k/邻居上下限。服务
  `mrepath-aes-cache-20260916.service` 在 CPU 构建完整 WSI 缓存（204 同时两队列、
  202 HNSC 一队列），状态 `cache_pipeline_status.json`；完整验收后 GPU 控制器才训练。
- 两个服务均为持久 systemd user service；不要另启同一任务。失败时查看各 task.log、
  controller_task.log 和 scheduler events，已完成折由 checkpoint+prediction+metric 验收后跳过。

更新时间：2026-09-14（下方原有章节保留历史记录）

## 2026-09-16：新划分前三模型 30 折已完成

最终汇总见 `results/results_author_patient_disjoint_20260914/LIVE_RESULTS.md` 和 `table.md` 顶部。
原始 MRePath、PIBD、SurvPath 在 BLCA/BRCA 的 30 折全部核验完成（0 失败），使用 BLCA 357、
BRCA 868 患者互斥五折、现有 ResNet50-1024D 特征和 DSS 终点：

| 模型 | BLCA Mean ± SD | BRCA Mean ± SD |
|---|---:|---:|
| 原始 MRePath | 0.676504 ± 0.060056 | 0.713741 ± 0.050413 |
| PIBD | 0.582271 ± 0.027208 | 0.717700 ± 0.052639 |
| SurvPath | 0.569623 ± 0.053448 | 0.647979 ± 0.088831 |

每折病例预测、标签、风险有限性和 C-index 已重算验收；完整逐折数值在 `table.md`。四个队列服务已结束，
没有失败折。旧有重叠划分结果仍保留为历史数据，不与本结果混用。MMP、LD-CVAE、DIMAF、SlotSPE 的 100 折
尚未启动，仍等待输入协议确认及官方特征/原型依赖。

## 2026-09-15 00:03：用户允许跨所有可用盘，剩余 6 折已重新安排

此节优先于下方原磁盘路径和任务归属。09-14 21:09 旧 204 队列因系统盘低于 64 GiB
保护停止，完整结果 24/30 折；202 原 BLCA 十折已完成。用户确认不限定原结果盘。

- 完整盘点及恢复细节：`docs/STORAGE_RECOVERY_20260914.md`。四个文件系统当时约剩
  204 系统 42 GiB、204 数据 55 GiB、202 系统 88 GiB、202 数据 69 GiB。
- 原 204 物理结果完整保留，6.5 GiB 副本复制到 202 系统盘并通过 checksum 无差异验证。
  项目结果软链接现指 `/home/Lim/MRePath_remote202_results/author_patient_disjoint_20260914`，
  是 204 私有 SSHFS 访问 202 的实验结果目录；旧软链接另名保留。
- 204 新服务 `mrepath-clean-baselines-204-storage-recovery-20260914.service`：
  MRePath BLCA/BRCA fold4 + PIBD BRCA fold3/4，队列 `queue_204_recovery`。
- 202 剩余 SurvPath BRCA fold3/4 由 `mrepath-brca-recovery-after-mirror-20260914.service`
  等待约 34.935 GiB 已有 BRCA PT/依赖复制结束后校验并启动；不重复 204 的 fold0–2。
  202 结果也在系统盘，特征在 `/new_data`。每卡一个本项目任务；显存不够则等待。
- 实际状态看 `host202_brca_recovery_bootstrap.json` 和两机新队列，不能把等待复制称为训练中。
- 两边结果盘预留 22 GiB 已分配下载空间 + 32 GiB 安全余量；复制过程至少保留 202 数据盘
  24 GiB。挂载检查阻止失联后写回本地，训练服务绑定挂载服务。
- 已完成 24 折不重跑。中断 4 折没有完整 optimizer/RNG 状态，明确从头重跑；中间产物归档，
  另 2 折原未启动。模型、特征数值、seed、epoch、loss 和划分不变。
- 新报告服务 `mrepath-clean-baselines-report-storage-recovery-20260914.service`，按不重复的折
  合并跨主机结果，增加停止原因和恢复等待状态。旧队列的 stopped 是历史记录。
- 57 项回归测试 + 1 项真实 SSHFS 保存/加载/排他锁测试通过。
- 未删除数据/缓存/结果，未扩分区，未停其他项目；没有恢复旧 GDC 下载服务。
  后四模型 100 折仍未启动，仍待输入协议确认；本次磁盘授权不代表确认更换其 Encoder。

## 2026-09-14 08:33 起：新划分基线重跑已启动，每卡一个本项目任务

最新用户请求：MRePath 原始模型 / PIBD / SurvPath 重跑 BLCA、BRCA（30 折）；
MMP / LD-CVAE / DIMAF / SlotSPE 跑 BLCA、BRCA、COREAD、STAD、HNSC（100 折）。
总需求 130 折，但**只有前三模型的 30 折已安排；后 100 折尚未启动**。
用户要求现在每张显卡一个任务，取代下文旧的每卡双任务安排。

- 新入口：`results/results_author_patient_disjoint_20260914/LIVE_RESULTS.md`。
  204 该结果目录是指向 `/home/Lim/MRePath_runs/author_patient_disjoint_20260914` 的软链接，
  避免进一步挤占正在下载 BRCA 的 `/xmlg` 数据盘。
- 204：`mrepath-clean-baselines-204-20260914.service`，20 折，GPU 0/1/2/3 各最多一个。
  首批为 MRePath/BLCA fold0、MRePath/BRCA fold0、SurvPath/BRCA fold0、PIBD/BRCA fold0；
  已确认四者都有真实 batch loss。后续按完成顺序接续同四个模型/队列组合的其余折。
- 202：计划 PIBD/BLCA、SurvPath/BLCA 各五折，GPU0/1 各最多一个。
  `mrepath-blca-feature-mirror-stream-20260914.service`（在 204）正在复制 421 份现有 HDF5
  及输入/调度依赖，共 433 文件、25,448,860,130 bytes；没有重跑 ResNet。
  `mrepath-clean-202-after-mirror-20260914.service`（在 204）等待复制结束并核验，
  然后自动在 202 启动 `mrepath-clean-baselines-202-20260914.service`。
  实际进度看 `host202_bootstrap.json`，不要把等待复制说成已经训练。
- 最初的镜像服务在 `--checksum` 全量预扫描中遭遇磁盘 I/O 争用，尚未传出数据；
  已仅停止本次复制/等待服务，改为标准 rsync 流式传输（仍有传输校验、断点保留和旧文件备份），
  没有停止任何训练或下载。旧服务日志保留。
- 两机已有其他项目进程，不停止它们。本项目使用显式共享、启动前至少 18000 MiB
  空闲显存、两次准入检查、固定 `max_jobs_per_gpu=1`；旧项目任务不纳入本项目任务数。
  204 输出盘至少保留 64 GiB；202 扣除其 data 分片剩余下载后至少保留 60 GiB。
- 调度：`scripts/run_clean_baseline_queue.py`，沿用原始模型和旧 baseline 参数，30 epochs、seed1、
  DSS；原 MRePath 使用 original genomic encoder/default gene aggregation/dynamic+IFA，无 AES/KAN。
  各模型原生 batch/抽样/时间分箱差异仍保留。分折独立锁、输出保护、病例预测重算验收。
- 报告服务：`mrepath-clean-baselines-report-20260914.service`，每分钟更新新入口，
  完整五折才报均值；不修改历史实验结果。
- 新队列、患者划分、预测验收、历史报告及现有调度/缓存回归测试：51 项通过。
- MMP 官方代码已直连克隆：`third_party/MMP_20260914`，
  `https://github.com/mahmoodlab/MMP`，commit `1fd75e37592f7ab47b787f737733ba3c5a7e714c`。
  没有把 MMP 简化成另一个模型，也没有启动 MMP 正式训练。
  已在非训练用的 `.venvs/repository_baselines_20260913` 安装官方环境所列 POT==0.9.4；
  在仓库 `src/` 下 `python -m training.main_survival --help` 成功。
  这仅证明入口依赖可加载，不代表完成 MMP 真数据训练或性能验收；主训练环境未改。
- 后四模型的官方配方仍缺 UNI/CTransPath 特征、部分原生 RNA 和训练折原型；
  LD-CVAE/DIMAF 的 COREAD/STAD/HNSC、MMP 的 HNSC 还需输入队列适配。
  已询问是否统一现有 ResNet/RNA/DSS/五折做“统一输入对照”，尚未收到选择；
  不能擅自用 ResNet 冒充 UNI/CTransPath，也不能把未启动的 100 折说成正在排队训练。

## 2026-09-14：BLCA / BRCA 作者患者互斥五折（划分切换时点记录）

用户同意保留 BLCA **357 人**、BRCA **868 人**和原 ResNet50 Encoder，采用
SurvPath / PIBD 固定原始提交的五折，仅过滤非当前队列患者，不重新随机划分。
此决定取代下文“继续保留 BLCA / BRCA 有重叠划分”的历史要求。

- 规范文件及详细边界：`splits/author_patient_disjoint_20260914/README.md`、`manifest.json`。
- 204 项目默认 `splits/5folds/` 和本地 SurvPath / PIBD 两个 checkout 的 BLCA / BRCA
  入口已统一；202 已同步相同划分入口，但其主项目目前仍只有 HNSC 数据，未迁移图像/RNA。
- BLCA 各折训练/验证：287/70、286/71、282/75、287/70、286/71。
  BRCA：692/176、700/168、686/182、702/166、692/176。所有同折交集均为 0，
  每患者恰好验证一次，旧患者集合完全保留。
- 旧 CSV 备份至 `splits/archive/pre_author_patient_disjoint_20260914/`，旧成绩和权重保留；
  新划分尚未训练，不得复用旧成绩表示新性能。队列增加划分哈希变更拒绝复用旧输出的检查；
  历史报告改为读归档旧划分核验，不再随默认入口变化而误报历史预测损坏。
- **不需要重新提取 ResNet 特征**：BLCA 所需 421 张 WSI 已有 HDF5 / graph.x，
  BRCA 所需 926 张 WSI 已有 `.pt`；两者逐切片图和超图缓存也齐全。
  模型、Encoder、RNA、clinical、metadata、其他三队列划分均未修改。
- BLCA 独立补齐的 364 人队列未启用。用户选定的旧 357 人仍包含 CDR Redacted 病例
  `TCGA-C4-A0EZ`；本次只修复同折患者重叠，不替代临床入组和其他预处理泄漏审计。
- 本次没有启动训练、重提 ResNet、删除数据或停止下载。后续训练使用独立的新结果目录，
  如 `results/results_author_patient_disjoint_20260914/`，训练折 scaler / 分箱依现有流程重拟合。
- 验收：47 项测试通过，真实 loader 20 个分区名单与新 CSV 一致并通过图像/RNA样本读取；
  旧预测 25 折按归档划分核验错误 0；两机三个代码入口的 10 份 CSV 哈希一致。
  机器可读记录为规范划分目录内 `verification.json`。

## 2026-09-14：BLCA 公共多模态队列补齐完成（独立目录，未训练）

用户要求“把剩下的人队列补齐，告诉我最终 BLCA 多少人”。本次只下载/准备/验收数据，未启动新实验、未生成新划分，旧数据、缓存和结果保留。

- 新队列：`data/tcga_blca/public_dss_20260914/`。以公开诊断 DX WSI + 原发肿瘤 RNA + 有效 DSS（天数 > 0）+ 无 CDR Redacted 为纳入条件，不使用论文人数作为筛选依据。
- **全量验收通过：364 人、435 张 WSI、6,337,351 个 patch；失败项 0。** `final_audit.json`、`status.json` 为机器可读结果，`README.md` 说明完整来源及使用边界。
- 人数变化为旧实际可用 357 − 1（TCGA-C4-A0EZ，CDR Redacted）+ 补齐 8 = 364。其余两名 Redacted（TCGA-C4-A0F1、TCGA-C4-A0F7）也未纳入新队列；历史文件没有删除。
- 6 名已有切片缓存但缺旧 metadata/RNA 配套输入的患者已加入：C4-A0F6、DK-A1A6、E7-A8O8、FD-A43S、G2-A2EC、GD-A76B（均为 TCGA 前缀）。另外 HQ-A5NE、MV-A51V 的两张原始 WSI 已直连下载，合计 192,496,273 bytes，大小及 MD5 通过。
- 433 张旧缓存软链接复用；新增两张用原 true-20x/256×256/ResNet50-1024D/k=9 流程完成坐标、特征、图与超图缓存。不要覆盖式重建这些旧缓存软链接目标。
- **新队列 RNA 全部统一为同一份 Xena HiSeqV2_PANCAN 来源，364×20,530；不能拼接旧 4,999 基因矩阵。** 共同基因/患者的旧新表达值平均绝对差约 4.0932，旧 checkpoint 和旧成绩不能直接当作新队列结果。新 RNA 仅转置和患者选择，未做额外 log/填补/全队列 scaler 拟合；后续比较需统一新输入重新训练。
- 原数据工厂识别 364 人；补入的 8 人及一名原有多 WSI 患者通过真实 dataset 输入读取检查。6 组基因数为 `[81,304,498,424,1417,428]`。`loader_added_patients_smoke.json`、`source_alignment_audit.json` 留有证据。
- 旧 metadata、clinical、RNA、五折 CSV、`model.yaml` 的 SHA256 与补齐前完全一致。旧五折 CSV 并集为 384 人，不等于旧实际参与训练的 357 人；没有擅自把新 364 人塞进原划分，也没有切换 `model.yaml`。后续训练须先确认新队列划分方案。
- 脚本：`scripts/prepare_blca_public_cohort.py`（prepare/download/preprocess/audit）；6 项单元测试通过。新队列 `runtime/` 提供原 loader 相对 clinical/signatures 路径的隔离入口。当前结果仅证明自动计算完整性，不是病理专家复核。

## 2026-09-14：每卡双任务的新调度（优先于下方单任务旧规则）

用户要求“每张显卡至少分配两个任务”。以每张 4090 同时两个项目实验为目标，
显存/磁盘准入不满足或独立未完成折耗尽时不强行凑数，不停止 xmlg 任务。

- 204 原控制器 PID 704597 及已有训练不重启；增加
  `mrepath-baseline-double-204-20260914.service`，队列 `queue_204_double`。
  接管未开始的 SurvPath/BLCA 折，并运行从 202 分配过来的 SurvPath/HNSC 五折。
- 202 原始 MRePath/HNSC 控制器 PID 2793962 和已有折不重启。
  只重启无 active 折的 baseline 控制器，改为仅 PIBD/HNSC 五折，与原始模型并行。
  `60-two-jobs.conf` 覆盖旧 `50-gpu-sharing.conf` 的串行预留规则。
- 新增/更新 baseline 队列使用 `--max-jobs-per-gpu 2 --allow-gpu-sharing`
  和 `--min-gpu-free-mib 10000`，计入指定其他项目队列的存活 PID；两次准入和
  启动前复查保留。10000 MiB 是启动前空闲显存阈值，不是训练显存硬上限。
- 每折 worker 使用跨 exec 保留的 `execution.lock`；取得锁后重新验证已完成结果。
  这样旧 204 控制器内存中仍有相同待跑折时不会重复计算或覆盖结果。
  补充队列 `--leave-existing-training` 保留已有未完成目录，不将正在训练目录改名。
- 202 HNSC 的 415 个 HDF5 原样复制到 204 系统盘
  `/home/Lim/MRePath_feature_mirror_20260914/hnsc/h5_files`（19,077,461,496 bytes），
  项目 `data/tcga_hnsc/clam_20x_resnet50_paper_k9` 为指向该镜像的软链接。
  不删除或重编码 202 任何缓存，不占用 BRCA 下载盘空间。RNA、clinical、metadata、
  五折 CSV 两机 SHA256 完全一致，实际需要的 412 张 WSI 已做存在性审计。
  全量 `rsync -anc --itemize-changes` 校验退出 0、无差异。
- 模型结构、损失、seed、batch、epochs、特征数值和划分不变；报告增加读取
  204 的 HNSC 结果，202 不再启动 SurvPath/HNSC，禁止两机重复跑同一折。
- 新调度状态以各 `pipeline_status.json`、GPU PID 和日志为准；上述 PID 是变更时
  的定位记录。配置和测试见 `configs/systemd/host204/`、`host202/`、
  `tests/test_gpu_fold_queue.py`、`tests/test_baseline_double_queue.py`。
- 03:37 北京时间已核实六卡均为两个项目 GPU 训练进程，新增六折都有 batch loss。
  204：GPU0 SurvPath/BLCA 0+3，GPU1 SurvPath/BLCA 2+4，
  GPU2 SurvPath/BLCA 1 + HNSC 0，GPU3 PIBD/BLCA 4 + SurvPath/HNSC 1；
  202：GPU0 原始 MRePath/HNSC 0 + PIBD/HNSC 0，GPU1 对应两模型 HNSC 1。
  此为瞬时排布，完成后自动接续剩余折，不意味着实验全部完成。

## 2026-09-14：用户已明确允许共享 202 显卡

用户在获知 202 两卡被 xmlg 任务占用后答复：“没事，202主机照样用”。
此授权取代下文 9 月 13 日“未获准共享”的旧状态；不代表可以停止其他任务。

- 仅 202 的原始 MRePath/HNSC 与 PIBD/SurvPath/HNSC 调度器启用 `--allow-gpu-sharing`。
- 仍要求启动前空闲显存至少 18000 MiB、连续两次准入及启动前复查；每个队列每卡最多一个自己的任务。其他用户的进程不停止、不迁移。
- 原始 MRePath 队列先运行 HNSC 五折，完成后 PIBD/SurvPath 接续；两队列间的显卡预留不取消。
- 只重启了两个 `active=[]` 的等待中 202 调度器，无正在训练的折被中断。204 四卡原队列及其进程未重启。
- 持久化覆盖文件源位于 `configs/systemd/host202/*service.d/50-gpu-sharing.conf`，部署至 202 的 `/home/Lim/.config/systemd/user/`。模型、batch、epochs、seed、loss、划分和缓存不变。
- 共享模式只调整调度准入，不保证独占吞吐或其他任务未来不会增长显存；不足准入阈值时暂不启动下一折。
- GPU 队列测试：204 16 项通过；202 15 项通过、1 项因没有 BLCA 本地数据而显式跳过（该集成测试已在 204 通过）。
- 实际运行折和进度仍以 `results/results_requested_baselines_5fold_20260913/LIVE_RESULTS.md`、202 两个 `pipeline_status.json` 为准。

## 2026-09-13 晚：当前正在执行的用户请求

补齐原始结构 MRePath 的 BLCA/HNSC，以及 PIBD/SurvPath 的五个数据集。
不要重启已经在跑的折，不要重跑已验证完整的 BRCA 基线，不要混入 AES 或 Bernoulli + KAN。

- 原始 MRePath / BLCA 新五折已完成：0.715707、0.658349、0.707198、
  0.755130、0.776119，Mean ± population SD = **0.722501 ± 0.040830**。
- PIBD / BRCA、SurvPath / BRCA 各 5 折历史结果已通过患者集合、DSS 标签和
  病例预测 C-index 重算核验，分别为 **0.6628 ± 0.0800**、**0.6331 ± 0.0560**。
- 新增总计划 50 折。204 四卡已转入 PIBD/SurvPath 的 COREAD、STAD、BLCA
  五折队列；202 的 HNSC 原始 MRePath 和两个基线队列等待其他用户任务释放显卡。
  没有获准前，不停止或共享 xmlg 用户正在使用的 GPU。已向用户发出是否允许共享
  GPU 的非阻塞询问；截至本记录尚无答复。
- 当前完整进度、逐折成绩、失败状态，以自动更新的
  `results/results_requested_baselines_5fold_20260913/LIVE_RESULTS.md` 和
  `results.json` 为准。配置、服务名、主机目录、代码版本和恢复步骤见同目录 `RUN_STATUS.md`。
- BLCA 保留用户指定原划分，每折存在 11–13 名患者重叠。
  新审计也发现历史 BRCA 每折重叠 14、11、22、21、15 名患者；均须标注泄漏。
  BRCA 当前元数据/RNA 交集为 868 名，两个历史基线预测名单与当前划分完全一致；
  下文“871 名”是历史记录，不作为本轮已核验人数。
- 模型结构/专用损失保持原实现。MRePath 用项目既有训练折分箱；两个基线沿用
  官方队列级分箱与历史 BRCA 口径。batch、抽样、调度等原生差异见 RUN_STATUS，
  不能声称所有模型训练协议完全一致。
- 所有原始 WSI 下载、旧缓存、旧 checkpoint 保留。没有为本轮重建 WSI 特征。

以下为原 2026-08-26 交接内容；当前状态优先使用上面的实验记录。

## 1. 项目位置

- 原主机：`/mnt/e/mrepath`
- 204 主机：`/xmlg/Lim/Project1`
- GitHub：`https://github.com/CFLIMGQ0/Project10.git`

## 2. 最终研究目标

本项目不是只运行一次 MRePath，而是完成一条可以形成论文的研究路线：

1. 尽可能严格复现 MRePath 论文及官方仓库，在 COREAD、STAD、BRCA 上统一数据、固定五折、随机种子、终点、训练配置和评价方法。
2. 在 MRePath 基础上提出性能更好、稳定性更强的新模型。
3. 当前主要创新方向包括：
   - PC-CMKA-DDKAC 和 Bernoulli Views 图结构构建；
   - KAN 及其改进基因组编码器；
   - Quality + Conflict 质量与冲突平衡融合。
4. 通过单模块消融和关键组合实验筛选有效模块，不能盲目叠加所有组件。
5. 最终候选模型应在至少 COREAD、STAD、BRCA 上验证，并尽量稳定优于原始 MRePath 和主要多模态基线。
6. 正式结论需要多个随机种子、配对五折比较、统计检验以及 C-index、IBS、iAUC 等指标。
7. 禁止使用验证集或测试集信息进行数据泄漏式调参，不能仅凭某一折或一次高结果认定模块有效。

## 3. 公共实验原则

- 固定五折：使用项目已有划分。
- 默认随机种子：`seed=1`。
- 默认训练：30 epochs、batch size 1。
- 模型选择：验证集 C-index 最佳 Epoch。
- 生存终点：当前主要使用 DSS。
- WSI 特征：20x、ResNet50、1024-D，每例最多 4096 patches。
- 对比实验必须复用相同病例、五折划分、终点、特征和评价器。
- 每次正式实验需保留配置、完整日志、病例级预测、每折指标和 best checkpoint。

## 4. 配置结构

项目统一使用 `model.yaml` 描述模型模块，主要逻辑包括：

1. 基因组图结构构建开关：可选择已有图结构 Idea 或 `none`。
2. 基因组编码器：MLP、GCN、KAN 及其改进变体。
3. 病理图编码器：SHGNN、HGNN、GCN、GAT、MLP 等。
4. 多模态融合：论文 IFA、固定/动态权重、Quality + Conflict 等。

不要重新引入多个互相冲突的主配置文件，也不要破坏已经验证的基础接口。

## 5. 重要结果

完整结果以 `table.md` 为准。

### COREAD

- Bernoulli+KAN 最好：`BK_I03_mask2spline_hyperkan = 0.8032 ± 0.0968`。
- 图结构最好：`fixed_fold_graph = 0.8001 ± 0.1155`。
- 论文消融中 CTransPath：`0.7600 ± 0.1329`。
- 基因组 GCN：`0.7410 ± 0.1239`。
- 原始完整参考模型：`0.7265 ± 0.1177`。

### STAD

- Bernoulli+KAN 最好：`BK_I06_bernoulli_jensen_debiased = 0.6420 ± 0.0471`。
- 已筛选图结构中最好：`bernoulli_views = 0.6319 ± 0.0609`。
- 学弟运行的 SNN+CLAM：`0.6527 ± 0.0926`。
- 学弟运行的 Porpoise：`0.6215 ± 0.0695`。
- 本地 MRePath 参考结果约：`0.6288 ± 0.0508`。

### BRCA

- CMTA：`0.7704 ± 0.0347`。
- MRePath：`0.7453 ± 0.0829`。
- Porpoise：`0.7375 ± 0.0786`。
- SNN+CLAM：`0.6825 ± 0.1027`。
- PIBD：`0.6628 ± 0.0800`。
- MCAT：`0.6420 ± 0.0566`。
- SurvPath：`0.6331 ± 0.0560`。
- MOTCat：`0.5971 ± 0.0771`。

当前 BRCA 实际训练病例为 871；论文正文报告的 968 与公开仓库元数据不一致，不能在没有明确病例清单时人为补成 968。

## 6. 已完成实验

1. COREAD 论文消融：21 个已完成配置，见：
   - `results/results_coadread_paper_ablations_20260726/`
2. 图结构实验：
   - COREAD：15/15 个配置完成。
   - STAD：按筛选要求完成前五个配置。
   - 目录：`results/results_graph_structure_15x2_5fold/`
3. Bernoulli Views + KAN：
   - COREAD：10 个配置 × 5 折完成。
   - STAD：10 个配置 × 5 折完成。
   - 目录：`results/results_bernoulli_kan_5fold/`
4. BRCA 多模态基线：8 个正式模型 × 5 折完成。
   - 目录：`results_brca_multimodal_5fold/`

不要重复运行已经具有完整 5 折 `summary.csv` 的实验，除非用户明确要求多随机种子复验。

## 7. 204 主机数据状态

204 项目目录：`/xmlg/Lim/Project1`

已核对一致：

- COREAD graph files：302；hypergraph cache：301。
- STAD graph files：344；hypergraph cache：343。
- BRCA graph files：930；hypergraph cache：929。
- 图结构实验汇总：20 份 `summary.csv`。
- Bernoulli+KAN 汇总：20 份 `summary.csv`。
- BRCA 正式结果汇总已同步。
- `table.md` 已更新并与原主机 SHA256 一致。

正在从原主机续传：

- Bernoulli+KAN：100 个 best checkpoint，约 29.99 GiB。
- BRCA：929 个 PT 特征，约 35.03 GiB。

原始 WSI 没有整体同步到 204。运行现有 MRePath 图结构实验不需要原始 WSI；重新提取 patch/特征时才需要。

## 8. 关键文件

- 总结果表：`table.md`
- 早期综合记录：`result.md`
- 模型主配置：`model.yaml`
- 训练入口：`main.py`
- 图提取入口：`extract_graph.py`
- BRCA 套件配置：`configs/brca_multimodal_suite.json`
- COREAD/STAD 缓存实验配置：`configs/cached_coadread_stad_experiments.json`

## 9. 接手后的第一步

1. 阅读本文件、`table.md`、`model.yaml`。
2. 检查正在接收的 best 权重和 BRCA `pt_files` 是否完整。
3. 在开始新实验前检查 GPU、CPU、内存、磁盘和现有训练进程。
4. 不删除或覆盖正在同步的文件，不重新下载原始 WSI。
5. 新实验开始前先说明：实验假设、唯一变化模块、对照配置、输出目录和预计折数。
6. 实验结束后把每折结果、均值、标准差、配置和结果路径补入 `table.md`。

## 10. 下一阶段建议

优先从跨数据集结果中选择真正稳定的模块，而不是只选择 COREAD 单数据集最高值：

1. 以原始 MRePath 为严格对照。
2. 分别复验最佳图结构模块和最佳 KAN 组合。
3. 验证 `Bernoulli Views + KAN` 是否在 COREAD、STAD、BRCA 上均有增益。
4. 再将有效模块与 Quality + Conflict 组合，做最小且清晰的组合消融。
5. 对最终候选模型运行至少 3 个随机种子，并报告配对 fold 差值和稳定性。

## 11. 2026-09-13 新增官方基线代码接入

用户要求以官方仓库复现 LD-CVAE、DIMAF、SlotSPE。详见 `docs/REPOSITORY_BASELINES_2025_2026.md`，固定版本清单在 `configs/repository_baselines_20260913.json`。

- 三个 checkout 已下载到 204 和 202 的 `third_party/`。
- 204 的三个模型均已通过官方训练函数 CPU 合成数据测试：`results/repository_baselines_20260913/smoke_03/`；202 独立复测也全部通过，记录在同级 `smoke_202_01/`。两台各通过 8 项启动保护测试。这是代码验证，不是真实五折性能。
- DIMAF、SlotSPE 源码未修改；LD-CVAE 仅两份模型文件内的 CUDA 写死改为跟随输入 device，没有更改计算/损失。
- 新测试环境 `.venvs/repository_baselines_20260913`，只在新 venv 装覆盖层，未修改旧实验环境。不是原论文逐版本环境，也不是原始 WSI 提取环境。
- DIMAF 原生 BLCA/BRCA RNA 已直连下载并调用官方脚本处理，分别核验 359/868 名患者全部匹配；原始压缩文件和旧缓存保留。
- 正式训练仍缺对应 CTransPath/UNI 特征、DIMAF 的训练集原型/GPU FAISS、SlotSPE 的官方外链 RNA。不能偷偷换成 ResNet 或补零。
- 官方 cohort 不完全相同：LD-CVAE、DIMAF 只随附本项目 BLCA/BRCA 的划分；SlotSPE 含本项目五个 cohort。不要擅自重划分。
- `scripts/run_repository_baseline.py` 默认只做检查，`--execute` 才启动；要求数据齐全、来源清单、新输出目录和空闲 GPU。
- 本次没有停止或重启正在运行的 MRePath / PIBD / SurvPath 队列，也没有生成新三个模型的正式 C-index。
