# 设计：canonical STEP wall station 到 SynLab wall_intervals 的两阶段桥接

状态：只读设计稿，尚未实现/运行。参考固定的 wall-reference v1 快照（SHA `ceeeeec791ed1264bd73a2c0e9dd250ab39aa213a97f75725bf2e6eab91c3461`）、现存 VF semantics/OCP tessellation 与 SynLab helper/provenance 接口。没有读取正在变动的 `profile_catalog.py` 或现行 `wall_reference.py`；没有运行测试、solver 或 CAD。

## 决策

桥接拆成两个有独立状态的阶段：

1. **母 mesh binding**：固定 v1 的每个 canonical STEP wall station，绑定到由同一个 canonical STEP 重剖分得到的母三角网格，并保留 B-rep face → triangle lineage。只有所有 wall-reference stations 都成功、且 mesh/lineage/hash/frame 验证完整时，才允许生成 A12 baseline 输入。
2. **fragment lineage**：每个裂片/物理结果携带其来源母 mesh 的三角面 ID、每顶点/角点重心坐标、残差和父 mesh 身份。wall interval 测量仍按一个明确的 source mesh 与一个已证明为其 material subset 的 result mesh 调用。阶段1 PASS 不会自动晋级成阶段2 PASS，也不代表全局最小壁厚。

A12 的 `measure_material_intervals` 可直接接收的内容已经清楚：同一世界系 mm 下的 `trimesh.Trimesh` source/result，`N×3` wall surface station，`N×3` outward-from-source-material 方向，以及显式的方向与 subset 证据。它本身始终报告 `global_wall_status=UNVERIFIED` 和 `physical_qualification_status=UNKNOWN`。目前 `wall_intervals` 仍是独立 helper，A12 `open_items.md` 明确它未接入 P03。

## 身份、hash 与坐标契约

这些身份字段必须分别保存并各自对文件/数组核验：

- `canonical_step_file_sha256`：STEP 原始字节 SHA；由 asset 文件清单核对。
- `face_semantics_file_sha256`：语义 JSON 原始字节 SHA；其报告内 `canonical_step_sha256` 必须等于 STEP 文件 SHA。Face 索引只在这个 STEP SHA、face count 与记录的 CadQuery/OCP 版本组合下解释。
- `parent_surface_file_sha256`：`geometry/surface.npz` 文件字节 SHA。
- `parent_lineage_file_sha256`：`geometry/mesh_lineage.npz` 文件字节 SHA。其 `face_source_brep_index[i]` 把 parent triangle `i` 映到同一次 canonical STEP import 的零起始 B-rep face index。
- `parent_mesh_content_sha256`：另外定义的数组内容身份，输入包括固定 little-endian dtype 的 `vertices_mm`、`faces`、`face_source_brep_index`、形状、units、frame 和版本标签。这样 parent triangle ID 的命名空间含有 mesh 与 lineage，而不只含表面坐标。
- `synlab_mesh_hash`（可选）：如果 SynLab 的 `mesh_hash(mesh)` 用于互操作，必须单列。当前算法只含 vertices/faces、把坐标 round 到 9 位且不含 face attrs，不能替代 surface 文件 hash、lineage hash 或 composite mesh identity。
- `wall_reference_file_sha256`：冻结 v1 station 记录的原始字节 SHA。每个 station 同时存完整 STEP SHA、`source_wall_face_index_zero_based`、role 和原有 `station_id`。v1 station ID 带的是截短 hash 前缀，单靠该 ID 不足以作跨资产外键。

绝不能把任何 mesh/content/SynLab hash 填进 `canonical_step_sha256`。资产 units 是 length `mm`、frame `right_handed_z_up`；VesselForge/OCP 顶点、face semantics 的 `point_mm`、SynLab `stations_mm`、射线距离必须都保持此世界坐标和 mm。方向向量为 dimensionless 单位向量。若将来有变换，只允许记录显式 4×4 刚体变换并统一应用到 station 与方向；无法证明变换则 UNKNOWN。

## 阶段1：STEP station 绑定到 parent mesh

新增母 mesh binding 记录（建议 `vf.wall-mesh-binding.v1`），与现有 frozen wall-reference 分开保存。它至少包含：STEP/semantics/wall-reference 文件 SHA，parent surface 与 lineage 文件 SHA，composite `parent_mesh_content_sha256`，顶点/三角形/STEP face 数，frame/units，CadQuery 与 OCP 版本，绝对线性和角度 deflection，face lineage 的来源，以及每一条 station 的映射状态和诊断值。

建图顺序：

