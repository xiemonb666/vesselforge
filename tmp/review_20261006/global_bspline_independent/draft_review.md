# Global quintic B-spline 独立复审（source-only）

**结论：READY，仅指可供 root 按门控生成一个精确候选；未执行函数、求解或曲线评估。**

输入为 11 控制点/22 标量，r/z 等式各 5/4 条；代码精确检查行秩、KKT 可逆及方程残差。jerk Hessian 的 60²/h⁵ 缩放和二次 Bernstein Gram 正确；其零空间仅为全局二次函数，三个不同参数处的位置约束将其消去，满行秩时解唯一。Boehm 插结点至重数 5 得六段；端点导数和连接处 0–4 阶 jet 检查一致。P=S³−R²D² 的 degree-24 Bernstein 乘积/升阶正确，半径证书也要求整段正则性。

凸包与导数极点符号只给充分证书；失败状态是 NOT_CERTIFIED，不代表实际几何失败。混合曲率系数为 UNKNOWN，端点负值才报反例。因底转区间未定义，两项半径目标都筛全部六段，语义保守。92/122 mm 是未验证 crest 目标；源不建 lip、inner wall、offset 或 global reach，候选保持 NOT_PROMOTED。未见剩余 source blocker。

SHA-256：driver `5578CABC4C729363F2778BEC97F13D49F5F3AA664548D966D379BDF3C29EE050`；constraints `E2D978BB817FA83918D2A494E1A084863FE413B8E176411038E9A8BA757F15D9`；fixed cases `47AA718E1FEAE7005DB0B5D7FD77393C308D9D1EEFA0FAA43212DC077A865908`。
