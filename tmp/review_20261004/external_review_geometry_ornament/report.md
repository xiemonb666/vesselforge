# 外部 AI 报告几何与 ornament 核验

审阅日期：2026-10-04。仅核验外部报告 issue ID `#42–#152`、`#193–#201`、`#202–#210` 中与 geometry / ornament / 样本链有关的断言。未修改 source/test/docs/Git，未运行 CAD、pytest、solver 或渲染；只读了冻结源、现存 receipts/JSON/STL 哈希和已保存 PNG。报告中的类别表示证据状态，不等同于合并/验收意见。

## 关键结论

- **没有从报告所选项中确认到 P0/P1 的已发生几何损坏。** 多条把“预览没有显示”升级成“没有任何统计/实现”的断言被现存侧车证据反驳；另有高曲率采样、极端参数 CAD、表面距离纹样映射及 3D relief 安全等未验证风险，不能据此宣称已失败。
- **确认的生产桥接缺口：** `profile_catalog.py` 自身明确写明现有 `build_components(VesselSpec)` 不接 catalog profile（行 7–11）；静态搜索在 `vesselforge/src` 没找到 `build_profile()` 调用。ornament v2 明确只返回 scalar height field、不改 CAD/mesh，冻结清单明确“no asset/schema/mesh integration”，静态搜索也未找到其生产调用点。因此默认 profile 的 OCC/STL 侧车和 2D ornament 图都不能代表进入了生产资产→CAD/mesh→碎片链。
- **0.5 mm 的含义是 OCC `linear deflection` 输入容差，不是 max-edge，也不是 tetra 尺寸。** 真实调用是 `solid.tessellate(0.5, 0.2)`，导出 STL 也是 `tolerance=0.5, angularTolerance=0.2`。三个已存结果都有默认输入的闭合 incidence / 非流形边 / 折叠顶点三角面和 OCC-vs-mesh signed volume 数据；没有 tetra mesh、全边长、面积、局部法向、一致性/自交或曲率误差统计。
- **三个 mesh 证据仅覆盖默认 profile，且由锁定 profile 源 SHA `ff90…`（v1）生成。** 默认参数与 v2 相同，但 v2 新加的窄口 jar 用例 `mouth_diameter=10, wall=6, max_radius=60` 只有 meridian/math 测试，没有 OCC Solid/STL 证据。不能拿三个默认 mesh 为新 v2 回归或全参数范围背书。
- **ornament 预览的上下图差异符合给定 effects：** v1 drawing input 有三个 `paint` field（环带、波带、点阵，paint relief 被约束为 0）和一个 `raised` ring（+0.65 mm）；下图只有后者贡献 relief。图没有 `engraved` 输入，但冻结 v2 测试对一个负 relief 数值点做了断言；这仍不是三维刻蚀或 CAD 验证。
- **纹样的 `theta + z` 是柱坐标参数，不是一般器物表面的等距坐标。** 没有 Jacobian/测地长度校正是当前能力边界；若要求不同半径和斜肩处的 motif 保持相同物理间距，这是一个确认的桥接/功能缺口。当前代码支持坐标空间规则纹样，不应把这种坐标设计本身称为数值 bug。
- **缝合证据分层：** v2 有三种字段在 `-π+ε` / `+π-ε` 两侧的值、opacity、height seam 测试；无 gradient 或最终 mesh seam 测试。选定示例使用正 edge softness；但一般 API 允许 softness=0，返回硬阈值，所以不能将这个值测试推广成任意参数下的可微/网格无缝保证。
- **显示色彩有一个确定的诊断限制：** drawing script 在 `linear RGB` 中 alpha 混色后直接把值传给 `imshow`，未作 linear→sRGB 显示编码。linear 场运算与范围测试仍然有效，但 PNG 颜色外观没有经显示传递函数校准，不能当作真实颜料/材质色彩证据。`imshow(interpolation="nearest")` 的像素硬边也不能推出底层平滑 scalar field 一定产生几何硬边。
- **发现一个独立的 P2 参数类型边界 bug：** profile 的 `_finite_number` 明确拒绝内建 `bool`，但 `np.bool_(True)` 不属于 Python `bool`，会走 `float(value)` 转成 `1.0`。静态最小反例 `build_profile("bowl", wall_thickness_declaration_mm=np.bool_(True))` 会把布尔误收为 1 mm；按默认 bowl 的其它参数，1 mm 满足其几何比例约束。未执行此输入。冻结测试只覆盖 Python `True` 且把它放在 height 参数上，不能覆盖该反例。

## ID 分组核验

状态定义：

- `CONFIRMED_CURRENT_GAP`：当前代码/保存证据明确缺失的生产能力或资格边界。
- `RISK_NOT_TESTED`：报告指出的风险尚未被该组证据测试；这不表示已发生失败。
- `EXISTING_RAW_EVIDENCE`：存在源、receipt、统计或测试证据，范围以描述为准。
- `DIAGNOSTIC_SCOPE_NOT_BUG`：预览本来就声明的诊断范围，不是实现损坏。
- `INCORRECT_INFERENCE`：把图上不可见或单样本现象推断成实现错误/全局失败，超出证据。

