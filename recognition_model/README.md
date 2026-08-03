# 人员异常行为与轨迹确认 MVP

这是一个单视频分析服务：YOLO26 Pose + BoT-SORT 产生人员轨迹，规则检测跌倒、快速移动、滞留、徘徊和疑似激烈互动；通过验收的 R3D-18 模型为每条人员轨迹提供 `normal / violence / fall` 概率。所有告警都是待复核候选，不是对暴力、违法行为或人员身份的事实认定。

## 当前验证状态（2026-07-29）

- NVIDIA GeForce RTX 4060 Laptop GPU，PyTorch `2.7.1+cu128`，CUDA 可用。
- 数据、运行结果、训练产物和晋级模型共用 `10,737,418,240` 字节硬上限；当前四个受管根目录合计 `5,935,660,475` 字节（上限的 55.28%）。
- 三个训练类别各选 30 个独立原视频，共 90 个；`bad_videos.csv` 为 0 条。
- 固定划分为 train 63、val 13、test 14；group/subject/解析后文件路径的所有两两交集为空。
- 人员裁剪版模型 SHA-256 为 `0104fe009a5d0feb6f4aac9efba3ae73e24d7f585f38dd5efe5bd909e70296b0`。其 held-out test macro F1 为 `0.9221`，violence recall 为 `1.0000`，fall recall 为 `1.0000`；`models\best.pth` 已启用。

测试集很小且来源域明显不同，因此这些数字不是部署环境的泛化保证。参见“限制与人工复核”。

## 安装

需要 Python 3.12。基础环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