1. 先通过 asset manifest 核对实际 STEP 字节 SHA；通过 `forge.asset.v1` 检查 units/frame、face semantics PASS、face rows/hash、surface 与 lineage 文件 hash，以及每个 triangle 的 `face_source_brep_index` 都在 canonical face inventory 范围内。surface、lineage 与 STEP 的哈希保留为不同字段。
2. 用记录的 CadQuery/OCP 版本从这份 STEP reimport canonical B-rep；校验 face 数及 semantics report 与 STEP hash 绑定。墙 station 引用的 face index/role 必须与 frozen v1 inventory 一致；backend/face inventory 改变则生成新的 binding 或 UNKNOWN，不能按最近几何悄悄重编号。
3. 对 station 的原 B-rep face 用原 `u,v` 重新求点与 face-oriented outward normal。再用 `BRepClass_FaceClassifier` 对 **trimmed face** 验证 UV；仅接受 `TopAbs_IN`。若为 ON/OUT、UV chart 外、face hash/index 不符，或重求的 point/normal 与冻结 station 超过核验误差，给该 station UNKNOWN。不能投影到未裁剪无限曲面后就当成该 trimmed face。
4. 只对 `face_source_brep_index == station.source_wall_face_index_zero_based` 的 parent triangles 做点到三角形精确 closest-point，并算 barycentric。禁止在整个 mesh 上 nearest-only 选面。用重心坐标生成 `mesh_station_point_mm`，并记录其与冻结 B-rep 点的 `station_projection_error_mm`；传给 A12 的 station 用这个位于输入三角网格上的点，原始 CAD 点同时保留，不能静默替换。
5. `face_source_brep_index` 以外的三角面只作歧义探针，永不作为 fallback。若全局最近候选中另一个 canonical B-rep face 在 station/mesh uncertainty 以内并与最佳投影同距（`abs(d_other-d_best) <= ambiguity_tolerance_mm`），或 B-rep trimmed-face 身份与 triangle lineage 不一致，标 `AMBIGUOUS_FACE_LINEAGE` 并拒绝。不同 face 即使距离更近、法向更合适，也不能取代 station 指定的 face。这样薄壁另一侧、内外壁或自接近面不能被全局 nearest 抢走。
6. 同一 B-rep face 的网格边/顶点可能使相邻 triangles 同距：只有这些候选都具有同一个 source B-rep face、投影点彼此在 `tie_tolerance_mm` 内、且面法线通过角度核对，才按 triangle index 最小者确定性取一个 primary triangle；保留其它同面 candidate ID。不同 B-rep face 的 tie 一律 UNKNOWN。
7. 校验 BREP station normal 与所选 parent triangle 的有向 face normal 一致。建议先用明确配置的 `angle_tolerance_rad = min(15deg, max(5deg, 2*angular_deflection_rad))`；超限 UNKNOWN。内壁向量仍取 B-rep face material-outward 法向（通常指向 cavity），不能翻成 ray 的方向去代替来源方向，也不能拿 SynLab fracture interface normal 当壁法向。

`linear_projection_limit_mm` 应由实际输入参数计算并记录：`target_linear_deflection_mm + 2*weld_tolerance_mm + cad_numeric_tolerance_mm`。这只是每个 station 的局部允许误差；每站还要保存实测 projection error。现有 asset 的 mesh-to-STEP deviation 是有限采样，不能升格为全局 Hausdorff 界。若局部误差超限、站点落到另一面、或所有 v1 stations 未 100% 绑定，整体 `mother_mesh_binding_status=UNKNOWN`，不得产出可供 A12 标为 trusted 的方向证据。

建议单站记录：`station_id`、完整 `canonical_step_file_sha256`、source B-rep face index/role、冻结 `step_point_mm` 和 `outward_from_material`、重求的 trimmed UV 状态与点/法向误差、`parent_triangle_index`（由 parent mesh content hash 命名）、重心坐标、`mesh_station_point_mm`、点到网格误差、所选/同面备选三角 ID、其它 face 的最近距离/歧义判据、normal angle error、状态与 reason。Coverage 明确表示“有限 wall-reference stations 映射比例”，不称 area coverage。

阶段1 可将 parent `surface.npz` 加载成 `trimesh.Trimesh(vertices=vertices_mm, faces=faces, process=False)`，不 repair/reorder；向 A12 传 `mesh_station_point_mm`、规范化 BREP direction、原 station ID。`WallDirectionEvidence` 选择 `source="inner_outer_wall_map"`，证据 provenance 包含 STEP SHA、wall-reference SHA、binding SHA、face/role、parent mesh content SHA 和 classifier。只有校验完成后才置 `trusted=True`。`_trusted_directions` 只是检查几个字符串和 trusted bool，不会验证这些 hash；不可把“填了 trusted=True”当成证据本身。

