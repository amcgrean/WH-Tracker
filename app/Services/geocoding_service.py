import os
import gzip
import json
import re
import io
import math
from pathlib import Path
from collections import defaultdict
from rapidfuzz import fuzz
from datetime import datetime

# Normalization constants (ported from match_all_jobs_to_geojson.py)
STREET_ABBR = {
    "STREET":"ST","ST":"ST","AVENUE":"AVE","AVE":"AVE","ROAD":"RD","RD":"RD",
    "DRIVE":"DR","DR":"DR","COURT":"CT","CT":"CT","CIRCLE":"CIR","CIR":"CIR",
    "PLACE":"PL","PL":"PL","LANE":"LN","LN":"LN","TERRACE":"TER","TER":"TER",
    "PARKWAY":"PKWY","PKWY":"PKWY","HIGHWAY":"HWY","HWY":"HWY","BOULEVARD":"BLVD","BLVD":"BLVD",
    "WAY":"WAY","TRAIL":"TRL","TRL":"TRL"
}
DIR_ABBR = {"NORTH":"N","SOUTH":"S","EAST":"E","WEST":"W",
            "NORTHEAST":"NE","NORTHWEST":"NW","SOUTHEAST":"SE","SOUTHWEST":"SW",
            "N":"N","S":"S","E":"E","W":"W","NE":"NE","NW":"NW","SE":"SE","SW":"SW"}

STREET_STOP = set([
    "ST","AVE","AVENUE","RD","ROAD","DR","DRIVE","CT","COURT","CIR","CIRCLE",
    "PL","PLACE","LN","LANE","TER","TERRACE","PKWY","PARKWAY","HWY","HIGHWAY",
    "BLVD","BOULEVARD","WAY","TRL","TRAIL"
]) | set(DIR_ABBR.keys())

HN_RE      = re.compile(r"^\s*(\d+)", re.IGNORECASE)
POBOX_RE   = re.compile(r"\bP\.?\s*O\.?\s*BOX\b|\bPO\s+BOX\b", re.IGNORECASE)
PARENS_RE  = re.compile(r"\([^)]*\)")
UNIT_TAILS = re.compile(r"\b(APT|UNIT|STE|SUITE|#)\b.*$", re.IGNORECASE)

