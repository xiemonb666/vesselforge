# 创新研究底账

项目：**VesselForge**　｜　记录日期：**2026-10-04**

> 本文服务于 RelicWeave 碎片邻接检索与证据决策主线；候选可修改、合并或淘汰。登记不代表已实现、有效、原创或具备论文资格。成熟库/API/求解器、标准 CAD/mesh、包装器不登记为本项目原创算法；没有 primary-literature novelty audit 的条目一律保持候选。

**主线关系：** RelicWeave 主线在真实可获得的碎片观察、候选检查预算和误荐风险下，输出有序邻片候选及可追溯证据；证据不足时提出有成本约束的补采或停止推荐。VesselForge 是几何/材质字段与合成观察的支撑设施，不替代这条检索与决策主线。

## 共用的数据语义边界

- 总方案允许将早期程序分区或非平面切割明确标为 SYNTHETIC 几何基线保留；这不降低当前真实物理模拟目标的验收要求，也不得把程序切割标签称为物理 R2。
- R0、R1、R2、UNKNOWN 与 historical_R2、current_fit_valid、evidence_visible 按既有合同分字段保存；不得混并标签语义或用旧标签改写当前证据。
- bag/object 身份、完整装配信息与 GT/oracle 字段不得进入网络输入；只允许在隔离的标签、审计和评估侧使用。
- 来源范围：RelicWeave_V1.44_Optimized_Complete_Plan.docx：主线问题与输入权限见总纲/第2节及 P00003、P178–180；程序切割作为显式 SYNTHETIC 几何基线见 P1191–1192（由 root 复核）。

## 工程基线（不作为研究创新）

- 现有 `forge.asset.v1` 原型生成一类带融合把手的开口旋制器型，导出 STEP、三角网格、静止局部坐标系中的光学字段、来源与几何 QA。README 明确：力学值为 illustrative / `UNVALIDATED_PROTOTYPE`，绘制带纹 recipe 无几何起伏并标记 `NOT_VALIDATED`。这属于工程数据合同与原型字段实现，不是研究贡献。
- 完整曲面上的区域标签按 canonical STEP 修剪面类型/轴和面向法线分类，再经 triangle-to-face lineage 投影；未知面阻止着色与资产生成。这是有来源的工程追踪能力，不证明纹样历史真实性或邻片检索效果。
- 素材范围、全局壁厚、CAD/网格距离和生产可用性仍需按 `vesselforge/README.md` 的限制陈述；不得从单样例 QA 推为通用器型能力。

## 已证实验事实与边界

- C2 无把手 native BREP 仅为 `BREP_CANDIDATE` / `NOT_PROMOTED`。保留的实验说明一次 remesh 的 602 个确定性样本最大 trimmed-face 偏差为 0.040084606 mm，局部几何检查通过；这是有限采样，不是 Hausdorff 界。该实验没有替换生产 STEP。
- C2 无把手 BREP 候选自身的 STEP round-trip 失败（two shells、zero solids），该候选未晋级；此失败只适用于该 C2 候选，不对单独的 handled-cup production STEP 作 fail/pass 推断。较粗网格首轮 exit 2 与之后仅重网格 exit 0 均保留。
- 目前没有真实自由碎裂样本、材料标定、独立 remesh bias 实验、真实照片跨域检索结果、physical R2 或 PRETRAIN 准入。

## 主档案来源

- `vesselforge/README.md` — `forge.asset.v1`、区域/字段实现及 Scope and limitations。
- `vesselforge/experiments/smooth_cad_brep/README.md` — 记录的 BREP 候选、有限几何检查与失败边界。
- `vesselforge/experiments/smooth_cad_brep/execution_source_manifest.json` — 执行/保留源码与产物的 hash、bytes 和未晋级状态。
- `RelicWeave_V1.44_Optimized_Complete_Plan.docx` — 核心问题、评估分母、创新止损与 A12 合成实验室边界（只读总方案）。

