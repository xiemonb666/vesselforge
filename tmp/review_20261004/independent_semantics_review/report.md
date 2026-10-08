# VesselForge 独立只读语义审阅（2026-10-04）

## 范围与证据

只读审阅 `wall_reference.py` / `test_wall_reference.py` 与 `profile_catalog.py` / `test_profile_catalog.py`，并核对现存 `semantics.py`、`geometry.py` 的接口契约。没有重跑测试、没有运行 solver/CAD，也没有打开动态 CAD 预览；本报告只写在允许路径。

已检查留存测试证据：wall-reference 为 **7 passed**（1.54s，exit 0），输出 SHA-256 `272637a3aa11e33fee8370dec2ccc9d4f9ec7cdf402d871024a5383acf0168ae`；profile-catalog 为 **14 passed**（1.48s，exit 0），输出 SHA-256 `309e52e5a33528ecc4d115f992929c3a778b8570f0a8b505d9963a8e35c107da`。归档记录中的源文件哈希与当前目标源/测试文件相符。

## 发现

### P2 — 开口直径与径向壁厚约束误拒绝有效 jar

[vesselforge/src/vesselforge/profile_catalog.py:219](../../../src/vesselforge/profile_catalog.py:219) 将 `mouth_radius <= wall` 一律拒绝，错误文本也称壁厚径向声明会使 interior opening 不再为正。但本模块的定义在 [profile_catalog.py:244](../../../src/vesselforge/profile_catalog.py:244) 是 `outer_lip_radius = inside_opening_radius + wall`；随后内轮廓减去同一个 `wall`，所以内口半径仍等于用户提供的 `mouth_diameter_mm / 2`，不需要大于壁厚，只需要为正。允许参数范围已保证口径下限 10 mm。

最小反例：`build_profile("jar", max_radius_mm=60, mouth_diameter_mm=10, wall_thickness_declaration_mm=6)`（其余取 jar 默认值）在 [profile_catalog.py:219-220](../../../src/vesselforge/profile_catalog.py:219) 被拒。所有其它耦合约束都满足：壁厚 `6 <= min(10, 0.1*60)=6`；外口半径 `5+6=11 <= 60` 且 `11 <= 0.72*60=43.2`；颈肩高 `18+28=46 <= 0.54*120=64.8`；底厚 5.5 mm 合法。按实际轮廓公式，外口半径 11 mm、内口半径 5 mm，仍有正的 10 mm 清口，内壁所有侧点与外壁对应点径向相差 6 mm，且生成的 z 站点递增。这是有效的几何候选，被一个不符合本模块口径定义的额外条件误拒；建议删掉此条件，或若确实是产品造型规则则另行命名并作为显式参数约束，而不要称它为防止开口变成非正。

### P2 — coverage 数字字段接受 JSON 布尔值冒充整数/数值

[vesselforge/src/vesselforge/wall_reference.py:527-543](../../../src/vesselforge/wall_reference.py:527) 以普通 `!=` 比较 coverage 字段，未在这些位置排除 `bool`。Python 中 `True == 1`、`False == 0`，`True == 1.0`。因此，基于留存 hollow-cylinder 有效记录（恰有 1 个 outer 和 1 个 inner wall face），只把 `coverage.explicit_body_outer_face_count` 从 `1` 改为 JSON `true`，其余不变，验证仍会把记录判为 `VALID`。同一问题也影响 inner count、`unknown_or_pending_face_count`（`false` 冒充 0）和 coverage fraction（`true` 冒充 1.0）。

这不突破记录已经明确的 `MOTHER_SOURCE_ONLY` / `global_minimum_wall_claim: false` 范围，但会让畸形类型的审计元数据通过可信验证。建议对计数字段要求 `int and not bool`，fraction 要求有限 `int | float` 且排除 `bool`，再比较值。

## 其余契约结论

- 空心圆柱留存 JSON 的 STEP 文件 SHA、semantics 的 `canonical_step_sha256`、每张 face 与 station evidence 中的 SHA 一致；fixture 使用 `sha256_file(step_path)` 得到来源 hash。代码把输入命名并标记为 `canonical_step`，没有把 mesh hash 当成 STEP hash，也没有宣称 mesh 绑定。哈希仍由调用者从源文件独立提供，模块本身不读取 STEP 文件核验，这与 docstring 的调用契约一致。
- 材料外法向符号正确：圆柱外壁 `p·n=+10`，内壁 `p·n=-8`。这符合实体材料外法向在外表面指径向外、在内表面指向空腔的约定。frame 固定为 `right_handed_z_up`，长度要求 mm，方向是 dimensionless；wall 模块与当前 semantics classifier 的采样字段、分类器版本字段、面索引/hash字段兼容。数值/布尔类型检查在大部分源输入与 station 向量上会拒绝 bool 和数字字符串；发现的 bool 漏洞局限于上述 coverage 比较。
- 一面一个 interior station 只覆盖有限的 canonical STEP 墙面集合。实现及输出都明确 `mesh_binding_status=NOT_SUPPLIED`、`fragment_mapping_status=UNAVAILABLE`、`global_minimum_wall_status=NOT_ESTABLISHED`、global claim false、physics not assessed；不能从中推出全局最小壁厚或 mesh/碎片资格。
- Profile 输出的闭合截面不重复终点，闭合面积检查为正；两条开轮廓及闭合 material outline 都做了有限线段交叉检查。按公式，内侧壁各 control height 与外侧壁同高且半径少 `wall`，口部仍保留声明清口，底面高度差是 `base`；代码也明确这是恒定径向控制点偏移，不是法向最小壁厚。因此没有看到把径向厚度误报成法向厚度的问题。
- 没有从公式发现允许参数会令轮廓相交或内半径超外半径的额外反例。现有代码没有对 catalog profile 生成 OCC solid，且源码明确称其为 geometry-only candidate；因此此审阅不能确认所有合法极端参数在真实 OCC revolve 中都会成功，也没有证据支持概括成 CAD solid 全面失败。
- `VesselProfile` 内部轮廓用 tuple，`builder_profiles()` 导出 list-of-lists；坐标与现有 builder 的 `(r,z)` 数据一致。当前 `geometry.build_components(VesselSpec)` 仍使用固定 `PROFILE`，并不接收 catalog profile；profile 文档明确披露尚未集成。故它目前提供的是后续 adapter 数据，未证明可直接传入现有 build function，但这点已明示而非隐藏兼容性承诺。

## 审阅源 SHA-256

- `vesselforge/src/vesselforge/wall_reference.py`: `ceeeeec791ed1264bd73a2c0e9dd250ab39aa213a97f75725bf2e6eab91c3461`
- `vesselforge/tests/test_wall_reference.py`: `12f68d858a43158851b36a37e814fca92b15114cb9509ac8777b75cb1700e410`
- `vesselforge/src/vesselforge/profile_catalog.py`: `ff90a8f1c0528d326fc81bb184cc814cfebb38ae91b0ade82e59d09a7b3ef64f`
- `vesselforge/tests/test_profile_catalog.py`: `0752755c1e371afa6f5a03db46394d299f9acabc3c1d72dd84911672e2454e2e`
- `vesselforge/src/vesselforge/semantics.py` (接口参照): `dfcc366d868c65313bcd5a43faf91d482b89848c2b15d4d9e66158ac291231af`
- `vesselforge/src/vesselforge/geometry.py` (接口参照): `0c48940d9ef22aabb068a2e7c6e89b4249a7e724d0ade1c8933a6c951e086047`

本报告 SHA-256 将在写入后单独计算。

