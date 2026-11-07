"""Verify exported benchmark videos against their original trajectory records."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results", type=Path, required=True)
    p.add_argument("--replays", type=Path, required=True)
    p.add_argument("--videos", type=Path, required=True)
    args = p.parse_args()
    report_root = Path(os.path.relpath(args.results.resolve(), args.videos.resolve())).as_posix()
    result = json.loads((args.results / "summary.json").read_text())
    evidence = json.loads((args.results / "evidence_manifest.json").read_text())
    entries = {}
    for trial in evidence["replay_inputs"]:
        meta = json.loads((args.replays / trial / "replay.json").read_text())
        original = evidence["trials"][trial]
        assert meta["summary_sha256"] == original["summary.json"]["sha256"], trial
        assert meta["trajectory_sha256"] == original["motion/trajectory_evaluation_only.npz"]["sha256"], trial
        assert meta["trial"] == trial
        for name, recorded in meta["files"].items():
            video = args.videos / name
            assert digest(video) == recorded["sha256"], name
            info = json.loads(
                subprocess.check_output(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-select_streams",
                        "v:0",
                        "-show_entries",
                        "stream=codec_name,pix_fmt,width,height,r_frame_rate,nb_frames:format=duration,size",
                        "-of",
                        "json",
                        str(video),
                    ],
                    text=True,
                )
            )
            stream = info["streams"][0]
            assert stream["codec_name"] == "h264" and stream["pix_fmt"] == "yuv420p", name
            assert stream["r_frame_rate"] == "25/1", name
            assert int(stream["nb_frames"]) == meta["frames"], name
            assert abs(float(info["format"]["duration"]) - meta["frames"] / 25) < 0.01, name
            entries[name] = {
                **recorded,
                **stream,
                "duration_s": float(info["format"]["duration"]),
                "original_run": {k: v for k, v in meta.items() if k != "files"},
            }
    manifest = {
        "protocol_sha256": digest(args.results / "protocol.json"),
        "note": "Original recorded simulation states; no new inference or physics steps. "
        "25 fps simulation time is not wall-clock execution time.",
        "videos": entries,
    }
    (args.videos / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    lines = [
        "# 统一评测：原始轨迹视频",
        "",
        "这些视频来自正式试验保存的 25 Hz 物理状态，没有重新跑一次后替换结果。"
        "每段都保留原始仿真时长，左侧全景、右侧腕部；工具架成功运行另外提供独立腕部视频。"
        "静态推理与离线规划等待不计入仿真视频时长。",
        "",
        f"[完整评测报告]({report_root}/README.md) · " "[视频、原始轨迹与摘要校验值](manifest.json)",
        "",
    ]
    hero = evidence["rack_success_demo"]
    if hero:
        lines += [
            "## 工具架自装配与承重",
            "",
            f"采用无扰动完整方法中最低成功种子：`{hero}`。",
            "",
            f"[完整全景＋腕部]({hero}.mp4) · [独立腕部]({hero}__wrist.mp4)",
            "",
        ]
    lines += [
        "## 预定规则选出的失败案例",
        "",
        "| 试验视频 | 停止阶段 | 原始数值与失败原因 |",
        "|---|---|---|",
    ]
    for demo in result["failure_demos"]:
        name = demo["trial"]
        lines.append(
            f"| [{name}]({name}.mp4) | {demo['last_stage']} | "
            f"[原始摘要]({report_root}/trials/{name}.json) |"
        )
    lines += [
        "",
        "## 同种子的完整方法对照",
        "",
        "每个选中消融案例均附相同任务、扰动和种子的完整方法；无论成功还是失败都保留。",
        "",
        "| 消融失败视频 | 完整方法视频 | 完整方法结果 |",
        "|---|---|---|",
    ]
    for baseline, full in evidence["paired_full_method_replays"].items():
        report = json.loads((args.results / "trials" / (full + ".json")).read_text())
        outcome = "成功" if report["success"] else "失败"
        lines.append(f"| [{baseline}]({baseline}.mp4) | [{full}]({full}.mp4) | {outcome} |")
    lines += [
        "",
        "## 本地回放与查看",
        "",
        "下载 MP4 后使用 `xdg-open 文件名.mp4` 或 VLC；" "MP4 是视频文件，不能直接当 shell 命令执行。",
        "",
        f"原始选中轨迹在 [replay_inputs/]({report_root}/replay_inputs/)；"
        "安装仿真环境后可用 `scripts/replay_trial.py --trial ... --output 新目录 --export 新文件.mp4` "
        "重新渲染，无需 FoundationPose 推理环境。失败轨迹不会因为回放而改变验收结果。",
        "",
    ]
    (args.videos / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"verified_videos": len(entries), "original_trials": len(evidence["replay_inputs"])}))


if __name__ == "__main__":
    main()
