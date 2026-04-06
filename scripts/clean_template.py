"""
P0 Refactoring: Remove orphaned JS from platform_config.html

Strategy: KEEP lines 1-1108, REMOVE lines 1109-1977, KEEP lines 1978-end
"""
import pathlib

target = pathlib.Path(__file__).parent.parent / "app" / "templates" / "pages" / "platform_config.html"

lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
print(f"Original: {len(lines)} lines")

# KEEP 1: lines 1-1108 (index 0-1107)
keep1 = lines[:1108]

# KEEP 2: lines 1978-end (index 1977 onwards)  
keep2 = lines[1977:]

# Verify boundaries
print(f"KEEP1 last line: {keep1[-1].strip()[:80]}")
print(f"Removed first line: {lines[1108].strip()[:80]}")
print(f"Removed last line: {lines[1976].strip()[:80]}")
print(f"KEEP2 first line: {keep2[0].strip()[:80]}")

# Sanity checks
assert "platform_config_simulation.js" in keep1[-1] or "classifiers" in keep1[-1], f"Unexpected KEEP1 end: {keep1[-1]}"
assert "renderSimulationResult" in keep2[0], f"Unexpected KEEP2 start: {keep2[0]}"

# Write clean file
clean = keep1 + ["\n"] + keep2
target.write_text("".join(clean), encoding="utf-8")

print(f"\nClean: {len(clean)} lines")
print(f"Removed: {len(lines) - len(clean)} lines")
print("Done!")
