# retry02 保存结果补充审阅

本补充只读核对 retry02 的保存 JSON/receipt、当前 source 与 pins；没有重跑证书或曲线计算。

结果 SHA-256 为 `4b7d019d2c119fb7f5db398f1205bc4830d72702f21a565a0859e1a6282335bf`，receipt SHA-256 为 `3ec65b5f54581a5371c2e95eefe87a1a0e83a682965746f6167a780fe3aeb806`。receipt 记录返回码 0、未超时、0.125 秒，且 16 项 pre/post source/input pin 完全相同。当前 source SHA-256 为 `ae1d34351e113bf08f4de287468b38d5035f4bf1c75f98e3fb84d7b361c851ce`，与 pins 声明一致；case SHA-256 为 `9e7b9e7945a14b3dd45517c75a672607cf0923cdac5c723ab614fa0162fc127b`，当前 source-pins manifest SHA-256 为 `bdfbf05dd6bf7d3a8f4e6d7ebf4c90831f53726adc935c1061e372caeb7106ae`。receipt 同时保留被替代 source/pins 的旧 hash，未与当前 pin 混淆。

捕获目录有四个文件：receipt 10,296 B、result 4,355 B、stdout 4,355 B、stderr 0 B，合计 19,006 B。receipt 的 `output_tree_bytes=29,025` 统计范围还含父目录文件：两个 helper（8,138 B 与 1,048 B）以及 GO 记录（833 B），所以比四文件捕获目录多 10,019 B。

保存结果为 `GLOBAL_MERIDIAN_STRIP_INJECTIVITY_PROVED_CONDITIONAL`，范围明确为实际二维子午线映射 (F)、12 spans、(0\le s\le3) mm。记录了 12 组精确导数极点符号：底段 `z′=00000,r′=+++++`；side spans 1–10 的 `z′` 均严格开段为正，`r′` 依次为 `+++++`（1–4）、`++++0`（5）、`0----`（6）、`-----`（7–9）、`-0000`（10）；neck 为 `z′=+++++,r′=00000`。10 个侧段各有 25 个非负 R9 Bernstein 系数，并记录 local 与 global 系数按 (h^6) 相等；11 个接缝逐个记录 global-(u) 0–4 阶相等。端点语义为 axis ((0,0)	o(0,3))、base/side seam ((18,0)	o(18,3))、mouth ((26,120)	o(23,120))；lip 仅是数学域边界，未声称 CAD lip。

因此，之前 scope 字符串问题已由 retry02 保存结果解决，二维条带的条件性单射结果现在有实际保存核验支持。结论仍严格限于该二维映射：全局欧氏最小壁厚、native B-rep、physics 均为 `UNKNOWN`。轴纤维旋转退化和唇口/端盖缝合仍需单独处理。半径非负的 Q 系数仍依赖上游已 pin 的证据链；本源只核对保存系数叶，没有从当前控制点重建 Q。