| 外部 ID | 核验状态 | 结论与边界 |
|---|---|---|
| #42 | `DIAGNOSTIC_SCOPE_NOT_BUG` | 图标题和 `mesh_inputs.json` 都标为 `GEOMETRY-ONLY` / coarse preview，并明确不作 wall、curvature、solver、实物或物理资格结论。该范围声明正确，不是隐藏的 PASS。 |
| #43–45 | `INCORRECT_INFERENCE`; `RISK_NOT_TESTED` | `#43` 仅看图确实不知道参数，但完整生成脚本/JSON 明确为 OCC linear deflection 0.5 mm、angular tolerance 0.2 rad。`#44` 把它解释成体网格尺寸不成立：没有 tetra mesher。`#45` 从视觉三角边大于 0.5 推断超限也不成立，因为 0.5 不是 max edge。保存摘要没有最大三角边统计，若将来需要该阈值，则属未测试项。 |
| #46 | `DIAGNOSTIC_SCOPE_NOT_BUG` | 只有表面三角化、没有 tetra，artifact 的 scope/solver_used=false 已写明。若目标是 fracture-ready volume mesh，是后续能力，不是该预览声称完成的工作。 |
| #47–49 | `CONFIRMED_CURRENT_GAP`; `RISK_NOT_TESTED`; `DIAGNOSTIC_SCOPE_NOT_BUG` | profile 只声明对应控制高度上的 radial meridian offset 与底部 datum；没有全局/法向最小 wall map。v2 还显式标为非物理资格。曲率误差和全参数 surface 壳体分离没有测试；但这里不是曲面法向 offset 算法，报告将其描述成 offset 构造的通用失效尚无失败反例。默认三例各有 `solid.isValid()`、一个 solid/一个 shell 的 OCC 证据。 |
| #50–52 | `INCORRECT_INFERENCE`; `EXISTING_RAW_EVIDENCE` | JSON 已报告三个 mesh 的 boundary edge=0、nonmanifold edge=0、welded-vertex degenerate triangle=0、watertight edge incidence=true。没有单独 `boundary loop count` 字段；0 条 boundary edge 已排除该网格上的开边界环。 |
| #53–57 | `RISK_NOT_TESTED`; `EXISTING_RAW_EVIDENCE` | duplicate triangle 未统计；“degenerate=0”只按 weld 后三角形三个 vertex ID 是否互异计数，不是面积/近零面积检查；未报告局部 winding/normal 一致性或 mesh self-intersection。`solid_count=1`/`shell_count=1` 是 OCC 计数，不是 mesh connected-component 图统计。默认 B-rep 有 `isValid` 证据，但不足以替代这些 mesh 诊断。 |
| #58 | `INCORRECT_INFERENCE`; `EXISTING_RAW_EVIDENCE` | 已保存 OCC volume 和 mesh signed volume。相对差值：bowl −0.0037795、beaker −0.0049677、jar −0.0032372，均在摘要设定的 1% 内。 |
| #59–61 | `RISK_NOT_TESTED` | 没有 CAD/mesh surface-area、质心或惯量误差对照。它们是未测指标；在几何-only preview 未宣称物理资格的前提下，不构成失败证据。 |
| #62–72 | `EXISTING_RAW_EVIDENCE`; `RISK_NOT_TESTED` | 保存的 mesh preview 可定性看到轴向拉长/网格密度变化、肩/足等过渡和圆周多边形化；具体哪片三角形的 aspect ratio、gradation、曲率或误差多大，JSON 未量化。视觉观察不等于质量失败。当前 OCC angular tolerance 0.2 rad 和 coarse surface preview 足以解释多边形化；没有局部误差一致性资格。 |
| #73–83 | `EXISTING_RAW_EVIDENCE`; `DIAGNOSTIC_SCOPE_NOT_BUG`; `RISK_NOT_TESTED` | 三个 profile 确实是 bowl/beaker/jar 的单母线旋转体；不含椭圆、偏心、倾斜、手作不规则或非旋转附件。这是当前三个 analytic starter envelope 的特征/覆盖限制。没有数据证明它们已进入大规模训练，所以 domain shortcut 是条件风险，不能报成已观察到的训练问题。 |
| #84–87 | `EXISTING_RAW_EVIDENCE`; `RISK_NOT_TESTED` | `build_profile` 对每次调用检查有限范围、上下限、inner/outer profile 简单性与闭合 outline 自交/面积；不是“完全没有合法性检查”。但保存 OCC mesh 只取三个默认参数，未做范围采样/Fuzz，也未证明极端参数经 OCC 和 tessellation 均有效。特别是新 v2 窄口 jar regression 只有数学 profile test，未进 OCC。可作为后续 CAD 测试向量的边界例：bowl `(H=30,R=12,mouthD=17.72,wall=0.5,base=0.5)` 满足代码中的标量比例边界（mouth radius + wall 恰为 `0.78R`），实际 OCC 有效性/采样效果本轮不可核验。它表明风险存在，不是失败反例。 |
| #88–90 | `INCORRECT_INFERENCE`; `DIAGNOSTIC_SCOPE_NOT_BUG` | 参数结构分别含 height/radius/mouth/wall/base；v2 测试也有独立改变 beaker dimensions 与窄口 jar case。它们仍有比例约束，不能说统计上完全独立。底厚与侧壁 radial declaration 是分开的输入/公式，但二者都不是真实全局最小壁厚。外轮廓含 lip radius/foot 起始结构；没有专门的真实器物增厚/复杂足型参数，这属于原型覆盖范围。 |
| #91–96 | `INCORRECT_INFERENCE`; `EXISTING_RAW_EVIDENCE`; `DIAGNOSTIC_SCOPE_NOT_BUG` | drawing 输入可追溯：`level-ring`、`wave-band`、`repeated-motifs` 均为默认 `effect="paint"`、relief=0；只有 `raised-ring` 有 +0.65 mm。因此颜料图有点阵/波纹/水平带而 relief 图只显示 raised band 是按 effect 分离的预期，不是数据丢失。v2 数据类型分开 `region/pigment/base/relief`，paint/raised/engraved 符号约束明确。图把 pigment 与 relief 放在一起比较，图例不足可改善；代码语义本身不歧义。 |
| #97–99 | `INCORRECT_INFERENCE`; `EXISTING_RAW_EVIDENCE`; `DIAGNOSTIC_SCOPE_NOT_BUG` | 该绘图脚本没有 `engraved` 字段；colorbar 的 ±0.7 是绘图固定范围，唯一 raised amplitude 是 +0.65，故此预览不应有负 relief。保存 v2 测试有一个负幅值 engraved 数值断言和未知墙厚时 fail-closed；它没有验证 CAD engraving。单个窄 raised ring 造成稀疏 relief 是这个例子的构造结果，不代表所有 field 都稀疏。 |
| #100–104 | `EXISTING_RAW_EVIDENCE`; `RISK_NOT_TESTED` | v2 source 明确后来 pigment 按 alpha-over、coverage 取 union、各 layer relief signed-additive；`FieldStackEvaluation.layers` 保留每个 layer 的 mask/weight/pigment/relief，另有 merged mask/weight。绘图只显示最终 pigment 与总 relief，不展示每层 mask/overlap。当前 6 项 v2 测试没有针对两层重叠时的期望 RGB/alpha/height 做精确例，因此“规则没有实现”不成立，“交叠数值回归覆盖不全”成立。 |
| #105–109 | `RISK_NOT_TESTED`; `CONFIRMED_CURRENT_GAP` | 源有 merged mask/weight 和总 relief，但没有独立数值报告；不等于数组不存在。无 relief gradient/Hessian、曲率或 cusp 统计。关键边界是当前没有三维 relief surface，也无 stack-level wall/cusp qualification，因此这些三维安全指标确未建立。stack height 按 layer additive；没有总 relief cap/stack geometry gate，未来若叠加多个 engraved field 必须对**总和**做 wall gate；现有 `qualify_geometry_field` 只接单个 `FieldEvaluation`，并明确永不返回 `geometry_qualified=True`。这是桥接前置缺口，不是当前生成了坏 Solid。 |
| #110–113 | `INCORRECT_INFERENCE`; `RISK_NOT_TESTED` | 保存图使用 `imshow(..., interpolation="nearest")`；绘图四 field 的 ring/wave softness 为默认 0.35 mm、motif softness 为 0.08，因此图中像素硬边不能证明底层示例 field 不连续，更不能证明几何尖边。source 对通用 API 允许 softness=0 并返回硬阈值；该配置若映射成 relief 确有尖锐边界风险。当前没有 3D 映射或曲率检验。 |
| #114–122 | `CONFIRMED_CURRENT_GAP`; `RISK_NOT_TESTED` | source 从 rest XYZ 取 `theta=atan2(y,x)` 和 `z`，没有 surface parameterization/Jacobian/测地度量。轴对称表面上周向距离为 `r(z) dθ`，母线长度为 `sqrt(1+(dr/dz)^2) dz`；同一角间距会随半径变物理长度，斜肩的 z 宽度也非沿面宽度。若产品要求全表面物理 motif 尺寸恒定，此限制是实际缺口；当前代码只定义 cylindrical/rest-coordinate pattern，不是算错其自身坐标公式。 |
| #123–127 | `EXISTING_RAW_EVIDENCE`; `RISK_NOT_TESTED`; `INCORRECT_INFERENCE` | v2 test 在 `±π` 邻近点对三种 field 的 `region_weight / relief / pigment_opacity` 比较到 `1e-7`；stack pigment 与 relief 使用同一个每层 evaluation/weight，因此 #123/#126 的 value path 有证据。没有 derivative 或最终 mesh seam test。绘图的 waving `repeat_count=6` 是整数，smoothstep输入的数学表达式周期；但通用硬阈值配置梯度可不存在，且无 mesh seam 证据。不能把“没在图上报告”说成 value seam 失效。 |
| #128–142 | `EXISTING_RAW_EVIDENCE`; `RISK_NOT_TESTED`; `DIAGNOSTIC_SCOPE_NOT_BUG` | v1 示例是规则、确定的 ring/wave/motif；source 目前未提供磨损、缺纹、随机相位/尺寸、颜料扩散或真实手工误差模型。作为 starter diagnostic 不是 bug；若打算大量训练，合成器风格捷径是合理的条件风险，但没有训练集、真实分布或模型结果支持“已产生 shortcut”。 |
| #143–152 | `CONFIRMED_CURRENT_GAP`; `RISK_NOT_TESTED`; `DIAGNOSTIC_SCOPE_NOT_BUG` | 无 ornament→真实 CAD surface displacement→remesh/volume mesh 的 producer。profile source 也注明生产 builder 尚不接 catalog。故 relief 后 watertight、内壁穿透、负厚度、自交、法向或 tet 保留当前不可验证；这些是未实现链路上的验收要求，不能写作已发生的网格失败。`profile_catalog` 新增 v2 regression 也未包含在保存的三份 OCC 默认网格里。 |
| #193–201 | `EXISTING_RAW_EVIDENCE`; `CONFIRMED_CURRENT_GAP`; `RISK_NOT_TESTED` | 当前 profile 来源明确是 analytic starter、非实物测量。参考目录是 5 条 collection/source 索引；静态审阅说明没有图像、CAD、scan，high-fidelity synthetic count=0。故真实 vessel 形态、wall、motif、fracture 分布对照确实未建立；但“会导致模型 shortcut”仍是没有数据训练实验支持的风险，不是已确认后果。 |
| #202–204 | `INCORRECT_INFERENCE`; `EXISTING_RAW_EVIDENCE`; `RISK_NOT_TESTED` | “图本身无 PASS/FAIL 数值”成立；“现存证据完全没有资格指标”不成立。mesh sidecar JSON 已有默认三例 OCC valid、topology 和 volume PASS_GEOMETRY_ONLY 数值；ornament 有冻结 v2 targeted pytest 6 passed（仅字段/门控测试），无 surface distortion/wall/3D资格指标。按各自实际范围表述。 |
| #205–207 | `DIAGNOSTIC_SCOPE_NOT_BUG`; `RISK_NOT_TESTED` | #205 PG-Frag recompile/runtime 状态不在本审阅范围，且未检查其动态源。#206–207 是跨所有模块的 completion/pass 语义判断，当前证据不足以全局核验；本范围自身至少把 `GEOMETRY_ONLY_CANDIDATE`、`PASS_GEOMETRY_ONLY_CANDIDATE_MESHES`、`HEIGHT_FIELD_ONLY` 与 `geometry_qualified=false` 写得较明确。 |
| #208–210 | `CONFIRMED_CURRENT_GAP`; `INCORRECT_INFERENCE`; `RISK_NOT_TESTED` | 在已查 `vesselforge/src` 中 `build_profile()` 和 `evaluate_ornament_*()` 无生产调用点，且没有共同的 geometry→ornament→mesh样本 ID，因此 scoped end-to-end lineage 缺口成立。报告称“完全没有 hash”不对：profile/测试冻结 hash、mesh 输入 hash、每个 STL SHA、preview SHA、ornament v2 source/test SHA 都存在；缺的是贯通关联 ID/下游失效策略。跨整个系统的 cache invalidation 本轮不可证明。 |

