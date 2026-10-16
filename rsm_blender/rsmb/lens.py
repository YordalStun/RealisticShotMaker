"""Ray-traced lens model for Cycles, as an OSL custom camera.

The shader is generated per shot with the lens character baked in as
constants. Focus distance and aperture size come from the regular Blender
camera so they can be animated (rack focus, focus pulls) like any camera.

What it models, per camera ray:
  * polygonal aperture with curved blades and rotation
  * mechanical vignetting (cat's-eye bokeh towards the frame edges)
  * tangential astigmatism (swirl), field curvature
  * spherical aberration (focus depends on where the ray passes the aperture)
  * longitudinal and lateral chromatic aberration via spectral (R/G/B) sampling
  * radial distortion, focus breathing, cos^4 fall-off
  * soap-bubble and onion-ring bokeh texture
  * anamorphic (oval) aperture
"""
from __future__ import annotations

import os
from string import Template

OSL_TEMPLATE = Template(r"""
// RealisticShotMaker lens model -- generated, do not edit by hand.
#include "stdcycles.h"

#define FOCAL_MM      $focal
#define BLADES        $blades
#define BLADE_CURV    $blade_curvature
#define BLADE_ROT     $blade_rotation
#define CAT_EYE       $cat_eye
#define SWIRL         $swirl
#define SPHERICAL     $spherical
#define CA_LONG       $ca_long
#define CA_LAT        $ca_lat
#define K1            $k1
#define K2            $k2
#define FIELD_CURV    $field_curvature
#define BREATHING     $breathing
#define BOKEH_RIM     $bokeh_rim
#define ONION         $onion
#define VIGNETTE      $vignette
#define SQUEEZE       $squeeze
#define SPECTRAL      $spectral
#define ZOOMABLE      $zoomable

shader rsm_lens(output point position = 0.0,
                output vector direction = 0.0,
                output color throughput = 1.0)
{
  vector ss = vector(36.0, 24.0, 0.0);
  getattribute("cam:sensor_size", ss);
  float fd = 1.0;
  getattribute("cam:focal_distance", fd);
  float ap = 0.0;
  getattribute("cam:aperture_size", ap);
  fd = max(fd, 0.01);

  vector rnd = camera_shader_random_sample();
  point R = camera_shader_raster_position() - point(0.5, 0.5, 0.0);

  // position on the sensor in millimetres (this is the distorted image point)
  float sx = R[0] * ss[0];
  float sy = R[1] * ss[1];
  float half_diag = 0.5 * hypot(ss[0], ss[1]);
  float rn = hypot(sx, sy) / half_diag;

  // ---- spectral channel ---------------------------------------------------
  float lam = 0.0;
  throughput = color(1.0);
  if (SPECTRAL) {
    float hz = hashnoise(point(rnd[0] * 113.0, rnd[1] * 97.0, sx * 0.0137 + sy * 0.0191));
    if (hz < 1.0 / 3.0)      { lam =  1.0; throughput = color(3.0, 0.0, 0.0); }
    else if (hz < 2.0 / 3.0) { lam =  0.0; throughput = color(0.0, 3.0, 0.0); }
    else                     { lam = -1.0; throughput = color(0.0, 0.0, 3.0); }
  }

  // ---- distortion (invert k1/k2 model by fixed point iteration) -----------
  float ux = sx / half_diag;
  float uy = sy / half_diag;
  float dx0 = ux, dy0 = uy;
  for (int i = 0; i < 6; i++) {
    float rr = ux * ux + uy * uy;
    float s = 1.0 + K1 * rr + K2 * rr * rr;
    ux = dx0 / s;
    uy = dy0 / s;
  }
  // lateral colour: each colour is magnified slightly differently
  float mag = 1.0 + CA_LAT * lam * 0.0015;
  ux *= mag;
  uy *= mag;

  // ---- focus breathing: unit-focusing lenses get longer when focused close
  float f_m = FOCAL_MM * 0.001;
  float m = f_m / max(fd - f_m, 0.001);
  float f_eff = FOCAL_MM * (1.0 + BREATHING * 2.5 * m);
  if (ZOOMABLE) {
    // zoom moves (crash zoom, dolly zoom) animate the camera's aperture ratio as a zoom factor;
    // this lens draws its own aperture, so that property is otherwise unused
    float zf = 1.0;
    getattribute("cam:aperture_aspect_ratio", zf);
    f_eff *= max(zf, 0.05);
  }

  vector d = normalize(vector(ux * half_diag / f_eff, uy * half_diag / f_eff, 1.0));

  // ---- aperture sample ----------------------------------------------------
  // concentric map of the two random numbers onto the unit disk
  float a = 2.0 * rnd[0] - 1.0;
  float b = 2.0 * rnd[1] - 1.0;
  float px = 0.0, py = 0.0;
  if (a != 0.0 || b != 0.0) {
    float r, phi;
    if (fabs(a) > fabs(b)) { r = a; phi = (M_PI / 4.0) * (b / a); }
    else                   { r = b; phi = (M_PI / 2.0) - (M_PI / 4.0) * (a / b); }
    px = r * cos(phi);
    py = r * sin(phi);
  }
  float rho = hypot(px, py);

  // polygonal blades (rejection against a curved polygon)
  float area_norm = 1.0;
  if (BLADES >= 3 && BLADE_CURV < 0.999) {
    float seg = 2.0 * M_PI / BLADES;
    float ang = atan2(py, px) - radians(BLADE_ROT);
    float rel = ang - seg * floor(ang / seg) - seg * 0.5;
    float r_edge = cos(M_PI / BLADES) / cos(rel);
    float r_lim = mix(r_edge, 1.0, BLADE_CURV);
    if (rho > r_lim) { throughput = color(0.0); direction = d; return; }
    float poly_area = 0.5 * BLADES * sin(seg) / M_PI;
    area_norm = 1.0 / mix(poly_area, 1.0, BLADE_CURV);
  }

  // mechanical vignetting: a second stop (the lens barrel) shifted with field position
  if (CAT_EYE > 0.0 && rn > 0.0) {
    float cx = -CAT_EYE * 0.85 * (sx / half_diag);
    float cy = -CAT_EYE * 0.85 * (sy / half_diag);
    if (hypot(px - cx, py - cy) > 1.0) { throughput = color(0.0); direction = d; return; }
  }

  // swirl: stretch the aperture footprint tangentially, more towards the corners
  if (SWIRL > 0.0 && rn > 0.001) {
    float erx = sx / (rn * half_diag);
    float ery = sy / (rn * half_diag);
    float pr = px * erx + py * ery;
    float pt = -px * ery + py * erx;
    float k = SWIRL * rn * rn;
    pt *= 1.0 + 1.1 * k;
    pr *= 1.0 - 0.3 * k;
    px = pr * erx - pt * ery;
    py = pr * ery + pt * erx;
  }

  // anamorphic oval aperture
  float sq = sqrt(SQUEEZE);
  float lx = px / sq;
  float ly = py * sq;

  // ---- focus surface --------------------------------------------------------
  float fd_eff = fd;
  // Calibrated against the depth of field at 4K: at the focus plane these stay within about a
  // pixel, out of focus they shape the bokeh (fringes, glow, field-dependent softness).
  fd_eff *= 1.0 + FIELD_CURV * 0.012 * rn * rn;           // field curvature: corners focus slightly behind
  fd_eff *= 1.0 + CA_LONG * lam * 0.0012;                  // longitudinal colour
  fd_eff *= 1.0 - SPHERICAL * 0.0025 * (rho * rho - 0.5); // spherical aberration

  point Pf = d * (fd_eff / d[2]);
  point L = point(lx * ap, ly * ap, 0.0);

  position = L;
  direction = normalize(Pf - L);

  // ---- throughput weighting -------------------------------------------------
  float w = area_norm;
  w *= 1.0 + BOKEH_RIM * 1.5 * (rho * rho - 0.5);
  if (ONION > 0.0)
    w *= 1.0 + ONION * 0.45 * sin(rho * 46.0 + 1.3);
  w *= mix(1.0, pow(d[2], 4.0), VIGNETTE);
  throughput *= max(w, 0.0);
}
""")