class GeocodingService:
    def __init__(self, geojson_path=None):
        if geojson_path is None:
            # Look for it in common locations
            paths_to_try = [
                Path(r"C:\Users\amcgrean\python\gps\source.geojson.gz"),
                Path(r"C:\Users\amcgrean\python\gps\source.geojson"),
                Path("source.geojson.gz")
            ]
            for p in paths_to_try:
                if p.exists():
                    geojson_path = p
                    break
        
        self.geojson_path = geojson_path
        self.exact_idx = {}
        self.by_zip_idx = {}
        self.by_city_idx = {}
        self.is_loaded = False
        
        if self.geojson_path:
            self._load_index()

    def _norm_zip(self, z) -> str:
        s = str(z if z is not None else "").strip()
        s = re.sub(r"[^\d]", "", s)
        return s[:5] if s else ""

    def _norm_city(self, s: str) -> str:
        if not isinstance(s, str): return ""
        t = re.sub(r"[^\w\s]", " ", s.upper())
        return re.sub(r"\s+", " ", t).strip()

    def _leading_housenumber(self, s: str) -> str:
        if not isinstance(s, str): return ""
        m = HN_RE.match(s)
        return m.group(1) if m else ""

    def _street_core(self, s: str) -> str:
        if not isinstance(s, str): return ""
        t = s.upper()
        t = re.sub(r"[^\w\s]", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        t = re.sub(r"^\s*\d+(-\d+)?\s*", "", t)
        toks = []
        for tok in t.split():
            if tok in STREET_STOP: continue
            if tok.isalpha() or re.match(r"^\d+(ST|ND|RD|TH)$", tok):
                toks.append(tok)
        return " ".join(toks)

    def _norm_street(self, s: str) -> str:
        if not isinstance(s, str): return ""
        t = s.upper()
        t = re.sub(r"[^\w\s]", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        out = []
        for p in t.split():
            if p in DIR_ABBR: out.append(DIR_ABBR[p])
            elif p in STREET_ABBR: out.append(STREET_ABBR[p])
            else: out.append(p)
        return " ".join(out).strip()

    def _make_key(self, addr, city, state, zip5) -> str:
        return " | ".join([self._norm_street(addr), self._norm_city(city), (state or "IA").upper().strip(), self._norm_zip(zip5)])

    def _load_index(self):
        print(f"[{datetime.now()}] GeocodingService: Loading index from {self.geojson_path}...")
        exact = defaultdict(list)
        by_zip = defaultdict(list)
        by_city = defaultdict(list)
        
        def stream_geojson(path):
            raw_bytes = None
            if str(path).endswith(".gz"):
                with gzip.open(path, "rb") as gz: raw_bytes = gz.read()
            else:
                with open(path, "rb") as f: raw_bytes = f.read()
            
            try:
                text = raw_bytes.decode("utf-8", errors="ignore")
                obj = json.loads(text)
                if isinstance(obj, dict) and obj.get("type") == "FeatureCollection":
                    for feat in obj.get("features", []): yield feat
            except:
                buf = io.BytesIO(raw_bytes)
                for line in buf.readlines():
                    try: yield json.loads(line.decode("utf-8", errors="ignore"))
                    except: continue

        cnt = 0
        for feat in stream_geojson(self.geojson_path):
            props = feat.get("properties") or {}
            geom = feat.get("geometry") or {}
            if geom.get("type") != "Point": continue
            coords = geom.get("coordinates")
            if not coords or len(coords) < 2: continue
            
            num = props.get("number") or props.get("housenumber") or ""
            st = props.get("street") or props.get("street_name") or ""
            city = props.get("city") or ""
            zp = self._norm_zip(props.get("postcode") or props.get("zip"))
            full = props.get("full") or props.get("address") or f"{num} {st}".strip()
            
            hn = self._leading_housenumber(full)
            core = self._street_core(full)
            lat, lon = coords[1], coords[0]
            
            key = self._make_key(full, city, "IA", zp)
            rec = (full, city, zp, lat, lon, hn, core)
            exact[key].append(rec)
            
            if zp: by_zip[zp].append(key)
            if city: by_city[self._norm_city(city)].append(key)
            cnt += 1

        self.exact_idx = exact
        self.by_zip_idx = {z: list(dict.fromkeys(lst)) for z, lst in by_zip.items()}
        self.by_city_idx = {c: list(dict.fromkeys(lst)) for c, lst in by_city.items()}
        self.is_loaded = True
        print(f"[{datetime.now()}] GeocodingService: Indexed {cnt} features.")

    def geocode_address(self, address, city, zip_code):
        if not self.is_loaded:
            return None, None, "not_loaded"
        
        if not address or POBOX_RE.search(address):
            return None, None, "invalid_or_pobox"

        zip5 = self._norm_zip(zip_code)
        norm_c = self._norm_city(city)
        job_key = self._make_key(address, city, "IA", zip5)
        job_hn = self._leading_housenumber(address)
        job_core = self._street_core(address)
        job_tok = set(job_core.split())

        # 1. Exact Match
        if job_key in self.exact_idx:
            rec = self.exact_idx[job_key][0]
            return rec[3], rec[4], "exact"

        # 2. Fuzzy Tier 1: ZIP pool + same house number
        cands = self.by_zip_idx.get(zip5, [])
        best = None
        for ck in cands:
            rec = self.exact_idx[ck][0]
            if rec[5] != job_hn: continue
            
            c_sim = fuzz.token_set_ratio(job_core, rec[6])
            if c_sim < 88: continue
            
            cand_tok = set(rec[6].split())
            union = len(job_tok | cand_tok) or 1
            overlap = int(round(100 * len(job_tok & cand_tok) / union))
            if overlap < 50: continue
            
            if best is None or c_sim > best[0]:
                best = (c_sim, rec)
        
        if best and best[0] >= 90:
            return best[1][3], best[1][4], "fuzzy_zip"

        # 3. Fuzzy Tier 2: City pool + same house number
        cands = self.by_city_idx.get(norm_c, [])
        best = None
        for ck in cands:
            rec = self.exact_idx[ck][0]
            if rec[5] != job_hn: continue
            
            c_sim = fuzz.token_set_ratio(job_core, rec[6])
            if c_sim < 88: continue
            
            cand_tok = set(rec[6].split())
            union = len(job_tok | cand_tok) or 1
            overlap = int(round(100 * len(job_tok & cand_tok) / union))
            if overlap < 50: continue
            
            if best is None or c_sim > best[0]:
                best = (c_sim, rec)
        
        if best and best[0] >= 90:
            return best[1][3], best[1][4], "fuzzy_city"

        return None, None, "failed"