## Root 主审记录（2026-10-04）

- 决定：`accepted_for_tracking_only`。候选验证为 `NOT_RUN`，新颖性为 `NOT_AUDITED`。
- 论文候选的最终证据链必须检验 RelicWeave 邻片候选检索的可测收益。几何闭合、网格外观、包装器/API 成功只支持工程能力，不能单独证明论文贡献。
- 指标口径：拒识前排序报普通 Hit/Cov（例如 Hit@K/Cov@K）。 应用拒识后，将拒识 query 的候选列表置空，再报 EffectiveHit/EffectiveCov。 另报 接受率、接受子集指标、接受子集风险、无邻片误荐风险.
- VF-RC-001（P1）：优先保留为数据字段/lineage 研究候选；仅接受登记跟踪，不代表已验证或新颖。
- VF-RC-002（P2）：收窄为成像退化与可观测证据的配对生成协议；只负责 generator/metadata/paired intervention。候选排序、拒识和主动补采决策仍归 RelicWeave A3/A4/A6；动作效果仅作下游评估用途。
- 范围说明：C2 无把手 BREP 候选自身的 STEP round-trip 失败并未晋级；此结果不对单独的 handled-cup production STEP 作 fail/pass 推断。

## 候选/验证记录

| ID | 类型 | 状态 | 标题 |
|---|---|---|---|
| VF-RC-001 | candidate_research_contribution | `idea` | 连续母体材质坐标与可追溯纹样证据 |
| VF-RC-002 | candidate_research_contribution | `idea` | 成像退化与可观测证据的配对生成协议 |

### VF-RC-001 — 连续母体材质坐标与可追溯纹样证据

**状态：** `idea`
**初稿状态：** `pending-main-review`
**主审决定：** `accepted_for_tracking_only` — 优先保留为数据字段/lineage 研究候选；仅接受登记跟踪，不代表已验证或新颖。
**候选验证：** `NOT_RUN`（occurred=false）
**Novelty：** `NOT_AUDITED`
**审查优先级：** `P1`

**问题：**
对局部、缺失且可能低质量的器物碎片观察，把纹样/材质保持为母体静止材料坐标上的连续字段并追溯到可见证据区域，能否提高跨母体、跨网格和跨成像域的邻片候选检索，同时避免颜色相似捷径？

**与 RelicWeave 核心的关系：**
该候选只支持 RelicWeave 的候选排序、支持/冲突区域与证据来源；它不能替代 R0/R1/R2 真值，也不能把外观相似直接解释为物理接触。A12、VesselForge 是数据/标注基础设施。

**候选方法/验证方案：**
- 在母体 rest/material 坐标定义连续的母题、布局、重复/对称规则和材质字段；裁切、重三角化或生成碎片时从同一字段重采样，而不是在像素图上重绘标签。每个观测保存字段版本、几何 lineage、可见/遮挡区域、原图坐标回映和字段来源。
- 以区域级可见性和支持/冲突证据训练或诊断候选关系；推理侧只读取传感观察及允许的质量量，隐藏母体坐标和真值仅作审计。保留多邻片、未知和拒识。
- 这是一项待检验的字段/证据协议假设；当前 VesselForge 带状图案是零 relief 的 illustrative recipe，尚无碎片检索实现或效果数据。

**成熟上游内容与归属：**
VesselForge 已有 rest-local optical fields、面分类和 triangle-to-face lineage；参数化曲面、UV/material field、程序化纹理与局部视觉检索均有成熟上游内容。方法组件若只复用这些工具或给图案加标签，不构成原创。没有进行 primary-literature novelty audit；论文新颖性未成立。

