# 2026-09-14 磁盘保护后的跨盘恢复

## 授权和边界

用户明确可以使用两台主机上的其他磁盘，不限定原结果盘。
本次仅使用已经挂载、Lim 可写的磁盘，不扩分区、不格式化、不删除缓存/数据/历史结果，
不停止其他项目。没有更改模型结构、Encoder、RNA 数值、患者名单、五折、loss、seed 或 epochs。
后四模型的 100 折仍待输入协议确认，未启动。

## 实际盘点（2026-09-14 23:45 左右，GiB 近似值）

| 主机 | 实际文件系统 | 可用空间 | 本次用途/约束 |
|---|---|---:|---|
| 204 | `/dev/sda5`，含 `/home/Lim` | 42 | 保留原结果，不再接收本轮新 checkpoint |
| 204 | `/dev/sdb1`，`/xmlg` | 55 | 保留训练输入；旧 BRCA 分片仍差约 112.79 GiB，不能当作全量下载足够 |
| 202 | 系统 LVM，含 `/home/Lim` | 88 | 新结果盘；另有约 21.49 GiB 已分配 BRCA 下载量待完成 |
| 202 | `/dev/sdb1`，`/new_data` | 69 | 复制 34.935 GiB 的现有 BRCA PT/配套文件，至少保留 24 GiB |

以上为四个独立文件系统，不能把不同挂载路径重复计为额外磁盘。`tmpfs` 不是持久化磁盘。
202 `lsblk` 显示 sdb 总容量约 3.6T、sdb1 约 2T；尾部容量需另行核实/授权扩容，未计为当前可写空间。

## 结果存储

- 204 原物理结果完整保留：`/home/Lim/MRePath_runs/author_patient_disjoint_20260914`，约 6.5 GiB。
- 已复制至 202：`/home/Lim/MRePath_runs/host204_remote_storage_20260914/author_patient_disjoint_20260914`。
- 复制后 `rsync -anc --itemize-changes` 退出 0，无差异（检查发生在任何恢复目录变更之前）。
- 204 用私有 SSHFS 挂载访问：`/home/Lim/MRePath_remote202_results`。
- 项目原入口 `results/results_author_patient_disjoint_20260914` 改指新挂载下结果；
  旧入口软链接保存在 `results/results_author_patient_disjoint_20260914_local_before_storage_recovery`。
- SSHFS 仅使用该实验专属远端目录，无 `allow_other`，使用既有 SSH key；仅在项目工具目录
  解包 Ubuntu APT 提供的 sshfs（2.10 兼容构建），未安装/修改系统软件。
- 显式 mount 检查阻止网络挂载消失后落到本地空目录写入；训练和报告服务绑定挂载服务。
- 新结果盘保护为 22 GiB 已分配下载预留 + 32 GiB 安全余量，实际检查的是 202 文件系统。
  不是简单取消磁盘保护。网络重连/磁盘保护中断仍会保留输出。
- 202 自己的新 BRCA 结果放 `/home/Lim/MRePath_runs/host202_storage_recovery_20260914`，
  原项目入口下的 `survpath/brca` 和 `queue_202_recovery` 是指向这里的软链接。

## 剩余 6 折的唯一归属

| 计算主机 | 任务 | 队列 |
|---|---|---|
| 204 | MRePath BLCA fold4、MRePath BRCA fold4、PIBD BRCA fold3/4 | `queue_204_recovery` |
| 202 | SurvPath BRCA fold3/4 | `queue_202_recovery`，BRCA 特征复制完成后启动 |

每张 GPU 同时最多一个本项目任务。204 启动准入空闲显存 12000 MiB，202 SurvPath
启动准入 6000 MiB；根据前一轮约 6.8 GiB/1.1 GiB 的实际模型占用分别保留余量，
不是显存硬限制。连续两次准入、启动前复查仍在；空闲不足则等待，不停止其他进程。

截至恢复前，完整结果为 24/30 折；不重跑这些已核验折。中断的是 MRePath BLCA fold4、
MRePath BRCA fold4、PIBD BRCA fold3、SurvPath BRCA fold3；另两折从未启动。
原训练没有保存完整 optimizer/scheduler/RNG 续训状态，因此中断折从 seed1 重新完整跑，
不能把仅加载 best 权重称为无损断点续训。新结果副本中，三个 204 重跑折的旧 training 和 invocation
改名保留为 `*_interrupted_20260914_2109`；SurvPath 旧中断目录保留，202 使用独立目录从头跑。

SurvPath BRCA 的 fold0–2 在 204、fold3–4 在 202。报告器按不重复的折合并，
协议冲突或同一折重复归属会报错；只在五折全部核验后计算 Mean ± population SD。
报告新增队列停止原因及 202 恢复等待状态，避免空 GPU 表被误解为已经全部完成。

## 服务与验证

- 204 挂载：`mrepath-results-sshfs-202-20260914.service`。
- 204 恢复训练：`mrepath-clean-baselines-204-storage-recovery-20260914.service`。
- BRCA 复制：`mrepath-brca-recovery-feature-mirror-20260914.service`。
- 复制验收/202 自动启动：`mrepath-brca-recovery-after-mirror-20260914.service`。
- 202 恢复训练（复制后创建）：`mrepath-clean-baselines-202-storage-recovery-20260914.service`。
- 报告：`mrepath-clean-baselines-report-storage-recovery-20260914.service`。
- BRCA 复制清单：`configs/brca_recovery_transfer_20260914.{txt,json}`，926 个 PT + 3 份配套 CSV，合计 929 文件，约 34.935 GiB。
  七份调度/报告依赖单独同步并保留被替换文件，不与大特征传输期间的源代码变化混在一起。
  仅复制已存在特征，不重新编码。标准 rsync 传输校验、断点保留、被覆盖依赖备份均启用；
  启动前检查所有文件存在性/字节数，队列再验证输入、版本及划分。
- 57 项回归测试通过；额外真实远端存储测试通过（JSON 原子替换、PyTorch checkpoint 往返、排他锁）。
- 实际运行/等待/失败以新入口的 `LIVE_RESULTS.md`、两机 `pipeline_status.json` 和
  `host202_brca_recovery_bootstrap.json` 为准，不把服务创建当作完成训练。

本次没有恢复因空间保护已停止的 GDC 下载服务；实验恢复不等于原始 WSI 全量下载完成。
