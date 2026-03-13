from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

TAG_ORDER = {
    "PREFIX": -1,
    "ROOT": 0,
    "INFLECTION": 1,
    "POSSESSIVE": 2,
    "CASE": 3,
    "DERIVATIONAL": 4,
    "ADJECTIVE": 5,
    "DIMINUTIVE": 6,
    "VERB": 7,
    "NUMERAL": 8,
}

TAG_UZ = {
    "PREFIX": "Prefiks",
    "ROOT": "O'zak (Ildiz)",
    "INFLECTION": "Ko'plik",
    "POSSESSIVE": "Egalik",
    "CASE": "Kelishik",
    "DERIVATIONAL": "Yasovchi",
    "ADJECTIVE": "Sifat yasovchi",
    "DIMINUTIVE": "Kichraytirish",
    "VERB": "Fe'l",
    "NUMERAL": "Son yasovchi",
    "UNKNOWN": "Noma'lum",
}

DEFAULT_CODE_BY_TAG = {
    "PREFIX": "PX000",
    "ROOT": "ROOT",
    "INFLECTION": "SF001",
    "POSSESSIVE": "SF010",
    "CASE": "SF030",
    "DERIVATIONAL": "SF100",
    "ADJECTIVE": "SF200",
    "DIMINUTIVE": "SF300",
    "VERB": "SF400",
    "NUMERAL": "SF500",
    "UNKNOWN": "UNKNOWN",
}

NEW_CODE_BY_TAG = {
    "PREFIX": "8.8.8.8",
    "ROOT": "0.0.0.0",
    "INFLECTION": "1.1.1.1",
    "POSSESSIVE": "2.2.2.2",
    "CASE": "3.3.3.3",
    "DERIVATIONAL": "4.4.4.4",
    "ADJECTIVE": "5.5.5.5",
    "DIMINUTIVE": "5.5.5.5",
    "VERB": "6.6.6.6",
    "NUMERAL": "7.7.7.7",
    "UNKNOWN": "9.9.9.9",
}

LEGACY_TAG_MAP = {
    "STEM": "ROOT",
    "PLURAL": "INFLECTION",
}

CASE_SUBTYPES = {"ACC", "GEN", "DAT", "LOC", "ABL", "TERM", "SIM", "POSREL", "LOCADJ", "LOCEMPH"}
DIMINUTIVE_SUBTYPES = {"DIM", "AFF", "ENDEAR"}
APOSTROPHES = str.maketrans({"ʻ": "'", "ʼ": "'", "‘": "'", "’": "'", "`": "'", "ʹ": "'"})


@dataclass
class SuffixEntry:
    affix: str
    type: str
    category: str
    tag: str
    subtype: str
    code: str
    new_code: str
    source_category: str


def normalize_tag(tag: str) -> str:
    value = (tag or "").strip().upper()
    return LEGACY_TAG_MAP.get(value, value or "UNKNOWN")


def dotted_code_for_tag(tag: str) -> str:
    return NEW_CODE_BY_TAG.get(normalize_tag(tag), NEW_CODE_BY_TAG["UNKNOWN"])


