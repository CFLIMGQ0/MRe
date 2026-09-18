# 202 GPU sharing authorization — 2026-09-14

## 最新追加：每卡两个项目任务

用户随后要求“每张显卡至少分配两个任务”。`60-two-jobs.conf` 现在覆盖下方旧的
baseline 串行安排：202 只跑 PIBD/HNSC，与保持运行的原始 MRePath/HNSC 并行；
SurvPath/HNSC 五折迁至 204。baseline 每卡上限两个项目任务，计入原始模型队列
的存活任务，准入空闲显存阈值改为 10000 MiB。原始 MRePath 控制器未重启，
其已有命令、18000 MiB 准入阈值不变。所有训练配置不变。

仅重启了 active=[] 的 baseline 控制器；新增两折 PIBD 已实际输出 batch loss。
不停止或修改其他用户任务。可用未完成折充足且显存准入通过时自动补位。
部署路径仍为 `/home/Lim/.config/systemd/user/`，恢复时必须同时核对 50 和 60 两层覆盖，
不要因查看旧说明而将正在训练的服务重启或将 SurvPath 重新加回 202。

以下保留首次授权的历史记录，其中“每卡一个”“等待原始五折结束”已被上述规则取代。

用户已在获知 202 GPU 0/1 有 xmlg 训练任务后明确允许：“没事，202主机照样用”。

仅对两个既有 HNSC 队列启用 `--allow-gpu-sharing`：

- `mrepath-original-hnsc-5fold-20260913.service`
- `mrepath-pibd-survpath-202-5fold-20260913.service`

本目录的 `*.service.d/50-gpu-sharing.conf` 已部署至 202 的
`/home/Lim/.config/systemd/user/`，随后 daemon-reload 并重启两个**无 active 训练折**
的等待中调度器。原清单和状态已在各输出目录留副本。没有停止或修改 xmlg 的任务，
204 原调度进程没有重启。

共享模式取消默认“无外部 compute process 且显存使用 ≤1024 MiB”的条件，仍要求
空闲显存 ≥18000 MiB、两次准入及启动前复查，保留磁盘/BRCA 下载预留和队列间预留。
每队列每卡最多一个自己的折。只修改 GPU 准入，不修改模型、超参数、数据、损失或划分。

已确认原始 MRePath/HNSC fold 0 在 GPU 0、fold 1 在 GPU 1 开始训练，两者日志均已
推进超过 260 batches。首次确认训练 PID：2795503、2795508（PID 只表示该确认时点）。
五折之后既有 PIBD/SurvPath 队列接续。共享吞吐会受其他任务影响，不能承诺独占速度。

测试：204 GPU 队列 16 项通过；202 15 项通过、1 项 BLCA 本地数据集成测试显式跳过，
该项在 204 通过。源码默认依然禁止共享；204 没有传入该参数。

实时证据位于 202 项目下：

- `results/results_requested_baselines_5fold_20260913/mrepath/hnsc/pipeline_status.json`
- 同目录 `gpu_dispatch.jsonl` 和 `training_fold_*_gpu*.log`
- `results/results_requested_baselines_5fold_20260913/queue_202/pipeline_status.json`

以这些实时记录为准，不把初次 PID 或本说明当作持续监控状态。
