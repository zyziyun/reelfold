"""Optional model downloads for the CLI skill (the desktop app downloads the same pinned files itself, from
``apps/desk/packaging/assets.json``): sha256-checked, into ``<cache>/models/<dir>/``.

    python -m vstudio.assets list
    python -m vstudio.assets fetch cover            # matte-birefnet + upscale-esrgan + cover-aesthetic
    python -m vstudio.assets fetch matte-birefnet

Licences: BiRefNet MIT (ZhengPeng7; ONNX by onnx-community, MIT) - Real-ESRGAN BSD-3-Clause (xinntao) - LAION
aesthetic predictor v2 Apache-2.0 (christophschuhmann) on OpenAI CLIP ViT-L/14, MIT (ONNX q4f16 by Xenova).
"""
import argparse
import hashlib
import os
import sys
import urllib.request

HF = "https://huggingface.co"
GROUPS = {
    "matte-birefnet": dict(
        dir="birefnet-lite", env="VSTUDIO_BIREFNET_MODEL",
        licence="BiRefNet-lite, MIT (ZhengPeng7/BiRefNet; ONNX export onnx-community/BiRefNet_lite-ONNX, MIT).",
        files=[dict(url=f"{HF}/onnx-community/BiRefNet_lite-ONNX/resolve/de15b22ba131738a16dff04aab8bdf8dc32e3ac1/"
                        "onnx/model.onnx", dest="model.onnx", size=224005088,
                    sha256="5600024376f572a557870a5eb0afb1e5961636bef4e1e22132025467d0f03333")]),
    "upscale-esrgan": dict(
        dir="realesrgan", env="VSTUDIO_ESRGAN_WEIGHTS",
        licence="Real-ESRGAN realesr-general-x4v3 weights, BSD-3-Clause (xinntao/Real-ESRGAN v0.2.5.0).",
        files=[dict(url="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth",
                    dest="realesr-general-x4v3.pth", size=4885111,
                    sha256="8dc7edb9ac80ccdc30c3a5dca6616509367f05fbc184ad95b731f05bece96292")]),
    "cover-aesthetic": dict(
        dir="aesthetic", env="VSTUDIO_AESTHETIC_MODEL",
        licence="LAION aesthetic predictor v2 (sac+logos+ava1-l14-linearMSE), Apache-2.0 (christophschuhmann/"
                "improved-aesthetic-predictor); OpenAI CLIP ViT-L/14 vision tower, MIT (q4f16 ONNX by Xenova).",
        files=[dict(url=f"{HF}/Xenova/clip-vit-large-patch14/resolve/c307790166907339eed5a9a53a249af534102536/"
                        "onnx/vision_model_q4f16.onnx", dest="vision_model.onnx", size=173140193,
                    sha256="46c54f1fdabca466ed8f02967347d5070c8a05211f93f2e390140befc26c441f"),
               dict(url="https://raw.githubusercontent.com/christophschuhmann/improved-aesthetic-predictor/"
                        "6934dd81792f086e613a121dbce43082cb8be85e/sac%2Blogos%2Bava1-l14-linearMSE.pth",
                    dest="sac+logos+ava1-l14-linearMSE.pth", size=3714759,
                    sha256="21dd590f3ccdc646f0d53120778b296013b096a035a2718c9cb0d511bff0f1e0")]),
}
ALIASES = {"cover": ["matte-birefnet", "upscale-esrgan", "cover-aesthetic"]}


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def installed(gid):
    from .config import MODEL_DIR
    g = GROUPS[gid]
    return all(os.path.exists(os.path.join(MODEL_DIR, g["dir"], f["dest"])) for f in g["files"])


def fetch(gid, log=print):
    """Download one group (resumable by re-running; every file sha256-checked) -> its folder."""
    from .config import MODEL_DIR
    g = GROUPS[gid]
    d = os.path.join(MODEL_DIR, g["dir"])
    os.makedirs(d, exist_ok=True)
    for f in g["files"]:
        dst = os.path.join(d, f["dest"])
        if os.path.exists(dst) and os.path.getsize(dst) == f["size"] and _sha(dst) == f["sha256"]:
            log(f"  ok {gid}/{f['dest']}")
            continue
        log(f"  get {gid}/{f['dest']} ({f['size'] / 1e6:.0f} MB)")
        tmp = dst + ".part"
        urllib.request.urlretrieve(f["url"], tmp)  # noqa: S310  (pinned https URLs above)
        if _sha(tmp) != f["sha256"]:
            os.remove(tmp)
            raise RuntimeError(f"{gid}/{f['dest']}: sha256 mismatch - not installed")
        os.replace(tmp, dst)
    return d


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    fp = sub.add_parser("fetch")
    fp.add_argument("groups", nargs="+", help=", ".join(list(GROUPS) + list(ALIASES)))
    a = ap.parse_args(argv)
    if a.cmd == "list":
        for gid, g in GROUPS.items():
            mb = sum(f["size"] for f in g["files"]) / 1e6
            print(f"{gid:16s} {mb:6.0f} MB  {'installed' if installed(gid) else '-':9s}  {g['licence']}")
        return 0
    ids = [x for n in a.groups for x in ALIASES.get(n, [n])]
    bad = [x for x in ids if x not in GROUPS]
    if bad:
        print("unknown group:", ", ".join(bad), file=sys.stderr)
        return 2
    for gid in ids:
        print(fetch(gid))
    return 0


if __name__ == "__main__":
    sys.exit(main())