CUDA 12.8 安装与验证命令：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_cuda.ps1
```

该脚本执行：

```powershell
python -m pip install --upgrade torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu128
python -m pip install -r requirements-training.txt
python scripts\verify_cuda.py
```

## 数据来源、许可与选样

每个保留文件的 resolved URL、字节数和 SHA-256 位于 `D:\datasets\abnormal_behavior\receipts\<source>\source.json`；聚合状态位于 `source-manifest.json`。

- [Real Life Violence Situations (RLVS)](https://www.kaggle.com/datasets/mohamedmustafa/real-life-violence-situations-dataset)：Kaggle 数据卡标注 “Data files © Original Authors”，并要求引用 Soliman 等人的 ICICIS 2019 论文。没有推断额外的开放许可。为避免下载数千个视频，只按 Kaggle 精确文件路径获取 `NonViolence/NV_1..NV_30` 和 `Violence/V_1..V_30`，各 30 条。部分文件扩展名是 `.mp4`，容器实际为 AVI；API smoke test 使用真实容器对应的 `.avi` 上传名和 `video/x-msvideo` MIME。
- [UR Fall Detection Dataset](https://fenix.ur.edu.pl/mkepski/ds/uf.html)：从官方站点直接获取 camera-0 的 30 条 fall 和 40 条 ADL，共 70 条。官方页面声明 CC BY-NC-SA 4.0，必须保留署名并遵守非商业和相同方式共享条件。训练只使用 30 条 fall；ADL 保留为来源与 smoke 候选，不用来改变已确定的平衡训练选择。
- [CUHK Avenue Dataset](https://www.cse.cuhk.edu.hk/~leojia/projects/detectabnormal/dataset.html)：官方 16 个训练视频、21 个测试视频以及官方 ground truth。37 个视频只写入 `manifests\avenue\calibration.csv`，不参与三分类训练或 test 指标。保留 ICCV 2013 数据集引用并按研究用途处理。

下载器在每次写入和 ZIP 解压前检查聚合 10 GiB 上限，并把原目标与同目录临时文件同时存在的峰值计入预算；断链文件可续传。相同长度本身不构成复用依据，只有 receipt/sidecar 中的 SHA-256（以及适用时的 URL/ETag）重新验证成功才复用。重复下载命令会幂等复用四个完整来源；任一来源失败会在 `source-manifest.json` 中显式记录，不会覆盖其他成功来源。Kinetics-400 权重也通过同一个有已知长度和完整 SHA-256 的受限下载器获取。

```powershell
python -m anomaly_training download --datasets rlvs urfall avenue
python -m anomaly_training verify-sources
```

实际验收结果：RLVS receipt 60 文件、UR Fall receipt 70 文件、Avenue receipt 75 文件、Avenue ground-truth receipt 24 文件，全部 size/SHA-256 验证通过。

## 生成与审计 manifests

```powershell
python -m anomaly_training prepare
python -m anomaly_training audit-splits
```

确定性配置为 seed `42`、每类 30 条。实际类别计数：

| split | normal | violence | fall | total |
|---|---:|---:|---:|---:|
| train | 21 | 21 | 21 | 63 |
| val | 5 | 4 | 4 | 13 |
| test | 4 | 5 | 5 | 14 |

`train.csv`、`val.csv`、`test.csv`、`selection.json`、`audit.json` 和 `bad_videos.csv` 位于数据根目录的 `manifests` 下。canonical 输出严格固定为 seed `42`、每类 `30`、批准的 90 个成员以及当前 `63/13/14` 划分；CLI 会在扫描或写入前拒绝对 canonical 目录使用其他 seed/per-class。实验必须显式指定 canonical 目录之外的 `--output-dir`，并永久标记为 `promotable=false`。

`selection.json` 保存每个选中视频的 resolved path、label、source、group、subject、canonical spec 及其摘要。原视频 `group_id`、`subject_id` 和解析后的文件路径都不会跨 split；每个 split 都包含三个类别。审计验证 split 并集与 selection 精确相等、无重复/缺失/额外成员，并在最后原子发布的 `audit.json` 中固定三个 CSV、selection 文件、selection 记录和 canonical spec 的 SHA-256。所有 split、bad-video 和 Avenue calibration CSV 都先完整渲染，再通过受 10 GiB 临时峰值约束的同目录原子替换发布。

## CUDA smoke、训练、续训和评估

两 batch、1 epoch、保留 Kinetics-400 预训练权重的 smoke：

```powershell
python -m anomaly_training train --max-train-batches 2 --max-val-batches 2 --epochs 1 --run-dir training_runs\smoke
nvidia-smi
```

实测训练 PID 使用 CUDA，显存约 2.1–2.5 GiB，无 OOM。新训练写出 `best.pth`、`last.pth`、`training_metrics.json` 和 `training_confusion_matrix.png`；评估单独写出 `evaluation_metrics.json` 和 `evaluation_confusion_matrix.png`，`metrics.json` 仅为指向两类产物的兼容索引，评估不会覆盖训练历史。

项目默认训练日程仍是 5 个 head epoch + 最多 15 个 layer4 epoch：

```powershell
python -m anomaly_training train --run-dir training_runs\r3d18-baseline --batch-size 2 --accumulate-steps 4
```

本次受限基线明确使用 8 epoch（不是把受限运行冒充默认 20 epoch）：

```powershell
$env:CUBLAS_WORKSPACE_CONFIG = ":4096:8"
python -m anomaly_training train --run-dir training_runs\r3d18-baseline --batch-size 2 --accumulate-steps 4 --epochs 8 --head-epochs 3 --patience 3
```

重复同一命令会从 `training_runs\r3d18-baseline\last.pth` 恢复 optimizer、scheduler、scaler、epoch 和 early-stopping 状态。若要明确从头开始，追加 `--no-resume`。

最终候选先按冻结的 validation-only 协议从 seed 11、137、271 中选择，选择结果见 `docs/superpowers/specs/2026-07-29-crop-v3-candidate-result.md`。固定 held-out test 只能在候选选择和真实 app smoke 之后运行一次：

```powershell
python -m anomaly_training evaluate --checkpoint training_runs\r3d18-crop-v3-seed11\best.pth --split test --smoke-evidence training_runs\r3d18-crop-v3-seed11\app_smoke.json
```

实际混淆矩阵（行=true，列=predicted；顺序 normal/violence/fall）：

```text
[[3, 1, 0],
 [0, 5, 0],
 [0, 0, 5]]
