"""Source-shot face masking: OpenCV YuNet + Lucas–Kanade motion.

No identity embeddings or cloud upload. A target means its position in the seed frame, not a person's name.
Apply to individual source shots before dissolves. Uncertain tracking stops rendering; it never
passes an unmasked frame or replaces the whole picture with black as a successful result.
"""
import json
import math
import os
import subprocess
import tempfile

import cv2
import numpy as np


def detector(path=None):
    if path is None:
        from .config import optional_asset
        path = optional_asset('VSTUDIO_YUNET_MODEL', 'face-tracking', 'yunet.onnx', names=('yunet.onnx',))
        if not path:
            raise RuntimeError('Face tracking model is missing; run python -m vstudio.assets fetch face-tracking')
    from .assets import GROUPS
    if _sha(path) != GROUPS["face-tracking"]["files"][0]["sha256"]:
        raise ValueError('Face tracking model checksum does not match the pinned YuNet model')
    return cv2.FaceDetectorYN.create(str(path), '', (320, 320), .75, .3, 5000,
                                    cv2.dnn.DNN_BACKEND_OPENCV, cv2.dnn.DNN_TARGET_CPU)


def detect(net, img):
    h, w = img.shape[:2]
    net.setInputSize((w, h))
    _, faces = net.detect(img)
    return [] if faces is None else [np.array(f[:4], float) for f in faces if float(f[-1]) >= .75]