母 mesh baseline 可令 `source_mesh=result_mesh=parent_mesh`，`ResultSubsetEvidence` 只在两者 exact composite mesh identity 相同后用 identity subset provenance 标记 trusted。检查 A12 两个 mesh health 均 valid：watertight、winding consistent、positive volume、自交检查可用且不相交。按全部 wall stations 调用一次 interval helper，记录原始完整返回值。只有请求、分类、测量 station 数全相等，coverage/measurement coverage 各为 1.0，所有 row 状态与 sampled summary 是预期状态，才通过这个 **finite parent mesh baseline**；永远保留 `global_wall_status=UNVERIFIED` 与 physics UNKNOWN。`probe_offset_mm` 必须满足 A12 自己给的 float32 条件 `probe_offset_mm > 8*merge_tolerance_mm`、`16*merge_tolerance_mm < min_remaining_wall_mm`，并比局部几何特征小；若无可行区间就 UNKNOWN，不能放宽 tolerance 强迫通过。

## 阶段2：parent triangle lineage 到 fragment/result

建图的主键是 `(parent_mesh_content_sha256, parent_triangle_index)`。不能只保存裸 triangle index，也不能只靠 fragment ID 或 closest-point。VesselForge 的每个 triangle 已直接来自 canonical STEP face，因此可查回 `face_source_brep_index[parent_triangle_index]` 和 `body_outer/body_inner` 语义；几何切割中新生 interface triangles 没有 B-rep wall ancestry。

SynLab fracture `tag_source` 已接受 `triangle_ids`，`SourceTaggedResult` 保存 per-vertex `source_tri` 与 barycentric；`SourceResolver` 给出来源、ambiguous、locator distance，`Fragment` 存 `face_origin_kind`、`face_source_tri`、`face_interface_id`。桥接应把 `parent_mesh_content_sha256` 放进输入/事件/裂片的 ancestry metadata，并把来源 ID 命名为 parent triangle（不能与 STEP face index 混淆）。每个 fragment 输出面需持久化 per-corner 或 per-vertex `parent_triangle_id + barycentric + reconstruction_residual_mm`，再存派生的 `source_brep_face_index` 与 `wall_role`。只接受所有角点都能唯一落在同一个 parent triangle 的 inherited `ORIGIN_MOTHER_SURFACE` 面，且重构点残差在记录容差内；不接受现有 majority-vote face source 独自作为证明。跨源三角、来源 mesh id 混合、重心无效、locator ambiguous、残差超限一律 `ORIGIN_AMBIGUOUS` / UNKNOWN。Interface 面永不携带 wall face direction。

到物理 damage 输出的下一跳还需显式 compose `result face/vertex -> clean fragment face/triangle -> parent triangle -> canonical STEP face`。现有 `physical.classify_face_origin` 仅根据 damaged face centroid 的全局 closest clean triangle、容差和 `abs(normal dot)` 写 mother/interface/ambiguous class；它不保存 clean face index 或 parent triangle，也不能单独证明跨薄壁唯一 lineage。需要增加受限候选的 ancestry 映射：先按已继承 lineage 与 declared operation 选可能 parent triangles，再做几何残差验证；几何 nearest 只在该 lineage 子集中使用。若两个不同 B-rep wall faces/inner-outer roles 在误差带内都能解释结果，或裂片跨切口后不能唯一落到来源面，拒绝为 UNKNOWN。对 station 点落在多个 fragment 的切割边、站点 ancestry 丢失或 only-interface hit，输出 `AMBIGUOUS_FRAGMENT` / NOT_MAPPED，不挑一个最近的裂片。

阶段2 A12 调用按明确的 source/result 层次做：

- fracture 后评估指定裂片：source 是经 binding 的完整母 mesh，result 是一个已经证明为该母 mesh material subset 的 fragment；只对 ancestry 明确关联到该 fragment 的固定 wall stations 计量。没有 map 的站点记 NOT_MAPPED/UNKNOWN，不能按 missing interval 当作 perforation。
- damage 后评估指定物理 component：source 是该 component 的确切 clean fragment mesh，result 是对应损伤 mesh；stations 需从已验证的 parent lineage 投影到 clean fragment 的实际 source triangle，方向来自 STEP wall face 及记录的变换。若 result 不是 clean fragment 的 material subset，则不能传 trusted `ResultSubsetEvidence`。
- 不把多裂片的间断 material intervals 相加。A12 helper 将 source interval 内多段 result 判成 `SPLIT_INTERVAL`，剩余长度/相对损失置空；保留 FAIL/UNKNOWN，不合并跨空气间隙。