def build_osl(lens: dict, focal_mm: float, character: float = 1.0, ca_scale: float = 1.0, zoomable: bool = False) -> str:
    """Return OSL source for a lens. `lens` is a catalog.Lens as dict; `character` scales all quirks."""
    c = max(0.0, character)

    def q(key, default=0.0, scale=1.0):
        return float(lens.get(key, default)) * scale

    ca_long = q("ca_long") * c * ca_scale
    ca_lat = q("ca_lat") * c * ca_scale
    params = dict(
        focal=f"{float(focal_mm):.4f}",
        blades=int(lens.get("blades", 9)),
        blade_curvature=f"{min(1.0, 1.0 - (1.0 - q('blade_curvature', 1.0)) * min(c, 1.0)):.4f}",
        blade_rotation=f"{q('blade_rotation'):.3f}",
        cat_eye=f"{min(0.98, q('cat_eye') * c):.4f}",
        swirl=f"{q('swirl') * c:.4f}",
        spherical=f"{q('spherical') * c:.4f}",
        ca_long=f"{ca_long:.4f}",
        ca_lat=f"{ca_lat:.4f}",
        k1=f"{q('distortion') * c:.5f}",
        k2=f"{q('distortion') * c * 0.25:.5f}",
        field_curvature=f"{q('field_curvature') * c:.4f}",
        breathing=f"{q('breathing') * c:.4f}",
        bokeh_rim=f"{q('bokeh_rim') * c:.4f}",
        onion=f"{q('onion') * c:.4f}",
        vignette=f"{min(1.0, q('vignette') * c):.4f}",
        squeeze=f"{max(1.0, q('squeeze', 1.0)):.4f}",
        spectral=1 if (ca_long > 0.001 or ca_lat > 0.001) else 0,
        zoomable=1 if zoomable else 0,
    )
    return OSL_TEMPLATE.substitute(params)


def apply_lens(camera_data, osl_source: str, work_dir: str):
    """Point a Blender camera at the generated lens shader."""
    path = os.path.join(work_dir, "rsm_lens.osl")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(osl_source)
    camera_data.type = "CUSTOM"
    camera_data.custom_mode = "EXTERNAL"
    camera_data.custom_filepath = path
    return path
