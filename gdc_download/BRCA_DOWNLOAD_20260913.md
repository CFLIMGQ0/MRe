# BRCA 原始诊断切片分盘下载

启动时间：2026-09-13 03:47:49（Asia/Shanghai）。已确认三个后台任务运行，三个目录均开始写入实际数据。

## 范围与网络

- 原清单：`manifests/tcga_brca_fixed_folds_dx.tsv`，1,133 个原始 SVS，1,158,795,315,120 B = 1,079.21 GiB。
- 仅包括项目固定五折病例对应的 GDC 诊断切片，并非整个 TCGA-BRCA 的全部文件。
- 分片为互斥的文件集合，合计 1,133 个 UUID，无重复、无缺失；原始清单未改动。
- 用户确认后使用 202 系统盘的一部分空间；不使用 204 系统盘，不删除任何已有缓存或其他队列数据。
- 两台主机均清除 HTTP/HTTPS/ALL_PROXY，设置 NO_PROXY=*。启动时 GDC API 直连 HTTP 200，目标 IP 路由经 ens110f0 / 172.16.170.1，不经过 tailscale0。
- 保留原始 SVS 与 UUID 目录结构，使用 GDC 默认 MD5 校验和断点文件。

## 分配与空间保护

| 分片 | 文件数 | 下载量 GiB | 下载后预计剩余 GiB | 启动预留 GiB | 运行中停止阈值 GiB |
|---|---:|---:|---:|---:|---:|
| 204 数据盘 | 414 | 435.64 | 64.61 | 64 | 60 |
| 202 数据盘 | 368 | 336.20 | 64.62 | 64 | 60 |
| 202 系统盘 | 351 | 307.38 | 100.64 | 100 | 96 |

预计剩余空间按启动前快照计算，不包含其他作业随后产生的数据。每 15 秒检查可用空间；低于停止阈值时终止该分片下载并保留 partial 文件，不自动删除数据或重新启动。当前为分盘专用阈值，不沿用旧整队列 runner 的 80 GiB 默认值。

## 位置与后台任务

| 分片 | 原始数据目录 | systemd user unit |
|---|---|---|
| 204 数据盘 | `/xmlg/Lim/MRePath_GDC/raw_svs/tcga_brca/` | `mrepath-gdc-brca-204-data-20260913.service` |
| 202 数据盘 | `/new_data/Lim/MRePath_GDC/raw_svs/tcga_brca/` | `mrepath-gdc-brca-202-data-20260913.service` |
| 202 系统盘 | `/home/Lim/MRePath_GDC_BRCA/raw_svs/tcga_brca/` | `mrepath-gdc-brca-202-system-20260913.service` |

日志分别为：

- 204：`/xmlg/Lim/MRePath_GDC/brca_204_data_20260913.stdout.log`
- 202 数据盘：`/new_data/Lim/MRePath_GDC/brca_202_data_20260913.stdout.log`
- 202 系统盘：`/home/Lim/MRePath_GDC_BRCA/brca_202_system_20260913.stdout.log`

204 项目中的三份分片清单：`gdc_download/manifests/brca_split_20260913/{host204_data,host202_data,host202_system}/tcga_brca_fixed_folds_dx.tsv`。

202 使用的清单：`/new_data/Lim/MRePath_GDC/manifests/brca_split_20260913/host202_data.tsv` 与 `host202_system.tsv`。

下载脚本：204 `scripts/run_gdc_manifest_guarded.sh`；202 `/new_data/Lim/MRePath_GDC/bin/run_gdc_manifest_guarded_20260913.sh`。启动前已验证 Bash 语法和两端 SHA256 一致。每个任务使用 2 个 GDC 下载进程；两台主机均已启用 user linger，SSH 断开后继续运行。

注意：脚本重启时会保守地按未完成文件的完整大小检查空间；若已有较大的 partial 文件导致启动检查拒绝，不要删除 partial，应先重新核算空间再续传。

## 其他队列复查

同日按 manifest 检查正式文件大小：BLCA 455/455、COREAD 301/301、HNSC 415/415、STAD 341/341，均匹配。此检查不重复进行全量 MD5 运算。

## 状态查询与暂停

204：

```bash
systemctl --user status mrepath-gdc-brca-204-data-20260913.service
tail -n 10 /xmlg/Lim/MRePath_GDC/brca_204_data_20260913.stdout.log
# 仅在用户要求暂停时执行：
systemctl --user stop mrepath-gdc-brca-204-data-20260913.service
```

202 上查询或暂停相应两个 user unit。暂停会保留下载文件和断点；恢复前先检查实时磁盘空间，不要把完整 BRCA 清单重新投向任意一个分片目录，否则会重复下载其他分片。
