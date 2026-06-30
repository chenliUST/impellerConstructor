# 叶轮参数组合构建实验报告

日期：2026-06-29

目标：系统性扫描当前 impeller rule engine 在不同分类 facet 和参数组合下的构建表现，区分 kernel 能否返回数据、manifest validity 是否能发现问题、额外数学诊断是否认为几何可接受，以及 CAD export 是否真实成功。

## 1. 实验范围

本次实验没有修改几何核，只新增了可重复实验脚本：

```powershell
python scripts\impeller_parameter_experiment.py --out-dir runs\impeller_parameter_experiment --random-cases 180 --cad-limit 12 --cad-timeout-sec 30
```

输出文件：

- `runs/impeller_parameter_experiment/impeller_parameter_experiment_results.json`
- `runs/impeller_parameter_experiment/impeller_parameter_experiment_summary.json`
- `runs/impeller_parameter_experiment/impeller_parameter_experiment_summary.csv`

覆盖组合共 605 组：

- 6 组 preset default。
- 270 组 facet matrix：`flow_topology * shroud_topology * suction_topology * blade_exit_geometry * passage_topology`，working domain 固定为 pump。
- 149 组 one-factor stress：对 preset 做单参数或少量耦合极限扰动。
- 180 组 deterministic random：固定随机种子 `20260629`。

CAD 导出只跑 12 个优先样本，原因是 CADQuery loft/boolean/export 单例可能超过 30 秒。这个 CAD 子集用于发现导出层问题，不作为完整 CAD 统计。

## 2. 判定层级

本次实验分四层看成功：

1. `kernel_status`：`build_impeller_geometry()` 是否抛异常。
2. `declared_validity_status`：当前系统内置 `geometry_validity` 是否 PASS。
3. `diagnostic_status`：实验脚本额外计算的数学诊断，包括曲面法向翻转、相邻叶片干涉、blade span collapse、有符号半径穿轴、过大包角、未实现 passage specialization 等。
4. `cad_status`：有限 CAD 子集是否真正生成非占位 STEP/STL。

注意：`diagnostic_status` 是 sampled diagnostic，不是精确 B-rep 自交求解器。但它能暴露当前 9x5 参数网格已经可见的数学问题。

## 3. 总体结果

```text
case_count: 605
kernel_status: PASS 605
declared_validity_status: PASS 566, FAIL 39
diagnostic_status: PASS 47, WARN 159, FAIL 399
cad_status: PASS 8, FALLBACK_PLACEHOLDER 1, TIMEOUT 3, NOT_RUN 593
```

结论很明确：当前 kernel 鲁棒性表现为“几乎所有输入都能返回一个数据结构”，但不是“几乎所有输入都能生成数学上可接受的叶轮”。内置 validity 只拦住 39 组，而实验诊断认为 399 组存在 hard issue。这说明当前 validation 明显不足。

如果把 `single_channel`、`multi_channel`、`cutter` 这类尚未实现的 passage specialization 单独剥离，仍有 232 组存在真实几何 hard issue，主要来自曲面翻转、叶片干涉、叶高/厚度不可行、半径反向或 warp 穿轴。

## 4. Preset 结果

| Preset | Diagnostic | Declared validity | CAD | 主要问题 |
| --- | --- | --- | --- | --- |
| `radial_open_backward_single_reference` | WARN | PASS | PASS | `high_blade_wrap`，baseline 包角偏高 |
| `mixed_semi_open_radial_double_study` | WARN | PASS | FALLBACK_PLACEHOLDER | legacy shroud lines 非 surface_graph 来源；CAD 被 fallback 掩盖 |
| `axial_closed_forward_single_study` | WARN | PASS | PASS | legacy shroud lines 非 surface_graph 来源 |
| `radial_open_recessed_vortex_study` | PASS | PASS | PASS | 本次唯一 clean preset |
| `twisted_open_impeller_study` | WARN | PASS | PASS | hub 使用 warped/non-axisymmetric field，不是严格回转面 |
| `twisted_closed_impeller_study` | WARN | PASS | PASS | 同上，且 closed shroud legacy line 仍是 proxy |

这里的重点不是 preset 都坏了，而是 preset default 也暴露了两类架构问题：CAD fallback 会掩盖失败；旧的 shroud construction lines 与 `surface_graph.surface_uv` 并非同一来源。

## 5. Hard Issue 分布

