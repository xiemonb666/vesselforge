# Real-world vessel forms: source catalogue (2026-10-15)

This supplement records first-party product and collection evidence for the vessel families in VesselForge. It is an evidence index for future family design, not a reconstruction dataset. Reported measurements, arithmetic ratios, visual observations, and generator assumptions are kept separate. Unknown dimensions remain unknown.

## What the current generator supports

The reviewed README describes one open turned vessel with a swept, fused handle and says bowls, cups, plates, jars, bottles, and jugs need their own references. `src/vesselforge/profile_catalog.py` currently exposes analytic `bowl`, `beaker`, and `jar` starters and explicitly says these are not matched to real vessels; its bowl-foot fraction is a rule of the prototype, not an observed ratio. There is no `models.py`; the prototype `VesselSpec` is in `src/vesselforge/geometry.py`. Its fixed 41 mm body width, 56 mm body height, and 4 mm wall, with bounds 36–48 mm, 50–62 mm, and 3.5–5 mm, are prototype settings, not sourced object measurements.

The old 24 mm opening / 4 mm wall hemispherical shell remains useful as a numerical test only. It should not be described as a real bowl type.

## Family coverage

| Family | Everyday references checked | Historical / archaeological references checked | Current evidence boundary |
|---|---|---|---|
| Bowl | Aberdeen ABDMS095708.121 footed porcelain; Time & Style Ame rice bowl; IKEA 365+ rounded bowl | Met 18.56.44 plain circular footed bowl; Met 18.56.47 lobed bowl; Apsida SHM 17946:0047 footed two-handled bowl | Several envelope/foot measurements and photographs, but no calibrated full section. Met 18.56.44 is the best first rotational analog; 18.56.47 is a separate lobed type. |
| Beaker | **UNKNOWN**. Asakano-gama mug is only a cup near-neighbor and is not confidently classifiable as an unhandled beaker. | Met 50.61.8 | Museum H and top diameter only; wall and foot are unknown. |
| Jar | **UNKNOWN** for a directly checked everyday ceramic jar with useful geometry. | Met 1975.268.184, formally a jar and described as a narrow-neck bulbous bottle | Shape and qualitative thin wall are described; no numeric section or neck dimensions. |
| Handled vessel | **UNKNOWN** for a daily example with source-backed handle cross-section/attachment geometry. | Met 36.20.25 ewer; Apsida SHM 17946:0047 bowl with handles | Handle presence/manufacture is documented for the ewer, not its geometry. Apsida metadata lists an OBJ scan but it was not downloaded or inspected. |
| Plate | **UNKNOWN** in this pass. | Met 1971.27 is titled *Bowl*; the curatorial text calls the decorated surface a plate. | Shallow envelope is known; foot and profile are not. |
| Bottle | **UNKNOWN** for an everyday ceramic bottle. | Met 1975.268.184 | The museum calls it a small bulbous bottle with a narrow neck, while its formal object title is *Jar*. |
| Jug | **UNKNOWN** for an everyday jug with dimensions/technical drawing in this pass. | Met 36.20.25 is an *Ewer* and described as an earthenware pitcher | Molded body, thrown neck and handle are described. Do not infer a spout contour from the title alone. |

## Most useful bowl references

### Everyday footed bowl with a published foot diameter — Aberdeen ABDMS095708.121

