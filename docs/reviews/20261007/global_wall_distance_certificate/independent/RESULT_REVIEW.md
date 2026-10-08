# Global wall-distance run01：独立保存结果审阅

**保存结果接受，范围限于固定 jar 的二维曲线对及其数学旋转集合距离。** 本轮只读 result、receipt、GO 和 pinned 文件；未重跑 checker 或做曲线/数值计算。

结果 SHA-256 为 2ed29f2581c49304581c36dfdf8fdda9d02b193c8078629202bc82bcefe727f0，状态 MERIDIAN_CURVE_PAIR_MINIMUM_EXACTLY_3_MM。其声明范围是 outer meridian c(u) 与 inner meridian F(v,3) 的最小距离。24 个 endpoint-to-span degree-10 Bernstein 证书（axis 与 mouth 各覆盖 12 spans）全部 PASS，每项一个 full-span leaf；两条 endpoint minimum 都记为 EXACTLY_3。结果同时报告 extended strip F(0..6) PASS、10 个 side R9 spans、lambda 下界 1/3、depth-6 side/neck 半径下界 12/20 mm。

实际 checker source hash 2466306decc0af17d47c71d8e66b110aa77255f8f9279b94180a86ee7029886d 被 receipt 的 pre/post 条目绑定。该源重建并绑定 actual B-spline 到 12 个 offset Bezier spans；成功返回表示其 10 个 exact R9 检查及 11 个 actual global-u C4 joins（导数 0–4 阶）均通过。紧凑 result 未逐行序列化 C4 join 表，C4 执行依据是 receipt pin 的 source 与成功 status。

最小距离不是从 F(3) 单射直接推出：对于内点 v，q=F(v,3) 满足 q'=lambda*c'，lambda>0。最近对的 v 向驻值推出 c(u)=F(v,3±d)。假设 d<3 会令 F 的深度落在 (0,6)，与扩展条带单射冲突；outer 参数 u 可在端点。inner 参数为 axis/mouth 端点时，使用上述 24 个精确距离证书。相同方位取得子午线最小值；非负半径下，异方位项 2*r*rho*(1-cos(delta_theta)) 不小于零，因此理想数学旋转曲线集合距离也是 3 mm。

**范围限制：** 这是保存控制点所定义的曲线对与旋转集合结论。actual CAD lip、caps/axis 的原生拓扑、native B-rep 和 production wall qualification 仍为 UNKNOWN；不得将 3 mm 曲线对距离写成已合格的闭合器物壁厚。

receipt SHA-256 为 722f85de881745371bd051f02c5b1646a88c29e9b6e3ff780521bc8bac35a319，GO SHA-256 为 aead67272288550c1ca55c3c93733e413a829bb61023236db6d4450d125364ba。receipt 记录 rc=0、未超时、child 与 supervisor 各 0.140 s，授权调用 1 次。14 项 pre/post hashes 相同且当前文件均与 post hash 相符。捕获目录 5 文件共 14,852 B；receipt 中 input bundle 988,413 B，总 tally 1,003,265 B。未找到独立 timing addendum；receipt 标记 external tool timing 由 parent 记录。