# VesselForge inventory — 2026-10-15

本盘点只读；没有启动 CAD、Blender、服务、求解、训练或测试，也没有读 NPZ/STL 的数组负载。

## 仓库状态与当前结论

- 子仓：`C:\Users\xiemo\Desktop\ShardForge\vesselforge`；当前 branch `backup/forge-work-20261003`，HEAD `73116cf40bd8620e3142667dccd644cc16c47aac`（2026-10-08，`Archive complete source and review evidence`）。`git status` 显示 tracked 文件 0 项变更、373 个 untracked 路径，主要是 `experiments/` 与 `tmp/` 的历史证据；本次未触碰它们。
- `vesselforge/AGENTS.md`、父目录 `ShardForge/AGENTS.md` 与子仓内其他 `AGENTS.md` 均未找到。先读了 `README.md` 和 `docs/handover/20261007/HANDOVER.md` 的 VF 部分。
- README 的产品定位是独立原型，不是通用历史器型生成器。Handover 将 VF 定为解析子午线、有限曲线/理想距离证书及几何候选；完整历史器型、全局实物壁厚、真实纹样/材料、物理资格均未建立。最新 `c4_jar_native_ingress` 是 SOURCE_ACCEPTED 的静态来源包，执行授权为 false，CAD/STEP 调用数为 0。

## 可调用源 API 与边界

- `src/vesselforge/__init__.py` 导出 `create_asset_package(...)`、`validate_asset(...)`；CLI 在 `src/vesselforge/cli.py`。`create_asset_package` 位于 `asset.py`，会导出 `forge.asset.v1`：canonical STEP、三角网格及 B-rep face lineage、表面字段、材料/纹样 recipe、provenance、data dictionary、几何 QA。它当前固定调用 `geometry.build_components(VesselSpec)`，输出的是小型开口转体与扫掠融合把手；`geometry.py` 的默认范围约 41×56 mm、目标侧壁 4 mm。README 示例命令 `vesselforge generate --out .\out\four_bands --pattern four_bands --seed 20261003` 尚未在本盘点中执行。
- `src/vesselforge/profile_catalog.py:build_profile(family, ...)` 定义 bowl、beaker、jar 三个解析参数族及 profile 元数据；壁声明是按高度对应点的径向偏移，不是全局法向最小壁厚。`geometry.build_components` 尚不接受 `VesselProfile`。
- `src/vesselforge/appearance.py` 只支持 `four_bands`、`three_bands` 两种 painted bands，`geometry_relief_mm=0`。当前每三角形颜色用质心抽样；`tests/test_appearance.py` 明确记录第三条红带 `per_face_approximation_status=FAIL`，连续 shader 状态仍为 `PENDING`。
- `src/vesselforge/ornament_fields.py` 有 `GeometricRingBand`、`WavingBand`、`RepeatedMotif` 和 `evaluate_ornament_stack`，在静止母体 XYZ 坐标计算颜料/有符号高度场。它不修改 CAD 或网格。`qualify_geometry_field` 对浮雕只会报告 `HEIGHT_FIELD_ONLY_NOT_MESHED`；刻纹需要可信壁厚图，但其来源认证仍由调用方提供。当前 schema 只接受 painted 且零 relief。
- mechanics 字段只是示例数值：`rho=2100 kg/m³, E=5 GPa, nu=0.25, Gc=45 J/m²`，且 schema 强制 `UNVALIDATED_PROTOTYPE`。VF 没有断裂 solver、实验数据导入或训练 API。

## 已运行证据与留存候选

