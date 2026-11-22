"""Anticipatory Commerce Agent for AgentX Challenge 1.

Rezolve AI × Techfest, IIT Bombay 2026–27.
Standard library only: Python 3.9+.
"""
import csv
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

CATALOGUE_PATH = Path(__file__).resolve().parent / "catalogue.csv"
ENV_PATH = Path(__file__).resolve().parent / ".env"

# Cue words: do not commit if the last token is one of these
CUE_WORDS = {
    "size", "uk", "waist", "number",
    "under", "below", "within", "budget", "max", "up", "to", "not", "more", "than", "less",
    "tak", "se", "kam", "ke", "andar", "rs", "rupees", "inr",
    "in", "by", "from", "for", "only", "brand", "color", "colour",
    "and", "or", "also", "with", "but", "uh", "um", "like"
}

# Words indicating a correction or hesitation
CORRECTION_TRIGGER_WORDS = {
    "no", "wait", "sorry", "actually", "meant", "mean", "oops", "rather", "instead",
    "change", "make", "nahi", "matlab", "na"
}

# Number words that could be part of an incomplete compound amount
HALF_NUMBERS = {
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety",
    "saadhe", "sadhe", "dhai", "dedh", "char", "paanch", "chhe", "che", "saat", "aath", "nau", "das"
}


def is_half_number(w: str, words_so_far: list) -> bool:
    """Check if the last word is an incomplete / half-said number amount."""
    clean_w = w.lower().strip(".,!?;:\"'")
    if clean_w in ("saadhe", "sadhe", "dhai", "dedh"):
        return True
    if len(words_so_far) >= 2:
        prev = words_so_far[-2].lower().strip(".,!?;:\"'")
        if prev in ("under", "below", "within", "budget", "max", "to", "than", "less", "kam"):
            if clean_w in HALF_NUMBERS or clean_w.isdigit():
                return True
    return False


