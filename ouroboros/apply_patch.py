"""
Apply-patch shim for Claude Code CLI.
Installs `apply_patch` into a writable bin dir.
"""
import os
import pathlib

SYSTEM_APPLY_PATCH_PATH = pathlib.Path("/usr/local/bin/apply_patch")
USER_APPLY_PATCH_PATH = pathlib.Path.home() / ".local" / "bin" / "apply_patch"

APPLY_PATCH_CODE = r'''#!/usr/bin/env python3
import sys
import pathlib

def _norm_line(l: str) -> str:
    return l[1:] if l.startswith(" ") else l

def _find_subseq(hay, needle):
    if not needle:
        return 0
    n = len(needle)
    for i in range(0, len(hay) - n + 1):
        ok = True
        for j in range(n):
            if hay[i + j] != needle[j]:
                ok = False
                break
        if ok:
            return i
    return -1

def _find_subseq_rstrip(hay, needle):
    if not needle:
        return 0
    return _find_subseq([x.rstrip() for x in hay], [x.rstrip() for x in needle])

def apply_update_file(path: str, hunks: list[list[str]]):
    p = pathlib.Path(path)
    if not p.exists():
        sys.stderr.write(f"apply_patch: file not found: {path}\n")
        sys.exit(2)

    src = p.read_text(encoding="utf-8").splitlines()
    for hunk in hunks:
        old_seq, new_seq = [], []
        for line in hunk:
            if line.startswith("+"):
                new_seq.append(line[1:])
            elif line.startswith("-"):
                old_seq.append(line[1:])
            else:
                c = _norm_line(line)
                old_seq.append(c)
                new_seq.append(c)

        idx = _find_subseq(src, old_seq)
        if idx < 0:
            idx = _find_subseq_rstrip(src, old_seq)
        if idx < 0:
            sys.stderr.write("apply_patch: failed to match hunk in file: " + path + "\n")
            sys.exit(3)
        src = src[:idx] + new_seq + src[idx + len(old_seq):]

    p.write_text("\n".join(src) + "\n", encoding="utf-8")

def apply_add_file(path: str, content_lines: list[str]):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(content_lines) + "\n", encoding="utf-8")

def apply_delete_file(path: str):
    p = pathlib.Path(path)
    if p.exists():
        p.unlink()

def _is_action_boundary(line: str) -> bool:
    return line.startswith("*** ") and any(line.startswith(p) for p in (
        "*** Update File:", "*** Add File:", "*** Delete File:",
        "*** End Patch", "*** End of File",
    ))

def main():
    lines = sys.stdin.read().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("*** Begin Patch") or line.startswith("*** End Patch") or line.startswith("*** End of File"):
            i += 1
            continue

        if line.startswith("*** Update File:"):
            path = line.split(":", 1)[1].strip(); i += 1
            hunks, cur = [], []
            while i < len(lines) and not _is_action_boundary(lines[i]):
                if lines[i].startswith("@@"):
                    if cur:
                        hunks.append(cur); cur = []
                    i += 1
                    continue
                cur.append(lines[i]); i += 1
            if cur:
                hunks.append(cur)
            if i < len(lines) and lines[i].startswith("*** End of File"):
                i += 1
            apply_update_file(path, hunks)
            continue

        if line.startswith("*** Add File:"):
            path = line.split(":", 1)[1].strip(); i += 1
            content_lines = []
            while i < len(lines) and not _is_action_boundary(lines[i]):
                l = lines[i]
                if l.startswith("+"):
                    content_lines.append(l[1:])
                elif l.strip():
                    content_lines.append(l)
                i += 1
            if i < len(lines) and lines[i].startswith("*** End of File"):
                i += 1
            apply_add_file(path, content_lines)
            continue

        if line.startswith("*** Delete File:"):
            path = line.split(":", 1)[1].strip(); i += 1
            apply_delete_file(path)
            continue

        if line.startswith("***"):
            sys.stderr.write(f"apply_patch: unknown directive: {line}\n")
            sys.exit(4)

        i += 1

if __name__ == "__main__":
    main()
'''


def _install_at(path: pathlib.Path) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(APPLY_PATCH_CODE, encoding="utf-8")
        path.chmod(0o755)
        return True
    except Exception:
        return False


def install() -> None:
    if _install_at(SYSTEM_APPLY_PATCH_PATH):
        return
    if _install_at(USER_APPLY_PATCH_PATH):
        local_bin = str(USER_APPLY_PATCH_PATH.parent)
        os.environ["PATH"] = f"{local_bin}:{os.environ.get('PATH', '')}"
        return
    # best effort only
