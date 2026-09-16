from typing import List, Tuple

import re
from pathlib import Path

HEADING_RE = re.compile(r"^(#{1,6}\s+)(.+)$")
LIST_RE = re.compile(r"^(\s*(?:(?:[-*+]\s+|\d+\.\s+|>\s+)+))(.+)$")
FRONT_MATTER_LINE_RE = re.compile(r"^(\s*)([^:#][^:]*?)(\s*:\s*)(.*)$")
FRONT_MATTER_TEXT_KEYS = {"title", "description", "summary", "excerpt", "subtitle", "headline", "lang"}

# A clickable image, e.g. [![alt](image_target)](link_target) (an app-store badge, a video
# thumbnail...), optionally followed by a kramdown IAL. Matched before MEDIA_RE: [^\]]* isn't
# bracket-depth-aware, so on this nested shape MEDIA_RE would stop at the image's own closing
# "]" and fold the leading "![" into what it thinks is the link's label.
LINKED_IMAGE_RE = re.compile(r"\[!\[[^\]]*\]\([^)]+\)\]\([^)]+\)(?:\{:[^}]*\})?")
LINKED_IMAGE_DECOMPOSE_RE = re.compile(r"^(\[!\[)([^\]]*)(\]\([^)]+\)\]\([^)]+\)(?:\{:[^}]*\})?)$")
# A markdown link or image, e.g. [text](target) / ![alt](target), optionally followed by a
# kramdown IAL (e.g. {:target="_blank"}). The target must never reach DeepL: it's a URL/path,
# and a general-purpose translator can't tell an identifier from a real word.
# MEDIA_DECOMPOSE_RE re-parses a MEDIA_RE match to isolate the label; keep both in sync, an
# unrecognized shape silently falls back to fully opaque rather than raising an error.
MEDIA_RE = re.compile(r"!?\[[^\]]*\]\([^)]+\)(?:\{:[^}]*\})?")
MEDIA_DECOMPOSE_RE = re.compile(r"^(!?\[)([^\]]*)(\]\([^)]+\)(?:\{:[^}]*\})?)$")
# Jekyll/Liquid tags (e.g. {% include some_partial.html src="..." %}) are template directives,
# not prose: kept opaque entirely, including any human-readable attribute like title="...".
LIQUID_TAG_RE = re.compile(r"\{%.*?%\}")
# Raw HTML tags: only the tags themselves are protected, any real text between two tags
# (e.g. <strong>Attention</strong>) is still picked up as its own translatable segment.
HTML_TAG_RE = re.compile(r"<[^>]+>")
# Inline code spans (single or double backtick) often hold a literal URL/path/hostname
# (e.g. ``https://mondomain.tld``); double-backtick must be tried before single-backtick
# so a double-backtick span isn't mistaken for two single-backtick ones.
INLINE_CODE_RE = re.compile(r"``[^`]+``|`[^`]+`")
# A bare URL with no markdown/HTML wrapping at all (just typed directly in prose).
BARE_URL_RE = re.compile(r"https?://\S+")
PROTECTED_RE = re.compile(
    f"(?:{LINKED_IMAGE_RE.pattern})"
    f"|(?:{MEDIA_RE.pattern})"
    f"|(?:{INLINE_CODE_RE.pattern})"
    f"|(?:{BARE_URL_RE.pattern})"
    f"|(?:{LIQUID_TAG_RE.pattern})"
    f"|(?:{HTML_TAG_RE.pattern})"
)
# path is None for a same-page anchor "](#fragment)".
LINK_WITH_ANCHOR_RE = re.compile(r"\]\(([^)#]+)?#([^)\s{]+)\)")

# Reproduces kramdown's GFM heading-id algorithm (verified against the real gem, not assumed).
# Falls back to "section" for a heading with nothing left after stripping, like kramdown itself.
_SLUG_STRIP_RE = re.compile(r"[^\w\s-]", re.UNICODE)


def kramdown_slug(text: str) -> str:
    slug = _SLUG_STRIP_RE.sub("", text).replace(" ", "-").lower()
    return slug or "section"


def dedup_slugs(headings: List[str]) -> List[str]:
    used: dict = {}
    result: List[str] = []
    for heading in headings:
        base = kramdown_slug(heading)
        if base in used:
            used[base] += 1
            result.append(f"{base}-{used[base]}")
        else:
            used[base] = 0
            result.append(base)
    return result


class _Line():
    def __init__(self, segments: List[Tuple[bool, str]]):
        self.segments = segments

    def translatable_texts(self) -> set[str]:
        return {text for is_translatable, text in self.segments if is_translatable}