class Agent:
    """Anticipatory Shopping Agent.

    Streams words, incrementally infers shopping filters with correction support,
    runs budgeted searches with swappable backends, and commits early only when confidence is high.
    """

    PATIENCE = int(os.environ.get("PATIENCE", 2))  # Tuned to 2 to eliminate wrong commits
    CORRECTION_WINDOW = 3  # Guard window after any correction trigger

    def __init__(self, tools):
        self.tools = tools
        self.cache = {}  # Global filter signature -> hits cache
        self._load_vocabularies()

    def _load_vocabularies(self):
        """Build brand, colour, category, and size vocabularies from catalogue.csv."""
        with open(CATALOGUE_PATH, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        self.brands = sorted({r["brand"] for r in rows if r["brand"]}, key=len, reverse=True)
        self.categories = sorted({r["category"] for r in rows if r["category"]})
        self.colours = sorted({r["colour"] for r in rows if r["colour"]})
        self.sizes = sorted({r["size"] for r in rows if r["size"]})

        # Category pattern table (longer/compound phrases first)
        self.cat_patterns = [
            (r"\bhooded\s+sweatshirts?\b", "hoodies"),
            (r"\brunning\s+sneakers?\b", "running shoes"),
            (r"\brunning\s+shoes?\b", "running shoes"),
            (r"\bjogging\s+shoes?\b", "running shoes"),
            (r"\bcasual\s+sneakers?\b", "sneakers"),
            (r"\bcasual\s+shoes?\b", "sneakers"),
            (r"\bcasual\s+shirts?\b", "shirts"),
            (r"\bformal\s+shirts?\b", "shirts"),
            (r"\btrack\s+pants?\b", "track pants"),
            (r"\bpair\s+of\s+jeans\b", "jeans"),
            (r"\bpairs\s+of\s+jeans\b", "jeans"),
            (r"\bbag\s+packs?\b", "backpacks"),
            (r"\bschool\s+bags?\b", "backpacks"),
            (r"\bcollege\s+bags?\b", "backpacks"),
            (r"\bwrist\s+watch(?:es)?\b", "watches"),
            (r"\bwrist-watch(?:es)?\b", "watches"),
            (r"\bwristwatch(?:es)?\b", "watches"),
            (r"\bsmart\s+watch(?:es)?\b", "watches"),
            (r"\bsmart-watch(?:es)?\b", "watches"),
            (r"\bt-shirts?\b", "t-shirts"),
            (r"\bt\s+shirts?\b", "t-shirts"),
            (r"\btshirts?\b", "t-shirts"),
            (r"\btees?\b", "t-shirts"),
            (r"\brunners?\b", "running shoes"),
            (r"\bsneakers?\b", "sneakers"),
            (r"\bsneaks\b", "sneakers"),
            (r"\bslides?\b", "sandals"),
            (r"\bfloaters?\b", "sandals"),
            (r"\bsandals?\b", "sandals"),
            (r"\bslippers?\b", "sandals"),
            (r"\bchappals?\b", "sandals"),
            (r"\bhoodies?\b", "hoodies"),
            (r"\bsweatshirts?\b", "hoodies"),
            (r"\btrackpants?\b", "track pants"),
            (r"\bjoggers?\b", "track pants"),
            (r"\bsweatpants?\b", "track pants"),
            (r"\bjeans?\b", "jeans"),
            (r"\bdenims?\b", "jeans"),
            (r"\bkurtas?\b", "kurtas"),
            (r"\bkurtis?\b", "kurtas"),
            (r"\bdress(?:es)?\b", "dresses"),
            (r"\bfrocks?\b", "dresses"),
            (r"\bgowns?\b", "dresses"),
            (r"\bjackets?\b", "jackets"),
            (r"\bcoats?\b", "jackets"),
            (r"\bblazers?\b", "jackets"),
            (r"\bshirts?\b", "shirts"),
            (r"\bbackpacks?\b", "backpacks"),
            (r"\bbagpacks?\b", "backpacks"),
            (r"\brucksacks?\b", "backpacks"),
            (r"\bcaps?\b", "caps"),
            (r"\bhats?\b", "caps"),
            (r"\bwallets?\b", "wallets"),
            (r"\bpurses?\b", "wallets"),
            (r"\bwatch(?:es)?\b", "watches"),
            (r"\bheadphones?\b", "headphones"),
            (r"\bheadsets?\b", "headphones"),
            (r"\bearphones?\b", "headphones"),
            (r"\bearbuds?\b", "headphones"),
        ]

        # Colour pattern table (compounds & Hindi)
        self.colour_patterns = [
            (r"\bnavy\s+blue\b", "navy"),
            (r"\bolive\s+green\b", "olive"),
            (r"\bgolden\b", "gold"),
            (r"\bgray\b", "grey"),
            (r"\b(?:kaala|kala|kaali|kale)\b", "black"),
            (r"\bsafed\b", "white"),
            (r"\b(?:neela|neeli|nila)\b", "blue"),
            (r"\b(?:laal|lal)\b", "red"),
            (r"\bgulabi\b", "pink"),
            (r"\b(?:bhura|bhure)\b", "brown"),
            (r"\b(?:hara|hari)\b", "green"),
            (r"\b(?:peela|pila)\b", "yellow"),
        ]
        for c in self.colours:
            self.colour_patterns.append((rf"\b{c}\b", c))

        # Number words
        self.units = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
            "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
            "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19
        }
        self.tens = {
            "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90
        }

        # Hindi price expressions
        self.hindi_prices = {
            "saadhe teen hazaar": 3500, "sadhe teen hazaar": 3500,
            "dhai hazaar": 2500, "dhai hazar": 2500,
            "dedh hazaar": 1500, "dedh hazar": 1500,
            "paanch hazaar": 5000, "chhe hazaar": 6000, "char hazaar": 4000,
            "teen hazaar": 3000, "do hazaar": 2000, "ek hazaar": 1000,
            "pandrah sau": 1500, "satrah sau": 1700, "nau sau": 900,
            "gyarah sau": 1100, "baarah sau": 1200, "chauda sau": 1400,
            "solah sau": 1600, "atharah sau": 1800, "unnees sau": 1900,
        }

        # Size words
        self.apparel_sizes = [
            (r"\bextra\s+small\b", "XS"),
            (r"\bextra\s+large\b", "XL"),
            (r"\bdouble\s+xl\b", "XXL"),
            (r"\b2xl\b", "XXL"),
            (r"\bxxl\b", "XXL"),
            (r"\bxs\b", "XS"),
            (r"\bxl\b", "XL"),
            (r"\bsmall\b", "S"),
            (r"\bmedium\b", "M"),
            (r"\blarge\b", "L"),
        ]

        self.eng_num_sizes = {
            "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11",
            "twenty eight": "28", "thirty": "30", "thirty two": "32", "thirty four": "34", "thirty six": "36"
        }

        self.hindi_num_sizes = {
            "chhe": "6", "che": "6", "saat": "7", "aath": "8", "nau": "9", "das": "10", "gyarah": "11"
        }

    def start(self, request_id: str):
        """A new request begins."""
        self.request_id = request_id
        self.words = []
        self.last_sig = None
        self.current_hits = []
        self.current_commit = None
        self.pending_product = None
        self.pending_count = 0
        self.committed = False

    def _search_rezolve(self, filters: dict, k: int = 5):
        """Rezolve product-discovery API backend stub."""
        api_key = os.environ.get("REZOLVE_KEY")
        kb_id = os.environ.get("REZOLVE_KB_ID")
        if not api_key or not kb_id:
            if ENV_PATH.exists():
                with open(ENV_PATH, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("REZOLVE_KEY=") and not api_key:
                            api_key = line.split("=", 1)[1].strip().strip("\"'")
                        elif line.startswith("REZOLVE_KB_ID=") and not kb_id:
                            kb_id = line.split("=", 1)[1].strip().strip("\"'")

        if not api_key or not kb_id:
            raise ValueError("Rezolve API credentials not configured in environment or .env")

        # Every external search counts as one search
        self.tools.record_search(1)

        # Convert filter names to Rezolve format (price_lte for max_price)
        rezolve_filters = {}
        for key, val in filters.items():
            if val is None:
                continue
            if key == "max_price":
                rezolve_filters["price_lte"] = val
            else:
                rezolve_filters[key] = val

        url = "https://api.rezolvelabs.com/api/v1/product-discovery/search"
        payload = json.dumps({
            "knowledgeBaseId": kb_id,
            "query": "",
            "filters": rezolve_filters,
            "limit": k,
        }).encode("utf-8")

        headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        }

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        raw_results = (
            data.get("data", {}).get("results")
            if isinstance(data.get("data"), dict)
            else data.get("results") or data.get("items") or []
        )
        hits = []
        for r in raw_results:
            if isinstance(r, dict):
                pid = r.get("id") or r.get("product_id")
                hits.append({"product_id": pid, **r})
            elif isinstance(r, str):
                hits.append({"product_id": r})
        return hits

    def _search(self, filters: dict, k: int = 5):
        """Unified search method routing to Rezolve or local backend with automatic fallback."""
        if os.environ.get("USE_REZOLVE") == "1":
            try:
                return self._search_rezolve(filters, k=k)
            except Exception:
                # If Rezolve fails or times out, safely fall back to the local backend
                pass
        return self.tools.search(query="", filters=filters, k=k)

    def parse_filters(self, words: list) -> dict:
        """Parse all words so far into filters: category, colour, size, brand, max_price.

        Matches are indexed by text position so that later words override earlier ones.
        """
        text = " ".join(words)
        text_lower = text.lower()
        cleaned = re.sub(r"'\w+", "", text_lower)

        filters = {
            "category": None,
            "colour": None,
            "size": None,
            "brand": None,
            "max_price": None,
        }

        # 1. BRAND
        brand_matches = []
        for b in self.brands:
            for m in re.finditer(rf"\b{re.escape(b.lower())}\b", text_lower):
                brand_matches.append((m.start(), b))
        if brand_matches:
            brand_matches.sort(key=lambda x: x[0])
            filters["brand"] = brand_matches[-1][1]

        # 2. COLOUR
        colour_matches = []
        for pat, c_val in self.colour_patterns:
            for m in re.finditer(pat, text_lower):
                colour_matches.append((m.start(), m.end(), c_val))

        filtered_colours = []
        for s, e, val in colour_matches:
            is_sub = False
            for s2, e2, _ in colour_matches:
                if (s2 <= s < e2 or s2 < e <= e2) and (e2 - s2) > (e - s):
                    is_sub = True
                    break
            if not is_sub:
                filtered_colours.append((s, e, val))
        if filtered_colours:
            filtered_colours.sort(key=lambda x: x[0])
            filters["colour"] = filtered_colours[-1][2]

        # 3. CATEGORY
        cat_matches = []
        for pat, cat_val in self.cat_patterns:
            for m in re.finditer(pat, text_lower):
                cat_matches.append((m.start(), m.end(), cat_val))

        filtered_cats = []
        for s, e, val in cat_matches:
            is_sub = False
            for s2, e2, _ in cat_matches:
                if (s2 <= s < e2 or s2 < e <= e2) and (e2 - s2) > (e - s):
                    is_sub = True
                    break
            if not is_sub:
                filtered_cats.append((s, e, val))
        if filtered_cats:
            filtered_cats.sort(key=lambda x: x[0])
            filters["category"] = filtered_cats[-1][2]

        # 4. SIZE
        size_spans = []
        for h_w, s_val in self.hindi_num_sizes.items():
            for m in re.finditer(rf"\b{h_w}(?:\s+number)?\b", cleaned):
                if "number" in m.group(0) or f"size {h_w}" in cleaned:
                    size_spans.append((m.start(), m.end(), s_val))

        for pat, s_val in self.apparel_sizes:
            for m in re.finditer(pat, cleaned):
                size_spans.append((m.start(), m.end(), s_val))

        for e_w, s_val in self.eng_num_sizes.items():
            for m in re.finditer(rf"\b(?:size|uk|waist)\s+(?:is\s+)?{e_w}\b", cleaned):
                size_spans.append((m.start(), m.end(), s_val))
            for m in re.finditer(rf"\b{e_w}\s+(?:size|uk|waist)\b", cleaned):
                size_spans.append((m.start(), m.end(), s_val))
            for m in re.finditer(rf"\b(?:actually|meant|to|that)\s+{e_w}\b", cleaned):
                rest = cleaned[m.end():].strip()
                if not (rest.startswith("hundred") or rest.startswith("thousand")):
                    start_str = cleaned[max(0, m.start() - 6):m.start()]
                    if "up" not in start_str:
                        size_spans.append((m.start(), m.end(), s_val))

        for m in re.finditer(r"\b(?:size|uk|waist)\s+([a-z0-9]+)\b", cleaned):
            val = m.group(1).upper()
            if val in self.sizes:
                size_spans.append((m.start(), m.end(), val))

        for m in re.finditer(r"\b([a-z0-9]+)\s+(?:size|uk|waist)\b", cleaned):
            val = m.group(1).upper()
            if val in self.sizes:
                size_spans.append((m.start(), m.end(), val))

        pos = 0
        for w in words:
            idx = text.find(w, pos)
            clean_w = w.strip(".,!?;:\"'")
            if clean_w in ("XS", "S", "M", "L", "XL", "XXL", "2XL"):
                val = "XXL" if clean_w == "2XL" else clean_w
                before = text_lower[max(0, idx - 10):idx].strip()
                if "double" in before and val == "XL":
                    val = "XXL"
                elif "extra" in before and val == "S":
                    val = "XS"
                elif "extra" in before and val == "L":
                    val = "XL"
                size_spans.append((idx, idx + len(clean_w), val))
            if idx != -1:
                pos = idx + len(w)

        filtered_sizes = []
        for s, e, val in size_spans:
            is_sub = False
            for s2, e2, _ in size_spans:
                if (s2 <= s < e2 or s2 < e <= e2) and (e2 - s2) > (e - s):
                    is_sub = True
                    break
            if not is_sub:
                filtered_sizes.append((s, e, val))
        if filtered_sizes:
            filtered_sizes.sort(key=lambda x: x[0])
            filters["size"] = filtered_sizes[-1][2]

        # 5. MAX_PRICE
        raw_price_matches = []
        for phrase, val in self.hindi_prices.items():
            for m in re.finditer(rf"\b{phrase}\b", text_lower):
                raw_price_matches.append((m.start(), m.end(), val))

        for m in re.finditer(r"\b(\d+(?:\.\d+)?)\s*k\b", text_lower):
            raw_price_matches.append((m.start(), m.end(), int(float(m.group(1)) * 1000)))

        for m in re.finditer(r"\b(" + "|".join(self.units.keys()) + r")\s+thousand\s+(" + "|".join(self.units.keys()) + r")\s+hundred\b", text_lower):
            t_w, h_w = m.groups()
            raw_price_matches.append((m.start(), m.end(), self.units[t_w] * 1000 + self.units[h_w] * 100))

        for m in re.finditer(r"\b(" + "|".join(self.units.keys()) + r")\s+thousand\b", text_lower):
            t_w = m.group(1)
            raw_price_matches.append((m.start(), m.end(), self.units[t_w] * 1000))

        for m in re.finditer(r"\b(" + "|".join(self.tens.keys()) + r")\s+(" + "|".join(self.units.keys()) + r")\s+hundred\b", text_lower):
            t, u = m.groups()
            raw_price_matches.append((m.start(), m.end(), (self.tens[t] + self.units[u]) * 100))

        for m in re.finditer(r"\b(" + "|".join(self.units.keys()) + r")\s+hundred\b", text_lower):
            u = m.group(1)
            raw_price_matches.append((m.start(), m.end(), self.units[u] * 100))

        for m in re.finditer(r"(?:₹|rs\.?|inr)?\s*(\d{1,2},\d{3}|\d{3,5})\b", text_lower):
            raw_price_matches.append((m.start(), m.end(), int(m.group(1).replace(",", ""))))

        filtered_prices = []
        for s, e, val in raw_price_matches:
            is_sub = False
            for s2, e2, _ in raw_price_matches:
                if (s2 <= s < e2 or s2 < e <= e2) and (e2 - s2) > (e - s):
                    is_sub = True
                    break
            if not is_sub:
                filtered_prices.append((s, e, val))
        if filtered_prices:
            filtered_prices.sort(key=lambda x: x[0])
            filters["max_price"] = filtered_prices[-1][2]

        return filters

    def _get_sig(self, filters: dict):
        return tuple(sorted((k, str(v).lower()) for k, v in filters.items() if v is not None))

    def observe(self, word: str):
        """One more word arrives."""
        self.words.append(word)
        clean_w = word.lower().strip(".,!?;:\"'")

        parsed = self.parse_filters(self.words)
        num_known = sum(1 for v in parsed.values() if v is not None)

        filter_changed = False
        # Requirement 4: Call search only when filters change and >= 2 filters known
        if num_known >= 2:
            sig = self._get_sig(parsed)
            if sig != self.last_sig:
                self.last_sig = sig
                filter_changed = True
                if sig in self.cache:
                    hits = self.cache[sig]
                else:
                    hits = self._search(filters=parsed, k=5)
                    self.cache[sig] = hits
                self.current_hits = hits
        else:
            self.current_hits = []

        # Check if recent words indicate an ongoing correction
        recent_words = [w.lower().strip(".,!?;:\"'") for w in self.words[-self.CORRECTION_WINDOW:]]
        in_correction = any(w in CORRECTION_TRIGGER_WORDS for w in recent_words)

        is_cue = clean_w in CUE_WORDS
        is_half = is_half_number(clean_w, self.words)

        # Requirement 5: Commit condition check
        commit_target = None
        if in_correction:
            self.pending_product = None
            self.pending_count = 0
        elif len(self.current_hits) == 1 and num_known >= 3:
            cand = self.current_hits[0]["product_id"]
            if filter_changed:
                self.pending_product = cand
                self.pending_count = 0
            elif cand == self.pending_product:
                self.pending_count += 1
            else:
                self.pending_product = cand
                self.pending_count = 0

            if self.pending_count >= self.PATIENCE and not is_cue and not is_half:
                if self.pending_product != self.current_commit:
                    self.current_commit = self.pending_product
                    commit_target = self.current_commit
                    self.committed = True
        else:
            self.pending_product = None
            self.pending_count = 0

        # Calculate confidence for analysis
        if self.committed:
            confidence = 1.0
        elif len(self.current_hits) == 1:
            confidence = 0.8
        elif self.current_hits:
            confidence = max(0.2, min(0.7, 1.0 / len(self.current_hits)))
        else:
            confidence = min(0.5, num_known * 0.1)

        result = {
            "filters": parsed,
            "confidence": round(confidence, 2)
        }
        if commit_target:
            result["commit"] = commit_target

        return result

    def finish(self) -> str:
        """The request is complete. Re-parse the full request and return best product_id."""
        final_filters = self.parse_filters(self.words)
        sig = self._get_sig(final_filters)

        if sig in self.cache:
            final_hits = self.cache[sig]
        else:
            final_hits = self._search(filters=final_filters, k=5)
            self.cache[sig] = final_hits

        if final_hits:
            return final_hits[0]["product_id"]

        # Graceful backoff if over-constrained
        for drop in ("max_price", "brand", "size", "colour", "category"):
            f_copy = dict(final_filters)
            f_copy.pop(drop, None)
            sig_drop = self._get_sig(f_copy)
            if sig_drop in self.cache:
                hits = self.cache[sig_drop]
            else:
                hits = self._search(filters=f_copy, k=5)
                self.cache[sig_drop] = hits
            if hits:
                return hits[0]["product_id"]

        return self.current_commit