Official collection record: [Porcelain Small Footed Bowl](https://emuseum.aberdeencity.gov.uk/objects/186848/porcelain-small-footed-bowl), Aberdeen City Museums and Galleries, eMuseum (`emuseum.aberdeencity.gov.uk`). Object number ABDMS095708.121; maker Chris Keenan; dated 2007–2009; medium Limoges porcelain and celadon; museum classifications include food service, tableware, and utility.

**Reported facts:** overall H 53 mm × D 108 mm; base foot-ring diameter 31 mm. Five image entries appear on the page. Ratio H/overall D = 53/108 = **0.4907**; foot-ring D/overall D = 31/108 = **0.2870**. These are envelope ratios, not a meridian.

**Visual inference:** I directly inspected the main museum photograph. It shows a small circular foot ring and smoothly rounded bowl walls rising outward toward the rim. The rim looks light relative to the body in the photograph, but that is not a measured thin-wall fact. No complete section can be derived from this image.

**Geometry evidence and unknowns:** the foot-ring outside diameter is stated. Rim diameter, rim cross-section, ring height/cross-section, base thickness, wall thickness, and full inner/outer profile are **UNKNOWN**. The page does not provide a drawing or scan.

**Access and reuse:** the primary page is directly readable and the image is visible there. The page states © Chris Keenan and the site states images are copyrighted; no open image/model reuse license was found. Use measurements and silhouette notes as evidence; do not redistribute the image without permission.

### Everyday thin-body wording and alternate size — Time & Style Ame

Official product page: [Ame - Ceramic Brown - Rice Bowl](https://shopping.timeandstyle.com/en/products/ame-ceramic-brown-rice-bowl), Time & Style (`shopping.timeandstyle.com`). The page says it is made by a Mashiko ware potter on a wheel from soft Mashiko clay mixed with sand and calls it a “thin bowl.” It describes the Ame daily-basics line as made thinner, lighter, and slightly smaller for modern life.

**Reported facts:** small size W 120 × D 120 × H 55 mm; medium W 135 × D 135 × H 75 mm. Ratios H/W are **0.4583** (small) and **0.5556** (medium). Width/depth are not explicitly called rim diameters. Equal W/D suggests a circular footprint, but using either value as a CAD rim diameter is a **DESIGN_ASSUMPTION**.

**Visual inference / geometry boundary:** product images are available, but are not labeled calibrated side, underside, or section views. No foot ring, foot diameter/height, wall/base thickness, or measured inner/outer meridian is reported. “Thin” is qualitative only.

**Access and reuse:** open product page; no open image/geometry reuse license identified. No assets downloaded.

### Larger everyday scale — IKEA 365+ 202.783.51

Official product page: [IKEA 365+ bowl, rounded sides, white, 16 cm](https://www.ikea.com/gb/en/p/ikea-365-bowl-rounded-sides-white-20278351/), IKEA UK (`ikea.com`), item 202.783.51.

**Reported facts:** feldspar porcelain with glaze; H 70 mm; D 160 mm; brim volume 0.8 L. H/D = **0.4375**. Product text describes the series for everyday serving/eating. The four gallery image entries are product/use/table-setting views, not a section or calibrated underside view.

**Geometry boundary:** foot ring, base shape, wall thickness, rim section, and interior/exterior curve are **UNKNOWN**. General material text about porcelain being suitable for thin products does not establish this bowl's wall thickness. Page-listed 0.44 kg is under package details and is packaging weight, not measured object mass.

**Access and reuse:** open product page; no open image/geometry license found. No assets downloaded.

### Plain axisymmetric historical bowl with rim, foot, and height — Met 18.56.44

Official record: [Bowl, 18.56.44](https://www.metmuseum.org/art/collection/search/52389), The Metropolitan Museum of Art (`metmuseum.org`). China; Jin dynasty (1115–1234), 12th–13th century; stoneware with blue-gray glaze (Jun ware).

**Reported facts:** H **54 mm**, rim D **111 mm**, foot D **54 mm**. H/rim = **0.4865**; foot/rim = **0.4865**. The official page reports these values separately; it does not report foot height or a section.

**Visual inference:** I inspected the official main photograph (IIIF image [74400](https://collectionapi.metmuseum.org/api/collection/v1/iiif/52389/74400/main-image)). It shows a continuous unlobed circular rim, rounded deep bowl walls with a slight outward rise near the opening, and a low visible foot ring. It is a reasonable first **rotational analogue**; that judgment is based on the smooth circular form shown, not on a measured profile. One oblique view cannot prove perfect rotational symmetry.

**Geometry evidence and unknowns:** reported rim diameter and foot diameter are useful constraints. Rim lip cross-section, wall thickness, base thickness, foot height/section, and full meridian are **UNKNOWN**. No section or scan is linked on the reviewed page.

**Access and reuse:** the Met marks it Public Domain and states Met Open Access data/public-domain images are available for commercial and non-commercial reuse without permission or fee. This is a historical ceramic typology comparator; the record does **not** state an excavation context.

### Distinct lobed historical bowl — Met 18.56.47

Official record: [Lobed bowl, 18.56.47](https://www.metmuseum.org/art/collection/search/52680), The Metropolitan Museum of Art (`metmuseum.org`). China; Yuan to early Ming, 14th century; stoneware with crackled glaze (Ge ware).

**Reported facts:** H **73 mm**; overall and rim D **191 mm**; foot D **70 mm**. H/rim = **0.3822**; foot/rim = **0.3665**.

**Visual inference:** I inspected the official main photograph (IIIF image [1375845](https://collectionapi.metmuseum.org/api/collection/v1/iiif/52680/1375845/main-image)). It shows a broad shallow rounded bowl, a narrow low foot ring, outward-flaring upper walls, and a visibly lobed/wavy rim. It is not a plain smooth hemisphere. The body does not read as lotus-petal shaped; no clear rolled/inverted lip is visible in this view. The available photograph does not show a calibrated profile.

**Geometry evidence and unknowns:** the museum reports rim and foot diameters; the photo shows a foot ring and lobed rim. Rim-section geometry, lobe count/amplitude, wall/base thickness, foot height/section, and full profile are **UNKNOWN**. No section or scan is linked.

**Access and reuse:** Public Domain; the Met's Open Access statement permits commercial and non-commercial reuse of public-domain images/data. The museum page does not state an excavation context, so this is a historic-period comparator, not a claimed excavated find.

**Family implication:** retain this as a real future lobed-rim target. Do not pass it off as a plain axisymmetric source match by deleting the lobes. A rotational builder should use 18.56.44 or another plain circular reference, with lobing represented as a separate non-axisymmetric feature family.

### Archaeological footed bowl with a listed OBJ scan — Apsida SHM 17946:0047

Official item: [Footed bowl, SHM 17946:0047](https://apsida.cut.ac.cy/items/show/49281), Apsida / Medelhavsmuseet (`apsida.cut.ac.cy`). The indexed item metadata dates it to Cypro-Geometric III, 850–700 BCE, and identifies earthenware.

**Reported facts:** H **119 mm**, rim D **160 mm**, base D **70 mm**; H/rim = **0.7438** and base/rim = **0.4375**. The item description lists two horizontal round handles and describes a slightly convex conical foot with a conical cavity below, an upward-tapering stem, convex lower/middle body, a ridge, cylindrical upper body, and sharp rim.

**Visual/scan evidence boundary:** metadata links a 3D viewer and an OBJ format. The direct page timed out in this pass; the OBJ was not downloaded or inspected. Mesh units, scale calibration, internal-surface completeness, and whether the described complex body can be represented by a single meridian remain unverified. It is a handled, stemmed/footed bowl rather than a plain bowl profile.

**Access and reuse:** indexed item metadata states CC BY-SA 4.0 for the OBJ resource. Attribute the source and preserve share-alike terms for any derivative mesh if used. No scan was downloaded.

### Shallow historical plate-like bowl — Met 1971.27

Official record: [Bowl (1971.27)](https://www.metmuseum.org/art/collection/search/452209), The Metropolitan Museum of Art (`metmuseum.org`). Early 11th century, attributed to Egypt; earthenware, luster-painted. The formal title is *Bowl*; the curatorial description refers to its decorated surface as a plate.

**Reported facts:** H **67 mm**, D **249 mm**; H/D = **0.2691**. Two collection images are shown.

**Visual inference / geometry boundary:** its published envelope is much shallower than a hemispherical bowl, which makes it a useful plate-like comparison. Rim diameter, foot diameter/presence, lip, base, thickness, and exact basin curve are **UNKNOWN**. Do not invent a foot dimension.

**Access and reuse:** Public Domain / Met Open Access. The record does not state an excavation context.

## Other family references

### Beaker — Met 50.61.8

Official record: [Beaker, 50.61.8](https://www.metmuseum.org/art/collection/search/52532), The Met (`metmuseum.org`). Neolithic Longshan culture, c. 3000–1900 BCE; burned/burnished black earthenware. Reported H **186 mm**, top D **149 mm**; H/top-D = **1.2483**. Two images; Public Domain / Open Access. Rim section, foot, wall, and full profile are unknown. No excavation context is stated on the reviewed page.

### Jar / bottle-like vessel — Met 1975.268.184

Official record: [Jar, 1975.268.184](https://www.metmuseum.org/art/collection/search/50165), The Met (`metmuseum.org`). Late Jōmon, ca. 2500–1000 BCE; earthenware with incised decoration. The curatorial description calls it a small bulbous-shaped bottle with a narrow neck, thin walls, and two sets of suspension apertures. Reported H **200 mm**, listed D **165 mm** (measurement location unspecified); ratio **1.2121**. Three images; Public Domain / Open Access. Numeric wall thickness, neck opening/length, foot, aperture dimensions/coordinates, and full profile are unknown. The formal title remains *Jar*.

### Ewer / pitcher with handle — Met 36.20.25

Official record: [Ewer, 36.20.25](https://www.metmuseum.org/art/collection/search/449058), The Met (`metmuseum.org`). Excavated at Nishapur, Iran; 12th–13th century; unglazed earthenware with molded decoration. The description says the body was formed from two stamped hemispherical molds, joined with wet clay, and smoothed at the seam; the neck and handle were separately wheel-thrown and attached. Reported H **279 mm**, listed D **146 mm** (location unspecified); ratio **1.9110**. Four images; Public Domain / Open Access. Handle presence and construction are described; handle cross-section/coordinates, wall thickness, exact body profile, and spout contour are unknown. The title is *Ewer* and the text calls it a pitcher; do not claim a measured jug profile.

### Everyday cup near-neighbor — Asakano-gama SL-MUG-SL

Maker page: [Slim line mug cup](https://asakano.net/catalog/product120.php?pd=26&pl=en), Asakano-gama (`asakano.net`). The maker describes practical everyday ware, red clay and white glaze, an unglazed lower part, and handmade production. Reported H **88 mm**, D **82 mm**, capacity **260 ml**, mass **190 g**; H/D = **1.0732**. The text does not establish handle presence or foot geometry; do not classify it as an exact beaker or handled-vessel reference without further visual/object evidence. No section/scan or open image license was found; the maker page reserves rights.

## First candidate parameter constraints

### Daily footed bowl candidate (Aberdeen scale)

These reported dimensions can seed a candidate envelope: overall D **108 mm**, H **53 mm**, foot-ring D **31 mm**. Keep the source-reported extents separate from assumptions:

- **Reported facts:** overall height, overall diameter, and foot-ring diameter as above; calculated H/D **0.4907** and foot/overall-D **0.2870**.
- **Design assumptions needed by a rotational CAD builder:** using overall diameter as the maximum opening diameter; treating the vessel as axisymmetric; choosing meridian control points; choosing foot-ring height/section.
- **Unknown:** numeric wall thickness, base thickness, exact rim diameter/profile, interior/exterior meridian. The photograph's apparent light rim is not a measurement.
- **Separate thin-body evidence:** Time & Style describes its own Ame bowl as thin, but does not report a foot. Do not silently combine that qualitative feature with Aberdeen and attribute it to one object.
- **Alternate size variants:** Ame small 120 × 55 mm (W/D × H; circular mapping remains an assumption), IKEA 160 × 70 mm, and Ame medium 135 × 75 mm. Their foot and section details remain unknown.

### Plain historical rotational analogue (Met 18.56.44)

For a first archaeological/historical rotational family candidate, constrain the visible envelope with the museum's **rim D 111 mm**, **H 54 mm**, and **foot D 54 mm**. Ratios are H/rim **0.4865** and foot/rim **0.4865**. The photograph supports a continuous circular lip, rounded bowl body, and low foot ring.

The CAD meridian is still a **DESIGN_ASSUMPTION**: the Met has no section/scan, and a single photograph cannot provide precise inner and outer curves. Keep wall/base thickness, foot height/section, and lip cross-section unset/unknown until measured from an object or a verified section source. This candidate is distinct from the lobed Met 18.56.47 bowl, which belongs to a separate future non-axisymmetric family.

## Evidence and reuse rules for follow-on work

1. Treat a published maximum diameter as a rim diameter only when the source explicitly labels it “rim” or the mapping is marked `DESIGN_ASSUMPTION`.
2. Never infer wall thickness, foot dimensions, neck dimensions, handle section, or Bezier controls from an uncalibrated beauty photograph.
3. Keep official words such as *thin*, *footed*, *bottle*, or *pitcher* qualitative unless the source gives a numeric measurement or a verified scan.
4. The Met records here are Open Access/Public Domain as individually stated. The Apsida OBJ metadata says CC BY-SA 4.0. Aberdeen photos are © Chris Keenan / Aberdeen Art Gallery and Museums; product photos from IKEA, Time & Style, and Asakano-gama have no open reuse license identified in this pass.
5. No image, OBJ, CAD, or mesh was downloaded. The Apsida scan's scale and surface completeness were not validated. A source image count does not imply an orthographic set or a profile drawing.

## Source review notes

Reviewed on **2026-10-15**. Primary pages directly checked in this pass include the Met's individual object records, IKEA UK's product page, Time & Style's product page, Asakano-gama's maker catalog, and Aberdeen's eMuseum record/photo. The Apsida item was available through indexed metadata; its direct page timed out. No paid source, private message, image download, scan download, or modification to code/data was part of this catalogue.