**证据路径与范围：**
- `vesselforge/README.md` 全文：`forge.asset.v1` 的 rest 坐标光学字段、面到三角形 lineage、unknown-face fail closed，以及带纹/材质字段限制。
- `vesselforge/experiments/smooth_cad_brep/README.md` 的 Recorded candidate evidence：BREP lineage 的有限投影/几何证据与生产 STEP 的边界。
- `RelicWeave_V1.44_Optimized_Complete_Plan.docx` 2.3、A3.1、A4.9、G21：候选/证据输出、拒识分母、输入权限、按母体分簇评估和合成实验室范围。以上只支持问题与评测合同，不证明本候选有效。

**失败与不确定性：**
- 尚未建立多器型、多材质的有授权真值集，也没有由真实断裂产生的配对表面；单一带把手杯不能证明字段跨品种有效。
- 材料/纹样的真实物理含义与历史真实性未验证；同器纹样会造成身份泄漏，视角、遮挡和材质变化可让字段不可观察。
- 母体 CAD 坐标或完整纹样若被模型读到，会泄漏 GT；必须拆分 feature 与 label 并按母体谱系切分。

**对照基线：**
- 同一训练预算的 RGB/常规图像增强模型；无纹样字段的整片/断口双通道检索基线。
- 只用几何/可比较法向或距离的候选基线；颜色/纹样直方图与随机候选作为捷径/下界诊断。
- 字段局部证据相对只增加模型参数、只增加训练步数和无字段版本逐一对比。

**必要评估（消融/数值/视觉/真实数据）：**
- 按独立母体簇划分 train/dev/calibration/confirmation；整器、重复纹样族、相机/拍摄 setup 不跨确认边界。固定图库、候选池、query、ROI 来源、M/K、QA、阈值和训练预算。
- 最终论文候选收益由 RelicWeave 邻片检索确认：主指标候选沿用总方案的母体等权 CovRecall@10；拒识前报告普通排序 Hit@K/Cov@K，应用拒识后将拒识 query 的候选列表置空并报告 EffectiveHit/EffectiveCov；另报接受率、接受子集指标/风险、无邻片误荐风险与校准误差。差异用母体配对双侧 95% 区间，稀有误荐用独立母体事件的单侧 95% 上界。
- 用消融分离连续材料字段、区域 lineage、纹样外观、几何证据和可见性；报告候选召回与冲突证据定位。视觉图只检查原图→ROI→字段坐标是否对齐，注意力热图不算解释性证据。
- 必须在许可明确的真实碎片照片上做跨母体/跨相机确认；只有合成收益时结论限定为合成域。

**预冻结验收：**
- 启封前冻结 protocol hash、split/gallery/query、字段生成器与种子、ROI/来源、M/K、主指标、拒识阈值、clean guard、样本量与停止规则。总方案中的 3 个百分点 Cov@10 是 pilot 后可审议的最小有意义增益候选，不是本账已批准阈值。
- 仅在确认集的母体配对区间超过预注册增益、真实低质量观察上的拒识/风险界限合格且 clean guard 不退化时，才支持该实验假设；样本不足标 `NOT_ESTABLISHED`。
- 任何字段越权、GT 泄漏、未许可数据或把 illustrative 材质标为真实属性，均为硬失败。
- 若作为论文候选，最终须在固定 RelicWeave A3/A4/A6 与真实确认母体上证明邻片检索可测收益；字段对齐、几何 QA 或视觉示例通过不能替代该证据。

**否证或切换条件：**
- 若增益仅存在于合成集、特定图案或同器视角，独立真实母体无收益/退化，或支持证据无法从原图坐标复核，则否证跨域检索主张并保留为工程标签。
- 若无纹样或错误纹样的负控同样升分，或完整 CAD/字段信息进入推理输入，则判为捷径/泄漏失败，不通过调整阈值挽救。
- 若 primary-literature audit 显示方法对象与评测已被充分覆盖，改列成熟工程组合或停止论文创新主张。

