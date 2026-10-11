"""Where the eye goes in a frame without a face: the per-frame interest maps the ``subject`` reframe follows.

    from vstudio import saliency as S
    an = S.Analyzer(person=None)                   # person=None: MediaPipe selfie segmenter when installed
    m = an(bgr_small)                              # {"map": HxW float32 0..1, "motion": float, "gm": (dx, dy)}

Three cues, all deterministic (no randomness, no GPU):
  spectral residual   Hou & Zhang 2007 on a 128-px grey thumbnail: what stands out of the frame's own texture
                      (a person on a road, a red tree in a green slope, a boat on water)
  colour contrast     distance from the frame's mean Lab colour (Achanta 2009): the odd colour out
  vividness           saturation x brightness: autumn leaves, a lit field, a red jacket draw the eye more than
                      a grey roof of the same contrast
  residual motion     dense Farneback flow between this sample and the previous one, minus the global (camera /
                      drone) motion: what moves on its own (walkers, cars, a ferry) while the drone pans
  person mask         MediaPipe selfie segmenter (optional; Apache-2.0 model in the engine's model folder):
                      people near enough to read as a subject

The map is the weighted sum (``W``), each cue normalised to its own 99th percentile so a quiet frame does not
amplify noise. ``Analyzer`` keeps the previous grey frame for the motion cue: feed it the samples in time order and
call ``reset()`` at a shot cut.
"""
import numpy as np

GRID_W = 160                     # analysis grid width (maps are this wide)
W = dict(spectral=1.0, color=0.4, vivid=0.6, motion=1.4, person=1.6)


def _norm(m, floor=0.0):
    m = np.maximum(m.astype(np.float32) - floor, 0)
    hi = float(np.percentile(m, 99)) if m.size else 0.0
    return np.clip(m / hi, 0, 1) if hi > 1e-6 else np.zeros_like(m, np.float32)


def spectral_residual(grey):
    """Spectral-residual saliency of a small grey image (float32 0..1 map, same size)."""
    import cv2
    h, w = grey.shape
    tw = 128
    th = max(8, int(round(h * tw / w)))
    g = cv2.resize(grey, (tw, th), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    F = np.fft.fft2(g)
    amp = np.log(np.abs(F) + 1e-6)
    ph = np.angle(F)
    res = amp - cv2.blur(amp, (3, 3))
    sal = np.abs(np.fft.ifft2(np.exp(res + 1j * ph))) ** 2
    sal = cv2.GaussianBlur(sal.astype(np.float32), (0, 0), 2.5)
    return cv2.resize(_norm(sal), (w, h), interpolation=cv2.INTER_LINEAR)


def color_contrast(bgr):
    import cv2
    lab = cv2.cvtColor(cv2.GaussianBlur(bgr, (0, 0), 1.5), cv2.COLOR_BGR2LAB).astype(np.float32)
    d = np.linalg.norm(lab - lab.reshape(-1, 3).mean(0), axis=2)
    return _norm(d, floor=float(np.median(d)))


def vividness(bgr):
    import cv2
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    v = hsv[..., 1] * hsv[..., 2] / 255.0
    return _norm(cv2.GaussianBlur(v, (0, 0), 2.0), floor=float(np.median(v)))


def _taper(h, w, edge=0.05):
    """1 inside, falling to 0.5 at the outer ``edge`` of the frame (the FFT's wrap-around and lens vignetting make
    borders look salient)."""
    def ramp(n):
        e = max(1, int(round(n * edge)))
        r = np.ones(n, np.float32)
        r[:e] = np.linspace(0.5, 1.0, e)
        r[-e:] = np.linspace(1.0, 0.5, e)
        return r
    return np.outer(ramp(h), ramp(w))


def _person_segmenter():
    """MediaPipe selfie segmenter (IMAGE mode) or None (no mediapipe / no model: the cue is skipped)."""
    try:
        from mediapipe.tasks.python import BaseOptions, vision
        from .config import model
        return vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=model("selfie_segmenter")),
            output_confidence_masks=True, output_category_mask=False))
    except Exception:  # noqa: BLE001
        return None


class Analyzer:
    """Per-sample interest map on the analysis grid. ``person``: None = the MediaPipe segmenter when available,
    False = off, or any ``fn(bgr) -> HxW 0..1`` (tests)."""

    def __init__(self, person=None, grid_w=GRID_W, weights=None):
        self.grid_w = grid_w
        self.w = dict(W, **(weights or {}))
        self.prev = None
        self._seg = None
        if person is None:
            self._seg = _person_segmenter()
            self.person = self._mp_person if self._seg is not None else None
        else:
            self.person = person or None

    def reset(self):
        self.prev = None

    def close(self):
        if self._seg is not None:
            try:
                self._seg.close()
            except Exception:  # noqa: BLE001
                pass
            self._seg = None

    def _mp_person(self, bgr):
        import cv2
        import mediapipe as mp
        h, w = bgr.shape[:2]
        rgb = np.ascontiguousarray(cv2.cvtColor(cv2.resize(bgr, (256, 256), interpolation=cv2.INTER_AREA),
                                                cv2.COLOR_BGR2RGB))
        res = self._seg.segment(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
        m = np.asarray(res.confidence_masks[-1].numpy_view(), np.float32).reshape(256, 256)
        m = np.where(m > 0.6, m, 0.0).astype(np.float32)
        cover = float((m > 0).mean())
        if cover < 0.002 or cover > 0.5:              # nothing, or the whole frame (a wall of foliage read as skin)
            return None
        return cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)

    def __call__(self, bgr):
        import cv2
        h, w = bgr.shape[:2]
        gw, gh = self.grid_w, max(8, int(round(h * self.grid_w / w)))
        small = cv2.resize(bgr, (gw, gh), interpolation=cv2.INTER_AREA)
        grey = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        acc = (self.w["spectral"] * spectral_residual(grey) + self.w["color"] * color_contrast(small)
               + self.w["vivid"] * vividness(small))
        total = self.w["spectral"] + self.w["color"] + self.w["vivid"]
        motion, gm = 0.0, (0.0, 0.0)
        if self.prev is not None and self.prev.shape == grey.shape:
            flow = cv2.calcOpticalFlowFarneback(self.prev, grey, None, 0.5, 3, 13, 3, 5, 1.1, 0)
            med = np.median(flow.reshape(-1, 2), axis=0)
            gm = (float(med[0]) / gw, float(med[1]) / gh)          # global motion, frame widths / heights
            res = np.linalg.norm(flow - med, axis=2)
            floor = float(np.percentile(res, 80))
            peak = float(np.percentile(res, 99.5))
            motion = peak - floor
            if motion > 0.6:                          # something moves on its own (> ~0.6 grid px between samples)
                acc += self.w["motion"] * _norm(cv2.GaussianBlur(res, (0, 0), 1.5), floor)
                total += self.w["motion"]
        self.prev = grey
        if self.person is not None:
            pm = self.person(small)
            if pm is not None:
                acc += self.w["person"] * cv2.resize(np.asarray(pm, np.float32), (gw, gh))
                total += self.w["person"]
        return dict(map=(acc / total * _taper(gh, gw)).astype(np.float32), motion=round(motion, 3), gm=gm)
