# 独立 source review：z′ 修正版 normal-offset runner

**结论：SOURCE_READY（仅静态源码与输入元数据审阅；不代表已运行或几何通过）。**

核对文件及 SHA-256：runner `ae91c04bac02e9a057e9f1a099350a34a9cb261d21c5bbd70388f931cb17cd54`；证书 kernel `48ee9fbc2c69ba97dbeb3f34de298a60571786aaf3359cc784b79d2fbfaa6114`；retry pins `9aee6ad4032434279efebeabf9f1b6be525e4bfd3951c875b7b7d08e2b0b8203`；旧 failure manifest `78394f83e773830c23734c41071386cd9bf8e9fdba5fd54b7e3e80ecb5698a00`。各哈希与任务给定前缀一致。

与冻结的失败 runner 做静态 diff 后，仅有两项源码差异：`REVIEW` 指向隔离的 `retry01_after_zprime_fix` 子目录；记录 Q 系数时由错误的 `radius_numerator(rr, zz)` 改为 `radius_numerator(rr, kernel.derivative(zz))`。旧调用把六个 z 控制点当 z′，导致其平方项为十次而 r′ 平方项为八次，触发冻结日志中的 degree mismatch。修正版这一路径传入 6 个 r Bernstein 控制值及 5 个 z′ 控制值；两个 false-fixture 调用也都传 `derivative(cz)`。kernel 中实际证书调用也接收五项 z′，kernel 本身未改动。

kernel 按精确 Fraction Bernstein 算术构造 `Q = r²(r′²+z′²)−9z′²`，对 r、z′、Q 的非负性作端点反例和精确 de Casteljau 细分，超预算或混合符号保持 UNKNOWN。精确 Boehm 插结点把 11 个单结点各补至五重，共 44 次插入，形成 12 个六控制点 quintic spans。代码结构对应一个共享 64-node、depth-6 study budget；12 spans 的基础 36 次非负性调用加 flat-base 的 r′ 检查，共 37 次 primitive 调用。两个 false fixtures 分别使用独立的 8-node、depth-6 预算；第二个 fixture 的 unresolved 结果只接受 UNKNOWN，不会被当作失败反例。计划显示为每 span 25 个点；样点按真实单位法向公式 `(r−3z′/v, z+3r′/v)` 计算，但标记 `display_only`，且浮点样点不进入证明。

局部不穿轴的推理需同时有 `r≥0`、`z′≥0`、`v>0` 及 `Q≥0`；单有 r、z′ 的符号不足。该组合保证真实 inward-normal offset 的径向坐标不为负。侧壁偏移正则性另以已 pin 的 R9 和上游 regularity 作为前提。脚本明确把全局最小壁厚、normal-strip 全局单射、回转面自交、B-rep、材料和物理状态留作 UNKNOWN；本审阅不提升这些结论，也不独立重算上游 R9。

输入字段访问与已 pin 的 saved-result / independent-audit JSON schema 相符；audit 的绝对路径输入键与 `Path.resolve()` 比较方式相容。retry pins 的 runner、kernel、README、fixture、保存结果、冻结 driver、audit、failure manifest 哈希均与磁盘实际值匹配；失败冻结 manifest 内九个快照文件哈希也逐一匹配。旧 attempt 收据记录 rc=2、83-byte stderr、2890-byte 总持久化量且无结果文件；失败目录与新 retry 子目录的 one-shot lock/output 路径隔离。

序列化将 Fraction 结果写为有理数字符串，展示样点为有限浮点数并以 `allow_nan=False` 拒绝非有限值。固定点收据逻辑把结果、原始 stdout/stderr 和 lock 纳入 4 MiB 总量，给结果预留 64 KiB。收据的 `status=COMPLETE` 表示 worker 进程 rc=0，不代表证书成功；最终必须看结果 JSON 的 `status`（UNKNOWN 可能仍有 rc=0）。未发现需要阻断源码就绪的 schema、属性、pin、receipt 或预算问题。

本次只读文本、JSON 和 SHA；未导入或运行 runner/kernel，未调用数值、曲线、provider、CAD、renderer 或 pytest。SOURCE_READY 仅供 root 决定是否单独授权一次执行。