| Issue | Count | 数学含义 |
| --- | ---: | --- |
| `unsupported_passage_specialization` | 268 | taxonomy 接受了 `single_channel/multi_channel/cutter`，但 geometry 仍按 generic throughflow 构造 |
| `surface_normal_flip` | 210 | sampled surface 相邻 cell 法向反转，表示曲面局部折叠或参数化方向不连续 |
| `adjacent_blade_interference` | 84 | 相邻叶片中心线间距小于厚度所需 clearance，常见于小半径、高叶片数、大厚度或强 warp |
| `blade_span_collapse` | 51 | hub-tip span 小于 blade thickness 所需空间，叶片厚度相对叶高不可行 |
| `declared_validity_failed` | 39 | 当前内置 validity 发现失败，主要是 hub profile 非单调 |
| `excessive_blade_wrap` | 27 | blade inlet-to-outlet 包角超过 210 deg，loft 极易自交或视觉缠绕 |
| `radial_or_mixed_exit_not_greater_than_inlet` | 16 | radial/mixed 入口出口半径关系不满足 flow topology 约束 |
| `negative_signed_surface_radius` | 12 | warp 半径场穿过旋转轴，极坐标参数化发生翻转 |

Warning 里最重要的是：

- `legacy_shroud_lines_not_from_surface_graph`: 389
- `strict_revolve_hub_violation`: 252
- `recessed_vortex_with_shroud_topology`: 65
- `inlet/outlet_beta_silently_clamped`: 各 35

## 6. 典型失败模式

### 6.1 Passage facet 已分类但未几何专门化

`single_channel`、`multi_channel`、`cutter` 当前只是 taxonomy 值，实际仍走普通 throughflow bladed channel。数学上这不是“生成失败”，而是“语义声称与几何实现不一致”。这些组合应该在 service 层被标为 unsupported，或者分派到独立 kernel。

直接影响：前端选择这些类型时，会看到一个普通叶轮，但 manifest 声称是另一类 passage topology。

### 6.2 Blade theta 积分无可行域约束

当前公式：

```text
theta += dm / (r * tan(beta))
```

在以下情况下会迅速变坏：

- `beta` 接近 0 deg，`tan(beta)` 很小。
- 半径比过大，meridional path `dm` 过长。
- `blade_curve_gain` 与 backward/forward bias 叠加后造成局部包角过大。
- 极端 twist 与已有 theta 累积叠加。

实验中 `beta_zero`、`beta_cross_0_90`、`large_radius_ratio`、`curve_gain_min` 等组合都触发 `surface_normal_flip` 或 `excessive_blade_wrap`。这说明 beta 不是简单 clamp 到 `[3, 87]` 就足够，应该有基于 cumulative wrap、local curvature、cell orientation 的可行域约束。

### 6.3 厚度、叶片数、半径之间缺少 pitch 约束

典型失败：

```text
blade_count = 16
inlet_radius = 120 mm
blade_thickness = 200 mm
```

相邻 blade centerline gap 约 46.8 mm，但 required gap 约 210 mm。数学上这已经不可能形成不相交叶片阵列。

需要新增参数约束：

```text
blade_thickness_mm < k * min_u(2*pi*r(u)/blade_count)
```

其中 `k` 应该小于 1，并且需要给 fillet、manufacturing clearance 和 shroud clearance 预留余量。

### 6.4 Blade span 与 thickness 未耦合

`short_span` 类参数会出现：

```text
min_blade_span_mm = 1.0
blade_thickness_mm = 56.0
```

当前 kernel 仍然生成 blade side surfaces，但这在几何上是不可行的。需要约束：

```text
min_span(u) > blade_thickness_mm + root_fillet_allowance + tip_clearance
```

对于 recessed vortex，当前会把 blade height 乘以 0.72，因此厚叶片更容易触发 span collapse。

### 6.5 Warp 半径场可能穿轴

当前 warped surface field 近似为：

```text
radius = r + warp * 0.18 * sin(2*theta)
z = z + warp * cos(theta)
```

当 `r < 0.18 * warp`，有符号半径会小于等于 0。实验中的 `small_radius_high_warp` 组合出现：

```text
inlet_radius = 20 mm
hub_warp = 300 mm
tip_warp = 400 mm
min_signed_surface_radius = -52 mm
```

这会导致极坐标参数化翻面。当前内置 `positive_radii` 用 `hypot(x, y)` 检查，无法发现这个问题，因为负半径转换到笛卡尔坐标后仍有正的距离。

### 6.6 Strict revolve hub 与 twisted/warped hub 语义冲突

