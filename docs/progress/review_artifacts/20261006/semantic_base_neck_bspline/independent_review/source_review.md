# Semantic base/neck B-spline 独立源码审阅

**补充秩复核推翻初审的无阻塞结论：当前原始bowl等式组不相容，不能SOURCE READY。** 初审只核了自由维数，漏查实际约束行秩；具体更正见末尾。未运行作者函数、KKT、曲线、CAD或测试。

17根、5次、11个简单内结点对应12段，内部C4。固定极点确实令首段z恒0、末段r恒mouth半径；各case的foot/apex/neck-start/mouth与u位置、固定polerules和线性等式相互一致。自由维度为r10/z11，各3行等式；源检查自由行满秩并构造13×13、14×14 affine KKT。右端为`(-2 H_fF q_F, b-A_F q_F)`，与目标`qᵀHq`及固定变量消元一致；第三导数能量Gram与`60²/h⁵`缩放正确。全局二次零空间被至少一个整段固定极点组消除；满秩后唯一性成立，精确残差检查且奇异时拒绝，不加ridge/pinv。

Boehm插到内部重数5得12个Bezier段；P_R degree24乘积/升阶正确。源仅将R≥9施于段1–10；段0/11先按极点证明平底/圆柱语义，但这只是“排除曲率屏”，仍须同时通过`all_spans_regular_proved`。凸包、导数极点符号和strict端点条件是充分证书；混合P系数保持UNKNOWN，负端点才是反例。曲率指子午线，不代表周向曲率。92/122 mm仍是未建lip的crest目标；inner wall、offset、reach和材料资格均未声称。此footed geometry是模板变体，不推及所有真实器物都要平底。

SHA-256：driver `038974cbbe3965f7f03f1ad0199d0aba00b56294840e411ca9a21fbde42466a3`；fixed_cases `77ea80492af5092cf41f60cb7d10c5458c95197d74efc68def349f9824629824`。

### 等式行秩预检更正

另以独立精确Fraction Cox递推构造当前case等式行（不调用作者代码），在固定极点消元后的`A`及增广`[A|b]`上做行秩。当前bowl apex `u=10/12`：r为`rank(A)=2, rank([A|b])=3`，故等式不相容；虽有10个free pole和3行，apex半径/零径向导数在唯一可动的apex支撑自由极点上相关，固定neck poles令所需值冲突。z为3/3。当前jar apex `u=6/12`：r、z均3/3。

仅作参数位置提案：bowl apex改到`u=8/12`，物理`(60,77.4)`不变、neck仍`11/12`，重算r、z均为`rank(A)=rank([A|b])=3`。这证明该参数下等式组满行秩且相容；**不**证明KKT可逆、最小jerk解存在/唯一、曲率或任何几何筛查通过。此提案尚未改源case。