def choose(boxes, target='center', point=None):
    if not boxes:
        raise ValueError('No face found in the selected interval')
    if point is not None:
        hits = [b for b in boxes if np.all(point >= b[:2]) and np.all(point <= b[:2] + b[2:])]
        if len(hits) != 1:
            raise ValueError('Select a point inside one clear face')
        return hits[0].copy()
    ordered = sorted(boxes, key=lambda b: b[0] + b[2] / 2)
    if target == 'center' and len(ordered) > 1 and len(ordered) % 2 == 0:
        raise ValueError('The middle face is ambiguous; select a face or a clearer interval')
    return ordered[0 if target == 'left' else -1 if target == 'right' else len(ordered) // 2].copy()


def _gray(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def motion(prev, cur, box):
    """Forward/backward-checked optical flow inside the selected face, with a conservative scale bound."""
    x, y, w, h = map(float, box)
    mask = np.zeros(prev.shape, np.uint8)
    mask[max(0,int(y)):max(0,int(y+h)), max(0,int(x)):max(0,int(x+w))] = 255
    pts = cv2.goodFeaturesToTrack(prev, 35, .01, 2, mask=mask)
    if pts is None or len(pts) < 5:
        return None
    nxt, ok, _ = cv2.calcOpticalFlowPyrLK(prev, cur, pts, None, winSize=(21,21), maxLevel=3)
    if nxt is None:
        return None
    back, valid, _ = cv2.calcOpticalFlowPyrLK(cur, prev, nxt, None, winSize=(21,21), maxLevel=3)
    if back is None:
        return None
    keep = (ok.ravel() == 1) & (valid.ravel() == 1) & (np.linalg.norm(pts-back, axis=2).ravel() < 1.0)
    if keep.sum() < 5:
        return None
    a, inliers = cv2.estimateAffinePartial2D(pts[keep], nxt[keep], method=cv2.RANSAC, ransacReprojThreshold=2)
    if a is None or inliers.sum() < 5:
        return None
    scale = float(np.hypot(a[0,0], a[0,1]))
    if not .85 < scale < 1.18:
        return None
    center = a[:,:2] @ (box[:2]+box[2:]/2) + a[:,2]
    size = box[2:] * scale
    return np.r_[center-size/2, size]


def associate(boxes, predicted):
    """Match only a nearby, similarly-sized detection; close competing matches are ambiguous."""
    ranked = []
    for b in boxes:
        size = np.maximum(predicted[2:], 1)
        distance = np.linalg.norm((b[:2]+b[2:]/2 - predicted[:2]-predicted[2:]/2) / size)
        ratio = np.max(np.abs(np.log(np.maximum(b[2:],1)/size)))
        if distance < .85 and ratio < .55:
            ranked.append((distance + ratio, b))
    ranked.sort(key=lambda x: x[0])
    if not ranked or len(ranked) > 1 and ranked[1][0] - ranked[0][0] < .25:
        return None
    return ranked[0][1].copy()


def _ranges(indices, fps, start):
    out = []
    for i in indices:
        a, b = start+i/fps, start+(i+1)/fps
        if out and abs(out[-1][1]-a) < .5/fps:
            out[-1][1] = b
        else:
            out.append([a,b])
    return [[round(a,3),round(b,3)] for a,b in out]


def analyze(src, start, end, target='center', point=None, model_path=None, progress=None):
    """Track one continuous CFR source shot. A missing box requires review, not a successful mask."""
    if target not in ("center", "left", "right"):
        raise ValueError("Choose the left, middle or right face")
    start, end = float(start), float(end)
    if not all(math.isfinite(t) for t in (start, end)) or start < 0:
        raise ValueError("Face tracking times must be finite and nonnegative")
    if point is not None and (len(point) != 2 or not all(math.isfinite(float(v)) and 0 <= v <= 1 for v in point)):
        raise ValueError("Face selection must be a normalized point inside the picture")
    cap = cv2.VideoCapture(str(src))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not cap.isOpened() or not fps or not math.isfinite(fps):
            raise ValueError('Could not read the video for face tracking')
        first, last = int(math.floor(start*fps)), int(math.ceil(end*fps))
        if last <= first or last-first > fps*120:
            raise ValueError('Select a face-masking interval of at most two minutes')
        cap.set(cv2.CAP_PROP_POS_FRAMES, first)
        net = detector(model_path)
        warm = []
        for i in range(min(last-first, max(1,int(fps*2)))):
            ok, im = cap.read()
            if not ok:
                break
            warm.append((im, detect(net, im)))
        if not warm:
            raise ValueError('The selected face interval is outside the video')
        # Start on a clear frame rather than a shot boundary with a partly visible group.
        max_faces = max(len(b) for _, b in warm)
        if point is None and target == 'center' and max_faces > 1 and max_faces % 2 == 0:
            raise ValueError('The middle face is ambiguous; choose a clear face in this shot')
        candidates = [(i,b) for i,(_,b) in enumerate(warm) if b and len(b) == max_faces]
        if not candidates:
            raise ValueError('No unambiguous target face found; select its position on a clearer frame')
        seed, boxes = max(candidates, key=lambda ib: (len(ib[1]),ib[0]))
        H,W = warm[seed][0].shape[:2]
        xy = None if point is None else np.asarray(point, dtype=float)*[W,H]
        box = choose(boxes,target,xy)
        track = [None]*(last-first)
        track[seed] = box.copy()
        def step(prev, cur, dets, box, misses):
            gray = _gray(cur)
            if float(np.mean(np.abs(prev.astype(np.float32) - gray.astype(np.float32)))) > 25:
                return gray, box, misses + 1, None
            predicted = motion(prev, gray, box)
            found = associate(dets, box if predicted is None else predicted)
            if found is not None:
                return gray, found, 0, found
            misses += 1
            return gray, box if predicted is None else predicted, misses, None
        # Track backward only through the warm-up window (bounded memory), then forward as a stream.
        prev, current, misses = _gray(warm[seed][0]), box.copy(), 0
        for i in range(seed-1,-1,-1):
            prev,current,misses,b = step(prev,warm[i][0],warm[i][1],current,misses)
            track[i] = b
        prev,current,misses = _gray(warm[seed][0]),box.copy(),0
        for i in range(seed+1,last-first):
            if i < len(warm):
                im,dets = warm[i]
            else:
                ok,im = cap.read()
                if not ok:
                    raise ValueError('Video ended before the face-masking interval finished')
                dets = detect(net,im)
            prev,current,misses,b = step(prev,im,dets,current,misses)
            track[i] = b
            if progress and i % 15 == 0:
                progress(i/len(track))
        norm = [None if b is None else (b/[W,H,W,H]).round(7).tolist() for b in track]
        lost = _ranges([i for i,b in enumerate(norm) if b is None],fps,first/fps)
        return dict(version=1,start=first/fps,fps=fps,boxes=norm,uncertain=lost,seed=(first+seed)/fps,
                    target=target,frames=len(norm),tracked_frames=len(norm)-sum(b is None for b in norm),
                    width=W,height=H,source_sha256=_sha(src))
    finally:
        cap.release()


def cover(img, box, mode='mosaic', margin=1.65):
    """In-place coverage for a validated box. Never treat an absent or invalid box as a mask."""
    if mode not in ("mosaic", "blur", "cat", "dog") or not math.isfinite(margin) or margin < 1.5:
        raise ValueError("Choose mosaic, blur, cat or dog and a face margin of at least 1.5")
    h,w = img.shape[:2]
    if box is None:
        raise ValueError("Face tracking is uncertain on this frame")
    x,y,bw,bh = np.array(box)*[w,h,w,h]
    cx,cy=x+bw/2,y+bh/2
    x0,x1 = max(0,int(cx-bw*margin/2)), min(w,int(math.ceil(cx+bw*margin/2)))
    y0,y1 = max(0,int(cy-bh*margin/2)), min(h,int(math.ceil(cy+bh*margin/2)))
    roi=img[y0:y1,x0:x1]
    if not roi.size:
        raise ValueError("Face tracking box is outside this picture")
    if mode == 'mosaic':
        tiny=cv2.resize(roi,(max(1,min(4,roi.shape[1]//4)), max(1,min(4,roi.shape[0]//4))),interpolation=cv2.INTER_AREA)
        roi[:]=cv2.resize(tiny,(x1-x0,y1-y0),interpolation=cv2.INTER_NEAREST)
    elif mode == 'blur':
        # First reduce detail irreversibly, then soften the enlarged blocks.
        tiny=cv2.resize(roi,(max(1,min(3,roi.shape[1]//4)), max(1,min(3,roi.shape[0]//4))),interpolation=cv2.INTER_AREA)
        roi[:]=cv2.GaussianBlur(cv2.resize(tiny,(x1-x0,y1-y0)),(0,0),max(2,min(bw,bh)*.2))
    elif mode in ('cat','dog'):
        roi[:]=(100,195,245) if mode=='cat' else (100,165,210)
        rw,rh=x1-x0,y1-y0
        for ex in (.3,.7):
            cv2.circle(roi,(int(rw*ex),int(rh*.4)),max(1,int(rw*.07)),(25,30,35),-1)
        cv2.circle(roi,(rw//2,int(rh*.65)),max(1,int(rw*.09)),(40,60,80),-1)
        if mode=='cat':
            for ey in (.57,.68):
                cv2.line(roi,(0,int(rh*ey)),(int(rw*.3),int(rh*.6)),(40,60,80),1)
                cv2.line(roi,(int(rw*.7),int(rh*.6)),(rw-1,int(rh*ey)),(40,60,80),1)


def _sha(path):
    from .assets import _sha as sha
    return sha(path)


def _check_track(src, track):
    from . import media
    info = media.probe(src)
    if track.get("source_sha256") != _sha(src):
        raise ValueError("This face track belongs to a different video; analyze the current shot again")
    if track.get("start") != 0 or (track.get("width"), track.get("height")) != (info["w"], info["h"]):
        raise ValueError("Face masking expects the whole continuous source shot at its analyzed size")
    if info.get("rotation"):
        raise ValueError("Normalize shot rotation before face masking")
    boxes = track.get("boxes") or []
    fps = float(track.get("fps") or 0)
    if not math.isfinite(fps) or fps <= 0 or abs(fps - float(info["fps"])) > .001:
        raise ValueError("Face track frame rate does not match the video")
    if track.get("uncertain") or not boxes or any(b is None for b in boxes):
        at = ", ".join(f"{a:g}–{b:g}s" for a,b in track.get("uncertain") or [])
        raise ValueError("Face tracking needs checking" + (f" at {at}" if at else "") +
                         "; use a continuous shot with a clear selected face. No masked movie was written")
    if len(boxes) != track.get("frames") or abs(len(boxes)/fps - float(info["duration"])) > 1/fps + .001:
        raise ValueError("Face track does not span the whole shot")
    for b in boxes:
        if len(b) != 4 or not all(math.isfinite(float(v)) for v in b) or min(b[2:]) <= 0:
            raise ValueError("Invalid face track box")
        x,y,w,h = b
        if x >= 1 or y >= 1 or x+w <= 0 or y+h <= 0 or w > 2 or h > 2:
            raise ValueError("Face track box is outside the video")
    return info


def render(src, dst, track, mode="mosaic", margin=1.65, crf=18):
    """Mask an analyzed CFR shot atomically, retaining its audio. Reject incomplete/stale tracks.
    This is a source-shot pass: assemble transitions AFTER this, so both sides carry their masks.
    """
    from . import media
    info = _check_track(src, track)
    # Validate drawing options before creating anything.
    cover(np.zeros((8,8,3), np.uint8), [.3,.3,.3,.3], mode, margin)
    W,H,fps = info["w"],info["h"],track["fps"]
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="face-mask-", dir=os.path.dirname(os.path.abspath(dst))) as tmp:
        picture = os.path.join(tmp, "picture.mp4")
        cmd = [media.ffmpeg_bin(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
               "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-an", "-vf",
               "scale=in_range=pc:out_range=tv:out_color_matrix=bt709", "-c:v", "libx264", "-preset", "fast",
               "-crf", str(crf), "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709",
               "-color_trc", "bt709", "-color_range", "tv", picture]
        # FFmpeg honours matrix/range metadata when decoding RGB; OpenCV may ignore it.
        decoder = subprocess.Popen([media.ffmpeg_bin(), "-v", "error", "-i", str(src), "-map", "0:v:0",
                                    "-an", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        n = 0
        try:
            while True:
                buf = decoder.stdout.read(W*H*3)
                if not buf:
                    break
                if len(buf) != W*H*3:
                    raise ValueError("Incomplete decoded face-mask frame")
                img = np.frombuffer(buf, np.uint8).reshape(H,W,3).copy()
                if n >= len(track["boxes"]):
                    raise ValueError("Video has more frames than its face track")
                cover(img,track["boxes"][n],mode,margin)
                proc.stdin.write(img.tobytes())
                n += 1
        finally:
            decoder.stdout.close()
            decode_rc = decoder.wait()
            try:
                proc.stdin.close()
            except BrokenPipeError:
                pass
            error = proc.stderr.read().decode(errors="replace")
            rc = proc.wait()
        if decode_rc or rc or n != len(track["boxes"]):
            raise RuntimeError(f"Face mask render failed ({n} frames): {error[-300:]}")
        result = os.path.join(tmp, "masked.mp4")
        media.run(["ffmpeg", "-v", "error", "-y", "-i", picture, "-i", str(src), "-map", "0:v:0",
                   "-map", "1:a?", "-c", "copy", "-movflags", "+faststart", result])
        if _sha(src) != track["source_sha256"]:
            raise ValueError("Source changed while applying its face track; analyze it again")
        os.replace(result, dst)
    return dst


def mask_shot(src, dst, options, report=None):
    """Native Vlog hook: one chosen face within a shot, before its transition is assembled."""
    from . import media
    if not isinstance(options, dict):
        raise ValueError("face_mask must specify a target and a style")
    unknown = set(options) - {"target", "point", "style", "margin"}
    if unknown:
        raise ValueError("Unknown face mask options: " + ", ".join(sorted(unknown)))
    track = analyze(src,0,media.duration(src),target=options.get("target", "center"),point=options.get("point"))
    if report:
        with open(report,"w",encoding="utf-8") as f:
            json.dump(track,f,ensure_ascii=False)
    render(src,dst,track,mode=options.get("style", "mosaic"),margin=float(options.get("margin",1.65)))
    track["masked_sha256"] = _sha(dst)
    if report:
        with open(report,"w",encoding="utf-8") as f:
            json.dump(track,f,ensure_ascii=False)
    return track
