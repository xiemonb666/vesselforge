# Global wall-distance checker：独立 source / 数学审阅

**结论：数学路线有条件成立；保存候选尚未由此 checker 实际认证。** 本审阅静态读取 source、case、pins、README 和 pinned JSON schema；没有调用 checker、Fraction 函数、CAD、solver 或测试。

输入 SHA-256：source 2466306decc0af17d47c71d8e66b110aa77255f8f9279b94180a86ee7029886d；case 985b12a38a9996372a39afb700ecc413ecbb52c106f0594dc94350674b7c27d8；pins 63be31ab8ea506dc77888ccba0865ddc85ac938cd97e822cd2e5b8006f16d32f；README 7efb1da252847accba61ff0790703a017f73c34d24bd5d4245e85ab0d0d28a5a。四个 pinned inputs 的当前实际哈希均匹配。读取字段与保存 schema 相符：17 个 outer RZ controls、12 个 outer/offset spans、11 个 joins；offset 与 retry02 scope/status、outer jar exact-certificate 路径均匹配。

实现路线没有把 F(3) 单射直接当作最小壁厚。它从 17 个实际控制点精确 Boehm 提取 12 个 Bézier spans，与 offset spans 逐项匹配；重建十个 side 的 degree-24 R9 系数并以 h^6 与 global 证书绑定，重核全部 global-u C4 jets。符号表给出 side/neck 开段 z'>0、flat base z'=0 且 r'>0；侧段半径从 seam 18 增至 apex 54，再降至 neck 26，所以 side r>=18。R9 推出 0..6 mm 深度内 lambda>=1/3，因此 side radius>=12，neck radius>=20，base radius不变且非负。mouth-base 高差120 mm大于6 mm；固定高度下允许深度为连通区间，flat base seam 单独处理。由此可证明 extended F 在0..6 mm内单射。

最小曲线对距离的核心论证是对称驻值法。取最近对 c(u), q=F(v,3)。若 inner 参数 v 是端点，两个 endpoint-to-all-spans degree-10 证书覆盖该情形。若 v 是内点，q 对 v 的导数等于 lambda 乘 c 的导数，且 lambda>0；最小距离驻值条件推出 c(u)-q=正负 d*N(v)，其中 d=|c(u)-q|。于是 c(u)=F(v,3 正负 d)。若 d<3，两种深度都严格在0..6 mm内，与 c(u)=F(u,0) 及 extended F 单射矛盾。此论证允许 outer 参数 u 取端点，不需额外 inward 符号假设或单独排除 outer 端点；只需内曲线端点证书。原审阅提出的额外 inward 符号排除与 outer-endpoint 分支未独立核验，现予撤回。

Bernstein 子分割的 PASS 是充分证；若出现全负系数叶则返回 FAIL；达到深度8或64 leaves仍 unresolved 则返回 UNKNOWN，不会升级为 PASS。非负半径下，异方位距离平方比同方位多出 2*r*rho*(1-cos(delta_theta))，故旋转曲面集合距离不小于子午线距离。该结论仍限于 pinned curve pair，不证明 CAD lip、native B-rep、生产壁厚或 physics。

**来源完整性待补：** source 固定 case/pins SHA 并核对四个 inputs，但没有 source/self SHA guard，source_pins 也不含 checker 源 hash。任何实际 GO 的外部 receipt 应钉住并前后复核 source SHA。此前版本 SHA-256：REVIEW.md 1d680f3a67b9fad91f3532987c0882fc09c95a2b4824ded92541e9542042a3a7，review.json 603c8f719da1d778fdf02c9790dd5560717e58d12a86eafbd304ab3ec235c3bd；本次修订仅更正最小距离证明说明，未改被审 source。