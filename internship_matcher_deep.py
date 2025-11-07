#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Internship Finder — LLM-Driven (Enhanced with AI location gating and iterative scraping for 8 matches)

What this script does (single-file, plug & play):
- Lets you pick a resume each run (file dialog or CLI argument).
- Uses an OpenAI model (configurable via OPENAI_MODEL) to produce a structured ResumeProfile:
  domain weights, skills+levels, overall strength, suggested internship queries.
- Scrapes LinkedIn + Indeed broadly (Dallas + US-wide) WITHOUT relying on a "remote" keyword.
- Applies a spaCy-based Dallas/Remote location gate (the ONLY non-LLM filter) **that blocks only clearly out-of-area jobs** while allowing blank/ambiguous/US-wide/remote-like locations through to the LLM.
- Calls the LLM again (no batching) to evaluate EACH location-approved posting:
  Approve/Deny to apply, Match Score (0–100), priority, skills matched, gaps, concise reasons.
- Enforces LLM-only rules: grade/class-year fit, degree level fit, second-language (even "preferred" languages are treated as required).
- LLM-only hard degree gate (early reject): if a posting explicitly requires a degree the resume doesn’t satisfy, it’s dropped immediately before full evaluation.
- Continues scraping additional results until at least 8 final APPROVED internships are found (min. final matches met).
- Writes a timestamped CSV of the APPROVED jobs, sorted by LLM match score (highest first).
- Caches LLM outputs (profile, degree gate decisions, per-job decisions) to avoid re-billing on reruns.

Dependencies:
  python -m pip install requests beautifulsoup4 lxml spacy PyPDF2 python-docx openai PyMuPDF python-dotenv
  python -m spacy download en_core_web_sm

Environment:
  OPENAI_API_KEY   (required – your OpenAI API key for the live LLM calls)
  OPENAI_MODEL     (optional – default uses gpt-4)

Usage:
  python internship_matcher_deep.py [path/to/resume.pdf] [--min-evals 200] [--min-approved 8] [--top 25]
"""
import os, re, sys, csv, time, json, hashlib, argparse, traceback
from datetime import datetime
from typing import List, Dict, Any

# -------------------- HTTP & scraping deps --------------------
import requests
from bs4 import BeautifulSoup
from urllib3.util import Retry
from requests.adapters import HTTPAdapter

# -------------------- File parsing --------------------
import PyPDF2
import fitz  # PyMuPDF
from docx import Document

# -------------------- OpenAI API client --------------------
from openai import OpenAI
try:
    API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
    if not API_KEY:
        raise RuntimeError("Please set the OPENAI_API_KEY environment variable.")
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)

# -------------------- spaCy for location gate --------------------
try:
    import spacy
    try:
        NLP = spacy.load("en_core_web_sm")
    except Exception:
        from spacy.cli import download
        download("en_core_web_sm")
        NLP = spacy.load("en_core_web_sm")
except Exception as e:
    print("ERROR: spaCy + en_core_web_sm model are required for initial location filtering.\n"
          "Install with:\n"
          "  pip install spacy\n"
          "  python -m spacy download en_core_web_sm")
    print(f"Detail: {e}")
    sys.exit(1)

# -------------------- Globals & Config --------------------
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4").strip()
PROMPT_V = "2025-10-06.v1"
MIN_EVALS = 200
MAX_PER_QUERY = 120
MIN_APPROVED = 8          # ← keep at 8 (only change to the threshold)
DESCRIPTION_TRIM = None
CACHE_DIR = ".cache_llm_matcher"
os.makedirs(CACHE_DIR, exist_ok=True)

client = OpenAI()  # uses OPENAI_API_KEY from environment

def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()

# ==================== Robust HTTP session with retries ====================
def make_session(timeout_sec=12, retries=2, backoff=0.5):
    s = requests.Session()
    retry = Retry(total=retries, backoff_factor=backoff,
                  status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=frozenset(["GET"]))
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update({
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124 Safari/537.36"),
        "Accept-Language": "en-US,en;q=0.9",
    })
    s.request_timeout = timeout_sec
    return s

SESSION = make_session()

# (--- script continues ---)