**复现与许可审查：**
- 待执行：冻结生成器/字段定义版本、CAD/source hash、种子、相机参数、原图/ROI bytes 与指标脚本；独立环境复放候选资产和评测。现有 BREP manifest 不是本研究方法的可复现实验包。
- 待审：代码依赖、真实器物照片/纹样/馆藏权利、衍生图像和数据再分发许可；在审计结束前不得作为论文公开数据集承诺。
- 待做 primary-literature audit；目前无可支持“原创/首创/SOTA”的引文或对照。

**下一步：**
请 root 先判定这是值得进入开发集的研究假设还是纯标注工程；若进入，先写冻结数据/泄漏合同和小规模母体分簇 pilot，不改生产 schema。

**Novelty 审计：**
NOT_AUDITED — 主审只同意保留跟踪，不表示 novelty 或 method contribution 已成立。


### VF-RC-002 — 成像退化与可观测证据的配对生成协议

**状态：** `idea`
**初稿状态：** `pending-main-review`
**主审决定：** `accepted_for_tracking_only` — 收窄为成像退化与可观测证据的配对生成协议；只负责 generator/metadata/paired intervention。候选排序、拒识和主动补采决策仍归 RelicWeave A3/A4/A6；动作效果仅作下游评估用途。
**候选验证：** `NOT_RUN`（occurred=false）
**Novelty：** `NOT_AUDITED`
**审查优先级：** `P2`

**问题：**
能否为同一几何/材质/候选真值生成可复现的成像退化与观测干预配对样本，明确哪些区域变得不可见、哪些观察质量发生改变，并支持 RelicWeave 下游检验其证据使用？

**与 RelicWeave 核心的关系：**
VesselForge/A12 只负责受控观察生成、配对干预、可观测性标注与元数据。候选排序、拒识以及主动补采决策仍属于 RelicWeave A3/A4/A6；对应动作或候选指标只用于下游评价，不把策略引擎放入 VesselForge。

**候选方法/验证方案：**
- 以同一母体、材料字段、几何、真值和相机基准生成 clean/degraded 或 intervention-paired 观察；一次只改变预注册的焦点、照明、视角、遮挡、分辨率/压缩等观察轴，并记录 source hash、参数、受影响区域、可见证据标签及原图/ROI 坐标变换。
- 将配对样本作为受控干预：保持候选集合和 GT 不变，核验所声明观察轴确实改变、其他受控变量保持稳定；实际模型输出与补采/STOP 决策只由 RelicWeave A3/A4/A6 的冻结版本读取，用作下游评价。
- VesselForge 不实现排序、拒识阈值、动作策略或 STOP policy；本候选仅是 generator/metadata/paired intervention 协议。

**成熟上游内容与归属：**
相机退化模拟、可观测性质量标注、配对干预与图像增强均有成熟上游工作；A12 已有观察/退化设计。将既有退化算子搬入 VesselForge 不构成原创。可能的任务增量是带固定候选真值、区域证据与可复核 metadata 的配对生成合同；primary-literature novelty audit 未做。

**证据路径与范围：**
- `RelicWeave_V1.44_Optimized_Complete_Plan.docx` 2.2–2.3、A3/A4、G21：真实观察优先、候选条件补采、拒识风险与固定确认集合同。
- `relicweave-synlab/docs/a12/CONTINUATION_20261004.md` 当前窄结果：46 项 appearance tests 和四个小盒 toy 输出，仅属工程/小范围证据，不是捕获域迁移或真实邻片检索通过。
- `vesselforge/README.md` 的光学字段及 prototype scope；未含已验证相机/采集动作模型。

**失败与不确定性：**
- 没有经实测校准的镜头、焦点/景深/照明范围或真实 paired capture 数据；模拟的退化强度不能直接称真实采集效应。
- 若一次配对同时改变多个观测变量，或 metadata 不能重建实际变换，就无法把结果归因于一个证据变化。
- 候选排序/拒识/主动补采策略不是本候选的实现内容；当前没有确认这些下游系统会因本生成协议而改善。
- 现有 A12 appearance 小例不等于真实成像 realism，也不提供现实域召回或物理材质结论。