## 静态复核发现的 P2 输入边界问题

- 文件：[profile_catalog.py](C:/Users/xiemo/Desktop/ShardForge/vesselforge/src/vesselforge/profile_catalog.py:117)，SHA-256 `4344283912f4574dd28f3520d04e4b6d5414f37b681b29add7091cd32e44f864`。
- `_finite_number` 只用 `isinstance(value, bool)` 拒绝布尔；对 `np.bool_(True)` 会落入 `float(value)` 归一化成 `1.0`。最小静态反例：`build_profile("bowl", wall_thickness_declaration_mm=np.bool_(True))`。默认 bowl 上 wall=1 mm 符合 wall 上限、口半径和 radius 比例约束，因而可被当成合法输入继续造 profile。这里是类型 guard 逃逸，不是几何自交证明；没有执行该调用。

## 保存证据与来源哈希

| 项目 | 路径/结论 | SHA-256 |
|---|---|---|
| 外部报告 | `C:/Users/xiemo/.codex/attachments/91ec634d-1d25-4a0f-b3d6-8541952e5011/已粘贴的文本.txt` | `0b3544d4b2a02d8132660834ea5a3d44c71a2054836d3ffeb8ac29756a771bad` |
| frozen profile v2 module/test | `vesselforge/src/vesselforge/profile_catalog.py`、`vesselforge/tests/test_profile_catalog.py` 与 freeze 记录相符；保存 stdout 为 **15 passed**，未重跑 | module `4344283912f4574dd28f3520d04e4b6d5414f37b681b29add7091cd32e44f864`; test `e1400b7ddff53a64e3dc31321481a6a2fb9e21efc1c43a4ca363eeb7e514a9dd` |
| `geometry.py` + OCP candidate builder | geometry `0c48940d9ef22aabb068a2e7c6e89b4249a7e724d0ade1c8933a6c951e086047`; builder `fddbd332c8fd804d26c1cb840b962c4d30642717396052914797d6fa354f5886`；receipt 记录 CadQuery 2.8.0 | — |
| mesh 输入/摘要/PNG | `mesh_inputs.json` 锁定 profile SHA `ff90a8f1…`（v1）；`candidate_meshes.json` 为其现存输出 | inputs `4ef81ae0fa85c424fd64da5631dee333474ed6082b6bb5a1fa2f08d447e1faad`; summary `20de2218ce17b36726969c4e03984ebc3191a2e360a1342fe52c162ccec7f39b`; PNG `d4c210322367406bd33e6568d962a130e7472f21405a5b90a90bd70c92619f76` |
| mesh STL | bowl / beaker / jar | `51749d798e84b939a232ebaa890ff0fdc4b48f7a8d0e8e948feef9f33de4f452`; `9687fa0914aaadcf3d53d3f9cfcf7f566ce9e07e3ef6fb34bc852fbde77f1ae2`; `0955465dd5d7e546fb102d3077964fd34838cae8b507007991dce44cfdf94102` |
| frozen ornament v2 module/test | `ornament_fields/v2_freeze/ornament_fields.py` / `test_ornament_fields.py`; saved receipt says **6 passed**, before/after hashes match; no rerun | `6f9885f805f78ae4df283bbabd0e4cc1f5b8e3c2e12e606c966a06b5aff096ee`; `7cec79dfce6a867d70dbfc786d3d04b38b3cece47be2f6d6fc20f3987bafc022` |
| v1 plot + saved field preview | plot source hash is recorded in render receipt; receipt does **not** record imported ornament module SHA. No raw field array/JSON is saved. Plot output hash is recorded. | plot `0a9e9e6cce930acc30525f2f39fee454542a465f2dde9de26379fce2f1fd3c63`; PNG `7f05a6aa3db708afc01b0bfef420e59fcb6084bdcf2eae5594d90d224039fdc1` |
| reference inventory | static review says 5 collection IDs/URLs match; no images/CAD/scans, high-fidelity synthetic vessel count remains 0 | JSON `9a93a382003cb4c5809e408ecacfd4125a480bd6bde009b51bb28e1605ecf3e1` |

