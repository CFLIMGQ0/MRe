# Adaptive Edge Selection（AES）第一版

状态：独立实现与验证，不自动启动正式实验；正式实验的 p、T 尚未指定。

## 1. 严格边界

只将 Hypergraph Construction 中的 fixed-k 邻居选择换成 Top-p。
两条分支共用且仅有两个算法超参数：`p`、`T`。没有 `k_min`、`k_max`、
候选 Top-k、分支独立温度、可学习门控、新权重或新损失。

原有 Fixed-k 路径完整保留。未修改病理编码器、基因分支、Sheaf builder、
Sheaf diffusion、P_h 后处理、Dynamic Weighting、w_p/w_g、IFA、预测头、
训练入口、原始划分、优化器、训练参数或损失。`model.yaml` 也保持原样。
当前正在运行的 HNSC/BLCA Bernoulli Views + KAN 实验不切换为 AES。

## 2. 精确算法定义

输入来自单张 WSI 的已有 graph 文件：

- `centroid`：`[N, 2]` 空间坐标，沿用缓存中的原始坐标单位。
- `x`：`[N, D]` 固定图像特征，当前 ResNet50 为 D=1024。
- 不读取旧的 `edge_index`、`edge_latent` 来限制候选集合。

对于中心 i，仅在同一张 WSI 的 j≠i 候选上计算：

```text
S_T(i,j) = -EuclideanDistance(coords_i, coords_j)
S_F(i,j) = cosine(x_i, x_j)
P_T(i,:) = Softmax(S_T(i,:) / T)
P_F(i,:) = Softmax(S_F(i,:) / T)
```

两分支分别将概率降序排列，选取累计概率首次达到或超过 p 的最短前缀；
包含使累计概率跨过阈值的那个邻居。选完后加上中心 i，得到 E_T、E_F。

- `0 < p <= 1`，`T > 0`，必须有限；无默认实验值。
- 中心不参加 Softmax 分母，最后在自己的超边中加入一次。
- 同概率按原 patch 索引升序打破并列，不添加随机采样。
- p=1 时选择所有其他 patch，包括数值计算中指数下溢为零的候选。
- 零特征向量的余弦相似度约定为 0；非有限输入直接报错。
- N=1 时构造仅含中心的超边；既有采样加载器仍按原规则丢弃单节点超边。
- 概率只用于选连接，**不**作为额外超边权重传给 Sheaf。
- 计算余弦时的向量 L2 归一化只是余弦定义，不是额外的分数归一化机制。

T 虽然共用，但两路原始分数的数值尺度不同：坐标可能相差数百像素，余弦值
位于 [-1,1]。首版没有擅自引入距离尺度标准化。共享 T 不保证两路度数相近；
温度下降通常使分布集中，但完全相同的分数不会因为降低 T 而打破并列。

## 3. 与原模型对接及采样语义

每条分支输出原缓存格式的 `incidence: [2, M]` 和 `centers`。关联矩阵只含
节点索引和超边索引，仍由原模型合并两分支并调用原始 Sheaf。另存
`neighbor_counts` 仅用于诊断，不参与模型计算。

采用已讨论的最小改动路线：**每张完整 WSI 离线构建 AES 超图，再复用原
训练加载器的患者合并、patch 采样和诱导子图操作**。不跨 WSI 构造新超边。

因此 Top-p 概率保证成立于完整 WSI 的候选集合，不能宣称采样后的剩余超边
仍满足累计 p。若未来需要在每次采样后的 patch 集合或可训练的 256 维投影
特征上计算 AES，那是另一种实现，应另行明确，不与本版结果混为一谈。

原始图文件继续作为 ResNet 特征/坐标来源，其 fixed-k 连边在 AES 生成时
被忽略。无需重提 ResNet，也无需复制一套完整特征文件。

## 4. 文件与切换方式

- `utils/adaptive_edge_selection.py`：算法、原格式缓存记录及来源校验。
- `scripts/build_adaptive_hypergraph_cache.py`：独立 CPU 缓存构建入口。
- `tests/test_adaptive_edge_selection.py`：选择、缓存及原模型接口回归测试。

构建脚本只增加 `--p`、`--T` 两个算法参数，另有必需的输入/输出目录参数。
先等待该数据集原始 `graph_files` 完整、稳定，再构建完整 AES 缓存。

以下模板需先设置经确认的 `AES_P`、`AES_T`，没有提供默认数值：