1. **实际 bowl/jar CAD 运行（不是完整资产包）**：`docs/evidence/20261006/core_components/catalog_native_adapter/REVIEW.md` 及 `pilot_01/`。历史 pilot 各对 `profile_catalog.build_profile("bowl")`、`("jar")` 生成一个 CadQuery/OCC B-rep 并 STEP round-trip；8.36 s 总计，源 pins 前后相同。Bowl 为 1 valid solid、1 closed shell、14 faces；jar 为 1 valid solid、1 closed shell、16 faces。STEP bounding box/volume round-trip 与腔体探针通过；wall probe 只证实代表点材料存在，不是最小壁厚测量。保留文件包括 `bowl_default/candidate.step`、`jar_default/candidate.step`、各自 `native_case_receipt.json` 和 `native_brep_section_and_3d.png`。这是目前最快可复用的 bowl/jar 实际几何证据，但 adapter 位于 `experiments/catalog_native_adapter_20261006/`，没有生产集成、mesh、面语义或纹样字段。
2. **较早的 profile meshes**：`tmp/review_20261004/profile_catalog/meshes/{bowl,beaker,jar}.stl` 与预览图是三种解析型的历史 mesh 候选；不是 native STEP、不是已验收资产包，也不能替代 10/06 的 bowl/jar B-rep 证据。
3. **完整包格式 fixture**：`tmp/review_20261004/wall_mesh_binding/v4_run/cylinder_asset_run01/` 保存 synthetic cylinder 的 `forge.asset.v1` 包（STEP、surface/lineage/appearance arrays、manifest、face semantics、wall reference、geometry report）。其迁移副本的资产验证和两处母体 wall-station mapping 在 `docs/evidence/20261005/geometry_resume/report.md` 记录为 PASS。它是 fixture cylinder，不是陶器器型；材料仍为 `UNVALIDATED_PROTOTYPE`。
4. **纹样几何 patch**：`docs/evidence/20261005/ornament_resume/` 保存两个解析曲面局部细化候选（0.50 / 0.25 mm）、NPZ、PNG、checks 与 receipt；历史检查报告记录闭合网格、lineage/重建及有限误差探针通过。输入是单一解析圆柱场/样本，候选不是 bowl/jar、完整资产包、历史纹样匹配或壁厚资格。不要读取其 NPZ 负载来补结论。另有 `tmp/review_20261004/surface_ornament_route/run02/` 的纹样 fixture 和报告。
5. 子仓内未发现 `assets/`、`out/` 或 `generated/` 生产输出目录；`src/`、`tests/` 内无 STEP、STL、GLB 或 texture 图片。已有 PNG 是截面/mesh/field 预览，不是贴图文件。`docs/references/REAL_VESSEL_REFERENCE_CATALOG_20261004.md` 引用了 Met 藏品的一手记录，但没有本地扫描/CAD/校准颜色；馆藏尺寸和文字不能补出准确剖面、壁厚或力学参数。

## 当前运行时

- `pyproject.toml` 声明 Python `>=3.11,<3.14`、CadQuery `>=2.8,<2.9`、NumPy `>=2,<3`。仓库专用运行时路径为 `C:\Users\xiemo\Desktop\ShardForge\third_party\vesselforge-runtime\venv\Scripts\python.exe`；现场安装目录记录 CadQuery 2.8.0、cadquery-ocp 7.9.3.1.1、NumPy 2.5.3、VTK 9.6.2、SciPy 1.18.1。CadQuery/OCP 是实际生产 API 的 CAD/mesh 后端。根目录另有 Blender 5.2.2 打包目录，但 VF 当前代码没有 Blender 导出/纹理集成。
- 历史 adapter 的一次性命令记录见 `experiments/catalog_native_adapter_20261006/README.md` 与 evidence receipt；这是已消耗的历史运行，不应照抄重跑。此盘点没有执行命令或测试。

## 最小实现路线与验收条件