### 复核不可声称的项目

本轮没有读取/核验 PG-Frag 动态执行状态、训练集、真实器物图片/扫描或 3D ornament displacement。三个 mesh 是保存的 OCC 默认旋转体 candidate，不是三件真实考古器物；参考资料索引本身不构成真实性/测量资格。报告作者提及的图像只能作为显示证据，不能替代 raw field array、全表面几何分析或真实样本链。最终接受与后续实现优先级由 root 决定。
## 逐 issue 主分类与逐条依据

所有分配 issue ID 各指定一个主状态，下面各行可与上面的分组论证互相索引。分类数以 issue 个数计，共 129 项，不把一个 issue 的次级风险重复计数。

| 主状态 | issue 数 |
|---|---:|
| CONFIRMED_CURRENT_GAP | 11 |
| RISK_NOT_TESTED | 45 |
| EXISTING_RAW_EVIDENCE | 34 |
| DIAGNOSTIC_SCOPE_NOT_BUG | 24 |
| INCORRECT_INFERENCE | 15 |

| Issue | 主状态 | 逐条依据 |
|---:|---|---|
| #42 | DIAGNOSTIC_SCOPE_NOT_BUG | 标题和输入清单都限定 geometry-only coarse preview，明确排除 wall、curvature、solver、real-vessel 与 physical qualification。 |
| #43 | EXISTING_RAW_EVIDENCE | 完整脚本/JSON记录 OCC linear deflection=0.5 mm、angular tolerance=0.2 rad；仅凭PNG确实看不出这些参数。 |
| #44 | DIAGNOSTIC_SCOPE_NOT_BUG | 0.5不是tet size；未运行 tetra mesher，不能从表面预览推断体网格精度。 |
| #45 | INCORRECT_INFERENCE | linear deflection不是max-edge，视觉上边长超过0.5不代表容差失守；摘要未保存最大边长统计。 |
| #46 | DIAGNOSTIC_SCOPE_NOT_BUG | artifact scope就是表面三角化，没有tetra volume mesh，且solver_used=false。 |
| #47 | CONFIRMED_CURRENT_GAP | 只有radial meridian wall声明和base datum，没有经几何验证的全局/法向最小壁厚场。 |
| #48 | RISK_NOT_TESTED | 默认三个B-rep各有valid/one-solid/one-shell结果，但没有全参数或正式inner/outer间距资格证明。 |
| #49 | RISK_NOT_TESTED | 未测高曲率局部误差；profile_catalog做同高程径向偏移，旧fixed geometry的杯身则另用meridian normal miter offset，二者不能混称。 |
| #50 | EXISTING_RAW_EVIDENCE | 三个mesh sidecar均记录boundary_edges=0及watertight_edge_incidence=true。 |
| #51 | EXISTING_RAW_EVIDENCE | 三个mesh sidecar均记录nonmanifold_edges=0。 |
| #52 | EXISTING_RAW_EVIDENCE | 没有独立loop字段，但boundary_edges=0足以排除该统计网格中的开放边界环。 |
| #53 | RISK_NOT_TESTED | candidate mesh summary未做重复三角面/重复face检查。 |
| #54 | RISK_NOT_TESTED | degenerate计数只测weld后顶点ID重合，不测非重复共线零面积或近零面积。 |
| #55 | RISK_NOT_TESTED | 正signed volume是整体取向信号，不等于逐三角翻转或局部法线一致性检查。 |
| #56 | RISK_NOT_TESTED | 没有mesh self-intersection诊断；默认OCC shape valid不能代替该离散网格检查。 |
| #57 | EXISTING_RAW_EVIDENCE | OCC摘要有solid_count=1、shell_count=1；mesh graph connected-component 数仍未统计。 |
| #58 | EXISTING_RAW_EVIDENCE | OCC和mesh signed-volume及相对误差已保存，三例均在1%内。 |
| #59 | RISK_NOT_TESTED | 无OCC与mesh surface-area差异统计。 |
| #60 | RISK_NOT_TESTED | 无CAD/mesh centroid差异统计。 |
| #61 | RISK_NOT_TESTED | 无inertia差异统计。 |
| #62 | EXISTING_RAW_EVIDENCE | Beaker长轴向三角形可在保存PNG中定性观察；未量aspect ratio。 |
| #63 | EXISTING_RAW_EVIDENCE | Jar肩部triangulation外观可在保存PNG观察；未量长宽比或局部误差。 |
| #64 | EXISTING_RAW_EVIDENCE | Jar颈部呈轴向长条分片可定性观察；未量mesh quality。 |
| #65 | EXISTING_RAW_EVIDENCE | Bowl网格尺寸/分布变化可见，但未量化其尺度梯度。 |
| #66 | RISK_NOT_TESTED | 没有全mesh gradation统计；视觉变化本身不构成失效。 |
| #67 | EXISTING_RAW_EVIDENCE | 保存形体可见小底足与主体的轮廓尺度过渡；没有集中误差/应力证据。 |
| #68 | EXISTING_RAW_EVIDENCE | Jar底足到腹部有设计轮廓转折；未测曲率连续性或网格误差。 |
| #69 | EXISTING_RAW_EVIDENCE | Jar腹部到细颈的快速缩径由分析母线定义；是否曲率过急无资格指标。 |
| #70 | EXISTING_RAW_EVIDENCE | Beaker口沿附近轮廓转折可见；这只是图形观察，不是薄壁失效。 |
| #71 | RISK_NOT_TESTED | 未报告高曲率和直壁区的偏差对照或Hausdorff误差。 |
| #72 | EXISTING_RAW_EVIDENCE | 0.2 rad角度请求下口沿多边形化在预览可见，符合coarse preview范围。 |
| #73 | EXISTING_RAW_EVIDENCE | 当前三个profile由单母线绕Z轴旋转，轴对称是源定义。 |
| #74 | EXISTING_RAW_EVIDENCE | 三个家族当前主要差异在母线，不是非旋转拓扑附件。 |
| #75 | DIAGNOSTIC_SCOPE_NOT_BUG | 无椭圆截面是当前旋转体starter profile范围限制。 |
| #76 | DIAGNOSTIC_SCOPE_NOT_BUG | 无偏心是当前固定轴旋转profile的设计结果。 |
| #77 | DIAGNOSTIC_SCOPE_NOT_BUG | 无倾斜轴是当前固定轴旋转profile的设计结果。 |
| #78 | DIAGNOSTIC_SCOPE_NOT_BUG | 没有非均匀口沿参数或实测证明；starter profile并未承诺此特征。 |
| #79 | DIAGNOSTIC_SCOPE_NOT_BUG | 当前母线没有随机凹陷/鼓包，这属于覆盖范围限制。 |
| #80 | DIAGNOSTIC_SCOPE_NOT_BUG | 当前profile明确是analytic envelope而非手工器形重建。 |
| #81 | DIAGNOSTIC_SCOPE_NOT_BUG | 当前没有把手、流、盖或复杂非旋转附件生成器。 |
| #82 | RISK_NOT_TESTED | 没有训练集或模型结果证明轴对称先验已造成shortcut；只有条件性数据集风险。 |
| #83 | EXISTING_RAW_EVIDENCE | 默认三个CAD结果各为一个solid/一个shell，profile母线产生不同表面形态。 |
| #84 | EXISTING_RAW_EVIDENCE | 每次build_profile均执行输入范围、2D profile简单性和闭合截面检查；但这不是参数fuzz。 |
| #85 | RISK_NOT_TESTED | 默认三例不覆盖边界组合；v2窄口jar只跑了profile数学测试，没有实际OCC solid证据。 |
| #86 | RISK_NOT_TESTED | 保存证据中没有极端参数fuzz或随机profile CAD构建。 |
| #87 | RISK_NOT_TESTED | 参数声明范围较宽，但CAD摘要只覆盖三个默认尺度。 |
| #88 | INCORRECT_INFERENCE | height/radius/mouth/wall/base是单独参数，但受mouth/radius和wall/radius比例约束，不能称完全解耦。 |
| #89 | INCORRECT_INFERENCE | base datum与side radial declaration是分开输入与公式；两者均非实测全局最小厚度。 |
| #90 | DIAGNOSTIC_SCOPE_NOT_BUG | 当前有基本lip radius与foot轮廓点，但没有专门的真实器物口沿/足部增厚模型。 |
| #91 | INCORRECT_INFERENCE | 上图pigment与下图relief确实不同，但源输入把paint和raised分开，差异是设计语义。 |
| #92 | INCORRECT_INFERENCE | 点阵field为paint，按contract relief恒为0，不能据此判为点阵数据丢失。 |
| #93 | INCORRECT_INFERENCE | 波带field为paint，未要求产生relief；图中未输入wave raised layer。 |
| #94 | INCORRECT_INFERENCE | 水平paint ring与一个raised ring分属z=18和z=43，只显示raised ring有高度是预期。 |
| #95 | INCORRECT_INFERENCE | v2 source明示paint/raised/engraved与pigment/mask/relief分通道，代码语义已明确。 |
| #96 | INCORRECT_INFERENCE | field API区分视觉颜料与signed scalar displacement；图示布局可改进但模块contract不含糊。 |
| #97 | EXISTING_RAW_EVIDENCE | v1 plot只有+0.65 mm raised ring，vmin/vmax是绘图固定范围；该图自然没有负值。 |
| #98 | RISK_NOT_TESTED | v2单点测试证明negative scalar height数值路径，但没有3D engraving/CAD验证。 |
| #99 | DIAGNOSTIC_SCOPE_NOT_BUG | 示例只放一个窄raised band，稀疏relief是输入构造结果，不代表全API。 |
| #100 | EXISTING_RAW_EVIDENCE | stack代码定义later-pigment alpha-over、coverage union、signed relief additive并保留layers。 |
| #101 | EXISTING_RAW_EVIDENCE | source已有ordered layer compositing规则；PNG本身没有独立层优先级诊断。 |
| #102 | INCORRECT_INFERENCE | Per-layer masks/weights保存在FieldStackEvaluation.layers；未画出来不等于数据被覆盖丢失。 |
| #103 | DIAGNOSTIC_SCOPE_NOT_BUG | 当前contract定义叠加规则而非冲突状态；交叠数值回归覆盖仍有限。 |
| #104 | EXISTING_RAW_EVIDENCE | 每个layer保留region_mask；预览没有逐层显示它们。 |
| #105 | EXISTING_RAW_EVIDENCE | merged boolean mask和region_weight存在于stack输出；未保存单独范围摘要。 |
| #106 | CONFIRMED_CURRENT_GAP | 总relief做加法且无stack-level wall gate或总高度限幅；当前只返回height field，不生成几何。 |
| #107 | RISK_NOT_TESTED | 没有梯度场/有限差分或几何法向坡度诊断。 |
| #108 | RISK_NOT_TESTED | 没有二阶导、曲率或高频平滑性测试。 |
| #109 | CONFIRMED_CURRENT_GAP | 无displaced surface，所以当前不能证明最终三维纹饰边缘没有尖点。 |
| #110 | INCORRECT_INFERENCE | 绘图用nearest像素；当前图中field softness为正，像素硬边不证明scalar field硬跳变。 |
| #111 | INCORRECT_INFERENCE | 黑圆点的栅格边缘不能独立证明底层coverage不连续。 |
| #112 | INCORRECT_INFERENCE | 波带边缘外观受nearest raster影响，脚本默认edge_softness=0.35 mm。 |
| #113 | RISK_NOT_TESTED | 若几何端采用允许softness=0的输入，relief会有硬边；当前示例及CAD端均未生成/检查。 |
| #114 | CONFIRMED_CURRENT_GAP | 纹样坐标取atan2与z，没有surface arclength/Jacobian映射。 |
| #115 | EXISTING_RAW_EVIDENCE | 轴对称面周向弧长为r(z)dtheta，故固定角距的毫米间距随半径变化。 |
| #116 | RISK_NOT_TESTED | Jar腹/颈实际纹样尺寸畸变未用三维面场量测；只可从公式推出风险。 |
| #117 | EXISTING_RAW_EVIDENCE | 斜母线上的表面长度因子为sqrt(1+(dr/dz)^2)，code没有把它用于z宽度。 |
| #118 | RISK_NOT_TESTED | Jar肩部纹样的最终拉伸/压缩幅度没有surface metric数据。 |
| #119 | RISK_NOT_TESTED | Bowl曲面实际纹样畸变未量测；coordinate-space限制确定，程度未测。 |
| #120 | CONFIRMED_CURRENT_GAP | 没有从rest grid到真实3D surface的Jacobian或局部面映射。 |
| #121 | RISK_NOT_TESTED | 局部面积畸变没有计算或报告。 |
| #122 | RISK_NOT_TESTED | 局部长度畸变没有计算或报告。 |
| #123 | EXISTING_RAW_EVIDENCE | v2 test在±pi邻近点比较三类field的weight/relief/opacity到1e-7。 |
| #124 | EXISTING_RAW_EVIDENCE | 图上裁切motif不是 seam失败证据；值seam有单元测试，mesh seam没有。 |
| #125 | RISK_NOT_TESTED | 没有gradient seam test；整数频率sine公式周期，但通用zero-softness参数不保证可微。 |
| #126 | EXISTING_RAW_EVIDENCE | 同一layer evaluation/weight同时生成pigment opacity与relief，使用相同角周期公式。 |
| #127 | RISK_NOT_TESTED | 没有纹样参数seam与真实surface mesh seam的联合测试。 |
| #128 | EXISTING_RAW_EVIDENCE | 保存的motif示例规则等距、同参数重复。 |
| #129 | EXISTING_RAW_EVIDENCE | RepeatedMotif源码定义规则重复，不含单独尺寸扰动。 |
| #130 | EXISTING_RAW_EVIDENCE | WavingBand中心线是指定整数repeat_count的正弦。 |
| #131 | EXISTING_RAW_EVIDENCE | GeometricRingBand是固定z中心与宽度的水平环带。 |
| #132 | DIAGNOSTIC_SCOPE_NOT_BUG | starter field没有局部尺寸随机化功能；不是当前demo contract。 |
| #133 | DIAGNOSTIC_SCOPE_NOT_BUG | 当前模式没有随机线宽。 |
| #134 | DIAGNOSTIC_SCOPE_NOT_BUG | 当前plot input没有随机相位扰动。 |
| #135 | DIAGNOSTIC_SCOPE_NOT_BUG | 当前plot input没有随机缺失motif。 |
| #136 | DIAGNOSTIC_SCOPE_NOT_BUG | 当前field API没有磨损模型。 |
| #137 | DIAGNOSTIC_SCOPE_NOT_BUG | 当前field API没有断纹模型。 |
| #138 | DIAGNOSTIC_SCOPE_NOT_BUG | 当前field API没有颜料扩散/模糊模拟。 |
| #139 | DIAGNOSTIC_SCOPE_NOT_BUG | 当前field API没有人工绘制噪声。 |
| #140 | DIAGNOSTIC_SCOPE_NOT_BUG | 当前pattern relief振幅不是局部随机深度模型。 |
| #141 | RISK_NOT_TESTED | 没有随surface curvature调整pattern或制作误差的模型/验证。 |
| #142 | RISK_NOT_TESTED | 合成器风格shortcut只对未来训练集成立；目前无训练集或模型证据。 |
| #143 | CONFIRMED_CURRENT_GAP | 无ornament field到生产CAD surface的调用/位移/remesh集成。 |
| #144 | RISK_NOT_TESTED | 没有relief三维化后watertight的mesh可供检查。 |
| #145 | RISK_NOT_TESTED | 没有三维内壁穿透/间隙分析。 |
| #146 | RISK_NOT_TESTED | 没有三维engraving总深度/负壁厚资格。 |
| #147 | RISK_NOT_TESTED | 没有relief面自交检查。 |
| #148 | RISK_NOT_TESTED | 没有relief mesh局部法向一致性测试。 |
| #149 | RISK_NOT_TESTED | 没有后续volume mesher保留relief的证据。 |
| #150 | RISK_NOT_TESTED | 没有细纹样在tetrahedralization后保留的证据。 |
| #151 | RISK_NOT_TESTED | 没有pattern feature size对surface triangle edge size的对照。 |
| #152 | RISK_NOT_TESTED | 当前无最终实体证据排除小纹样只存在于scalar field。 |
| #193 | EXISTING_RAW_EVIDENCE | 当前只保存三类analytic profile与规则field示例；组合空间确实窄。 |
| #194 | RISK_NOT_TESTED | 类间共享生成规则可能造成domain shortcut，但无数据集或模型实测。 |
| #195 | RISK_NOT_TESTED | 合成风格识别风险未由训练/评估实验确认。 |
| #196 | CONFIRMED_CURRENT_GAP | 审阅的reference索引无真实样本分布对照数据。 |
| #197 | CONFIRMED_CURRENT_GAP | 无真实与合成几何统计对照；source明确profile不是实物测量。 |
| #198 | CONFIRMED_CURRENT_GAP | 无真实器物壁厚分布或其qualified measurements。 |
| #199 | CONFIRMED_CURRENT_GAP | 无真实纹样尺度数据/分布对比。 |
| #200 | RISK_NOT_TESTED | fracture morphology分布超出已审几何/ornament证据，没有比对数据。 |
| #201 | RISK_NOT_TESTED | 真实陶片fragment count/area/curvature对照在本证据中未建立。 |
| #202 | DIAGNOSTIC_SCOPE_NOT_BUG | PNG图本身没有数值层；侧车JSON/测试仍需与图一起读。 |
| #203 | INCORRECT_INFERENCE | geometry图上没有PASS/FAIL，但mesh summary旁车已存OCC、topology、volume指标。 |
| #204 | RISK_NOT_TESTED | ornament图无Jacobian/wall数值；保存field tests不构成3D物理qualification。 |
| #205 | DIAGNOSTIC_SCOPE_NOT_BUG | PG-Frag recompile状态不是本次分配的geometry/ornament审阅范围，未读取其动态源。 |
| #206 | RISK_NOT_TESTED | 对全系统COMPLETED语义的判断需检查被排除的动态solver路径。 |
| #207 | RISK_NOT_TESTED | 全局跨模块PASS语义本轮未审；本范围内status显式保留geometry-only/height-field语义。 |
| #208 | CONFIRMED_CURRENT_GAP | 已查src没有profile/ornament生产调用点，也没有贯通geometry→ornament→mesh的共同样本ID。 |
| #209 | INCORRECT_INFERENCE | 局部freeze/input/STL/PNG哈希都存在；缺少的是端到端共同ID和派生失效关系。 |
| #210 | RISK_NOT_TESTED | source版本冻结有hash，但端到端旧资产失效/重认证策略未被证据验证。 |

## Offset 术语边界

不要把 VesselForge 全部 builder 统称为 radial offset。catalog source 明确在对应控制高度作 constant radial meridian offset（[profile_catalog.py](C:/Users/xiemo/Desktop/ShardForge/vesselforge/src/vesselforge/profile_catalog.py:317)）；既有 fixed cup geometry 的 _offset_body_profile_inward 则计算 meridian tangent 的 inward normal 并作 miter offset（[geometry.py](C:/Users/xiemo/Desktop/ShardForge/vesselforge/src/vesselforge/geometry.py:101)）。该 geometry.py SHA-256 为 0c48940d9ef22aabb068a2e7c6e89b4249a7e724d0ade1c8933a6c951e086047。三份 profile mesh sidecar来自catalog-default几何-only候选，不能代表fixed cup builder，也不能替代catalog radial声明的全局wall资格。
