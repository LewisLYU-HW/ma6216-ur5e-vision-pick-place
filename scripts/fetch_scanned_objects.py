"""Fetch two pinned GSO tool models, without installing another simulator."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.request

REVISION = "6ff8d275cebfd5b47e49685e3cfbe64b20e49a3c"
REPOSITORY = "https://github.com/kevinzakka/mujoco_scanned_objects"
TOOLS = ("Cole_Hardware_Hammer_Black", "Craftsman_Grip_Screwdriver_Phillips_Cushion")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1]/"assets/library/gso")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    jobs = [(name, f) for name in TOOLS for f in
            ["model.obj", "model.xml", "texture.png", *[f"model_collision_{i}.obj" for i in range(32)]]]
    jobs.append((None, "LICENSE"))

    def fetch(job):
        name, filename = job
        relative = f"models/{name}/{filename}" if name else filename
        url = f"https://raw.githubusercontent.com/kevinzakka/mujoco_scanned_objects/{REVISION}/{relative}"
        with urllib.request.urlopen(url, timeout=45) as response:
            data = response.read(5_000_001)
        if len(data) > 5_000_000:
            raise RuntimeError(f"Unexpectedly large individual asset: {url}")
        path = args.output/name/filename if name else args.output/filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {"path": path.relative_to(args.output).as_posix(), "url": url,
                "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    with ThreadPoolExecutor(max_workers=8) as pool:
        records = list(pool.map(fetch, jobs))
    manifest = {"repository": REPOSITORY, "revision": REVISION,
                "assets_license": "CC-BY-4.0", "xml_license": "MIT",
                "original_dataset": "Google Scanned Objects; Downs et al., 2022",
                "mujoco_conversion": "Kevin Zakka, Scanned Objects MuJoCo Models, 2022",
                "files": records}
    (args.output/"SOURCE.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(json.dumps({"files": len(records), "bytes": sum(x["bytes"] for x in records)}))


if __name__ == "__main__":
    main()
