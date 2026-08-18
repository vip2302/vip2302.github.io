#!/usr/bin/env python3
"""
옵시디언 볼트 → Quartz 홈페이지 동기화 스크립트
────────────────────────────────────────────────
프론트매터에 `publish: true` 가 있는 노트만 ~/homepage/content 로 수집한다.
`section:` 값으로 사이트 내 폴더가 결정된다 (없으면 notes).

사용법:
    python3 sync-vault.py --dry-run    # 무엇이 공개될지 먼저 확인 (권장)
    python3 sync-vault.py              # 실제 수집
    python3 sync-vault.py --list       # publish:true 노트 목록만 보기

프론트매터 예시:
    ---
    publish: true
    section: investing        # notes | investing | research | teaching
    title: 복리의 비밀
    ---
"""

import re
import shutil
import sys
from pathlib import Path

# ══════════════════════════════════════════════════════════
# 설정
# ══════════════════════════════════════════════════════════

VAULT = Path.home() / "Library/Mobile Documents/iCloud~md~obsidian/Documents/이상용 Ph.D."
HOMEPAGE = Path.home() / "homepage"
CONTENT = HOMEPAGE / "content"

# 스캔에서 제외할 폴더 (볼트 최상위 기준)
EXCLUDE_DIRS = {
    ".obsidian", ".obsidian_outer_backup_2026-08-11",
    ".trash", ".trash_outer_backup_2026-08-11",
    ".smart-env", ".makemd", ".space", ".claude", ".agents",
    ".copilot", ".opencode",
    "04 Archives",          # 아카이브는 공개 대상에서 제외
    "99 Attachments",       # 첨부는 참조될 때만 복사
}

# 볼트 안 특정 폴더만 콕 집어 제외 (볼트 루트 기준 상대경로)
EXCLUDE_PATHS = {
    "01 Projects/홈페이지",   # 홈페이지 설정 파일·템플릿 보관소
}

# 사이트 섹션 (content/ 아래 폴더). section 값이 없으면 DEFAULT_SECTION
VALID_SECTIONS = {"notes", "investing", "research", "teaching"}
DEFAULT_SECTION = "notes"

ATTACH_SUBDIR = "attachments"

# ══════════════════════════════════════════════════════════

FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(\n|$)", re.S)
PUBLISH_RE = re.compile(r"^publish:\s*['\"]?(true|yes)['\"]?\s*$", re.M | re.I)
SECTION_RE = re.compile(r"^section:\s*['\"]?([A-Za-z_-]+)['\"]?\s*$", re.M)
EMBED_RE = re.compile(r"!\[\[([^\]|#]+?)(?:\|[^\]]*)?\]\]")
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf", ".excalidraw"}


def parse_note(path: Path):
    """(공개여부, 섹션, 본문) 반환. 읽기 실패 시 None."""
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None

    m = FM_RE.match(text)
    if not m:
        return None
    fm = m.group(1)
    if not PUBLISH_RE.search(fm):
        return None

    sm = SECTION_RE.search(fm)
    section = sm.group(1).lower() if sm else DEFAULT_SECTION
    if section not in VALID_SECTIONS:
        print(f"  [경고] 알 수 없는 section '{section}' → {DEFAULT_SECTION} 으로 처리")
        section = DEFAULT_SECTION

    return section, text


def iter_notes(vault: Path):
    """제외 폴더를 건너뛰며 .md 파일 순회."""
    for p in vault.rglob("*.md"):
        rel = p.relative_to(vault)
        if rel.parts and rel.parts[0] in EXCLUDE_DIRS:
            continue
        if any(part.startswith(".") for part in rel.parts[:-1]):
            continue
        rel_posix = rel.as_posix()
        if any(rel_posix.startswith(ex.rstrip("/") + "/") for ex in EXCLUDE_PATHS):
            continue
        yield p


def build_attachment_index(vault: Path):
    """첨부 파일명 → 실제 경로 (한 번만 스캔해서 캐싱)."""
    index = {}
    for p in vault.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in IMG_EXT:
            continue
        rel = p.relative_to(vault)
        if rel.parts and rel.parts[0] in {".trash", ".obsidian",
                                          ".trash_outer_backup_2026-08-11"}:
            continue
        index.setdefault(p.name, p)
    return index


def main():
    dry = "--dry-run" in sys.argv
    list_only = "--list" in sys.argv

    if not VAULT.exists():
        sys.exit(f"[오류] 볼트를 찾을 수 없습니다: {VAULT}")
    if not list_only and not dry and not HOMEPAGE.exists():
        sys.exit(f"[오류] 홈페이지 폴더가 없습니다: {HOMEPAGE}\n"
                 f"       먼저 Quartz를 설치하세요.")

    print(f"볼트   : {VAULT}")
    print(f"홈페이지: {CONTENT}")
    print(f"모드   : {'목록만' if list_only else ('미리보기' if dry else '실제 수집')}\n")

    # 1) 공개 대상 수집
    found = []
    for md in iter_notes(VAULT):
        parsed = parse_note(md)
        if parsed:
            found.append((md, parsed[0], parsed[1]))

    if not found:
        print("공개 대상 노트가 없습니다.")
        print("공개할 노트의 프론트매터에 `publish: true` 를 추가하세요.")
        return

    by_section = {}
    for md, section, _ in found:
        by_section.setdefault(section, []).append(md)

    for section in sorted(by_section):
        print(f"[{section}] {len(by_section[section])}개")
        for md in sorted(by_section[section]):
            print(f"    {md.relative_to(VAULT)}")
        print()

    if list_only or dry:
        print(f"총 {len(found)}개. 실제 수집하려면 옵션 없이 다시 실행하세요.")
        return

    # 2) 기존 섹션 폴더 비우기 (삭제된 노트가 사이트에 남는 것 방지)
    for section in VALID_SECTIONS:
        shutil.rmtree(CONTENT / section, ignore_errors=True)
    shutil.rmtree(CONTENT / ATTACH_SUBDIR, ignore_errors=True)

    # 3) 복사
    attach_index = build_attachment_index(VAULT)
    copied_attachments = set()
    missing = []

    for md, section, text in found:
        dest = CONTENT / section / md.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(md, dest)

        for asset in EMBED_RE.findall(text):
            asset = asset.strip()
            if asset.endswith(".md") or not asset:
                continue
            src = attach_index.get(asset)
            if src:
                if asset not in copied_attachments:
                    tgt = CONTENT / ATTACH_SUBDIR / src.name
                    tgt.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, tgt)
                    copied_attachments.add(asset)
            else:
                missing.append((md.name, asset))

    print(f"노트 {len(found)}개, 첨부 {len(copied_attachments)}개 수집 완료.")

    if missing:
        print(f"\n[경고] 찾지 못한 첨부 {len(missing)}건:")
        for note, asset in missing[:10]:
            print(f"    {note} → {asset}")
        if len(missing) > 10:
            print(f"    ... 외 {len(missing) - 10}건")

    print(f"\n다음 단계:")
    print(f"    cd {HOMEPAGE} && npx quartz build --serve")


if __name__ == "__main__":
    main()
