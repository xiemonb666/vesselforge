# 独立审阅：Catalog corner fairing

**窄结论：默认 bowl / jar 的平面 quintic 数学提案可接受继续讨论；没有发现本次范围内的控制多边形、端点 C2 或全参数正则性公式错误。它不是物理、应力或全局壁厚证明。**

审阅输入 SHA-256：`catalog_corner_fairing.py` `6c1e94150d769158c757469141aab23796b005421d3878b150271d375086d534`；`profile_catalog.py` `e9d4bc1458a107208e537449d6526f1c0077d6d3afc6953a6200d86512f9c26f`；`DESIGN_AUDIT.json` `e36bb07ea07469671babda8e35c11fcf5a4a15b1d624ed2a16eaf44a3f57cf7e`；图 `catalog_corner_fairing_profile_plot.png` `6427145d9e63a94c986170783f17d91a4b126224ec93b148c6545fcc7e864c0f`。保存回执为 `PASS_BOUNDED_MATH_DESIGN_ONLY`（0.953 s）；PRE/POST pins 相同且与现有 source/catalog/runtime hashes 一致。Catalog 明言这是解析起始轮廓，不是实物测量。

我从回执内 23 组已保存控制点独立重算端点切向、端点零曲率、控制点位于相邻截短线段、切向角平分线投影及二阶控制差分曲率上界，并各按 t=0…1 的 9 点网格直接代数评估：207 个独立参数样本，均通过；未导入候选脚本，未重建或运行几何。上界分别与作者回执吻合。保存审计本身也是单次 bowl 90 + jar 117 = 207 个参数评估、216 个轮廓采样点。两份 207 是两次各自独立记录，不合并冒称单次 207；超出这些已存记录的历史调用次数没有回执佐证。

最宽曲率上界位于两例 outer index 1 的 90° 底角：bowl 19.876 mm⁻¹，9 点网格峰值 1.919 mm⁻¹；jar 21.683 mm⁻¹，网格峰值 2.093 mm⁻¹。上界约为采样峰值 10.36 倍，对应仅能保证曲率半径不低于约 0.050 / 0.046 mm；该界较松，不能据有限网格证明实际极值，也不能把几何曲率换算成应力。所选圆角接头的切向与零曲率连续；内外轮廓分开修圆，底轴/唇口及 bowl 最大半径尖角仍保留，因此应力集中、断裂响应均 UNKNOWN。

复核保存轮廓数组：bowl 的 floor 6 mm / clear mouth 108 mm / height 90 mm / max radius 60 mm，jar 对应为 5.5 / 46 / 120 / 54 mm；axis 与两端点保持，声明的 max radius 也仍在。3 mm wall 仍只是 catalog 声明元数据；回执里的轮廓间距仅是有限 2D 折线距离（bowl 约 1.0252 mm、jar 约 1.3906 mm），不是法向厚度或全局最小壁厚。简单轮廓检查也是采样折线检查，采样间的自交/曲率极值未知。

源码用 `spec_from_file_location` 直接加载 `profile_catalog.py`，没有执行 `vesselforge` 包 `__init__`；并在计算与绘图后检查 CadQuery/OCP 模块。已有 audit 报告 `cad_imported=false`。我实际查看了保存图：它与审计数据相符，是等比例镜像 2D 子午截面叠图，能看轮廓转角但不显示 3D 曲面、制造或力学结果。30 s 预算是在完成后比较耗时的软检查，不是硬终止；已保存单次记录耗时 0.953 s。未运行候选、CAD、solver，也未改作者文件。
