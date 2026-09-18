# TCGA 固定五折诊断 WSI 下载状态

## 最新状态：2026-09-13

- BRCA 已于北京时间 03:47:49 启动直连下载，1,133 个 SVS，共 1,079.21 GiB。
- 分散在 204 数据盘、202 数据盘和 202 系统盘，三个后台任务均已开始写入数据。
- 分配、日志、服务名称和低空间自动停止规则见 [BRCA_DOWNLOAD_20260913.md](BRCA_DOWNLOAD_20260913.md)。
- 同日复查文件大小：BLCA 455/455、COREAD 301/301、HNSC 415/415、STAD 341/341，均完整。
- 已有特征、图、超图缓存及已下载队列均未删除、未覆盖。

---

以下保留 **2026-09-05 的历史快照**，不代表当前运行状态：

更新时间：2026-09-05 22:24（Asia/Shanghai；已恢复直连下载）

## 当前状态

- 204 与 202 均已恢复下载，并从已有文件和 `.partial` 断点续传。
- 下载脚本会清除 `HTTP_PROXY`、`HTTPS_PROXY` 和 `ALL_PROXY` 等代理变量；
  两台主机均通过 `ens110f0` 和网关 `172.16.170.1` 直连 GDC。
- 恢复时 BLCA 已完成 275/455，HNSC 已完成 414/415；202 会先补齐 HNSC
  最后一个文件，再继续 STAD。

## 下载口径

- 数据来源：GDC 公共 `Slide Image` 文件。
- 只下载项目固定五折病例对应的诊断切片（文件名中的 `DX`），保留 GDC 原始
  SVS 文件及 UUID 目录结构。
- 五个队列的 manifest 位于 `gdc_download/manifests/`，由
  `scripts/prepare_gdc_fixed_fold_dx_manifests.py` 生成。
- 已有 `data/tcga_*` 特征、图和超图缓存不删除、不覆盖。

## 队列与分配

| 队列 | 病例 | DX 文件 | 大小 | 状态/位置 |
|---|---:|---:|---:|---|
| BLCA | 384 | 455 | 664.21 GiB | 直连下载中；204 `/xmlg/Lim/MRePath_GDC/raw_svs/tcga_blca/` |
| COREAD | 297 | 301 | 194.70 GiB | 未开始；204 `/xmlg/Lim/MRePath_GDC/raw_svs/tcga_coadread/` |
| HNSC | 394 | 415 | 377.58 GiB | 正在直连补最后 1 个文件；202 `/new_data/Lim/MRePath_GDC/raw_svs/tcga_hnsc/` |
| STAD | 317 | 341 | 289.38 GiB | HNSC 后续传；202 `/new_data/Lim/MRePath_GDC/raw_svs/tcga_stad/` |
| BRCA | 1062 | 1133 | 1079.21 GiB | manifest 已生成；当前没有单块数据盘可安全容纳，暂未启动 |

## 后台任务

- 204：systemd user unit `mrepath-gdc-resume-204.service`。
- 204 日志：`/xmlg/Lim/MRePath_GDC/download.stdout.log`。
- 202：systemd user unit `mrepath-gdc-resume-202.service`。
- 202 日志：`/new_data/Lim/MRePath_GDC/download.stdout.log`。
- 两端均使用 GDC Client 2.3.0、4 个下载进程、8 MiB chunk、MD5 校验和可续传
  UUID 目录；runner 在开始下一队列前保留至少 80 GiB 可用空间。

## 复查命令

```bash
systemctl --user status mrepath-gdc-download-204.service
tail -f /xmlg/Lim/MRePath_GDC/download.stdout.log

ssh -i /home/Lim/.ssh/id_ed25519_project4_pool Lim@172.16.170.202 \
  'ps -p 292683 -o pid,etime,stat,cmd; tail -f /new_data/Lim/MRePath_GDC/download.stdout.log'
```

下载任务可以安全重启；runner 会按 manifest 中的文件大小跳过已经完整的文件，
GDC Client 会继续 `.partial` 文件。
