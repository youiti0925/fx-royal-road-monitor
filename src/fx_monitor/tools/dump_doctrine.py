"""Dump knowledge_pack_v2.json into a human-readable Markdown file.

Run:
    python -m fx_monitor.tools.dump_doctrine

Writes ``docs/doctrine_v7.md`` (or whatever the current doctrine_version is)
so the same source the AI judge consumes is also reviewable by a human.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _emit_kv(lines: list[str], k: str, v) -> None:
    if isinstance(v, list):
        lines.append(f"**{k}:**")
        for item in v:
            if isinstance(item, dict):
                lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
            else:
                lines.append(f"- {item}")
        lines.append("")
    elif isinstance(v, dict):
        lines.append(f"**{k}:**")
        for ssk, ssv in v.items():
            lines.append(f"- `{ssk}`: {ssv}")
        lines.append("")
    else:
        lines.append(f"**{k}:** {v}")
        lines.append("")


def render(kp: dict) -> str:
    lines: list[str] = []
    lines.append(f"# Royal Road Doctrine — {kp.get('doctrine_version', 'unknown')}")
    lines.append("")
    lines.append(
        "Auto-generated from `src/fx_monitor/ai/knowledge_pack_v2.json` via "
        "`python -m fx_monitor.tools.dump_doctrine`."
    )
    lines.append("AI 判定が参照する全テキストをここに展開する. 人間も同じソースを開ける.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Doctrine Summary")
    lines.append("")
    lines.append(f"> {kp.get('doctrine_summary_ja', '')}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Principles")
    lines.append("")
    for k, v in kp.get("principles", {}).items():
        if isinstance(v, dict):
            label = v.get("label_ja") or v.get("name_ja") or ""
            desc = v.get("description_ja") or v.get("definition_ja") or ""
            lines.append(f"### `{k}` {label}")
            lines.append("")
            lines.append(desc.strip())
            lines.append("")
            for sk, sv in v.items():
                if sk in ("label_ja", "name_ja", "description_ja", "definition_ja"):
                    continue
                _emit_kv(lines, sk, sv)
        else:
            lines.append(f"### `{k}`")
            lines.append("")
            lines.append(str(v))
            lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Procedure Steps")
    lines.append("")
    for s in kp.get("procedure_steps", []):
        lines.append(f"### `{s['key']}` {s.get('name_ja', '')}")
        lines.append("")
        lines.append(s.get("definition_ja", "").strip())
        lines.append("")
        for sk, sv in s.items():
            if sk in ("key", "name_ja", "definition_ja"):
                continue
            _emit_kv(lines, sk, sv)
    lines.append("---")
    lines.append("")
    lines.append("## Glossary")
    lines.append("")
    for term, defn in kp.get("glossary", {}).items():
        lines.append(f"### {term}")
        lines.append("")
        lines.append(str(defn).strip())
        lines.append("")
    fs = kp.get("few_shot_examples", []) or []
    lines.append("---")
    lines.append("")
    lines.append(f"## {len(fs)} Few-Shot Examples")
    lines.append("")
    for i, ex in enumerate(fs, 1):
        lines.append(f"### Example {i}")
        lines.append("")
        if isinstance(ex, dict):
            for k, v in ex.items():
                if isinstance(v, (dict, list)):
                    lines.append(f"**{k}:**")
                    lines.append("```json")
                    lines.append(json.dumps(v, ensure_ascii=False, indent=2))
                    lines.append("```")
                else:
                    lines.append(f"**{k}:** {v}")
                lines.append("")
        else:
            lines.append(str(ex))
            lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fx_monitor.tools.dump_doctrine")
    p.add_argument(
        "--knowledge-pack",
        type=Path,
        default=Path("src/fx_monitor/ai/knowledge_pack_v2.json"),
    )
    p.add_argument("--out", type=Path, default=Path("docs/doctrine_v7.md"))
    args = p.parse_args(argv)

    kp = json.loads(args.knowledge_pack.read_text(encoding="utf-8"))
    md = render(kp)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(md, encoding="utf-8")
    print(f"wrote {args.out} ({len(md.splitlines())} lines, doctrine={kp.get('doctrine_version')})")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
