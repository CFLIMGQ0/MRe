# LD-CVAE / DIMAF / SlotSPE 官方代码接入记录

日期：2026-09-13。任务：以官方仓库为准复现代码；不是重写简化模型。

## 1. 当前结论

三个仓库已固定版本并下载到 204、202。两台主机上三者均已通过 **CPU 合成输入的官方训练函数测试**，包括反向传播、有限梯度、参数更新、权重保存/加载。**这不代表真实 TCGA 五折训练完成，也没有新增 C-index 性能结果。**

| 模型 | 官方来源 / 固定版本 | 本地目录 | 204 / 202 实测 |
|---|---|---|---|
| LD-CVAE | [RobustMultiModel](https://github.com/JJ-ZHOU-Code/RobustMultiModel)，`df8c50d94179a63edf3d9017641295a268ce9148` | `third_party/LD_CVAE_20260913` | MCAT、SurvPath 两个 backbone 均通过 warmup / jointly；各 6 次真实 optimizer.step；完整和缺失模态推理通过 |
| DIMAF | [DIMAF](https://github.com/Trustworthy-AI-UU-NKI/DIMAF)，`286dae63fcdc65de38224981cf345845d25c57be` | `third_party/DIMAF_20260913` | PANTHER → DIMAF → 官方 Cox + distance-correlation 损失 → 参数更新通过 |
| SlotSPE | [SlotSPE](https://github.com/zylvemvet/SlotSPE)，`02051a2083add7b427727e0200e4263516903561` | `third_party/SlotSPE_20260913` | 官方 331 个 combine signature 输入、8+8 slots、10 次 slot iteration；主损失和辅助损失训练通过；完整和缺失模态推理通过 |

可复核的测试输出：

- `results/repository_baselines_20260913/smoke_03/summary.json`
- 202 独立复测：`results/repository_baselines_20260913/smoke_202_01/summary.json`（已取回 204 同路径归档）。
- 同目录下 `ld_cvae.json`、`dimaf.json`、`slotspe.json` 与各自 `.log`。
- `smoke_01`、`smoke_02` 保留了环境缺项与 CUDA 写死问题的失败记录，不覆盖历史。
- 官方 CLI 的 `--help` 均通过：LD-CVAE `main.py`、DIMAF `main_survival.py` / `main_prototype.py`、SlotSPE `survival.py`。
- `tests/test_repository_baseline_launch.py`：204、202 各通过相同的 8 项启动保护测试。
- LD-CVAE 还用真实随仓库基因数据/metadata 验证了数据工厂和第 0 折归一化：BLCA 373 名患者（298/75），BRCA 957 名患者（765/192）；仅验证读取和处理，不包含图像特征或正式训练。

## 2. 原代码改动边界

### LD-CVAE：仅设备放置兼容，两份文件

- `models/model_ldvae.py`：三个高斯 prior 不再直接调用 `.cuda()`，改为放到输入或模型所在 device。prior 的形状、数值、float32 dtype、PoE 计算不变。
- `models/model_transformer.py`：两处 query token 的 `.cuda()` 改为 `.to(features.device)`。不改变 VIB-Trans 的计算。
- 当前 diff：9 行新增、5 行删除。完整 diff 写入 smoke JSON 和启动清单。
- 条件生成器、VIB-Trans、功能组后验、重建、分布对齐、KL 项、warmup / jointly 分支、最终预测头和训练损失均保留。
- **没有把原仓库的整套训练器改成 CPU 训练器**：原始完整训练入口和验证器仍有 CUDA 调用。CPU 测试调用原训练 epoch 函数及模型推理；正式完整流程仍使用 GPU。

### DIMAF、SlotSPE：源码零改动

没有替换模型结构、损失、优化器逻辑、缺失模态生成逻辑和官方划分。

新增代码在项目 `scripts/`，负责环境、测试、路径、启动前检查和 RNA 下载，不插入模型内部。

## 3. 为什么不能直接把现有 ResNet 缓存叫作官方复现

| 项目 | LD-CVAE | DIMAF | SlotSPE |
|---|---|---|---|
| WSI 输入 | 仓库提供编码器名称和维度参数，CLI 维度默认 768；本次启动配方明确选择 CTransPath / 768 | UNI / 1024；256×256、0.5 μm/px；先做训练集原型聚类和 PANTHER | 官方示例使用 UNI / 1024；每袋 4096 patches |
| 进入预测网络前的病理表示 | 原生 patch features | 16 个 prototype，每个为概率 + 1024 维均值，即 `16×1025` | 原生 patch features，由 Slot Attention 处理 |
| 基因输入 | 仓库随附的基因组数据/功能组表 | 原仓库 Xena PANCAN RNA，50 个 hallmark pathways | 官方外链 RNA 表，默认 combine signatures；有效 pathways 由真实 RNA 交集决定 |
| 原生标签 | `survival_months` + `censorship`，不擅自重命名为 DSS | `dss_survival_days` | `survival_months_dss` |

本项目已有的 ResNet50 / ImageNet 缓存不等价于 UNI、CTransPath，也不能因为维度同为 1024 就当作同一编码器。LD 仓库参数提示的 `RN50-B` 同样不能未经确认就等同于我们的 ResNet50。

若之后要做“同一 ResNet 输入、同一 DSS/划分”的统一口径对照，应单列为另一种实验协议；不能把它与官方原生协议结果混在一起。这次没有擅自开展该替代实验。

## 4. 原仓库划分覆盖与我们的五个队列

| 模型 | 随仓库提供划分的数据集 | 与本项目五个数据集的交集 |
|---|---|---|
| LD-CVAE | BLCA、BRCA、GBMLGG、LUAD、UCEC | BLCA、BRCA |
| DIMAF | BLCA、BRCA、KIRC、LUAD | BLCA、BRCA |
| SlotSPE | BLCA、BRCA、COADREAD、HNSC、KIRC、LUAD、LUSC、SKCM、STAD、UCEC | 五个均有 |

启动器对没有随仓库提供的 cohort 报出明确阻塞，不擅自新建患者划分。不重做已经在跑的 MRePath / PIBD / SurvPath 实验。

LD-CVAE 原 loader 本身包含固定的异常切片排除列表。启动检查从该源码读取并复用原列表，不自行增加排除项；BLCA、BRCA 实际所需切片分别是 437、1021 张。

## 5. 训练设置与缺失模态口径

启动器调用官方 entrypoint，不重新实现训练循环，也不自动覆盖其训练参数。

| 设置 | LD-CVAE | DIMAF | SlotSPE |
|---|---|---|---|
| seed 默认值 | 2024 | 1 | 3；官方示例另外跑 2、1 |
| epochs | 20，warmup 5 | 30 | 30 |
| batch size | 1，gc=1 | 64 | 32 |
| learning rate | 2e-4 | 1e-4 | 5e-4 |
| 主/辅助损失 | 原生 survival NLL + 重建 + VIB survival + 对齐 + 退火 KL | Cox + 7×distance correlation | 原生 survival NLL + slot decoder NLL + 0.01×重建项 |

重要口径：

- LD-CVAE CLI 的 `missing_rate` 默认 **1.0**，即测试时基因全部缺失。我们的启动器要求区分 `--evaluation full` / `missing`，分别映射到原生 `--missing_rate 0.0` / `1.0`。
- SlotSPE CLI 默认完整模态，但官方示例 `scripts/SlotSPE.sh` 带 `--omic_missing`。启动器 `full` 不传该标志，`missing` 才传。
- DIMAF 原入口没有对应的缺失模态实验开关，启动器拒绝虚构该设置。
- SlotSPE 默认 Adam 实现没有使用 `args.reg`，这是原代码行为，本次没有偷偷增加 weight decay。
- 不把原始输出 CSV 的汇总行直接视作已核验的性能；正式训练结束后仍需核验每折病例级预测并重新算均值/标准差。

## 6. 已准备与仍缺的数据

### DIMAF 原生 RNA 已补齐本项目相关两个 cohort

通过官方 `src/data/README.md` 的 Xena URL **直连下载**，执行未改动的 `preprocess_TCGA_rna.py`。同时保留 `.gz`、解压源文件、预处理 CSV；没有删除旧缓存。

| cohort | 压缩源大小 | 官方划分所需患者 | RNA 匹配 | RNA 基因列 |
|---|---:|---:|---:|---:|
| BLCA | 30,642,178 bytes | 359 | 359，0 缺失、0 重复 | 20,530 |
| BRCA | 83,389,754 bytes | 868 | 868，0 缺失、0 重复 | 20,530 |

文件位于 `third_party/DIMAF_20260913/src/data/data_files/tcga_<cohort>/rna/`。`preparation_audit.json` 包含源 URL、原始与处理文件 SHA256、处理命令和患者集合检查。

### 正式训练尚缺

- LD-CVAE：对应官方患者/切片集合的、具有来源证明的 CTransPath patch 特征。本次 768 维配方不能直接喂现有 ResNet 1024 维特征。
- DIMAF：UNI patch 特征、每折仅由训练集生成的 16 个病理原型。当前环境安装的是 **FAISS CPU** 供导入和兼容测试；官方 `--mode faiss` 的 GPU 聚类还需要可用的 GPU FAISS 环境，启动器会检查并拒绝 CPU 包冒充 GPU 聚类。
- SlotSPE：UNI patch 特征、作者的 `raw_rna_data_inter/<cohort>_rna_inter.csv`。官方 [Google Drive 链接](https://drive.google.com/drive/folders/1RxCjSZYTWhJRnbYWAGySyvZk2RUKYb1t) 在 204/202 直连尝试均超时；没有切换 VPN，也没有用现有基因表或零值伪装它。
- 未发现本项目中可确认的 UNI 权重/特征。已询问用户授权权重或已有特征路径；不要索取或记录账号/token。

SlotSPE 原始 loader 在找不到切片特征时会补零。源码保持不变，但项目启动器会先检查全部必需切片文件，缺文件就阻止启动，不让这种情况产生“正式复现结果”。

## 7. 使用方式

204 兼容运行环境：`.venvs/repository_baselines_20260913/bin/python`。

202 环境位于 `/new_data/Lim/MRePath_experiments/Project1/.venvs/repository_baselines_20260913/bin/python`，运行时使用 `LD_LIBRARY_PATH=/home/Lim/conda/envs/myenv/lib`。202 的依赖改由内网同步 204 缓存的 wheel 后离线安装，没有改动旧环境，也没有使用 VPN。wheel 缓存在 `results/repository_baselines_20260913/wheelhouse/`，新建环境时可传 `--wheelhouse`。

这是 **Python 3.12 / Torch 2.12.1+cu126 的实测兼容环境**，不是原论文逐版本环境。LD 原 requirements 含两个互相矛盾的 NumPy 精确版本，不能直接逐行照装。新环境只读借用现有 Torch 等包，在新 venv 中覆盖 NumPy 1.26.4、scikit-survival 0.24.1 等；**原实验环境没有被修改**。

共享的无关图像编解码包仍可能声明 NumPy 2 依赖，因此这个环境只用于已提取特征的模型测试/训练，不能宣称全量 `pip check` 无冲突，也不要用它提取原始 WSI 特征。

```bash
cd /xmlg/Lim/Project1
export LD_LIBRARY_PATH=/xmlg/Lim/conda/envs/myenv/lib
PY_BASELINE=.venvs/repository_baselines_20260913/bin/python

# 新测试目录，不能使用已有 smoke_03 覆盖测试记录
$PY_BASELINE scripts/smoke_repository_baselines.py --output results/repository_baselines_20260913/smoke_next

# 只检查，不启动训练；缺数据时退出码 2 是预期保护
$PY_BASELINE scripts/run_repository_baseline.py --model slotspe --cohort brca
$PY_BASELINE scripts/run_repository_baseline.py --model dimaf --cohort blca
$PY_BASELINE scripts/run_repository_baseline.py --model ld_cvae --cohort brca --evaluation full
```

正式特征目录准备好后，提供一个真实来源清单，例如：

```json
{
  "encoder": "UNI",
  "feature_dim": 1024,
  "feature_dir": "/absolute/path/to/real_UNI/pt_files",
  "provenance": "实际权重版本/来源、提取脚本、patch 与倍率设置；这里必须填真实记录"
}
```

```bash
$PY_BASELINE scripts/run_repository_baseline.py \
  --model slotspe --cohort brca \
  --wsi-root /absolute/path/to/real_UNI/pt_files \
  --feature-manifest /absolute/path/to/real_feature_manifest.json \
  --evaluation full --gpu 0 --output /absolute/path/to/NEW_run_directory
```

先检查打印的 `ready`、`blockers` 和官方命令。只有确认就绪才追加 `--execute`。执行时再次检查 GPU，已有 compute PID 或显存使用超过 1 GiB 则拒绝共享；只创建全新输出目录，保存运行命令、源码 diff 和日志。

- LD-CVAE 的 `--wsi-root` 是 **含 pt_files 的父目录**；支持 `--ld-backbone mcat` / `survpath`。
- DIMAF 使用官方固定目录层级；`--data-root` 是 cohort 根目录，特征放 `wsi/extracted_res0_5_patch256_uni/feats_h5/`。`--stage prototypes` 调用官方聚类入口；默认 `train` 调用原训练入口。聚类阶段会写入原生各 fold 的 `prototypes_DIMAF`，已有目录则拒绝覆盖。
- SlotSPE 的 `--wsi-root` 是 **pt 文件所在目录**；`--data-root` 可指向已经按原格式准备好的 metadata 根目录。
- DIMAF `--data_source` 保留尾部 `/`，兼容其原 loader 的相对路径查找；没有改其源码。
- 特征来源清单是操作者声明，启动器检查名称/维度/路径及一个实际特征形状；不声称自动认证全部权重来源或所有张量数值。

## 8. 新增维护入口

- `configs/repository_baselines_20260913.json`：仓库版本、原生协议与改动说明。
- `configs/repository_baselines_overlay_requirements.txt`：实测兼容环境覆盖层。
- `scripts/setup_repository_baselines_env.py`：以指定现有 Python 为基础创建**全新** venv，不升级旧环境。
- `scripts/smoke_repository_baselines.py`：三个仓库进程隔离，避免 `models` / `utils` 包互相污染。
- `scripts/run_repository_baseline.py`：官方命令生成、数据/GPU/输出保护。
- `scripts/prepare_dimaf_native_rna.py`：直连下载原生 RNA、保留源文件、调用原脚本并核验患者。
- `tests/test_repository_baseline_launch.py`：启动保护回归测试。
- `results/repository_baselines_20260913/native_data_preflight_204.json`：三模型 × 五 cohort 的数据缺项清单；`environment_204.json` 记录实测包版本。

当前新三个模型没有被放入正式 GPU 队列。原 MRePath / PIBD / SurvPath 服务和旧结果均保留，既不抢占也不重启它们。
