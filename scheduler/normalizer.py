"""Name normalization and identity resolution engine.

Implements Section 3 of AGENTS.md:
- Accents & case normalization
- Punctuation & separator normalization
- Initials, abbreviated, and first-name-only resolution
- Strict ambiguity detection without arbitrary guessing
"""

import re
import unicodedata

from scheduler.models import Person


def clean_string(s: str) -> str:
    """Removes accents, trims whitespace, and converts to lowercase."""
    if not s:
        return ""
    normalized = unicodedata.normalize("NFKD", s)
    ascii_bytes = normalized.encode("ASCII", "ignore")
    return ascii_bytes.decode("utf-8").strip().lower()


def tokenize_name(raw_name: str) -> list[str]:
    """Splits a name into lowercase tokens, handling separators (., _, -, spaces)."""
    cleaned = clean_string(raw_name)
    # Replace non-alphanumeric separators with spaces
    spaced = re.sub(r"[._,\-\s]+", " ", cleaned)
    return [p for p in spaced.split() if p]


def format_display_name(raw_name: str) -> str:
    """Formats a raw name into a clean, capitalized display name."""
    cleaned = raw_name.strip()
    # Split on common separators
    parts = [p for p in re.split(r"[._\s]+", cleaned) if p]
    if not parts:
        return raw_name
    return " ".join(p.capitalize() for p in parts)


class NameMatcher:
    """Evaluates whether a query name matches a known person entity."""

    def __init__(self, first_name: str, last_tokens: list[str] | None = None):
        self.first_name = clean_string(first_name)
        self.last_tokens = [clean_string(t) for t in (last_tokens or []) if t]

    @property
    def last_name_str(self) -> str:
        return "-".join(self.last_tokens)

    def matches(self, raw_query: str) -> bool:
        """Determines if raw_query refers to this person."""
        q_tokens = tokenize_name(raw_query)
        if not q_tokens:
            return False

        q_clean = clean_string(raw_query)
        q_compact = re.sub(r"[^a-z0-9]", "", q_clean)

        # 1. Check compact / compressed representations (e.g. "louisr" or "lrodet")
        if self.last_tokens:
            last_initial = self.last_tokens[0][0]
            first_initial = self.first_name[0]
            # "louisr" -> first + last_initial
            if q_compact == (self.first_name + last_initial):
                return True
            # "lrodet" -> first_initial + last_name
            if q_compact == (first_initial + "".join(self.last_tokens)):
                return True
            # "louisrodet"
            if q_compact == (self.first_name + "".join(self.last_tokens)):
                return True

        # 2. Single token query (e.g. "Louis" or "Rodet")
        if len(q_tokens) == 1:
            tok = q_tokens[0]
            # Matches first name exactly
            if tok == self.first_name:
                return True
            # Matches full last name
            return bool(self.last_tokens and (tok == self.last_name_str or tok in self.last_tokens))

        # 3. Two tokens query (e.g. "Louis Rodet", "Louis R", "L. Rodet")
        if len(q_tokens) == 2:
            t1, t2 = q_tokens[0], q_tokens[1]
            if self.last_tokens:
                # Case A: t1 is first name, t2 is last name or last initial
                if t1 == self.first_name:
                    if t2 == self.last_name_str or t2 in self.last_tokens:
                        return True
                    if len(t2) == 1 and self.last_tokens[0].startswith(t2):
                        return True
                    # Also handle compound last name parts (e.g., Entat)
                    if any(part.startswith(t2) for part in self.last_tokens):
                        return True

                # Case B: t1 is first initial, t2 is last name
                if len(t1) == 1 and self.first_name.startswith(t1) and (t2 == self.last_name_str or t2 in self.last_tokens):
                    return True
            return False

        # 4. Three or more tokens (e.g. "Avril Entat Pantagene")
        if len(q_tokens) >= 3:
            return bool(q_tokens[0] == self.first_name and self.last_tokens and q_tokens[1:] == self.last_tokens)

        return False


class AmbiguousNameError(Exception):
    """Raised when a query name matches multiple distinct people."""
    def __init__(self, query: str, matched_candidates: list[Person]):
        self.query = query
        self.matched_candidates = matched_candidates
        names_str = ", ".join(f"'{p.display_name}'" for p in matched_candidates)
        super().__init__(
            f"Ambiguous name match for '{query}': matches multiple people ({names_str}). "
            f"Cannot resolve without additional information."
        )


class IdentityResolver:
    """Manages canonical person identities and resolves raw references across CSVs."""

    def __init__(self):
        self._people: list[Person] = []
        self._matchers: list[tuple[Person, NameMatcher]] = []

    @property
    def people(self) -> list[Person]:
        return list(self._people)

    def register_person(self, raw_name: str, is_board: bool = False) -> Person:
        """Parses and registers a new person entity if not already existing."""
        existing = self.find_matches(raw_name)
        if len(existing) == 1:
            p = existing[0]
            p.aliases.add(raw_name)
            if is_board:
                p.is_board = True
            return p
        elif len(existing) > 1:
            raise AmbiguousNameError(raw_name, existing)

        tokens = tokenize_name(raw_name)
        if not tokens:
            raise ValueError(f"Cannot register empty person name from '{raw_name}'")

        first_name = tokens[0]
        last_tokens = tokens[1:] if len(tokens) > 1 else []
        canonical_id = f"{first_name}_{'-'.join(last_tokens)}" if last_tokens else first_name

        # Choose an attractive display name
        display_name = format_display_name(raw_name)

        person = Person(
            canonical_id=canonical_id,
            display_name=display_name,
            first_name=first_name,
            last_tokens=last_tokens,
            is_board=is_board,
            aliases={raw_name}
        )

        matcher = NameMatcher(first_name, last_tokens)
        self._people.append(person)
        self._matchers.append((person, matcher))
        return person

    def find_matches(self, query: str) -> list[Person]:
        """Finds all registered people matching the given raw query."""
        cleaned_query = clean_string(query)
        if not cleaned_query:
            return []

        # 1. Check exact raw alias match first
        alias_matches = [p for p in self._people if any(clean_string(a) == cleaned_query for a in p.aliases)]
        if alias_matches:
            return alias_matches

        # 2. Check full matching logic
        matches = [p for p, m in self._matchers if m.matches(query)]
        return matches

    def resolve(self, query: str) -> Person | None:
        """Resolves a query name to a single Person. Raises AmbiguousNameError if ambiguous."""
        matches = self.find_matches(query)
        if len(matches) == 1:
            matched_person = matches[0]
            matched_person.aliases.add(query)
            return matched_person
        if len(matches) > 1:
            raise AmbiguousNameError(query, matches)
        return None
