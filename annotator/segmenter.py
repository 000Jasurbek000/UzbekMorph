from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

TAG_ORDER = {"STEM": 0, "PLURAL": 1, "POSSESSIVE": 2, "CASE": 3}
TAG_UZ = {
    "STEM": "O'zak",
    "PLURAL": "Ko'plik",
    "POSSESSIVE": "Egalik qo'shimchasi",
    "CASE": "Kelishik qo'shimchasi",
    "UNKNOWN": "Noma'lum",
}
DEFAULT_CODE_BY_TAG = {
    "STEM": "0.0.0",
    "PLURAL": "1.1.1",
    "POSSESSIVE": "2.2.2",
    "CASE": "3.3.3",
    "UNKNOWN": "9.9.9",
}

AUTO_SUFFIXES = {
    "PLURAL": {"lar", "ler"},
    "POSSESSIVE": {"im", "ing", "i", "si", "imiz", "ingiz", "lari", "miz", "ngiz"},
    "CASE": {"ni", "ning", "ga", "ka", "qa", "da", "ta", "dan", "tan"},
}


@dataclass
class SuffixEntry:
    suffix: str
    tag: str
    subtype: str
    code: str


class UzbekMorphSegmenter:
    def __init__(self, suffix_path: Path):
        self.suffix_path = suffix_path
        self.by_tag: Dict[str, List[SuffixEntry]] = {
            "PLURAL": [],
            "POSSESSIVE": [],
            "CASE": [],
        }
        self.by_suffix: Dict[str, List[SuffixEntry]] = {}
        self._load_suffixes()

    def _load_suffixes(self) -> None:
        with self.suffix_path.open("r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                suffix = (row.get("suffix") or "").strip().lower()
                tag = (row.get("tag") or "").strip().upper()
                subtype = (row.get("subtype") or "").strip()
                code = (row.get("code") or "").strip() or DEFAULT_CODE_BY_TAG.get(tag, DEFAULT_CODE_BY_TAG["UNKNOWN"])
                if not suffix or tag not in self.by_tag:
                    continue
                e = SuffixEntry(suffix=suffix, tag=tag, subtype=subtype, code=code)
                self.by_tag[tag].append(e)
                self.by_suffix.setdefault(suffix, []).append(e)

        for tag in self.by_tag:
            self.by_tag[tag].sort(key=lambda x: len(x.suffix), reverse=True)

        self.auto_by_tag: Dict[str, List[SuffixEntry]] = {"PLURAL": [], "POSSESSIVE": [], "CASE": []}
        for tag, suffixes in AUTO_SUFFIXES.items():
            self.auto_by_tag[tag] = [e for e in self.by_tag[tag] if e.suffix in suffixes]
            self.auto_by_tag[tag].sort(key=lambda x: len(x.suffix), reverse=True)

    def _match_stage(self, word: str, tag: str, alternate: bool = False) -> Optional[SuffixEntry]:
        matched: List[SuffixEntry] = []
        source = self.auto_by_tag[tag]
        for e in source:
            if len(word) > len(e.suffix) and word.endswith(e.suffix):
                matched.append(e)
        if not matched:
            return None
        if alternate and len(matched) > 1:
            return matched[1]
        return matched[0]

    def segment(self, word: str, strategy: str = "primary") -> Dict[str, List[str]]:
        original = (word or "").strip()
        w = original.lower()
        if not w:
            return {"segments": [""], "tags": ["STEM"], "subtypes": [""], "codes": [DEFAULT_CODE_BY_TAG["STEM"]]}

        use_alt = strategy == "alternate"
        rem = w
        chosen: List[SuffixEntry] = []

        case_suffix = self._match_stage(rem, "CASE", alternate=use_alt)
        if case_suffix:
            rem = rem[: -len(case_suffix.suffix)]
            chosen.append(case_suffix)

        possessive_suffix = self._match_stage(rem, "POSSESSIVE", alternate=use_alt)
        if possessive_suffix:
            rem = rem[: -len(possessive_suffix.suffix)]
            chosen.append(possessive_suffix)

        plural_suffix = self._match_stage(rem, "PLURAL", alternate=use_alt)
        if plural_suffix:
            rem = rem[: -len(plural_suffix.suffix)]
            chosen.append(plural_suffix)

        if not rem:
            return {"segments": [original], "tags": ["STEM"], "subtypes": [""], "codes": [DEFAULT_CODE_BY_TAG["STEM"]]}

        chosen = list(reversed(chosen))
        segments = [rem] + [e.suffix for e in chosen]
        tags = ["STEM"] + [e.tag for e in chosen]
        subtypes = [""] + [e.subtype for e in chosen]
        codes = [DEFAULT_CODE_BY_TAG["STEM"]] + [e.code for e in chosen]

        # Strict order validation
        last = 0
        for t in tags[1:]:
            cur = TAG_ORDER.get(t, -1)
            if cur < last:
                return {"segments": [original], "tags": ["STEM"], "subtypes": [""], "codes": [DEFAULT_CODE_BY_TAG["STEM"]]}
            last = cur

        return {"segments": segments, "tags": tags, "subtypes": subtypes, "codes": codes}

    def relabel(self, segments: List[str], tags: List[str]) -> Dict[str, List[str]]:
        clean_segments = [s.strip().lower() for s in segments if s and s.strip()]
        clean_tags = [t.strip().upper() for t in tags if t and t.strip()]
        if not clean_segments:
            return {"segments": [], "tags": [], "subtypes": [], "codes": []}

        if len(clean_tags) < len(clean_segments):
            clean_tags += ["UNKNOWN"] * (len(clean_segments) - len(clean_tags))
        clean_tags = clean_tags[: len(clean_segments)]

        clean_tags[0] = "STEM"
        subtypes = [""]
        codes = [DEFAULT_CODE_BY_TAG["STEM"]]

        for seg, tag in zip(clean_segments[1:], clean_tags[1:]):
            entries = self.by_suffix.get(seg, [])
            matched = next((e for e in entries if e.tag == tag), None)
            if matched:
                subtypes.append(matched.subtype)
                codes.append(matched.code)
            else:
                subtypes.append("")
                codes.append(DEFAULT_CODE_BY_TAG.get(tag, DEFAULT_CODE_BY_TAG["UNKNOWN"]))

        return {
            "segments": clean_segments,
            "tags": clean_tags,
            "subtypes": subtypes,
            "codes": codes,
        }