```bash
LD_LIBRARY_PATH=/xmlg/Lim/conda/envs/myenv/lib \
.venvs/mrepath_20260913/bin/python scripts/build_adaptive_hypergraph_cache.py \
  --graph-dir data/tcga_blca/clam_20x_resnet50_paper_k9/graph_files \
  --cache-dir "data/tcga_blca/clam_20x_resnet50_paper_k9/hypergraph_cache_aes_p${AES_P:?请先设置确认的p}_T${AES_T:?请先设置确认的T}" \
  --p "$AES_P" --T "$AES_T"
```

复用原始 MRePath 的训练命令，仅将已有的
`--mrepath_hypergraph_cache_dir` 指向完成的 AES 缓存，并使用独立实验结果目录。
不需要新增模型构造参数，不需要编辑 Sheaf/IFA/训练代码。

退回 fixed-k 时，将该参数指回原来的 `hypergraph_cache`。公平对比须让两组
使用相同的原始模型配置、缓存加载路线、患者/划分、采样、seed、epoch 和评估。
不要把只改 AES 的原始 MRePath 对比与 Bernoulli Views + KAN 组合实验混写。

## 5. 缓存隔离及执行保护

- 禁止输出到原始 graph 目录、其父子目录或标准 `hypergraph_cache` 目录。
- 不能把已有的无 AES 标记目录当成 AES 输出，也不覆盖旧的已完成缓存。
- 同一输出目录用文件锁防止两个构建进程同时写入。
- `aes_manifest.json` 记录共享 p/T、分数定义、候选范围、实现版本和源目录。
- 每张缓存保存来源文件的大小、mtime 和 SHA256；构建/续跑时校验内容。
  修改 p/T 或输入后，使用新的输出目录；不静默覆盖旧缓存。
- 缓存兼容原 `load_cache_record`。原加载器的来源检查仍使用原有大小/mtime，
  所以正式训练期间输入和缓存应保持只读；新建缓存前可重新运行构建脚本校验 SHA256。
- float64 CPU 分块计算只改变执行内存布局，不减少候选、不近似 Top-p。
  精确计算需要约 O(N²D + N²logN) 时间；稠密输出本身仍可能是 O(N²)。
- 分支关联索引预估占用超过当时主机可用内存一半时直接中止并报错，**不截断
  邻居、不调整 p/T**。这是共享主机的资源保护，不是额外算法超参数。
- CPU 构建最多用 4 个 Torch 线程，不使用 CUDA；大数据正式构建前仍应检查资源。

## 6. 验证与限制

CPU 测试覆盖独立参考实现、阈值跨越、温度作用、自身排除、概率并列、无隐藏
Top-k 上限、p=1、极小 T、零向量、小样本边界、分块一致性、原数据不变、缓存
复用/隔离、粗粒度时间戳下的源内容变化、多 WSI 不交叉连边、原采样加载器，
以及原 Sheaf + Dynamic Weighting + IFA + NLL 的前向/反向和切回 fixed-k。

CPU 集成测试只将**测试实例**内 Sheaf 的张量分配设备设为 CPU；原类和 forward
没有修改。该测试不是 CUDA 性能验证，也不产生 C-index。

联调观察：当前环境的 CPU 路径中，fixed-k 和 AES 的 `sheaf_builder` 参数均
没有收到梯度，而 Sheaf diffusion 层、病理投影、动态加权、IFA 和预测头有
有限梯度。独立 CPU 最小例子确认：当前 torch_sparse 的稀疏矩阵乘内部使用
`C._values()`，其 `spspmm` 返回值 `requires_grad=False`，而原生稀疏结果的
`C.values()` 保留梯度。证据为 `existing_cpu_sparse_gradient.json`。
本次按“不得修改 Sheaf”的约束保留，不将此现象归因于 AES，
也不声称已经验证所有 Sheaf 参数可训练。CUDA 侧该现象尚未验证。

验证日志放在 `results/aes_implementation_verification/`。测试中出现的 p/T
仅为测试数据，不是正式实验选值；新增模块不代表其有效性或新颖性已获证明。

2026-09-13 验证结果：204/202 各 26 项 AES 测试通过，204 原模块 15 项回归
测试通过。四个新增代码/测试/说明文件同步至 202 专用项目；未改其现有模型。
204 受保护的 15 个原文件 SHA256 与实现前一致，校验清单为
`results/aes_implementation_verification/original_source_files.sha256`。

单张真实 BLCA WSI（1149 patches）通过 AES 生成、原加载器读取及断点复用。
测试值 p=0.8、T=0.2 下：Topology 平均 3.81 个邻居、Feature 平均 861.59 个
邻居；这表明该测试温度下 Feature 超边仍很稠密，不是推荐参数，也不是模型
效果验证。完整原始特征及 fixed-k 文件均未修改。
