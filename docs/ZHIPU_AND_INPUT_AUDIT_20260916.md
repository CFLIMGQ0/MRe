# 智普改动与本轮输入审计（2026-09-16）

## 结论

- 智普没有在 2026-09-16 改写五个队列的原始 ResNet50 `.pt`、`.h5` 或
  `graph_files/*.pt`。204 与 202 上这些目录当天修改文件数均为 0。
- 智普新写入的是独立的 `hypergraph_cache_aes_p0.8_T0.2`、结果空目录和调度日志；
  原始特征目录没有被它覆盖。本轮保留这些失败/部分产物，但不把它们当成有效结果。
- 08:30 那批 LD-CVAE、DIMAF、SlotSPE 均在原生输入预检阶段失败，没有开始正式训练；
  HNSC/BLCA 的 Bernoulli+KAN 10 折也立即失败。AES 只产生 7 个完整的部分缓存和
  3 个 `.tmp`，未形成任一完整队列。
- DIMAF 与 SlotSPE checkout 无 tracked diff。LD-CVAE 有两处早已存在的设备兼容修改：
  把硬编码 `.cuda()` / CUDA prior 改为跟随输入设备；没有修改网络方程、损失或参数量。
  未跟踪的 `__pycache__` 是 Python 导入缓存，不是模型或数据。

## 原始 ResNet50 缓存盘点（204）

| 队列 | PT tensor | HDF5 | graph.x 容器 | 2026-09-16 被改写 |
|---|---:|---:|---:|---:|
| BLCA | 0 | 455 | 455 | 0 |
| BRCA | 929 | 0 | 929 | 0 |
| COREAD | 0 | 0 | 301 | 0 |
| STAD | 0 | 0 | 343 | 0 |
| HNSC 镜像 | 0 | 415 | 0 | 0 |

202 上供调度使用的原始缓存也没有当天修改：BLCA 421 个 HDF5、BRCA 926 个 PT、
HNSC 415 个 HDF5 + 415 个 graph 容器。COREAD/STAD 仅在 204 运行；HNSC 的图模型
仅在 202 运行。

## 本轮三个仓库模型的输入边界

新入口为 `scripts/run_resnet50_repository_model.py`。它导入 pinned checkout 中的原模型类
和原损失，只适配项目当前的患者划分、DSS、RNA 与 ResNet50-1024D 缓存：

- 只读顺序为已有 PT → HDF5 → `graph.x`；不复制、不转码、不覆盖任何缓存。
- 每例多张 WSI 按患者拼接；最多取 4096 个 patch。
- 所有模型使用相同 active 五折和训练折 DSS 分箱；缺少 metadata 或 RNA 的 split 条目
  按项目原 dataset factory 的规则从所有多模态模型共同排除，不用零向量伪造。
- LD-CVAE 使用仓库的六组网络、生成器和 NLL；DIMAF 使用 Hallmark RNA prototypes、
  PANTHER 16 个训练折原型及 Cox+distance-correlation；SlotSPE 使用 combine pathways、
  8+8 slots 和仓库的 NLL/辅助损失。
- 适配器三模型各通过了 1 epoch/64 patches 的真实缓存 smoke；202 的 HNSC 也通过。

因此本轮成绩应写作“官方模型结构/损失 + 统一项目输入的 ResNet50 对照复现”，不能冒充
原论文的 UNI/CTransPath 原生输入成绩。

## AES 处置

智普擅自使用的 `p=0.8,T=0.2` 在真实特征上会产生极稠密超边，未继续使用。
本轮仅用不含标签的邻居规模审计登记第一组运行值 `p=0.8,T=0.001`：不增加候选 Top-k、
最小/最大邻居数或任何第三个模型超参数。新缓存使用独立目录；完整 WSI 缓存验收后，
GPU 调度器才允许相应 AES 五折进入训练。

## 本轮恢复说明

外部模型首次调度暴露了 PyTorch 多进程 DataLoader 的文件描述符传递错误
（`received 0 items of ancdata`）。正式外部模型适配器现固定使用单进程数据读取
（`num_workers=0`）；这只改变数据读取并发度，不改变已有 ResNet50 张量、样本、模型、
损失、优化器或训练轮数。失败日志原样保留，随后以新 invocation/manifest 重跑未完成折。
调度器也已增加本轮既有 GPU 进程识别，保证控制器重启后每张卡仍最多一个实验任务。