用户前面指出 hub 应该是由一段或多段 NURBS profile 定义的回转面。当前 `hub_twist_deg/hub_warp_mm` 会让 hub 变成 non-axisymmetric field，因此严格来说不再是 surface of revolution。

这不是单个参数的问题，而是建模语义冲突：

- 如果 hub 必须严格回转，则 hub 不应暴露 twist/warp 参数。
- 如果需要扭曲的 blade attachment surface，应单独定义 `attachment_surface` 或 `blade_root_reference_surface`，不能继续叫 strict hub revolve。
- closed shroud/tip 可以考虑非轴对称变形，但也需要明确它是否是真实 shroud surface，还是 design reference surface。

### 6.7 当前 conformance validity 存在自证式检查

当前 `blade_hub_boundary_conformance` / `blade_tip_boundary_conformance` 的实现只比较 `surface_graph.boundary_curves` 中同一个 key 的曲线，因此只要数据被写入，就会得到 0 距离。

它证明的是“boundary curve 被记录了”，不是“boundary curve 确实落在 hub/tip/shroud surface 上”。

下一步需要改成：

```text
for each blade boundary point:
  find corresponding surface parameter sample or evaluate surface(u, theta)
  compute point-to-surface or point-to-parametric-boundary distance
```

对于 sampled kernel，最小可接受实现是比较 blade boundary 与同一参数 `(u, blade_theta(u))` 下的 hub/tip/shroud evaluator 输出，而不是比较 boundary curve 自身。

### 6.8 CAD export fallback 掩盖失败

CAD 子集 12 个样本：

```text
PASS: 8
FALLBACK_PLACEHOLDER: 1
TIMEOUT: 3
```

`mixed_semi_open_radial_double_study` 在 kernel 和 declared validity 都 PASS，但 CAD export 失败后 service 写了占位 STEP/STL。当前 `_write_exports()` 捕获所有异常并静默 fallback，这会让 API 看起来成功，但工程上不可接受。

需要至少在 manifest 增加：

```json
"exports": {
  "step": "...",
  "stl": "...",
  "status": "fallback_placeholder",
  "error": "..."
}
```

更好的策略是：研究阶段允许 fallback，但必须在 manifest 和前端醒目标红。

## 7. 根因总结

当前问题不是一个单点 bug，而是几何规则引擎缺少“可行域层”和“真实拓扑验证层”。

主要根因：

1. 参数是独立 bounded，没有按 facet 建立耦合约束。
2. `theta` 积分没有累计包角、局部曲率、相邻叶片 pitch 的上限约束。
3. `hub/tip/shroud` 的数学类型还没有严格区分：回转面、非轴对称参考面、真实闭合 shroud surface 被混在一起。
4. `passage_topology` taxonomy 超前于 geometry implementation。
5. validity 仍是结构性检查为主，缺少曲面 orientation、自交、point-on-surface、pitch clearance、signed radius 等数学检查。
6. CAD export 异常被 fallback 吞掉，导致“构建成功”的定义不可信。

## 8. 建议的下一步

建议不要马上继续扩展更多叶轮类型。下一步应该先建立 feasibility/validity gate：

1. 新增 `impeller_feasibility.py`：在 build 前做 facet-aware 参数可行域检查。
2. 新增 hard constraints：
   - radial/mixed: `exit_radius_mm > inlet_radius_mm`
   - signed radius: `min(r_h, r_s) > 0.18 * max_warp + margin`
   - span/thickness: `min_span > thickness + fillet + clearance`
   - pitch/thickness: `thickness < k * min(2*pi*r/blade_count)`
   - wrap: `abs(theta_out - theta_in) < max_wrap`
3. 重写 conformance validity：不能再做 boundary self-compare。
4. 把 `single_channel/multi_channel/cutter` 暂时从可生成类型中降级为 unsupported，或实现独立 passage kernel。
5. 决定 hub 的严格语义：如果 hub 是 NURBS revolve，就移除/禁用 hub twist/warp；如果保留非轴对称 attachment surface，就在 ontology 中单独命名。
6. CAD export 改为 fail-visible：占位文件可以保留，但 manifest 必须记录 `export_status != PASS`。

## 9. 本阶段结论

当前规则引擎的最小通路已经能稳定返回 deterministic manifest，但还不能说“参数空间内的大量组合都能生成数学正确的叶轮”。

最应该优先修的是 validation，不是视觉效果。否则前端会继续展示很多“看起来有模型”的失败组合，而这些组合在数学上已经违反了半径、pitch、span、包角或 topology implementation 的基本条件。
