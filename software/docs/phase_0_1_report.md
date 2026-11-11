# Phase 0 / Phase 1 实施报告

日期：2026-10-20（Asia/Shanghai）。状态：工程检查通过，等待人工确认基线与目录结构。未进入 Phase 2。

## 交付位置

新工程：`D:\疵病检测\DefectInspectionSoftware`。
原算法参考源：`D:\疵病检测\DefectDetectionProject`。

- `docs/existing_algorithm_inventory.md`：17项算法盘点，含当前入口、RAW、ROI和可选两级调度、阈值、恢复、关联、计量、分级、依赖与限制。
- `baseline/source_snapshot/`：277份原工程源码/配置/测试/关键文档回滚副本。
- `baseline/source_manifest.json`：逐文件SHA256；执行前后完全一致。
- `baseline/results/unified_26/`：本轮双帧结果完整副本，保留mask、候选审计和输入溯源。
- `baseline/screenshots/`：本轮双帧最终矩形标注图。
- `baseline/metrics/`：原工程pytest日志、独立QA日志、逐对象及整图差异、原运行环境锁定。
- `baseline/baseline_manifest.json`：命令、模式、RAW哈希、结果文件哈希、数量/面积和验收范围。
- `docs/main_window_phase1.png`：实际启动的中文空窗口截图。
- `requirements.txt`、`requirements-lock.txt`：声明依赖与独立虚拟环境精确版本。

## Phase 0：实际执行结果

原目录不是Git仓库，采用独立快照作为本轮回滚点，不在原目录初始化Git。
不修改现有算法核心、参数、测试或原始数据；原工程仅新增唯一运行输出。

实际命令（在原工程目录）：

```powershell
.\.venv\Scripts\python.exe main.py --case unified-final --sample 26 --run-id SOFTWARE_PHASE01_BASELINE_20261020_01
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp 'D:\疵病检测\DefectInspectionSoftware\baseline\test_tmp_phase0'
.\.venv\Scripts\python.exe scripts/verify_unified_revision.py outputs/SOFTWARE_PHASE01_BASELINE_20261020_01
```

以上run-id已存在，重新运行必须使用新名称。QA脚本会在指定新运行结果下创建独立QA记录。

| 项目 | 26_1 | 26_2 |
| --- | ---: | ---: |
| 本轮自动入选对象 | 36 | 35 |
| 分割面积 px² | 20356 | 17709 |
| 全源候选审计行 | 32370 | 8332 |
| 人工确认暗斑面积 px² | 297、398 | 348、370 |
| 相对v4新增/消失对象 | 0 / 0 | 0 / 0 |
| ID/位置/尺寸/Feret/等级/来源变化 | 0 | 0 |
| 整图二值分割PNG SHA256一致 | PASS | PASS |

原工程全套pytest：**354 passed in 18.55s**；独立像素QA退出码0、状态PASS。
验证包含精确mask、Feret、全源去向、原入选像素保留、四处确认暗斑精确不变、人工负例无重叠等。
本轮基线与v4逐对象表格和全分辨率mask完全相同，已确认暗斑及既有入选划痕像素无退化。

### 运行模式必须说明

本轮执行当前算法的双帧复核入口：**重新执行最终判定和RAW恢复，复用并记录冻结J4/J5及历史上游依赖**。
本轮没有从空盘重新计算两帧的1620块J4/J5，也未执行可选 `--roi-mode` 加速分支。
历史完整RAW运行证据已在原工程存在，位置见盘点文档和原UNIFIED_FINAL_ACCEPTANCE。
此基线足以冻结当前软件化前的结果，但不能被表述为本轮重新验证了全部可选运行模式。

## Phase 1：工程和环境

已建立独立 `.venv`（Python 3.14.7，include-system-site-packages=false），未修改系统/原工程Python环境。
PySide6 6.12.0；NumPy/OpenCV等准确版本见requirements-lock.txt。该环境仅验证了依赖导入/兼容性和GUI，算法尚未接入，不宣称已在新环境验证算法数值等价。

目录按五层分离：

```text
app/                 启动入口 + application预留
ui/                  独立MainWindow + viewer/table/detail等预留模块
core/                detector/pipeline及检测分层目录预留
domain/              长期模型文件预留，未实现Phase 2模型
infrastructure/      IO/Repository/export/logging预留
configs/             三种YAML占位，明确标注非生产配置
tests/ docs/ output/ logs/ baseline/
```

启动（在新工程目录执行）：

```powershell
.\.venv\Scripts\python.exe -m app.main
```

主窗口为中文最小空壳，只提示基线和后续接入状态；没有提前实现检测、数据模型、报告或EXE。

### 验证

- `python -m pip check`：退出码0，依赖无冲突。
- `python -m app.main --smoke-test --screenshot docs/main_window_phase1.png`：实际显示窗口、检查可见状态、保存截图、正常退出，退出码0。
- 已目视检查截图：中文内容、状态栏显示正常，窗口大小1100×720。
- 原工程277份冻结文件再次SHA256对比全部一致。
- 原工程354项测试及独立QA均通过，无算法修改。

安装复现：`python -m venv .venv`，然后 `.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt`。
PyInstaller/ReportLab属于后续阶段，尚未安装或执行发布。

## 回滚与提交

新工程已建立Git。初始回滚点：`c4d0dc1`，包含Phase 0源码清单与初始Phase 1骨架。
最终阶段提交以 `git log -1 --oneline` 查看，包含完整文档与验证记录。
原源码快照、基线大文件和虚拟环境不入Git，独立保存在baseline和.venv中；不可仅靠Git恢复这些文件。
CHANGELOG已更新。原工程无代码删除、替换、阈值变化或结果覆盖。

## 人工确认与阶段边界

按任务书第24节：**“完成后先停止，不进入 Phase 2，等待人工确认基线与工程结构。”**

本轮已停止在Phase 1。待确认内容：双帧标注图与基线指标、独立目录结构、3.2μm仅为像面像元且物面标定未知。
后续算法接口设计还需明确默认完整RAW模式与今天新增两级ROI可选模式如何进入统一适配层；本轮未自行切换默认分支。
71个自动入选对象不等于71个人工真值。全源台账中的微小候选也不能当作已全部确认的微小疵病。
没有独立密集真值，不能承诺物理零漏检或给出精确率/召回率。所有现有结果和人工审批历史保留。
