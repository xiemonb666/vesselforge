"""Generic, semantic meridian sections revolved into closed vessel solids.

The module keeps the meridian as the source of truth.  Each section edge is
revolved separately, sewn into one shell, and its face role is carried through
the sewing history.  This is intended for geometry candidates; it makes no
claim about a measured specimen profile or physical material behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Literal, Sequence

import cadquery as cq
import numpy as np
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
from OCP.BRepLib import BRepLib
from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt
from OCP.TopoDS import TopoDS


CurveKind = Literal["line", "bezier", "arc"]
RegionRole = Literal["body_outer", "body_inner", "rim", "base", "foot"]
_ROLES = {"body_outer", "body_inner", "rim", "base", "foot"}
_JOIN_TOL_MM = 2e-7


def _point2(value: Sequence[float], label: str) -> tuple[float, float]:
    try:
        result = tuple(float(component) for component in value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be an (r, z) point") from exc
    if len(result) != 2 or not all(math.isfinite(component) for component in result):
        raise ValueError(f"{label} must be a finite (r, z) point")
    return result[0], result[1]


@dataclass(frozen=True)
class MeridianSegment:
    """One directed meridian edge, with its semantic face role.

    ``points`` means two endpoints for a line, four control points for a cubic
    Bezier, and start / through / end points for a circular arc.
    """

    role: RegionRole
    kind: CurveKind
    points: tuple[tuple[float, float], ...]

    def __post_init__(self) -> None:
        if self.role not in _ROLES:
            raise ValueError(f"unsupported meridian role: {self.role}")
        expected = {"line": 2, "bezier": 4, "arc": 3}.get(self.kind)
        if expected is None:
            raise ValueError(f"unsupported meridian curve kind: {self.kind}")
        normalized = tuple(_point2(point, f"{self.role}.{self.kind}.point") for point in self.points)
        if len(normalized) != expected:
            raise ValueError(f"{self.kind} segment requires exactly {expected} points")
        object.__setattr__(self, "points", normalized)
        if self.kind == "arc":
            center, radius, _, sweep = self._arc_frame()
            del center
            if radius <= 1e-10 or abs(sweep) <= 1e-10 or abs(sweep) >= 2.0 * math.pi - 1e-8:
                raise ValueError("arc must define a non-degenerate sweep smaller than a full circle")

    @property
    def start(self) -> tuple[float, float]:
        return self.points[0]

    @property
    def end(self) -> tuple[float, float]:
        return self.points[-1]

    def _arc_frame(self) -> tuple[np.ndarray, float, float, float]:
        p0, pm, p1 = (np.asarray(point, dtype=np.float64) for point in self.points)
        matrix = 2.0 * np.vstack((pm - p0, p1 - p0))
        determinant = float(np.linalg.det(matrix))
        if abs(determinant) <= 1e-12:
            raise ValueError("arc start, through, and end points must not be collinear")
        rhs = np.asarray(
            [float(pm @ pm - p0 @ p0), float(p1 @ p1 - p0 @ p0)],
            dtype=np.float64,
        )
        center = np.linalg.solve(matrix, rhs)
        radius = float(np.linalg.norm(p0 - center))
        a0 = math.atan2(float(p0[1] - center[1]), float(p0[0] - center[0]))
        am = math.atan2(float(pm[1] - center[1]), float(pm[0] - center[0]))
        a1 = math.atan2(float(p1[1] - center[1]), float(p1[0] - center[0]))
        ccw = (a1 - a0) % (2.0 * math.pi)
        mid_ccw = (am - a0) % (2.0 * math.pi)
        sweep = ccw if mid_ccw <= ccw + 1e-10 else ccw - 2.0 * math.pi
        return center, radius, a0, sweep

    def point(self, parameter: float) -> np.ndarray:
        t = float(parameter)
        if not math.isfinite(t) or t < -1e-12 or t > 1.0 + 1e-12:
            raise ValueError("curve parameter must lie in [0, 1]")
        t = min(1.0, max(0.0, t))
        p = np.asarray(self.points, dtype=np.float64)
        if self.kind == "line":
            return p[0] + t * (p[1] - p[0])
        if self.kind == "bezier":
            s = 1.0 - t
            return s**3 * p[0] + 3.0 * s**2 * t * p[1] + 3.0 * s * t**2 * p[2] + t**3 * p[3]
        center, radius, start_angle, sweep = self._arc_frame()
        angle = start_angle + sweep * t
        return center + radius * np.asarray([math.cos(angle), math.sin(angle)])

    def derivative(self, parameter: float) -> np.ndarray:
        t = float(parameter)
        if not math.isfinite(t) or t < -1e-12 or t > 1.0 + 1e-12:
            raise ValueError("curve parameter must lie in [0, 1]")
        t = min(1.0, max(0.0, t))
        p = np.asarray(self.points, dtype=np.float64)
        if self.kind == "line":
            return p[1] - p[0]
        if self.kind == "bezier":
            s = 1.0 - t
            return 3.0 * (s**2 * (p[1] - p[0]) + 2.0 * s * t * (p[2] - p[1]) + t**2 * (p[3] - p[2]))
        _, radius, start_angle, sweep = self._arc_frame()
        angle = start_angle + sweep * t
        return radius * sweep * np.asarray([-math.sin(angle), math.cos(angle)])

    def second_derivative(self, parameter: float) -> np.ndarray:
        t = float(parameter)
        if not math.isfinite(t) or t < -1e-12 or t > 1.0 + 1e-12:
            raise ValueError("curve parameter must lie in [0, 1]")
        t = min(1.0, max(0.0, t))
        p = np.asarray(self.points, dtype=np.float64)
        if self.kind == "line":
            return np.zeros(2, dtype=np.float64)
        if self.kind == "bezier":
            return 6.0 * (
                (1.0 - t) * (p[2] - 2.0 * p[1] + p[0])
                + t * (p[3] - 2.0 * p[2] + p[1])
            )
        _, radius, start_angle, sweep = self._arc_frame()
        angle = start_angle + sweep * t
        return -radius * sweep**2 * np.asarray([math.cos(angle), math.sin(angle)])

    def reversed(self) -> "MeridianSegment":
        if self.kind == "arc":
            points = (self.points[2], self.points[1], self.points[0])
        else:
            points = tuple(reversed(self.points))
        return MeridianSegment(role=self.role, kind=self.kind, points=points)

    def to_edge(self) -> cq.Edge:
        def as_vector(point: tuple[float, float]) -> cq.Vector:
            return cq.Vector(float(point[0]), 0.0, float(point[1]))

        if self.kind == "line":
            return cq.Edge.makeLine(as_vector(self.points[0]), as_vector(self.points[1]))
        if self.kind == "bezier":
            return cq.Edge.makeBezier([as_vector(point) for point in self.points])
        return cq.Edge.makeThreePointArc(*(as_vector(point) for point in self.points))

    def to_dict(self) -> dict[str, object]:
        return {"role": self.role, "curve": self.kind, "points_rz_mm": [list(point) for point in self.points]}


@dataclass(frozen=True)
class MeridianSection:
    """A directed, closed meridian polygon made from smooth CAD segments."""

    segments: tuple[MeridianSegment, ...]
    name: str = "unnamed_meridian_section"

    def validate(self, *, join_tolerance_mm: float = _JOIN_TOL_MM) -> None:
        if len(self.segments) < 3:
            raise ValueError("section requires at least three segments")
        tolerance = float(join_tolerance_mm)
        if not math.isfinite(tolerance) or tolerance <= 0.0:
            raise ValueError("join_tolerance_mm must be finite and positive")
        for index, segment in enumerate(self.segments):
            next_segment = self.segments[(index + 1) % len(self.segments)]
            gap = float(np.linalg.norm(np.asarray(segment.end) - np.asarray(next_segment.start)))
            if gap > tolerance:
                raise ValueError(f"section is open between segments {index} and {(index + 1) % len(self.segments)} ({gap:.6g} mm)")

        polyline: list[np.ndarray] = []
        for segment in self.segments:
            steps = 40 if segment.kind == "arc" else 72 if segment.kind == "bezier" else 1
            points = [segment.point(i / steps) for i in range(steps + 1)]
            if not polyline:
                polyline.extend(points)
            else:
                polyline.extend(points[1:])
        coordinates = np.asarray(polyline, dtype=np.float64)
        if not np.isfinite(coordinates).all():
            raise ValueError("section contains non-finite sampled coordinates")
        if float(np.min(coordinates[:, 0])) < -tolerance:
            raise ValueError("section crosses the rotation axis into negative radius")
        if float(np.max(np.linalg.norm(np.diff(coordinates, axis=0), axis=1))) <= tolerance:
            raise ValueError("section has no finite extent")
        if _polyline_self_intersects(coordinates, tolerance=max(1e-9, tolerance * 0.25)):
            raise ValueError("section meridian self-intersects")
        signed_area = 0.5 * float(
            np.sum(coordinates[:-1, 0] * coordinates[1:, 1] - coordinates[1:, 0] * coordinates[:-1, 1])
        )
        if abs(signed_area) <= tolerance**2:
            raise ValueError("section encloses no meridian area")

    def sampled_points(self, *, samples_per_bezier: int = 80, samples_per_arc: int = 48) -> np.ndarray:
        result: list[np.ndarray] = []
        for segment in self.segments:
            count = samples_per_bezier if segment.kind == "bezier" else samples_per_arc if segment.kind == "arc" else 1
            rows = [segment.point(i / count) for i in range(count + 1)]
            result.extend(rows if not result else rows[1:])
        return np.asarray(result, dtype=np.float64)

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "schema": "vf.meridian_section.v1",
            "name": self.name,
            "coordinate_frame": "radius_mm_vs_z_mm; revolved about Z axis; Z-up",
            "orientation": "directed closed boundary; native face role is assigned from source segment",
            "segments": [segment.to_dict() for segment in self.segments],
        }


def _polyline_self_intersects(points: np.ndarray, *, tolerance: float) -> bool:
    if len(points) < 4:
        return False
    starts = points[:-1]
    ends = points[1:]
    count = len(starts)

    def orientation(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
        ab = b - a
        ac = c - a
        return float(ab[0] * ac[1] - ab[1] * ac[0])

    def on_segment(a: np.ndarray, b: np.ndarray, p: np.ndarray) -> bool:
        return (
            min(a[0], b[0]) - tolerance <= p[0] <= max(a[0], b[0]) + tolerance
            and min(a[1], b[1]) - tolerance <= p[1] <= max(a[1], b[1]) + tolerance
        )

    for i in range(count):
        a, b = starts[i], ends[i]
        for j in range(i + 2, count):
            if i == 0 and j == count - 1:
                continue
            c, d = starts[j], ends[j]
            if (
                max(a[0], b[0]) < min(c[0], d[0]) - tolerance
                or max(c[0], d[0]) < min(a[0], b[0]) - tolerance
                or max(a[1], b[1]) < min(c[1], d[1]) - tolerance
                or max(c[1], d[1]) < min(a[1], b[1]) - tolerance
            ):
                continue
            o1, o2 = orientation(a, b, c), orientation(a, b, d)
            o3, o4 = orientation(c, d, a), orientation(c, d, b)
            if ((o1 > tolerance and o2 < -tolerance) or (o1 < -tolerance and o2 > tolerance)) and (
                (o3 > tolerance and o4 < -tolerance) or (o3 < -tolerance and o4 > tolerance)
            ):
                return True
            if (
                (abs(o1) <= tolerance and on_segment(a, b, c))
                or (abs(o2) <= tolerance and on_segment(a, b, d))
                or (abs(o3) <= tolerance and on_segment(c, d, a))
                or (abs(o4) <= tolerance and on_segment(c, d, b))
            ):
                return True
    return False


def normal_offset_point_and_derivative(
    segment: MeridianSegment, parameter: float, offset_mm: float
) -> tuple[np.ndarray, np.ndarray]:
    """Return the right-normal offset and its derivative for a directed curve.

    For a bottom-to-rim inner wall, the right normal is outward: given tangent
    ``(r', z')`` it is ``(z', -r') / hypot(r', z')``.  Positive offsets follow
    ``r_out = r + t*z'/speed`` and ``z_out = z - t*r'/speed``.
    """
    distance = float(offset_mm)
    if not math.isfinite(distance):
        raise ValueError("offset_mm must be finite")
    point = segment.point(parameter)
    tangent = segment.derivative(parameter)
    acceleration = segment.second_derivative(parameter)
    speed = float(np.linalg.norm(tangent))
    if speed <= 1e-12:
        raise ValueError("normal offset is undefined where the source tangent vanishes")
    right = np.asarray([tangent[1], -tangent[0]], dtype=np.float64)
    right_derivative = np.asarray([acceleration[1], -acceleration[0]], dtype=np.float64)
    tangent_dot_acceleration = float(tangent @ acceleration)
    normal = right / speed
    normal_derivative = right_derivative / speed - right * tangent_dot_acceleration / speed**3
    return point + distance * normal, tangent + distance * normal_derivative


def normal_offset_bezier_segments(
    segment: MeridianSegment,
    offset_mm: float,
    *,
    fit_tolerance_mm: float = 0.005,
    role: RegionRole = "body_outer",
    max_segments: int = 512,
) -> tuple[list[MeridianSegment], float]:
    """Fit a sampled true normal offset with adaptively subdivided cubics.

    The returned deviation is the largest of three interior checks per
    accepted subcurve. It is an adaptive fit diagnostic, not a continuous or
    global approximation-error certificate.
    """
    if segment.kind != "bezier":
        raise ValueError("adaptive offset fitting currently requires a cubic Bezier source")
    distance = float(offset_mm)
    tolerance = float(fit_tolerance_mm)
    if not math.isfinite(distance) or distance <= 0.0:
        raise ValueError("offset_mm must be finite and positive")
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("fit_tolerance_mm must be finite and positive")
    if isinstance(max_segments, bool) or int(max_segments) < 1:
        raise ValueError("max_segments must be a positive integer")

    accepted: list[MeridianSegment] = []
    maximum_error = 0.0

    def fit(a: float, b: float, depth: int) -> None:
        nonlocal maximum_error
        p0, d0 = normal_offset_point_and_derivative(segment, a, distance)
        p3, d1 = normal_offset_point_and_derivative(segment, b, distance)
        span = b - a
        candidate = MeridianSegment(
            role=role,
            kind="bezier",
            points=(
                tuple(p0),
                tuple(p0 + span * d0 / 3.0),
                tuple(p3 - span * d1 / 3.0),
                tuple(p3),
            ),
        )
        error = max(
            float(
                np.linalg.norm(
                    candidate.point(local_t)
                    - normal_offset_point_and_derivative(segment, a + span * local_t, distance)[0]
                )
            )
            for local_t in (0.25, 0.5, 0.75)
        )
        if error <= tolerance:
            accepted.append(candidate)
            maximum_error = max(maximum_error, error)
            if len(accepted) > int(max_segments):
                raise ValueError(f"normal offset fit exceeded the {max_segments}-segment resource limit")
            return
        if depth >= 18:
            raise ValueError("normal offset could not meet fit_tolerance_mm before the subdivision limit")
        mid = 0.5 * (a + b)
        fit(a, mid, depth + 1)
        fit(mid, b, depth + 1)

    fit(0.0, 1.0, 0)
    return accepted, maximum_error


def meridian_volume_mm3(section: MeridianSection, *, quadrature_order: int = 32) -> float:
    """Independent volume integral ``pi * abs(∮ r² dz)`` over the meridian."""
    section.validate()
    if isinstance(quadrature_order, bool) or int(quadrature_order) < 4:
        raise ValueError("quadrature_order must be an integer of at least four")
    nodes, weights = np.polynomial.legendre.leggauss(int(quadrature_order))
    total = 0.0
    for segment in section.segments:
        for node, weight in zip(nodes, weights):
            parameter = 0.5 * (float(node) + 1.0)
            radius = float(segment.point(parameter)[0])
            dz = float(segment.derivative(parameter)[1])
            total += 0.5 * float(weight) * radius * radius * dz
    return math.pi * abs(total)


def build_revolved_solid(
    section: MeridianSection,
    *,
    sewing_tolerance_mm: float = 2e-6,
) -> tuple[cq.Shape, dict[str, object]]:
    """Revolve and sew segment-derived faces while preserving semantic lineage."""
    section.validate()
    sewing_tolerance = float(sewing_tolerance_mm)
    if not math.isfinite(sewing_tolerance) or sewing_tolerance <= 0.0:
        raise ValueError("sewing_tolerance_mm must be finite and positive")

    axis = gp_Ax1(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(0.0, 0.0, 1.0))
    sewing = BRepBuilderAPI_Sewing(sewing_tolerance)
    staged: list[dict[str, object]] = []
    source_face_count = 0
    for segment_index, segment in enumerate(section.segments):
        edge = segment.to_edge()
        if not edge.isValid() or len(edge.Edges()) != 1:
            raise ValueError(f"section segment {segment_index} did not produce one valid OCC edge")
        revolver = BRepPrimAPI_MakeRevol(edge.wrapped, axis, 2.0 * math.pi, True)
        revolver.Build()
        revolved_shape = revolver.Shape()
        if revolved_shape.IsNull():
            # A segment on the rotation axis becomes a degenerate edge rather
            # than a surface and is already closed by adjacent revolved faces.
            if max(abs(segment.start[0]), abs(segment.end[0])) <= _JOIN_TOL_MM:
                continue
            raise ValueError(f"revolution of segment {segment_index} produced a null shape")
        generated = cq.Shape.cast(revolved_shape)
        for generated_face in generated.Faces():
            sewing.Add(generated_face.wrapped)
            staged.append(
                {
                    "source_face": generated_face.wrapped,
                    "source_segment_index": segment_index,
                    "role": segment.role,
                }
            )
            source_face_count += 1
    if source_face_count < 3:
        raise ValueError("revolved section produced fewer than three surface faces")

    sewing.Perform()
    sewn = cq.Shape.cast(sewing.SewedShape())
    shells = sewn.Shells()
    if len(shells) != 1 or not shells[0].wrapped.Closed():
        raise ValueError(
            "sewn revolved section must produce one closed shell; "
            f"shells={len(shells)}, free_edges={sewing.NbFreeEdges()}, multiple_edges={sewing.NbMultipleEdges()}"
        )
    solid_builder = BRepBuilderAPI_MakeSolid(TopoDS.Shell_s(shells[0].wrapped))
    if not solid_builder.IsDone():
        raise ValueError("OpenCascade could not make a solid from the sewn shell")
    raw_solid = solid_builder.Solid()
    if not BRepLib.OrientClosedSolid_s(raw_solid):
        raise ValueError("OpenCascade could not orient the closed shell with matter inside")
    solid = cq.Shape.cast(raw_solid)
    if not solid.isValid() or len(solid.Solids()) != 1 or len(solid.Shells()) != 1:
        raise ValueError("revolved section did not produce one valid solid and shell")
    if not solid.Shells()[0].wrapped.Closed() or not math.isfinite(float(solid.Volume())) or solid.Volume() <= 0.0:
        raise ValueError("revolved section shell is open or has non-positive volume")

    face_lineage: dict[int, dict[str, object]] = {}
    for row in staged:
        sewn_face_shape = sewing.Modified(row["source_face"])
        matches = [
            face_index
            for face_index, face in enumerate(solid.Faces())
            if face.wrapped.IsSame(sewn_face_shape)
        ]
        if len(matches) != 1:
            raise ValueError("native sewing history did not resolve a segment face to exactly one solid face")
        face_index = matches[0]
        entry = face_lineage.setdefault(face_index, {"roles": set(), "source_segment_indices": []})
        entry["roles"].add(str(row["role"]))
        entry["source_segment_indices"].append(int(row["source_segment_index"]))

    if set(face_lineage) != set(range(len(solid.Faces()))):
        missing = sorted(set(range(len(solid.Faces()))) - set(face_lineage))
        raise ValueError(f"revolved solid has faces without native segment lineage: {missing}")
    semantics: dict[str, object] = {}
    for face_index, entry in sorted(face_lineage.items()):
        roles = sorted(str(role) for role in entry["roles"])
        if len(roles) != 1:
            raise ValueError(f"solid face {face_index} received conflicting semantic roles: {roles}")
        adaptor = BRepAdaptor_Surface(solid.Faces()[face_index].wrapped, True)
        semantics[str(face_index)] = {
            "role": roles[0],
            "source_segment_indices": sorted(set(entry["source_segment_indices"])),
            "surface_type_occ_id": int(adaptor.GetType()),
            "lineage_basis": "generated face from source meridian edge; propagated by BRepBuilderAPI_Sewing.Modified",
        }
    return solid, {
        "schema": "vf.native_meridian_face_lineage.v1",
        "status": "PASS",
        "face_count": len(solid.Faces()),
        "source_revolved_face_count": source_face_count,
        "region_roles": sorted({str(row["role"]) for row in staged}),
        "faces": semantics,
    }


@dataclass(frozen=True)
class FootedBowlDesign:
    """Dimensioned bowl candidate; unmeasured craft details stay assumptions."""

    name: str
    rim_outer_diameter_mm: float
    overall_height_mm: float
    wall_thickness_mm: float
    foot_outer_diameter_mm: float
    foot_height_mm: float
    body_floor_radius_mm: float
    body_floor_z_mm: float
    underside_recess_z_mm: float
    foot_contact_width_mm: float
    rim_tangent_degrees: float = 55.0
    normal_offset_fit_tolerance_mm: float = 0.005
    body_start_handle_fraction: float = 0.60
    body_end_handle_height_fraction: float = 0.22

    def validate(self) -> None:
        dimensions = {
            "rim_outer_diameter_mm": self.rim_outer_diameter_mm,
            "overall_height_mm": self.overall_height_mm,
            "wall_thickness_mm": self.wall_thickness_mm,
            "foot_outer_diameter_mm": self.foot_outer_diameter_mm,
            "foot_height_mm": self.foot_height_mm,
            "body_floor_radius_mm": self.body_floor_radius_mm,
            "body_floor_z_mm": self.body_floor_z_mm,
            "underside_recess_z_mm": self.underside_recess_z_mm,
            "foot_contact_width_mm": self.foot_contact_width_mm,
            "rim_tangent_degrees": self.rim_tangent_degrees,
            "normal_offset_fit_tolerance_mm": self.normal_offset_fit_tolerance_mm,
            "body_start_handle_fraction": self.body_start_handle_fraction,
            "body_end_handle_height_fraction": self.body_end_handle_height_fraction,
        }
        for name, value in dimensions.items():
            if isinstance(value, bool) or not math.isfinite(float(value)):
                raise ValueError(f"{name} must be a finite number")
            if name != "rim_tangent_degrees" and float(value) <= 0.0:
                raise ValueError(f"{name} must be positive")
        if self.foot_outer_diameter_mm >= self.rim_outer_diameter_mm:
            raise ValueError("foot diameter must be smaller than the rim diameter")
        if self.foot_height_mm <= 2.0 * min(0.5, self.foot_height_mm / 8.0):
            raise ValueError("foot height is too small to carry its rounded contact edges")
        if not 5.0 < self.rim_tangent_degrees < 85.0:
            raise ValueError("rim_tangent_degrees must lie strictly between 5 and 85 degrees")
        if not 0.05 <= self.body_start_handle_fraction <= 1.0:
            raise ValueError("body_start_handle_fraction must lie between 0.05 and 1.0")
        if not 0.05 <= self.body_end_handle_height_fraction <= 0.45:
            raise ValueError("body_end_handle_height_fraction must lie between 0.05 and 0.45")
        if self.body_floor_radius_mm >= self.foot_outer_diameter_mm / 2.0:
            raise ValueError("body_floor_radius_mm must remain inside the foot outer radius")
        if self.underside_recess_z_mm <= 0.0 or self.body_floor_z_mm <= self.underside_recess_z_mm:
            raise ValueError("base floor must lie above a positive underside recess")
        if self.body_floor_z_mm - self.wall_thickness_mm <= self.underside_recess_z_mm + 1e-8:
            raise ValueError("central base thickness must exceed the body wall thickness to avoid a folded lower junction")
        if self.foot_height_mm >= self.overall_height_mm:
            raise ValueError("foot height must be below the rim height")


def make_footed_bowl_section(design: FootedBowlDesign) -> tuple[MeridianSection, dict[str, object]]:
    """Create a rounded, normal-offset footed-bowl section from design inputs."""
    design.validate()
    radius = float(design.rim_outer_diameter_mm) / 2.0
    height = float(design.overall_height_mm)
    wall = float(design.wall_thickness_mm)
    lip_radius = wall / 2.0
    center = np.asarray([radius - lip_radius, height - lip_radius], dtype=np.float64)
    theta = math.radians(float(design.rim_tangent_degrees))
    tangent = np.asarray([math.cos(theta), math.sin(theta)], dtype=np.float64)
    outward = np.asarray([math.sin(theta), -math.cos(theta)], dtype=np.float64)
    inner_lip = center - lip_radius * outward
    outer_lip = center + lip_radius * outward
    cap_through = center + lip_radius * np.asarray([math.cos(theta), math.sin(theta)], dtype=np.float64)

    floor_radius = float(design.body_floor_radius_mm)
    floor_z = float(design.body_floor_z_mm)
    radial_body_span = float(inner_lip[0]) - floor_radius
    start_handle = float(design.body_start_handle_fraction) * radial_body_span
    end_handle = max(float(design.body_end_handle_height_fraction) * height, wall * 3.0)
    inner_body = MeridianSegment(
        role="body_inner",
        kind="bezier",
        points=(
            (floor_radius, floor_z),
            (floor_radius + start_handle, floor_z),
            tuple(inner_lip - end_handle * tangent),
            tuple(inner_lip),
        ),
    )
    outer_body_forward, offset_fit_error = normal_offset_bezier_segments(
        inner_body,
        wall,
        fit_tolerance_mm=float(design.normal_offset_fit_tolerance_mm),
        role="body_outer",
    )

    foot_radius = float(design.foot_outer_diameter_mm) / 2.0
    corner = min(0.5, float(design.foot_height_mm) / 8.0, float(design.foot_contact_width_mm) / 4.0)
    contact_outer = foot_radius - corner
    contact_inner = foot_radius - 2.0 * corner - float(design.foot_contact_width_mm)
    if contact_inner <= corner or float(design.underside_recess_z_mm) <= corner:
        raise ValueError("foot contact width or underside recess leaves no finite support wall")
    body_outer_start = outer_body_forward[0].start
    foot_top_inner = (foot_radius - corner, float(design.foot_height_mm))
    shoulder_span = foot_top_inner[0] - body_outer_start[0]
    if shoulder_span <= corner:
        raise ValueError("foot shoulder has insufficient radial span to meet the body")
    shoulder = MeridianSegment(
        role="foot",
        kind="bezier",
        points=(
            body_outer_start,
            (body_outer_start[0] + 0.32 * shoulder_span, body_outer_start[1]),
            (foot_top_inner[0] - 0.32 * shoulder_span, foot_top_inner[1]),
            foot_top_inner,
        ),
    )

    def quarter_arc(role: RegionRole, start: tuple[float, float], mid: tuple[float, float], end: tuple[float, float]) -> MeridianSegment:
        return MeridianSegment(role=role, kind="arc", points=(start, mid, end))

    inv_sqrt2 = 1.0 / math.sqrt(2.0)
    top_corner_center = (foot_radius - corner, float(design.foot_height_mm) - corner)
    top_corner = quarter_arc(
        "foot",
        foot_top_inner,
        (top_corner_center[0] + corner * inv_sqrt2, top_corner_center[1] + corner * inv_sqrt2),
        (foot_radius, float(design.foot_height_mm) - corner),
    )
    foot_outer_wall = MeridianSegment(
        role="foot",
        kind="line",
        points=((foot_radius, float(design.foot_height_mm) - corner), (foot_radius, corner)),
    )
    bottom_outer_center = (foot_radius - corner, corner)
    bottom_outer_corner = quarter_arc(
        "foot",
        (foot_radius, corner),
        (bottom_outer_center[0] + corner * inv_sqrt2, bottom_outer_center[1] - corner * inv_sqrt2),
        (foot_radius - corner, 0.0),
    )
    support_face = MeridianSegment(
        role="foot",
        kind="line",
        points=((contact_outer, 0.0), (contact_inner + corner, 0.0)),
    )
    inner_foot_center = (contact_inner + corner, corner)
    inner_foot_corner = quarter_arc(
        "foot",
        (contact_inner + corner, 0.0),
        (inner_foot_center[0] - corner * inv_sqrt2, inner_foot_center[1] - corner * inv_sqrt2),
        (contact_inner, corner),
    )

    segments: list[MeridianSegment] = [
        MeridianSegment("base", "line", ((0.0, floor_z), (floor_radius, floor_z))),
        inner_body,
        MeridianSegment("rim", "arc", (tuple(inner_lip), tuple(cap_through), tuple(outer_lip))),
        *[segment.reversed() for segment in reversed(outer_body_forward)],
        shoulder,
        top_corner,
        foot_outer_wall,
        bottom_outer_corner,
        support_face,
        inner_foot_corner,
        MeridianSegment("foot", "line", ((contact_inner, corner), (contact_inner, float(design.underside_recess_z_mm)))),
        MeridianSegment("base", "line", ((contact_inner, float(design.underside_recess_z_mm)), (0.0, float(design.underside_recess_z_mm)))),
        MeridianSegment("base", "line", ((0.0, float(design.underside_recess_z_mm)), (0.0, floor_z))),
    ]
    section = MeridianSection(segments=tuple(segments), name=design.name)
    section.validate()
    profile_info: dict[str, object] = {
        "outer_normal_offset_mm": wall,
        "normal_offset_fit_max_sampled_deviation_mm": offset_fit_error,
        "normal_offset_fit_acceptance_sample_mm": float(design.normal_offset_fit_tolerance_mm),
        "normal_offset_error_scope": "maximum of t=0.25, 0.5 and 0.75 checks per accepted cubic subcurve; no continuous or global error bound is claimed",
        "wall_thickness_status": "DESIGN_ASSUMPTION; exact normal-offset formula supplies cubic control points, with finite sampled fit diagnostics and no continuous/global error certificate",
        "body_profile": {
            "curve": "cubic Bezier",
            "start_handle_fraction_of_floor_to_inner_lip_radial_span": float(design.body_start_handle_fraction),
            "start_handle_length_mm": start_handle,
            "end_handle_height_fraction_of_overall_height": float(design.body_end_handle_height_fraction),
            "end_handle_length_mm": end_handle,
            "inner_control_points_rz_mm": [list(point) for point in inner_body.points],
            "status": "DESIGN_ASSUMPTION; adjustable visual profile control, not measured from source",
        },
        "lip": {
            "construction": "semicircular cap tangent to the inner and outer body at the declared tangent angle",
            "radius_mm": lip_radius,
            "center_rz_mm": center.tolist(),
            "center_formula": "(D_outer/2 - t/2, H - t/2)",
            "tangent_angle_degrees": float(design.rim_tangent_degrees),
            "body_inner_endpoint_rz_mm": inner_lip.tolist(),
            "body_outer_endpoint_rz_mm": outer_lip.tolist(),
            "actual_cap_extrema_rz_mm": {"max_radius": radius, "max_z": height},
        },
        "foot": {
            "outer_diameter_mm": float(design.foot_outer_diameter_mm),
            "height_mm": float(design.foot_height_mm),
            "contact_annulus_radii_mm": [float(contact_inner + corner), float(contact_outer)],
            "contact_width_mm": float(contact_outer - (contact_inner + corner)),
            "corner_radius_mm": float(corner),
            "underside_recess_z_mm": float(design.underside_recess_z_mm),
            "status": "DESIGN_ASSUMPTION unless expressly measured in source record",
        },
        "base": {
            "inside_floor_z_mm": floor_z,
            "recessed_underside_z_mm": float(design.underside_recess_z_mm),
            "central_base_thickness_mm": floor_z - float(design.underside_recess_z_mm),
            "status": "DESIGN_ASSUMPTION",
        },
    }
    return section, profile_info


def shape_bounds(shape: cq.Shape) -> dict[str, object]:
    """Return a compact absolute B-rep bounding-box record."""
    bounds = shape.BoundingBox()
    return {
        "x_min_mm": float(bounds.xmin),
        "x_max_mm": float(bounds.xmax),
        "y_min_mm": float(bounds.ymin),
        "y_max_mm": float(bounds.ymax),
        "z_min_mm": float(bounds.zmin),
        "z_max_mm": float(bounds.zmax),
        "diameter_x_mm": float(bounds.xmax - bounds.xmin),
        "diameter_y_mm": float(bounds.ymax - bounds.ymin),
        "height_mm": float(bounds.zmax - bounds.zmin),
    }

