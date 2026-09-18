# 2026-09-16 至 19 日无人值守实验运行说明

## 当前队列

本轮共 22 个“模型 × 数据集”任务，每项内部顺序完成五折，共 110 折：

- LD-CVAE、DIMAF、SlotSPE：五个数据集，共 15 项；
- Bernoulli Views + KAN M3（`BK_I03_mask2spline_hyperkan`）：BLCA、HNSC，共 2 项；
- AES `p=0.8,T=0.001`：五个数据集，共 5 项。

所有模型训练只读现有 ResNet50-1024D 特征。AES 写入单独缓存目录，不覆盖固定 k
缓存或源图。

## 持久服务与恢复策略

- `mrepath-requested-six-gpu-20260916.service`：每 20 秒检查 204 的四张卡和 202 的
  两张卡。空闲显存至少 18,000 MiB 才启动；每张卡最多一个本轮任务。
- `mrepath-aes-cache-20260916.service`：CPU 构建五个 AES 缓存，逐 WSI 原子落盘并可续跑。
  204 同时只构建一个队列、202 构建 HNSC；构建进程使用 idle I/O 优先级及 nice 10，
  优先让 GPU 训练读取特征。
- `mrepath-requested-health-20260916.service`：每 60 秒检查两个控制器、四个物理文件系统、
  六张 GPU、任务心跳、重试和终态失败。
- 三个服务都已 enable；`Linger=yes`，退出登录后仍继续运行。控制器异常退出由 systemd
  在 60 秒后重启。
- 单任务失败不会阻塞其他任务。失败任务最多尝试 12 次，退避从 60 秒开始，最长 6 小时；
  完整折由 checkpoint、predictions 和 metric 验收后跳过。
- 每个训练 wrapper 每 30 秒写心跳。进程仍存活但连续 8 小时没有日志进展时，watchdog
  只终止该任务的进程组，让调度器重试，不碰其他用户进程。
- 控制器重启后同时扫描 `nvidia-smi` 和两机 `/proc`，因此 DIMAF 的 CPU prototype 阶段
  也被视为占用对应任务槽，不会在同一卡重复派发。

## 全盘容量策略

2026-09-16 22:22 的全部物理数据文件系统盘点：

| 主机 | 文件系统 | 可用空间 | 本轮角色 |
|---|---|---:|---|
| 204 | `/` | 约 24.7 GiB | 不放实验大文件，仅监控 |
| 204 | `/xmlg` | 约 308.5 GiB | 本地结果和四个 AES 缓存 |
| 202 | `/` | 约 83.1 GiB | 远端结果和 HNSC AES 缓存 |
| 202 | `/new_data` | 约 34.0 GiB | 已有源数据，只读 |

监控覆盖两台机器全部上述物理数据盘，而非只检查项目目录。由于 204 系统盘和 202
`/new_data` 已接近满盘，不把新大文件写入这两处；这不是忽略它们，而是避免系统盘或源数据盘
被写满。训练新任务要求目标盘至少剩 60 GiB；AES 要求 204 `/xmlg` 至少 80 GiB、202
系统盘至少 60 GiB，并在每张 WSI 前复查。低于门槛时保留已有产物并等待，不删除缓存。
20 GiB 是全盘 critical 告警线。

当前缓存和 checkpoint 增长外推约 40–60 GiB，低于两个实际写盘文件系统的安全余量。
如果其他用户继续大量占盘，门槛会先阻止新任务和 AES 新 WSI 写入。

## 启动前验证

- 三个外部模型 × 五数据集 × 五折的 75 个输入组合全部通过：训练/验证非空、无患者交叠、
  RNA 和 pathway 维度有效。
- 五数据集实际入组的 2,402 张 slide 特征逐张只读检查：缺失 0、空张量 0、维度异常 0。
- 202 HNSC 的 415 个图容器逐个可加载，维度全部为 1024。
- 外部模型、AES 和缓存 I/O：40 tests + 15 subtests 通过。
- 重启后的真实运行已观察到 M3 batch/epoch、SlotSPE epoch，以及 AES 缓存持续增长。

SlotSPE 日志开头保留了修复前 `num_workers=2` 的历史 traceback；当前 invocation 强制
`num_workers=0`，已有新的正常 epoch 输出。判断当前失败必须看调度状态、心跳和日志尾部，
不能只搜索旧 traceback。

## 返回后查看

- GPU/任务主状态：`results/requested_full_20260916/scheduler/pipeline_status.json`
- AES 状态：`results/requested_full_20260916/scheduler/cache_pipeline_status.json`
- 综合健康状态：`results/requested_full_20260916/scheduler/health_status.json`
- 健康状态变化：`results/requested_full_20260916/scheduler/health_events.jsonl`
- 调度事件和重试：`events.jsonl`、`retry_state.json`、`cache_retry_state.json`

不要另启同一批任务；三个 systemd 服务会自行续跑和补卡。