这一步需要输出独立 `fragment_wall_binding_status`、各源/结果 asset hash、parent mesh SHA、fragment/event/component IDs、face lineage source、mapped/ambiguous/unmapped station counts 和 per-station IDs。映射完成不等于墙厚通过；间隔结果仍按 A12 的 `SAMPLED_PASS/SAMPLED_FAIL/UNKNOWN`，`global_wall_status` 固定 UNVERIFIED。`coverage_fraction` 是实际输入该次 helper 的 station 中可分类比例；另行报告 wall-reference 总站点到此 fragment 的 mapping fraction，不要把二者合成一个“global coverage”。

## 拒绝/降级规则

- 任一 STEP/semantics/wall-reference/surface/lineage hash 不闭合，或 mesh identity 与 `process=False` 加载后的数组不符：UNKNOWN。
- 该 station 的 STEP 点没通过 trimmed face `IN`、B-rep face index/role 改变、face lineage 缺失，或者 only untrimmed-surface projection 命中：UNKNOWN。
- parent triangle 候选只能从别的 B-rep face 找到，薄壁两侧在误差/tie 带中无法区分，多个 distinct face 命中，mesh normal 与 BREP outward normal 不一致：UNKNOWN。
- direction 证据是 fragment/interface face normal、normal 无 source hash/face role 或单位/frame 不明：UNKNOWN。
- parent/fragment face provenance 只有 nearest/majority label，没有 per-corner ancestry 与误差验证；unknown/ambiguous lineage 被当作 wall face：UNKNOWN。
- result subset 没有上游布尔/材料守恒证明，Open3D float32 精度不足，mesh open/inverted/self-intersecting，射线 grazing/unresolved、源区间缺失/有歧义、结果超 source interval：沿用 helper 的 UNKNOWN reason，不自行修补或记 PASS。
- 所有有限 stations PASS 只表示本次采样点上的区间检查。wall-reference 一面一站不能推导 surface area coverage、连续面全局最小厚度、碎片映射完整或物理资格。

## 最小验收顺序（未来实现时执行；本稿未运行）

1. **Hash/单位/索引**：用一个 canonical STEP fixture 经 VF 导出 surface 与 lineage。逐个 SHA 按准确文件核验且保存独立字段；检查 `triangle_count == len(faces) == len(face_source_brep_index)`、索引范围与 wall station face inventory。故意互换 STEP 与 surface hash、lineage 文件，均必须 UNKNOWN。bytes/array identity 改变会使 station triangle ID 命名空间更新或失效。
2. **双壁正向基线**：外半径 10 mm、内半径 8 mm 的封闭 hollow-cylinder STEP，外/内 wall station 都从 frozen v1 face semantics 生成。每条 station 的 trimmed UV 重核、material-outward 法向、face index 与 mesh projection 均通过；外壁 `+radial`、内壁 `-radial`。parent mesh self-baseline 的 sampled interval 是约 2 mm，误差界事先用 `2*linear_deflection + helper.measurement_uncertainty_mm + station projection terms` 写入，不在看到结果后调整。summary 只能是 finite sampled status，global 未验证。
3. **薄壁反向/歧义**：构造小于 mesh projection bound 或跨外/内壁近邻 tie 的 case。请求外壁 station 时只能找外壁 face lineage；若它自身投影失败或另一 face 与它落入 ambiguity band，binding 必须 UNKNOWN。删除/交换 triangle face lineage 也要 UNKNOWN，不能借全网格 nearest 投向内壁后仍通过。
4. **trimmed face 与接缝**：UV 为 ON/OUT、一个站点落在 B-rep face trim edge 或跨两张不同 B-rep face 时 UNKNOWN；同一 B-rep face 的网格 edge tie 可按确定性规则处理，点与法向须一致。确认周期 seam candidate 只在 exact same B-rep face ID 中消歧。
5. **A12 helper 合同**：缺 direction evidence、提供 interface-normal source、错误单位/frame、subset 证据缺失、Open3D 精度条件失败时为 UNKNOWN；baseline 输入 source=result exact parent mesh 时才给 identity subset evidence。保留完整 row/reason/tolerance/hash，不只保留一个 PASS 字段。
6. **fragment ancestry**：通过一次切割得到至少两个 fragment；原母 surface 的 retained faces 可经 parent triangle+barycentric+residual 唯一追到 STEP wall face；新 interface 与 ambiguous faces 没有 wall ancestry。故意将 fragment 三角面顺序改掉但不更新 lineage/hash，必须拒绝。父三角跨裂片或站点落在切口边不能被 majority vote 自动指派。
7. **sample/global 状态隔离**：即使所有 v1 wall stations 都是 `SAMPLED_PASS` 且两种 mapping coverage 都是 1.0，报告仍写 `global_wall_status=UNVERIFIED`、`physical_qualification_status=UNKNOWN`、`global_minimum_wall_claim=false`。若 result 一条 ray 给多个分段，保持 `SPLIT_INTERVAL`，不把各段或裂片间隙相加。

