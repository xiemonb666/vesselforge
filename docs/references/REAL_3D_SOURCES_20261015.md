# 可复用真实器具 3D 几何来源（2026-10-15）

本目录只记录馆藏/实物来源的可下载三维几何与数据集入口，供后续器型和几何来源决策。它不证明网格就是完整实物剖面，也不等同于通过器壁、内腔、底面、闭合性或制造质量检查。此次只读取官方网页/API/数据表元数据，并对少量直链做 HTTP HEAD；没有下载网格、扫描数据或图像媒体。

## 可直接用来判断的结论

- **日常实物扫描：YCB Object and Model Set** 提供逐件 3D 网格档案，包括 bowl、mug、pitcher、bottle、plate。其官方论文把 Bowl（024）明确称为搪瓷涂层金属碗、Mug（025）称为金属杯；这是真实日常物的扫描几何，但不是陶瓷薄壁样本。论文说明 Poisson 网格为 watertight，同时明确说物体底面没有扫描、因此网格底面没有纹理。器内腔、网格坐标单位、实体壁厚均不能从数据集简介判定。
- **考古/历史器物扫描：Apsida 的 SHM 17946:0047** 是最有用的足部碗候选：馆方记录给出高度、底径、口径和足、柄、肩/腹特征，并提供 CC BY-SA 4.0 的 OBJ ZIP。它有两个水平柄，整体不能简化成纯旋转体。
- **Smithsonian 3D Digitization** 提供另一条免费原生几何路径。已核实的 Colonoware pot（2017.108.1.1）适合当窄颈鼓腹历史罐的几何近邻，但对象本身有破损、粘接和修复；F1980.194a-b 是有明确 H×D 的青花 beaker-shaped vase，可做历史 beaker/vase 参考。
- **未找到本轮可证实的日常陶瓷器皿实物扫描。** YCB 的日常金属器可作实物形体对照，不能说成陶瓷扫描。Amazon Berkeley Objects（ABO）虽有大量面向真实商品目录的 3D 资产，但 Berkeley 官方说明其 7,953 个网格为 artist-designed，因此不符合“由实物扫描得到”的筛选条件；可另作产品设计/外观对照，不能充当实物剖面证据。

## 证据标签

- **FACT_FROM_SOURCE**：来源明确给出的文字、编号、尺寸、文件格式、扫描/网格加工说明或许可。
- **VISUAL_INFERENCE**：仅基于来源页面的实物图或可视化表现的形态判断，不是量测值。
- **DESIGN_ASSUMPTION**：如后续建模必须补参数，必须显式标记为设计假设，不能写回来源事实。
- **UNKNOWN**：本轮官方来源没有给出的事实；文件存在不代表这些字段已知。

## 来源速览