```

| metric | value |
|---|---:|
| macro precision | 0.9444 |
| macro recall | 0.9167 |
| macro F1 | 0.9221 |
| normal recall | 0.7500 |
| violence recall | 1.0000 |
| fall recall | 1.0000 |
| accepted | true |

验收条件是 macro F1 ≥ 0.75、violence recall ≥ 0.80、fall recall ≥ 0.80。晋级还要求 checkpoint 内的当前和最佳验证报告都已验收，训练时的 train/val manifest、selection/spec 摘要和源文件 SHA-256 与当前 canonical audit 完全一致，并有绑定同一 checkpoint SHA-256 的真实 app smoke。最后才允许读取固定 test manifest；任何一道门失败都不会晋级。通过后 checkpoint 以同目录临时文件原子替换 `models\best.pth`。

本次基线在该修复之前曾由旧 evaluate 覆盖 `metrics.json`，因此完整逐 epoch 训练历史已无法从现有产物可靠恢复；没有据此伪造 `training_metrics.json`。修复后的 canonical test 结果已迁移/重写到 `evaluation_metrics.json`，checkpoint 中的 epoch、优化器、调度器、scaler 和 early-stopping 状态仍可验证。

本轮训练数据完整性实现/修复提交（设计与说明文档另见 `cb0721a`、`45e5bc2`）：

```text
3cddb1c fix: harden training data promotion workflow
97d1a90 fix: lock canonical training manifests
a493cad fix: bound descendant manifest audits
```

## 启动与 API

```powershell
python -m anomaly_tracker --host 127.0.0.1 --port 8000
```

浏览器打开 `http://127.0.0.1:8000`，API 文档位于 `http://127.0.0.1:8000/docs`。

上传和读取结果：

```text
POST /api/jobs
GET  /api/jobs/{job_id}
GET  /api/jobs/{job_id}/result
GET  /api/jobs/{job_id}/video
```

真实 app smoke 使用 canonical manifest 中各一个 normal、violence、fall 样本。三个任务均报告 `mode=hybrid`、`device=cuda:0`，分别产生 55/22/28 个分类窗口和 21/2/4 条轨迹，三个 annotated MP4 均可解码播放。这个 smoke 只验证端到端上传、CUDA 分类、跟踪、结果和视频产物，不把某个样本是否产生告警当作性能指标。

## 限制与人工复核

- test 只有 14 条，且 normal/violence 来自 RLVS、fall 来自 UR Fall，模型可能学习来源、背景或拍摄风格，不能把 0.9221 当作跨摄像头性能。
- app smoke 的 normal 视频仍产生 7 个候选事件，而 violence 样本在严格的双人邻近与运动证据门控下没有产生暴力事件；阈值和规则必须在目标摄像头上重新校准。
- 训练和线上都使用 25% padding 的逐帧人员裁剪；90 条训练视频的 10,902 个采样帧中有 1,106 帧（10.14%）未检测到人员并回退全帧。遮挡、跟踪 ID 切换、远距离人员和小目标仍会改变概率。
- 像素速度、距离和姿态规则依赖分辨率、镜头角度和帧率。未经相机标定不能解释为真实世界速度或距离。
- 只支持单摄像头视频；`track_id` 不能跨摄像头当作同一身份。
- 输出不能识别真实身份、年龄或意图，也不能自动做执法、处分、医疗或安全决策。
- 每个事件都包含 `requires_review=true`。部署者必须保留原视频、概率、规则证据、track IDs 和轨迹，由具备上下文的人审核。

## 测试

```powershell
python -m pytest -q --basetemp=.pytest-tmp -o cache_dir=.pytest-cache
python -m compileall anomaly_tracker anomaly_training
git diff --check
```

原始数据、训练缓存和 `.pth` 权重均由 `.gitignore` 排除，不应提交到 Git。
