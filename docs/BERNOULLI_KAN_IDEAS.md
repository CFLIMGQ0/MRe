# Bernoulli Views + KAN 十方法实现说明

十个方法作为 PC-CMKA 基因组编码器内部的可选 refinement 层实现。公共输入仍是六个功能组的原始组学张量，公共输出仍为 `[batch, 6, 256]`，因此没有改变 MRePath、融合层或生存头的调用接口。

## 配置名称

| 实验 | `bernoulli_kan.mode` | 实现要点 |
|---|---|---|
| `BK_I01_bv_jetkan` | `bv_jetkan` | 共享KAN输出一致性和随机投影Jacobian一致性 |
| `BK_I02_uvr_kan` | `uvr_kan` | 双视图分歧门控grid 3/grid 7两支KAN |
| `BK_I03_mask2spline_hyperkan` | `mask2spline_hyperkan` | 五维mask摘要生成pathway mixer低秩样条系数偏移 |
| `BK_I04_kan2bern_controller` | `kan2bern_controller` | 下游生存梯度EMA反向更新safe/hard逐边保留率 |
| `BK_I05_bml_kan` | `bml_kan` | 编码mask交集/并集并学习软估值残差 |
| `BK_I06_bernoulli_jensen_debiased` | `bernoulli_jensen_debiased` | 沿双视图方向估计KAN二阶曲率并校正期望偏差 |
| `BK_I07_overlap_calibrated_jacobian` | `overlap_calibrated_jacobian` | Jaccard重合率校准投影Jacobian一致性 |
| `BK_I08_bernoulli_barycentric_grid` | `bernoulli_barycentric_grid` | base/双视图训练分布的分位重心更新共享KAN knots |
| `BK_I09_stable_cross_pathway_gate` | `stable_cross_pathway_gate` | 视图贡献方差EMA门控6×6跨通路KAN边 |
| `BK_I10_sensitivity_correlated_views` | `sensitivity_correlated_views` | KAN反馈敏感度控制具有正确边际的相关Bernoulli pair |

## 关键实现位置

- 方法主体：`models/layers/pc_cmka/bernoulli_kan.py`；
- 双视图和反馈采样：`models/layers/pc_cmka/augmentation.py`；
- PC-CMKA视图token暴露及损失汇总：`models/layers/pc_cmka/encoder.py`；
- 可检查KAN边贡献、低秩系数adapter、动态grid：`models/layers/kan.py`；
- 实验参数：`configs/pc_cmka_ddkac_word.json`；
- 顺序断点续跑：`scripts/run_bernoulli_kan_ideas.sh`。

## 实验协议

正式实验固定：seed 1、官方五折、每折30 epochs、batch size 1、4096 patches、ResNet50特征、SHGNN病理端、DSS、训练折生存分箱和best-validation-C-index checkpoint。COREAD完成后顺序运行STAD；已经有完整fold产物时自动跳过。

快速门禁命令：

```bash
bash scripts/run_bernoulli_kan_ideas.sh smoke
```

正式双数据集五折命令：

```bash
bash scripts/run_bernoulli_kan_ideas.sh formal
```

正式结果目录为 `results/results_bernoulli_kan_5fold/{coadread,stad}/<experiment>`。

## 计算近似说明

完整KAN Jacobian代价过高，因此Idea 1/7使用固定Rademacher输出投影后的Jacobian，是Frobenius差异的Hutchinson型估计。Idea 6使用双视图方向上的有限差分二阶导数。Idea 4/10通过保持前向值等于完整图预测的straight-through bridge，把真实生存梯度送到随机边权；梯度敏感度只用于下一次采样并停止梯度，避免控制器直接形成标签捷径。