class StructuredMarkdownFile():
    def __init__(self, src_file: Path):
        self.__src_file = src_file
        self.__parsed_source_lines: List[_Line] = []
        self.__src_lines = src_file.read_text(encoding="utf-8").splitlines()
        self.__headings: List[str] = []

    @property
    def src_file(self) -> Path:
        return self.__src_file

    def get_headings(self) -> List[str]:
        return self.__headings

    def parse(self):
        self._in_front_matter: bool = False
        self._front_matter_allowed: bool = True
        self._in_code_src: bool = False

        for idx, src_line in enumerate(self.__src_lines):
            if self.__process_front_matter_line(
                idx=idx,
                line=src_line
            ):
                continue

            self.__parse_line(src_line)

    def get_translatable_texts(self) -> set[str]:
        texts: set[str] = set()
        for line in self.__parsed_source_lines:
            texts.update(line.translatable_texts())
        return texts

    def get_parsed_lines(self) -> list[_Line]:
        return list(self.__parsed_source_lines)

    def __add_non_translatable_line(self, line: str) -> None:
        self.__parsed_source_lines.append(_Line([(False, line)]))

    def __add_translatable_line(self, prefix: str, line: str, suffix: str = "") -> None:
        segments: List[Tuple[bool, str]] = []
        if prefix:
            segments.append((False, prefix))
        segments.append((True, line))
        if suffix:
            segments.append((False, suffix))
        self.__parsed_source_lines.append(_Line(segments))

    def __add_segments_line(self, segments: List[Tuple[bool, str]]) -> None:
        self.__parsed_source_lines.append(_Line(segments))

    def __process_front_matter_line(
        self,
        idx: int,
        line: str
    ) -> bool:
        stripped = line.strip()

        if self._front_matter_allowed and stripped == "---" and self.looks_like_front_matter_start(self.__src_lines, idx):
            # Start of front matter
            self.__add_non_translatable_line(line)
            self._in_front_matter = True
            return True

        if self._front_matter_allowed and not self._in_front_matter and stripped != "":
            # If we encounter a non-empty line before front matter, we disable front matter processing for the rest of the file.
            self._front_matter_allowed = False

        if not self._in_front_matter:
            # If we are not in front matter, we don't process front matter lines.
            return False

        if stripped == "---":
            # End of front matter
            self.__add_non_translatable_line(line)
            self._in_front_matter = False
            self._front_matter_allowed = False
            return True

        front_matter_match = FRONT_MATTER_LINE_RE.match(line)
        if front_matter_match:
            indent = front_matter_match.group(1)
            key = front_matter_match.group(2)
            separator = front_matter_match.group(3)
            value = front_matter_match.group(4)

            if self.__looks_translatable_front_matter_value(key, value):
                prefix = f"{indent}{key}{separator}"
                suffix = ""
                text = value

                if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                    prefix = f"{prefix}{value[0]}"
                    suffix = value[-1]
                    text = value[1:-1]

                self.__add_translatable_line(prefix, text, suffix)
                return True

        self.__add_non_translatable_line(line)
        return True

    def __parse_line(self, line: str) -> None:
        stripped = line.rstrip("\n")

        if stripped.lstrip().startswith("```"):
            self._in_code_src = not self._in_code_src
            self.__add_non_translatable_line(line)
            return

        if self._in_code_src:
            self.__add_non_translatable_line(line)
            return

        if stripped.strip() == "":
            self.__add_non_translatable_line(line)
            return

        heading = HEADING_RE.match(stripped)
        if heading:
            rest = heading.group(2).strip()
            self.__headings.append(rest)
            self.__add_segments_line([(False, heading.group(1))] + self.__split_protected(rest))
            return

        list_item = LIST_RE.match(stripped)
        if list_item:
            rest = list_item.group(2).strip()
            self.__add_segments_line([(False, list_item.group(1))] + self.__split_protected(rest))
            return

        plain = stripped.strip()
        self.__add_segments_line(self.__split_protected(plain))

    def __split_protected(self, text: str) -> List[Tuple[bool, str]]:
        """Split a line into (is_translatable, text) segments, keeping link/image targets,
        Liquid tags and HTML tags out of anything that gets sent to DeepL, wherever in the
        line they appear (not just when they make up the whole line)."""
        segments: List[Tuple[bool, str]] = []
        pos = 0
        for match in PROTECTED_RE.finditer(text):
            if match.start() > pos:
                segments.append(self.__gap_segment(text[pos:match.start()]))
            segments.extend(self.__decompose_protected(match.group()))
            pos = match.end()
        if pos < len(text):
            segments.append(self.__gap_segment(text[pos:]))
        if not segments:
            segments.append((False, text))
        return segments

    def __gap_segment(self, text: str) -> Tuple[bool, str]:
        return (True, text) if self.__looks_translatable(text) else (False, text)

    def __decompose_protected(self, matched: str) -> List[Tuple[bool, str]]:
        if matched.startswith("[!["):
            return self.__decompose_media(matched, LINKED_IMAGE_DECOMPOSE_RE)
        if matched.startswith("[") or matched.startswith("!["):
            return self.__decompose_media(matched, MEDIA_DECOMPOSE_RE)
        # Liquid tag or raw HTML tag: always opaque.
        return [(False, matched)]

    def __decompose_media(self, matched: str, decompose_re: re.Pattern) -> List[Tuple[bool, str]]:
        media_match = decompose_re.match(matched)
        if media_match:
            prefix, label, suffix = media_match.group(1), media_match.group(2), media_match.group(3)
            # A link's label can itself be a bare URL (e.g. the target repeated as its own
            # display text): still not prose, must not be translated either.
            if label and self.__looks_translatable(label) and not BARE_URL_RE.fullmatch(label.strip()):
                return [(False, prefix), (True, label), (False, suffix)]
        return [(False, matched)]

    def __looks_translatable(self, text: str) -> bool:
        # If there are no alphabetic chars, skip to avoid wasting API queries.
        return any(ch.isalpha() for ch in text)

    def __looks_translatable_front_matter_value(self, key: str, value: str) -> bool:
        normalized_key = key.strip().lower()
        if normalized_key in FRONT_MATTER_TEXT_KEYS:
            return self.__looks_translatable(value)

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            return self.__looks_translatable(value[1:-1])

        return self.__looks_translatable(value) and any(ch.isspace() for ch in value)

    def looks_like_front_matter_start(self, lines: List[str], start_index: int) -> bool:
        if lines[start_index].strip() != "---":
            return False

        saw_key_value_line = False
        for candidate in lines[start_index + 1:]:
            stripped = candidate.strip()
            if stripped == "":
                continue
            if stripped == "---":
                return saw_key_value_line
            if FRONT_MATTER_LINE_RE.match(candidate):
                saw_key_value_line = True
                continue
            return False

        return False
