# ExecCon v2 实验代码

ExecCon v2 用于验证：在多智能体 specialist 数量从 **2 → 5 → 8**（h1–h3）扩展时，加入真实 execution evidence 是否能改善候选收敛，减少错误候选和干扰候选的影响。

## 实验条件

- **E0**：屏蔽 execution evidence；
- **E1**：开放真实 execution evidence；
- **E2**：使用错绑或冲突 evidence，作为负对照。

E0/E1 使用同一批冻结候选、同一收敛程序、同一提示词和预算，只改变 evidence 是否可见。

## 研究范围

| 阶段 | Specialist 数量 | 是否纳入 |
|---|---:|---|
| h1 | 2 | 是 |
| h2 | 5 | 是 |
| h3 | 8 | 是 |
| h4–h6 | — | 否，平台缺少对应 agent bundle |

本项目不声称完成完整六阶段或 24-agent EvoHarness 复现。

## 目录

```text
├── core/                 # ExecCon 核心协议和实验逻辑
├── protocol/             # 实验范围与验收门禁
├── scripts/offline/      # 本地离线验证和 fail-closed 入口
├── scripts/remote/      # 可选的 EvoHarness 远端脚本
├── tests/                # 单元测试和协议测试
├── config/.env.example   # 环境变量模板
└── docs/                 # 实验状态说明
```

核心代码包括：候选 bundle 冻结、provenance 校验、E0/E1 纯度检查、候选收敛、artifact 校验、官方评分隔离和 fail-closed 门禁。

## 环境配置

复制配置模板后填写本地环境变量：

```bash
cp config/.env.example .env
```

需要的变量：

| 变量 | 用途 |
|---|---|
| `EVAL_SERVICE_API_KEY` | EvoHarness 任务和 session 访问 |
| `EVAL_SERVICE_URL` | EvoHarness 服务地址 |
| `DMXAPI_API_KEY` | 模型 API |
| `DMXAPI_BASE_URL` | 模型 API 地址 |
| `DMXAPI_MODEL` | 模型名称，默认使用 `gpt-5.6-luna` |

`.env`、API key、SSH 凭据和运行报告不能提交到 GitHub。

## 安装与本地运行

推荐 Python 3.10+：

```bash
python -m pip install -e ".[test]"
python -m pytest -q
python scripts/offline/run_offline_protocol.py --output reports/offline-run
```

`settings.py` 会自动读取仓库根目录的 `.env`；已经存在的进程环境变量优先于 `.env`。离线测试不需要真实 API key。运行报告目录属于本地产物，不要提交。

本地测试主要验证 bundle 完整性、候选来源、E0/E1 处理纯度、收敛稳定性、MCP 错误处理和 clean staging。

## 远端脚本

`scripts/remote/` 下的脚本需要配置 EvoHarness 服务。候选采集入口已经参数化 h1–h3：

```bash
python scripts/remote/collect_candidate.py \\
  --stage h2 \\
  --specialist numerics_stats \\
  --candidate-id h2-numerics-001 \\
  --output runs/h2-numerics-001/candidate.json
```

各阶段 specialist pool 固定为 h1=2、h2=5、h3=8，并写入候选 provenance。`canary_h1.py` 和 `evoharness_minimal_repro.py` 是 h1 专用诊断脚本。

- `canary_h1.py`：h1 无模型 provisioning 检查；
- `inspect_task.py`：公开任务检查；
- `probe_platform.py`：平台探针；
- `collect_candidate.py`：模型候选采集；使用 `--stage h1|h2|h3` 支持 2/5/8 specialist pool，可用 `--output` 指定候选报告路径；
- `evoharness_minimal_repro.py`：平台问题复现。

远端实验必须先通过 provisioning 和 runtime smoke 检查。基础设施失败单独记录，不计为模型得分 0。

## 依赖

离线核心仅使用 Python 标准库；测试和远端脚本依赖分别由 `pyproject.toml` 的 `test`、`remote` extra 声明。推荐安装：

```bash
python -m pip install -e ".[test]"
```

## 当前限制

- h4–h6 暂时无法运行，因为平台缺少对应 agent bundle；
- 远端模型执行曾出现 runtime 权限、缓存目录和 artifact 读取问题；
- 这些问题属于平台基础设施问题，不等于 ExecCon 方法或模型失败；
- 只有通过全部验收门禁、候选区分度门禁并完成官方评分的 cell，才能进入正式主表；候选没有可观察预处理差异时标记为 `diagnostic_only_no_discrimination`，不进入 treatment-effect 分母。

详细规则见：

- `protocol/MVE_ACCEPTANCE.md`
- `protocol/STAGE_SCOPE.md`
- `docs/EXPERIMENT_STATUS.md`