class UzbekMorphSegmenter:
    CATEGORY_ORDER = ["POSSESSIVE", "CASE", "INFLECTION", "NUMERAL", "DIMINUTIVE", "ADJECTIVE", "DERIVATIONAL", "VERB"]
    COMBINED_POSSESSIVE = {"lari", "leri"}
    CHAIN_ORDER = {
        "DERIVATIONAL": 1,
        "ADJECTIVE": 1,
        "DIMINUTIVE": 1,
        "VERB": 1,
        "NUMERAL": 1,
        "INFLECTION": 2,
        "POSSESSIVE": 3,
        "CASE": 4,
    }

    def __init__(self, suffix_path: Path):
        self.suffix_path = suffix_path
        self.prefixes: List[SuffixEntry] = []
        self.suffixes: List[SuffixEntry] = []
        self.by_category: Dict[str, List[SuffixEntry]] = {}
        self.by_affix: Dict[str, List[SuffixEntry]] = {}
        self._generated_counts: Dict[str, int] = {}
        self._load_lexicon()

    def _default_headers(self) -> List[str]:
        return ["affix", "category", "type", "pos_from", "pos_to", "code", "new_code", "subtype"]

    def _generate_new_code(self, tag: str, explicit_new_code: str) -> str:
        if explicit_new_code:
            return explicit_new_code
        return dotted_code_for_tag(tag)

    def _normalize_text(self, text: str) -> str:
        return (text or "").strip().lower().translate(APOSTROPHES)

    def _normalize_entry(self, raw_category: str, raw_type: str, subtype: str, pos_to: str = "") -> tuple[str, str]:
        category = (raw_category or "").strip().upper()
        affix_type = (raw_type or "").strip().upper()
        subtype = (subtype or "").strip().upper()
        pos_to = (pos_to or "").strip().upper()

        if affix_type == "PREFIX":
            return "PREFIX", "PREFIX"

        if category == "PLURAL":
            return "SUFFIX", "INFLECTION"
        if category in {"POSSESSIVE", "CASE", "VERB", "NUMERAL"}:
            return "SUFFIX", category
        if category == "ADJECTIVE":
            return "SUFFIX", "ADJECTIVE"
        if category in {"DERIVATIONAL", "NOUN_DERIV"}:
            if pos_to == "ADJ":
                return "SUFFIX", "ADJECTIVE"
            return "SUFFIX", "DERIVATIONAL"
        if category == "DIMINUTIVE":
            return "SUFFIX", "DIMINUTIVE"

        if category == "INFLECTION":
            if subtype.startswith("P"):
                return "SUFFIX", "POSSESSIVE"
            if subtype in CASE_SUBTYPES:
                return "SUFFIX", "CASE"
            if subtype in DIMINUTIVE_SUBTYPES:
                return "SUFFIX", "DIMINUTIVE"
            return "SUFFIX", "INFLECTION"

        if affix_type == "INFLECTION":
            if category == "POSSESSIVE":
                return "SUFFIX", "POSSESSIVE"
            if category == "CASE":
                return "SUFFIX", "CASE"
            return "SUFFIX", "INFLECTION"

        if affix_type == "SUFFIX":
            if category in {"POSSESSIVE", "CASE", "VERB", "NUMERAL"}:
                return "SUFFIX", category
            if category == "ADJECTIVE":
                return "SUFFIX", "ADJECTIVE"
            if category in {"DERIVATIONAL", "NOUN_DERIV"}:
                if pos_to == "ADJ":
                    return "SUFFIX", "ADJECTIVE"
                return "SUFFIX", "DERIVATIONAL"
            return "SUFFIX", "DERIVATIONAL"

        return "SUFFIX", category or "UNKNOWN"

    def _generate_code(self, tag: str, explicit_code: str) -> str:
        if explicit_code:
            return explicit_code

        base_map = {
            "PREFIX": 0,
            "INFLECTION": 1,
            "POSSESSIVE": 10,
            "CASE": 30,
            "DERIVATIONAL": 100,
            "ADJECTIVE": 200,
            "DIMINUTIVE": 300,
            "VERB": 400,
            "NUMERAL": 500,
        }
        if tag == "ROOT":
            return "ROOT"
        if tag == "UNKNOWN":
            return "UNKNOWN"

        self._generated_counts[tag] = self._generated_counts.get(tag, 0) + 1
        seq = base_map.get(tag, 900) + self._generated_counts[tag] - 1
        prefix = "PX" if tag == "PREFIX" else "SF"
        return f"{prefix}{seq:03d}"

    def _build_rows_with_codes(self, rows: List[dict], fieldnames: List[str]) -> tuple[List[dict], List[str], bool]:
        normalized_fieldnames = list(fieldnames) if fieldnames else self._default_headers()
        if "code" not in normalized_fieldnames:
            insert_at = normalized_fieldnames.index("pos_to") + 1 if "pos_to" in normalized_fieldnames else len(normalized_fieldnames)
            normalized_fieldnames.insert(insert_at, "code")
        if "new_code" not in normalized_fieldnames:
            insert_at = normalized_fieldnames.index("code") + 1 if "code" in normalized_fieldnames else len(normalized_fieldnames)
            normalized_fieldnames.insert(insert_at, "new_code")

        generated_counts: Dict[str, int] = {}
        changed = False
        updated_rows: List[dict] = []

        for original_row in rows:
            row = {key: value for key, value in original_row.items() if key is not None}
            affix = self._normalize_text(row.get("affix") or "")
            raw_category = (row.get("category") or "").strip()
            raw_type = (row.get("type") or "").strip()
            subtype = (row.get("subtype") or "").strip().upper()
            pos_to = (row.get("pos_to") or "").strip()
            existing_code = (row.get("code") or "").strip().upper()
            existing_new_code = (row.get("new_code") or "").strip()

            if affix:
                entry_type, tag = self._normalize_entry(raw_category, raw_type, subtype, pos_to)
                if existing_code:
                    code = existing_code
                else:
                    base_map = {
                        "PREFIX": 0,
                        "INFLECTION": 1,
                        "POSSESSIVE": 10,
                        "CASE": 30,
                        "DERIVATIONAL": 100,
                        "ADJECTIVE": 200,
                        "DIMINUTIVE": 300,
                        "VERB": 400,
                        "NUMERAL": 500,
                    }
                    generated_counts[tag] = generated_counts.get(tag, 0) + 1
                    seq = base_map.get(tag, 900) + generated_counts[tag] - 1
                    code = f"{'PX' if entry_type == 'PREFIX' else 'SF'}{seq:03d}"
                new_code = self._generate_new_code(tag, existing_new_code)
                if row.get("code") != code:
                    row["code"] = code
                    changed = True
                if row.get("new_code") != new_code:
                    row["new_code"] = new_code
                    changed = True
            else:
                row.setdefault("code", "")
                row.setdefault("new_code", "")

            updated_rows.append(row)

        return updated_rows, normalized_fieldnames, changed

    def _persist_rows(self, rows: List[dict], fieldnames: List[str]) -> None:
        with self.suffix_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames, delimiter="\t", extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({name: row.get(name, "") for name in fieldnames})

    def _load_lexicon(self) -> None:
        if not self.suffix_path.exists():
            return

        with self.suffix_path.open("r", encoding="utf-8", errors="ignore", newline="") as file:
            reader = csv.DictReader(file, delimiter="\t")
            raw_rows = list(reader)
            fieldnames = reader.fieldnames or []

        rows_with_codes, fieldnames, changed = self._build_rows_with_codes(raw_rows, fieldnames)
        if changed:
            self._persist_rows(rows_with_codes, fieldnames)

        self._generated_counts = {}
        for row in rows_with_codes:
                affix = self._normalize_text(row.get("affix") or "")
                raw_category = (row.get("category") or "").strip()
                raw_type = (row.get("type") or "").strip()
                subtype = (row.get("subtype") or "").strip().upper()
                pos_to = (row.get("pos_to") or "").strip()
                explicit_code = (row.get("code") or "").strip().upper()
                if not affix:
                    continue

                entry_type, tag = self._normalize_entry(raw_category, raw_type, subtype, pos_to)
                entry = SuffixEntry(
                    affix=affix,
                    type=entry_type,
                    category=tag,
                    tag=tag,
                    subtype=subtype,
                    code=self._generate_code(tag, explicit_code),
                    new_code=self._generate_new_code(tag, (row.get("new_code") or "").strip()),
                    source_category=(raw_category or "").strip().upper(),
                )

                if entry.type == "PREFIX":
                    self.prefixes.append(entry)
                else:
                    self.suffixes.append(entry)

                self.by_category.setdefault(tag, []).append(entry)
                self.by_affix.setdefault(affix, []).append(entry)

        self.prefixes.sort(key=lambda item: len(item.affix), reverse=True)
        self.suffixes.sort(key=lambda item: len(item.affix), reverse=True)
        for category in self.by_category:
            self.by_category[category].sort(
                key=lambda item: (len(item.affix), item.source_category != "NOUN_DERIV", item.affix),
                reverse=True,
            )

    def _match_prefix(self, word: str) -> Optional[SuffixEntry]:
        for entry in self.prefixes:
            if len(word) > len(entry.affix) and word.startswith(entry.affix):
                return entry
        return None

    def _iter_suffix_matches(self, word: str, category: str) -> List[SuffixEntry]:
        matches: List[SuffixEntry] = []
        for entry in self.by_category.get(category, []):
            if entry.type != "SUFFIX":
                continue
            if len(word) <= len(entry.affix):
                continue
            if not word.endswith(entry.affix):
                continue
            if entry.affix in self.COMBINED_POSSESSIVE:
                continue
            if entry.source_category == "NOUN_DERIV" and len(entry.affix) <= 2:
                continue
            matches.append(entry)
        return matches

    def _match_suffix(self, word: str, category: str) -> Optional[SuffixEntry]:
        matches = self._iter_suffix_matches(word, category)
        return matches[0] if matches else None

    def _score(self, root: str, chain: List[SuffixEntry]) -> tuple[int, int, int, int]:
        suffix_chars = sum(len(entry.affix) for entry in chain)
        suffix_count = len(chain)
        exact_steps = sum(1 for entry in chain if entry.category in {"INFLECTION", "POSSESSIVE", "CASE"})
        lexical_steps = sum(1 for entry in chain if entry.category in {"ADJECTIVE", "DERIVATIONAL", "DIMINUTIVE", "VERB", "NUMERAL"})
        ambiguity_penalty = sum(1 for entry in chain if entry.source_category == "NOUN_DERIV")
        return (suffix_chars - ambiguity_penalty, lexical_steps, exact_steps, suffix_count)

    def _is_valid_chain(self, chain: List[SuffixEntry]) -> bool:
        previous = 0
        for entry in chain:
            current = self.CHAIN_ORDER.get(entry.category, 1)
            if current < previous:
                return False
            previous = current
        return True

    def _best_suffix_chain(self, word: str, min_root_length: int) -> tuple[str, List[SuffixEntry]]:
        memo: Dict[str, tuple[str, List[SuffixEntry]]] = {}

        def solve(rem: str) -> tuple[str, List[SuffixEntry]]:
            if rem in memo:
                return memo[rem]

            best_root = rem
            best_chain: List[SuffixEntry] = []
            best_score = self._score(rem, []) if len(rem) >= min_root_length else (-10_000, 0, 0, 0)

            for category in self.CATEGORY_ORDER:
                for entry in self._iter_suffix_matches(rem, category):
                    next_rem = rem[:-len(entry.affix)]
                    if len(next_rem) < 1:
                        continue

                    root, chain = solve(next_rem)
                    if len(root) < min_root_length:
                        continue

                    candidate_chain = chain + [entry]
                    if not self._is_valid_chain(candidate_chain):
                        continue
                    candidate_score = self._score(root, candidate_chain)
                    if candidate_score > best_score:
                        best_root = root
                        best_chain = candidate_chain
                        best_score = candidate_score

            memo[rem] = (best_root, best_chain)
            return memo[rem]

        return solve(word)

    def segment(self, word: str, strategy: str = "primary") -> Dict[str, List[str]]:
        original = (word or "").strip()
        normalized = self._normalize_text(original)
        if not normalized:
            return {"segments": [""], "tags": ["ROOT"], "subtypes": [""], "codes": ["ROOT"], "new_codes": [dotted_code_for_tag("ROOT")]}

        segments: List[str] = []
        tags: List[str] = []
        subtypes: List[str] = []
        codes: List[str] = []
        new_codes: List[str] = []

        working = normalized
        prefix_entry = self._match_prefix(working)
        if prefix_entry:
            working = working[len(prefix_entry.affix):]
            segments.append(prefix_entry.affix)
            tags.append("PREFIX")
            subtypes.append(prefix_entry.subtype)
            codes.append(prefix_entry.code)
            new_codes.append(prefix_entry.new_code)

        min_root_length = 3 if len(working) > 4 else 2
        root, suffix_chain = self._best_suffix_chain(working, min_root_length)
        if not root:
            root = working
            suffix_chain = []

        segments.append(root)
        tags.append("ROOT")
        subtypes.append("")
        codes.append("ROOT")
        new_codes.append(dotted_code_for_tag("ROOT"))

        for entry in suffix_chain:
            segments.append(entry.affix)
            tags.append(entry.category)
            subtypes.append(entry.subtype)
            codes.append(entry.code or DEFAULT_CODE_BY_TAG.get(entry.category, "UNKNOWN"))
            new_codes.append(entry.new_code or dotted_code_for_tag(entry.category))

        return {"segments": segments, "tags": tags, "subtypes": subtypes, "codes": codes, "new_codes": new_codes}

    def relabel(self, segments: List[str], tags: List[str]) -> Dict[str, List[str]]:
        clean_segments = [self._normalize_text(segment) for segment in segments if segment and segment.strip()]
        clean_tags = [str(tag or "").strip().upper() for tag in tags if str(tag or "").strip()]
        if not clean_segments:
            return {"segments": [], "tags": [], "subtypes": [], "codes": [], "new_codes": []}

        if len(clean_tags) < len(clean_segments):
            clean_tags += ["UNKNOWN"] * (len(clean_segments) - len(clean_tags))
        clean_tags = clean_tags[: len(clean_segments)]
        clean_tags = [normalize_tag(tag) for tag in clean_tags]

        subtypes: List[str] = []
        codes: List[str] = []
        new_codes: List[str] = []
        for segment, tag in zip(clean_segments, clean_tags):
            if tag == "ROOT":
                subtypes.append("")
                codes.append("ROOT")
                new_codes.append(dotted_code_for_tag("ROOT"))
                continue

            matched = next((entry for entry in self.by_affix.get(segment, []) if entry.category == tag), None)
            if matched is None and tag == "INFLECTION" and segment in {"lar", "ler"}:
                matched = next((entry for entry in self.by_affix.get(segment, []) if entry.category == "INFLECTION"), None)

            if matched:
                subtypes.append(matched.subtype)
                codes.append(matched.code)
                new_codes.append(matched.new_code)
            else:
                subtypes.append("")
                codes.append(DEFAULT_CODE_BY_TAG.get(tag, "UNKNOWN"))
                new_codes.append(dotted_code_for_tag(tag))

        return {"segments": clean_segments, "tags": clean_tags, "subtypes": subtypes, "codes": codes, "new_codes": new_codes}