**对照基线：**
- Clean-only 数据和普通、非配对的通用 image augmentation。
- 相同退化边际分布但打乱 pair correspondence/metadata 的数据，用于检验配对信息是否必要。
- 由 RelicWeave 固定 A3/A4/A6 检验同一候选池和相同预算下的下游结果；策略方法不是 VesselForge baseline。

**必要评估（消融/数值/视觉/真实数据）：**
- 生成器数值检查：逐 pair 比较 CAD/材质/GT/hash 恒定项与唯一 intervention 项；量化可见面积/ROI overlap、焦点/模糊/曝光/遮挡/像素分辨率等声明质量量；校验坐标回映与 metadata 可重放。
- 做单因素退化轴与组合退化消融；与 unpaired augmentation、clean-only 对比。图像/区域可视化只审查 intervention 前后和受影响证据区是否对应，不据此宣称真实感。
- 在许可明确的真实器物照片与实测采集条件上验证成像指标范围；合成结果只支持 synthetic protocol 结论。
- 论文证据链最终需由冻结 RelicWeave A3/A4/A6 在真实独立母体上检验邻片候选收益；固定 query/gallery/预算，报告拒识前 Hit/Cov、拒识后 EffectiveHit/EffectiveCov、接受率和接受子集风险。动作效果只属下游评价，不是 VesselForge 策略功能。

**预冻结验收：**
- 生成前冻结 geometry/material/GT/source hashes、相机 profile、每次仅改变的退化轴、参数范围、pair ID、可见区域标签、split、seed 和 replay contract。
- 配对正确性门须逐项闭合：不变量 hash 一致、干预参数与区域标签一致、变换可重放、部署 feature 不含 GT/母体身份。任何不一致标 `FAIL/UNKNOWN`。
- 若形成论文主张，另需预注册的 RelicWeave 邻片候选下游收益和风险界限；真实确认数据不足标 `NOT_ESTABLISHED`，不以 generator/metadata 通过代替。

**否证或切换条件：**
- 若 pair 未能隔离一个 intervention、质量标签与实际像素变化不符、source/GT 泄漏或无法重放，就否证当前生成协议，不进入下游评估。
- 若固定 RelicWeave 下游比较未提升邻片候选检索、风险没有改善，或收益只在 synthetic images 上，则只保留工程数据协议，不作论文方法主张。
- 若 primary-literature audit 显示该配对合同没有可区分增量，保留为工程测试数据生成规范，不主张研究创新。

**复现与许可审查：**
- 保存每对 clean/intervention bytes 与 SHA-256、生成器/source/build hash、相机和退化参数、区域标签、seed、ROI transform、原始失败输出及 replay script；独立环境复放。
- 审查真实器物/馆藏影像、纹样、拍摄人员和第三方来源许可；未经许可不公开原图、可逆 crop 或生成 derivative。
- 当前 appearance / BREP evidence 不是本配对协议的复现包；primary-literature novelty audit 未做。

**下一步：**
按主审边界先写 generator/metadata/paired-intervention schema 与单因素 pilot；邻片模型和动作评价由 RelicWeave A3/A4/A6 持有，不在 VesselForge 增加策略功能.

**Novelty 审计：**
NOT_AUDITED — 主审只同意保留跟踪，不表示 novelty 或 method contribution 已成立。

## 共通签收口径

- 研究状态与证据结论分开；仿真退出成功、资产几何 QA、代码可执行和材料物理合格是不同事实。
- 当前没有真实自由碎裂/材料标定/独立方向偏差/physical R2 或 PRETRAIN 准入证据。论文主张需在后续预注册对照、真实数据评估和许可证审查后另行裁决。
- 本账未作广泛文献搜索，也不承诺完成比例、SOTA、独创或已可投稿。
