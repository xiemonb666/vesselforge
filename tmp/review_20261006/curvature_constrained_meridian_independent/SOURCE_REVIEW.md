# Curvature-constrained meridian：独立静态源码审阅

**结论：SOURCE READY，可供root按默认固定case决定是否授权一次本地试验；未验证任何候选几何。** 审阅绑定实现SHA-256 `96875bb6592a6fd57ceef4dc326c35faeb3f96de16607faa816c7d3fed1e08ce`（450行）。只读源码、README、case/pins与文件哈希；未导入driver/数值结果/SciPy，未运行RREF、Bezier、曲线、solver或CAD。

实现与pins现已一致：输出根为`vesselforge/tmp/...`；driver、fixed case、seed和design case哈希分别与常量及pins相符，哈希可复核。模块顶层只导入标准库；SciPy在显式`root_ready=True`、输入校验与精确高度预检之后才惰性导入。run marker和`xb`结果文件拒绝覆盖；没有API key或远程调用。

等式消元写法正确：先固定pole，再对free列做Fraction RREF；用新旧右端残差对seed作pivot-only仿射修正，非pivot坐标不动；再以每个nonpivot自由变量为单位构造nullspace方向。代码检查三主元及10/11 free维数，对应7个r、8个z方向，失败会中止。这样保持case等式和固定极点；Q0是与新case相容的warm start，目标仅最小化到Q0的控制极点距离。按本任务限制，我没有独立计算实际RREF/秩。

曲率筛查的尺度一致：Bezier局部参数`t`下由一阶、二阶导数构造`P_R=|v|^6−R²det(v,a)^2`；坐标除以9 mm，优化半径9.09 mm相应除以9，最终冻结driver用exact Fraction验证R9。局部`t`改全局`u`使两项同乘正因子`h^-6`，不改变符号。Bernstein乘积得到degree24，再将`det²`升阶；所有系数非负是充分证书，混合符号保持UNKNOWN。优化器只用float找点，十进制alpha转Fraction后由冻结driver重验特征、C4、严格点条件、速度、凸包和全span R9；精确endpoint反例为FAIL，未证明项不晋升。C4来自固定五次、简单结点结构并另经jet检查；这不等于器物物理资格。

默认bowl改用`(60,72)`，D=3、H=14，仅通过R9必要高度界；旧`77.4`值仍冻结且被设计case明确排除。jar的D>2R记为NOT_APPLICABLE，不冒充通过。默认调用使用pin住的design case；显式`design_cases`入口只允许改bowl apex高度并仍过高度预检，首次试验应使用默认`None`。预算为每family至多一次SLSQP/80迭代、共享60秒、输出8MiB；deadline保护优化及精确复核，但前置建模/提取和最终序列化不是可强制中断的硬实时段。所有通过状态仍仅为geometry engineering candidate；不声称physics/style、inner wall、lip、CAD或全局法向壁厚。
