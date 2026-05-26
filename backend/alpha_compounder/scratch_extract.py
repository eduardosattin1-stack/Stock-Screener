import os
import json

path = r"C:\Users\Bruno\.gemini\antigravity\brain\0702dfe7-3c8b-4006-968c-0d1a47aca1bb\.system_generated\logs\transcript.jsonl"
out_path = r"c:\Users\Bruno\Stock-Screener\option_c_info.md"

matches = []

with open(path, "r", encoding="utf-8", errors="ignore") as f:
    for idx, line in enumerate(f):
        try:
            step = json.loads(line)
            content = step.get("content", "") or ""
            thinking = step.get("thinking", "") or ""
            combined = (content + "\n" + thinking).lower()
            
            # Check if it mentions option c, trajectory shape, cagr, etc.
            if "option c" in combined or "trajectory-shape" in combined or "validation gate" in combined or "agent e" in combined:
                matches.append(f"### Line {idx} | Step {step.get('step_index')} | Source {step.get('source')} | Type {step.get('type')}\n")
                if step.get("thinking"):
                    matches.append(f"**Thinking:**\n{step['thinking']}\n\n")
                if step.get("content"):
                    matches.append(f"**Content:**\n{step['content']}\n\n")
                matches.append("-" * 40 + "\n")
        except Exception as e:
            pass

with open(out_path, "w", encoding="utf-8") as out_f:
    out_f.write("\n".join(matches))

print(f"Done! Matches found: {len(matches)}")