## 实际接口依据与边界

- VF `asset.py:112-148` 先写 canonical STEP、重新 import，再用该对象分类并 `mesh_shape`；triangulation 每个 STEP face 枚举后写 `triangle_sources`。`geometry.py:178-256` 在每个 OCP face 上取得 triangulation，保留 triangle source face，weld 顶点后只同步过滤 degenerate triangles；`schema.py:130-160,166-237` 核验 STEP/semantics hash、face inventory、triangle lineage 长度与范围和 region 对应。这个现存直接 lineage 是阶段1基础。几何QA的 mesh-to-STEP deviation 是有限 edge-midpoint/triangle-centroid samples，不是全局界。
- `semantics.py:47-83,119-155` 在 trimmed UV 内保存 sample point、face-oriented outward normal，并以 global Z 的旋转壁面 normal radial sign 区分 body_outer/body_inner。壁法向从这里的 wall face station 延续；分类 face normal 与 fracture interface normal 必须分开。
- SynLab `wall_intervals.py:55-85,114-184,211-224,280-390,457-662,677-732,759-783` 需要显式 wall directions 与 subset attestation；采用 all-hit intersections、法向事件和 occupancy 来识别材料 intervals，不是最近一次 hit。`station_tol` 还要求 source interval 唯一从 probe offset 起始，split result intervals 返回 FAIL 并且不制造总厚度。A12 当前 evidence 只是字符串/bool contract，桥接 adapter 的哈希与 ancestry 检查是必要前置。
- `fracture/booleans.py:50-103,106-120,451-515` 已有 `triangle_ids`、输出 per-vertex source triangle/barycentric、ambiguity 与 locator distance；`fragment.py:68-103,125-196` 分出 connected component 并写 face origin/source triangle；`runtime.py:193-207` 定义这些 face channels。`physical/api.py:284-397,1132-1213` 当前 map 的 face provenance 没保留 STEP parent tri 外键，所以阶段2需显式 compose，而不能推断已完成。
- 现存 SynLab helper 定向测试源码包含 hollow-box 已知厚度、uniform erosion、perforation、source interval 缺失、grazing、split interval、open/inverted/self-intersecting mesh、精度阈值与 evidence 缺失案例；没有执行这些测试。`docs/a12/open_items.md:32` 记录 helper 仅局部测试且未接入 P03。

## 设计基线源 SHA-256

- 冻结 `wall_reference.py` v1：`ceeeeec791ed1264bd73a2c0e9dd250ab39aa213a97f75725bf2e6eab91c3461`
- VF `semantics.py`: `dfcc366d868c65313bcd5a43faf91d482b89848c2b15d4d9e66158ac291231af`
- VF `geometry.py`: `0c48940d9ef22aabb068a2e7c6e89b4249a7e724d0ade1c8933a6c951e086047`
- VF `asset.py`: `f9c11a60beed1d165431b8ea590c52db382b780479ad262fee1cc5a7be3274d0`
- VF `schema.py`: `b58ae7b3bc5e09b699a36fe57fada12dd969759cf9991bf2749660d6cfbbdfe9`
- SynLab `degrade/wall_intervals.py`: `02799e54cd1567405b43bfbbdfd1044fed609ccfc5be6de88764f3544ce16693`
- SynLab `test_wall_intervals_20261004.py`: `05bb645d63f07ac39153e82f327836d16c25f0365692d7af80771ad7b52394fa`
- SynLab `fracture/booleans.py`: `033b2e6f999a3e9061ea538b4ae923dbe0b91ad167295d7125b1425a46378032`
- SynLab `fracture/fragment.py`: `53a581c5964d7b350a6c938bb188e908adb06e87e4114cbc5914bf6ee1e079fd`
- SynLab `physical/api.py`: `4685fb7d37cddfdd737cfd92c4021691f1a416e208163b80f5f829fc3f518ea9`
- SynLab `schemas/runtime.py`: `080b6e9c5abed88873786f5dce4d654e78072cb71e3e04106ceda17640352609`
- SynLab `docs/a12/open_items.md`: `b48bac656c30a604d5fe2d2568890ec985220dff4d61ba375abbec78436743cc`