1. **选 bowl 做首个完整器型包**：从已运行的 bowl native pilot 与 `profile_catalog.build_profile("bowl")` 复用闭合材料剖面，接入统一 asset builder；为无把手器型加入明确的面语义规则（body outer/inner、rim、base），将 `base_thickness_declaration_mm` 与侧壁声明分开传递。canonical STEP re-import 后再 mesh，保留三角形到 B-rep face lineage 和来源哈希。至少验收：1 valid solid/closed shell、正体积与空腔、STEP round-trip 尺寸/体积阈值、watertight/oriented mesh、全 canonical faces 分类无 UNKNOWN、recipe 与 profile provenance 完整。壁厚只报告已测/证明的范围，不将径向声明叫全局最小壁厚。
2. **在 outer body 上合成首个重复纹样**：先选 `RepeatedMotif(effect="paint")`，保持零 relief；在 `asset.py` 将现有绘饰 pipeline 接入 `evaluate_ornament_stack`，保存参数 recipe 与不可变母体 rest-coordinate 的顶点颜色或 UV texture，并更新 schema/data dictionary。验收 theta seam 两侧权重/颜色连续、只落在外表面、色值有限且在 [0,1]、相同 seed/input 哈希一致；不要依赖目前已知缺失红带的 per-face centroid 近似。首个包声明“程序化视觉候选”，不声称历史真实性。真实浮雕应另行实现有界网格位移/重网格、全局残余壁厚与自交检查后再进 schema。
3. **真实破裂和实验训练链属于 PG-Frag + 实物试验，不在 VF 内**：至少需要带来源的实物批次/试件、含不确定度的材料测试、受控重复撞击数据（载荷/传感器时间序列、高速影像、断后 3D 扫描）及关联的 CAD/mesh/材料版本。训练/标定须按试件分组留出独立验证；通过载荷/能量误差、裂纹路径/断口和碎片断开、网格/方向收敛审查后，才称实验校准。当前 VF 和 handover 都没有这条真实数据链。

### 新增独立 spherical-bowl API 的适配性

若目标是第一条短链，可增加 `src/vesselforge/spherical_bowl.py`，暴露新的 immutable spec、solid builder 和 package builder，不改写旧 `create_asset_package(VesselSpec)`。以半球子午圆弧绕 Z 轴旋转：`Ro=12 mm, Ri=8 mm, center_z=12 mm, z<=12 mm`，在 `z=12` 以 `r=8..12` 闭合环口。理想同心球壳设计壁厚恰为 4 mm；它仍是解析几何声明，不代表实物测量或材料已验证。相比球体布尔切割，解析闭合子午剖面 revolve 更容易保持单一 STEP solid，须用受限 CAD 运行确认。

现有 `geometry.mesh_shape`、`mesh_topology_metrics`、`sampled_mesh_to_cad_metrics`、STEP 导出和 `schema.validate_asset` 可复用；旧 asset QA 中依赖把手/旧 profile 的壁厚与连接检查不可直接复用。`schema.validate_asset` 不要求每个 region code 都出现，所以无把手包可只用 body_outer/body_inner/natural_rim（1/2/3）；但现有 semantics classifier 不认识球面，需在新 classifier 中用球心到采样点的径向向量与有向法线点积分类内外球面，并将 `z=12` 平面分类为 rim。最终 canonical STEP 的每一面都必须有可审计分类和相同 STEP 哈希。

这条独立 builder 能满足现有 `forge.asset.v1` 的 painted、zero-relief 几何候选包；当前 validator 仍强制 mechanics 为 `UNVALIDATED_PROTOTYPE`、ornament 为 painted/零 relief，因此不能借此表示已校准材料或真实浮雕。将 `RepeatedMotif` 采样成 per-face centroid 色值有欠采样风险；若要求高保真连续纹理，需扩展现有只接受 `F×3` albedo 的 schema，明确 vertex-color/UV texture payload 和验证条件。建议实现者只拥有新 spherical-bowl 模块及对应测试；主代理保留公共包合同、数据/物理边界和跨仓验收，避免多人并行修改 `asset.py`、`schema.py`、`semantics.py`。

### 核对命令（只读）

```powershell
Set-Location C:\Users\xiemo\Desktop\ShardForge\vesselforge
git branch --show-current
git rev-parse HEAD
git status --short --branch
Get-Content docs\evidence\20261006\core_components\catalog_native_adapter\REVIEW.md
Get-Content docs\reviews\20261007\native_c4_source_independent\FINAL_SOURCE_REVIEW.md
```