| 来源与候选 | 家族适配 | 公开原生几何 | 关键已报尺度 | 主要边界 |
|---|---|---|---|---|
| [YCB 024 bowl](https://ycb-benchmarks.s3.amazonaws.com/index.html) | 日常 bowl | Berkeley processed mesh `.tgz`，HEAD 20,628,076 B | 159 × 53 mm（论文表格只写 Dimensions，轴名未逐项标注） | 搪瓷金属；底面未扫描；内腔/网格单位/壁厚未知 |
| [Apsida SHM 17946:0047](https://apsida.cut.ac.cy/items/show/49281) | 考古足圈碗、带柄器 | 页面列 OBJ；直接 ZIP，HEAD 21,934,200 B | H 119 mm；base D 70 mm；rim D 160 mm | 双柄；扫描坐标单位、内腔/底面覆盖、壁厚未知 |
| [Smithsonian Colonoware 2017.108.1.1](https://3d.si.edu/object/3d/colonoware-pot-cooper-river-charleston-county-sc%3A79da3e3f-3ad7-41de-8956-e891d88a3c5f) | 历史 pot / jar 近邻 | API 有 full OBJ ZIP 29,160,378 B、GLB 7,893,908 B | H 230 mm；D 267 mm | 破损、拼接及底部修复；不完整器物；壁厚/内外完整覆盖未知 |
| [Smithsonian F1980.194a-b](https://3d.si.edu/object/3d/beaker-shaped-vase-five-piece-garniture%3Ad8c64b96-4ebc-11ea-b77f-2e728ce88125) | 历史 beaker/vase | API 有 full OBJ ZIP 70,698,813 B、GLB 5,666,060 B | H 430 mm；D 206 mm | 器物是陈设用 beaker-shaped vase；壁厚/内腔/底足测量未知 |

## 日常实物扫描：YCB Object and Model Set

官方数据页列出逐件下载入口、Berkeley 扫描架和 Google 扫描网格；数据许可为 CC BY 4.0，代码为 MIT。官方论文说明扫描使用 BigBIRD 架上的 5 个 RGB-D 传感器与 5 个高分辨率 RGB 相机，物体放在转台上每 3°取一组视角，共 120 个转台方向、600 组 RGB-D 与 RGB 图。作者用 Poisson surface reconstruction 生成 watertight meshes；同段明确说明“物体底部未扫描，网格底部也没有纹理”。详见 [数据页](https://ycb-benchmarks.s3.amazonaws.com/index.html)、[Calli et al. 2015 论文](https://www.ri.cmu.edu/pub_files/2015/7/ICAR-FINAL.pdf)（扫描过程及表 I）与官方 [ycb_downloader.py](https://ycb-benchmarks.s3.amazonaws.com/scripts_to_publish/ycb_downloader.py)。

访问方式是单件 S3 直链，不需登录；示例文件头信息如下。HEAD 仅确认 URI/响应长度，不代表内容已下载或网格通过检查。Berkeley “processed”包官方代码说明包含分割点云和带纹理网格；本轮没有打开包内文件，因此不臆测其网格扩展名、坐标单位或是否同时含 OBJ/PLY。

| ID / 适配 | 来源论文中报告的实物数据 | 可复用档案 | 形态与适配说明 |
|---|---|---|---|
| `024_bowl` / bowl | `Dimensions` 159 × 53 mm；mass 147 g。表格列标题单位为 mm；论文表格未为两轴各自命名。图注称 enamel-coated metal bowl。若按常见 bowl 顺序把 159 mm 解释为外径、53 mm 解释为高，则 H/D = 53/159 = **0.3333（条件比例）**。 | [Berkeley meshes `.tgz`](https://ycb-benchmarks.s3.amazonaws.com/data/berkeley/024_bowl/024_bowl_berkeley_meshes.tgz)；20,628,076 B。 | 是真实日常金属碗形体的最佳 YCB 直接候选；材料并非陶瓷。论文扫描流程可支持真实外形扫描来源；内部碗面是否完整扫描没有按单件确认。 |
| `025_mug` / handled vessel、杯近邻 | `Dimensions` 80 × 82 mm；mass 118 g；图注称 metal mug。若假设第一值为直径、第二值为高，H/D = 82/80 = **1.025（条件比例）**。 | [Berkeley meshes `.tgz`](https://ycb-benchmarks.s3.amazonaws.com/data/berkeley/025_mug/025_mug_berkeley_meshes.tgz)；12,799,152 B。 | 实物金属杯；可对照杯身和柄整体，但它不是无柄 beaker，也不是陶瓷杯。柄的截面、接合处、器壁不应从尺寸表臆造。 |
| `019_pitcher_base` / jug 近邻 | `Dimensions` 108 × 235 mm；mass 178 g；表格未给各轴名称。 | [Berkeley meshes `.tgz`](https://ycb-benchmarks.s3.amazonaws.com/data/berkeley/019_pitcher_base/019_pitcher_base_berkeley_meshes.tgz)；40,894,472 B。 | 数据名为 Pitcher Base，论文图中为 pitcher。可作为日用带柄倾倒器近邻；不是有完整口沿/颈/盖的通用 jug 参数集。 |
| `006_mustard_bottle` / bottle | `Dimensions` 58 × 95 × 190 mm；mass 603 g；轴顺序未在表格中逐轴解释。 | [Berkeley meshes `.tgz`](https://ycb-benchmarks.s3.amazonaws.com/data/berkeley/006_mustard_bottle/006_mustard_bottle_berkeley_meshes.tgz)；20,051,277 B。 | 现实商业包装瓶，不是陶瓷储液瓶。可作日用 bottle 的实际扫描来源，但颈口、盖与器壁几何没有单独报数。 |
| `029_plate` / plate | `Dimensions` 258 × 24 mm；mass 279 g；图注称 metal plate。若假设 258 mm 为外径、24 mm 为总体厚/高包络，则厚高/径 = **0.0930（条件比例）**。 | [Berkeley meshes `.tgz`](https://ycb-benchmarks.s3.amazonaws.com/data/berkeley/029_plate/029_plate_berkeley_meshes.tgz)；37,703,920 B。 | 真实金属盘形体；不能替代陶瓷盘边、圈足或薄壁参数。 |

**尺寸与网格的边界：** 表 I 单位是 mm，mass 是 g；作者致谢提到 Michael Leddy 测量了对象物理属性，但论文未给每件测量的不确定度，也未明确 YCB mesh 顶点坐标的单位/比例。所以上表实物尺度可用于尺寸对照；mesh-native unit 必须在未来实际接入时以文件元数据/包文档确认。`watertight` 是作者对 Poisson 重建网格的表述；它不表示按真实器壁厚度封闭，也不解决扫描支撑面下的底面缺失。论文未声明碗内腔是否被完整采集，因此这里为 **UNKNOWN**。

许可：数据集 [官方页](https://ycb-benchmarks.s3.amazonaws.com/index.html) 标 CC BY 4.0，使用时保留归属并引用 Calli et al.；官方脚本许可 MIT。当前只 HEAD 检查 024、025、019、006、029 五个 Berkeley 处理网格链接，没有取回档案内容。

## 历史器物：Apsida / Medelhavsmuseet SHM 17946:0047

官方记录：[SHM 17946:0047 — Footed bowl](https://apsida.cut.ac.cy/items/show/49281)。Apsida 记录由数字文化遗产研究实验室托管，馆藏来源为 Medelhavsmuseet / Världskulturmuseerna Database。页面 `Format: OBJ`、`Type: 3D`，提供 3D Viewer，并把下载文件列为 `Footed_Bowl_SHM_17946_0047_Obj06.zip`；对该直链只做了 HEAD，HTTP 200、21,934,200 B，未取回 ZIP。页面记 `Rights: CC BY-SA 4.0`。

**FACT_FROM_SOURCE**

- 年代字段原文为 C.G. III（850–700 BC）；材料 `Earthenware; Clay; Pottery`，另外描述为浅砖色陶土、哑光浅赭色化妆土、哑光红/黑颜料。
- 高度 11.9 cm；底径 7.0 cm；口径 16.0 cm。比值 H/rim D = **0.7438**，base D/rim D = **0.4375**。这些是馆方/数据库记录的器物尺寸，不是从模型缩放推出来的值。
- 文字形态记录：微凸锥形足，足底有锥形内凹；向上收细的足柱；下腹凸；中腹微凸且与上腹之间有一道棱；上腹近筒形；尖锐口沿；中腹有两个水平圆柄。文字还明确记载内侧底部有同心圆装饰。
- 官方页面含两张器物图、OBJ 3D Viewer 和直接下载 ZIP。

**形态解释（依据馆方文字描述）**：足、足柱、分段圆身和圆口文字描述提示器身可能近似绕竖轴对称；这只是对文本形态的建模解释，没有检查或量测 OBJ。两侧水平圆柄是馆方记载的真实特征；移除柄后的模型不应称作与完整器物相符。

**UNKNOWN / 接入约束**：OBJ 坐标单位及实物尺寸到网格变换、扫描设备/摄影测量方法、模型是否有完整内表面/底面、mesh 是否 watertight、壁厚、口沿截面、足环/足柱横截面，以及各曲率位置均未在这条记录的元数据中给出。内底装饰文字不是内腔网格覆盖证据。若后续从 mesh 提取 meridian，必须先用馆方 H/rim/base 尺寸进行尺度校验，并把遮挡/缺面区域保留为 UNKNOWN。

许可与访问：CC BY-SA 4.0；再发布时需 attribution，衍生几何应按 ShareAlike 条款核对。直接文件：[OBJ ZIP](https://apsida.cut.ac.cy/files/original/529/49281/Footed_Bowl_SHM_17946_0047_Obj06.zip)。建议归属 “Medelhavsmuseet, SHM 17946:0047; via Apsida / Digital Heritage Research Lab” 并链接条目页与许可。

## 历史器物：Smithsonian 3D Digitization 与 Open Access API

Smithsonian 的 [3D API 文档](https://3d-api.si.edu/api-docs/)公开 `GET https://3d-api.si.edu/api/v1.0/content/file/search`，可用 `model_url`、`model_type`、`file_type`、`file_quality` 查 GLB/PLY/OBJ/glTF 等文件；文档称此接口返回的文件属于 Smithsonian Open Access。对象页面还必须逐件核对 Rights；`CC0` 可复制、修改、再发布，Smithsonian 推荐署名并要求不要误导来源。见 [Open Access FAQ](https://www.si.edu/openaccess/faq)。本轮直接请求了两个 `model_url` API 查询，只读取文件记录，未下载网格。

### Colonoware pot，NMAAHC 2017.108.1.1

来源：[馆藏对象记录](https://www.si.edu/object/colonoware-pot-cooper-river-charleston-county-sc%3Anmaahc_2017.108.1.1)与[3D 对象页](https://3d.si.edu/object/3d/colonoware-pot-cooper-river-charleston-county-sc%3A79da3e3f-3ad7-41de-8956-e891d88a3c5f)。对象记录将其定为约 1700–1800 年的 Colonoware 陶 pot；无釉，描述为圆鼓身、圆底、窄颈与微外撇口沿。尺寸 H×W 23.0×26.7 cm，另报直径 26.7 cm；H/D = **0.8614**。对象已断裂后拼接，底部做过修复；描述记录了内口沿/内身装饰，但不是完整扫描覆盖证明。

官方 API 包 UUID 为 `3d_package:79da3e3f-3ad7-41de-8956-e891d88a3c5f`。已核实的直接包：

- Full-resolution OBJ ZIP：`https://3d-api.si.edu/content/document/3d_package:79da3e3f-3ad7-41de-8956-e891d88a3c5f/resources/2017_108_1_1-ColonoPottery-full_resolution-obj_std.zip`，API 报 29,160,378 B。
- 可较轻量预览/接入的 GLB：`https://3d-api.si.edu/content/document/3d_package:79da3e3f-3ad7-41de-8956-e891d88a3c5f/resources/2017_108_1_1-ColonoPottery-150k-4096_std.glb`，API 报 7,893,908 B；另有 Draco GLB 1,525,892 B。
- API 查询：[按 model_url 搜索](https://3d-api.si.edu/api/v1.0/content/file/search?model_url=3d_package%3A79da3e3f-3ad7-41de-8956-e891d88a3c5f&rows=100)。文档允许 file_quality `Water_tight`，但对此包实际查询结果为 0 行；只表示没有这项质量标签，不证明网格必然不 watertight。

权利：该对象的 3D 页面标注 public domain/CC0，并建议署名 Smithsonian；不误述对象或数据来源。报告尺寸是馆藏记录的物理尺寸，API 未给网格单位/变换。**UNKNOWN**：该单件具体扫描设备/流程、完整内腔/底面覆盖、网格坐标单位、壁厚和 watertight 状态。可作为历史窄颈 pot/jar 近邻，但破损与修复会进入捕获几何；不要把它当作完好标准罐轮廓。

### Beaker-shaped vase，NMAA F1980.194a-b

来源：[Smithsonian 3D 对象页](https://3d.si.edu/object/3d/beaker-shaped-vase-five-piece-garniture%3Ad8c64b96-4ebc-11ea-b77f-2e728ce88125)及[National Museum of Asian Art 馆藏记录](https://asia.si.edu/explore-art-culture/collections/search/edanmdm%3Afsg_F1980.194a-b/)。馆藏记录称其为五件一组中的 beaker-shaped vase，清康熙时期（1662–1722），景德镇白瓷、釉下钴料、透明无色釉，尺寸 H×D = 43×20.6 cm，H/D = **2.0874**。文字记有外撇颈部；此器是陈设瓷，不等于日常饮用杯的使用形制。

官方 API 包 UUID `3d_package:d8c64b96-4ebc-11ea-b77f-2e728ce88125`：

- Full-resolution OBJ ZIP：`https://3d-api.si.edu/content/document/3d_package:d8c64b96-4ebc-11ea-b77f-2e728ce88125/resources/f1980_194-full_resolution-obj.zip`，API 报 70,698,813 B。
- GLB：`https://3d-api.si.edu/content/document/3d_package:d8c64b96-4ebc-11ea-b77f-2e728ce88125/resources/f1980_194-150k-4096.glb`，API 报 5,666,060 B；Low-resolution OBJ ZIP 为 6,860,431 B。
- API 查询：[按 model_url 搜索](https://3d-api.si.edu/api/v1.0/content/file/search?model_url=3d_package%3Ad8c64b96-4ebc-11ea-b77f-2e728ce88125&rows=100)。请求 `file_quality=Water_tight` 时 0 行，同样只意味着 API 没有水密标签。

权利：对象与 3D 媒体标 CC0/public domain；可复制、修改、再分发，建议 Smithsonian attribution。馆藏提供 H×D 尺度；mesh 坐标单位、测量/校准到 mesh 的变换、器内/底面覆盖、壁厚、rim/foot 局部截面、单件扫描技术仍是 **UNKNOWN**。可作历史 beaker/vase 原生几何路径候选，不能把 web viewer 存在等同于内外表面齐全或尺度已校准。

Smithsonian 的 [3D Program about](https://3d.si.edu/about) 说明其项目使用三维扫描技术；但所选器物记录没有逐件公布采集设备或处理链。因此该目录只把它们记作 Smithsonian 3D Digitization 机构发布的对象模型，不把未知的具体扫描方式写成事实。

## ABO：适合产品外观对照，但不列入“实物扫描”候选

[ABO 官方数据页](https://amazon-berkeley-objects.s3.amazonaws.com/index.html)称该数据集含 glTF 2.0、高分辨率材质模型；3D 总压缩档页面标为 `154 Gb`，3D metadata 公开在 `s3://amazon-berkeley-objects/3dmodels/metadata/`，字段含 `3dmodel_id/path/vertices/faces/extent_x/y/z`。它提供交互式 explorer、S3 与 Athena 元数据路径，但本轮不加载官方页面标出的 `68 Mb` explorer metadata、不下载 3D 模型包，也没有选定某一个 bowl/cup/jar 产品模型。

决定性限制：[Berkeley BAIR 官方项目说明](https://bcommons.berkeley.edu/amazon-berkeley-objects-large-scale-dataset-3d-object-understanding)称 7,953 个 mesh 为 **artist-designed**。因此 ABO 的商品关联模型不是从该件实物扫描获得的几何；extents 单位也未在公开 schema 内给出。可以作为真实商品名录、材料/纹理与视觉渲染参考，不能用来支撑实物外形测量、内腔、底足或壁厚结论。

授权：ABO 官方数据下载页声明 CC BY 4.0，要求适当署名、附许可证链接并说明改动；数据署名 Amazon.com，并建议引用 Collins et al., CVPR 2022。当前 catalog 以下载页 LICENSE 为准。模型实际可接入前仍应按所需商用场景复核各档案内授权说明。

## 家族覆盖与工程边界

| 器型家族 | 日常真实 3D 实物 | 考古/历史真实 3D 对象 | 本轮判断 |
|---|---|---|---|
| bowl | YCB 024，搪瓷金属、非陶瓷 | Apsida SHM 17946:0047（足柱、双柄） | 有实际对象网格与尺寸证据；无完整校准 meridian/壁厚证据 |
| beaker | YCB 025 mug 只是带柄杯近邻，不是 beaker | Smithsonian F1980.194a-b beaker-shaped vase | 有历史器物原生 OBJ/GLB 与 H×D；日常 beaker scan **UNKNOWN** |
| jar | 本轮未确认 YCB 明确命名为 jar 的扫描器；bottle 不冒充 jar | Smithsonian Colonoware pot 是窄颈 pot 近邻 | 日常 jar scan **UNKNOWN**；考古对象破损修复，不能当完整 jar 理想模板 |
| handled vessel | YCB 025 mug / 019 pitcher | Apsida 双柄碗 | 都有真实物体形态网格路径；陶瓷 daily handled scan **UNKNOWN** |
| plate | YCB 029 金属 plate | 本轮未核实到可下载的考古 plate 网格 | 有金属日常扫描；考古 plate **UNKNOWN** |
| bottle | YCB 006 mustard bottle（商业包装） | 本轮未核实到 bottle-form 馆藏 mesh | 有日常瓶扫描；陶瓷日常瓶与考古瓶 **UNKNOWN** |
| jug | YCB 019 Pitcher Base 是倾倒器近邻 | Met 36.20.25 等器物已有文字/图像资料，但本轮未核实对应原生 3D 下载 | 有日用 pitcher scan 近邻；考古 jug/ewer mesh **UNKNOWN** |

**网格复用不是 geometry PASS。** 对上述所有器物，报告的实物外形尺寸不等于网格文件坐标单位；未检查网格内部结构前，不得写入物理壁厚、材料、壁强度或器内曲线。对扫描缺面或被 Poisson 填补的区域，应保留扫描来源与 UNKNOWN 标记。实际网格接入、单位标定、封闭性检查和受损区域处理由主代理另行决策。

