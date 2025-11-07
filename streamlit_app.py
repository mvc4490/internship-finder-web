import streamlit as st
import subprocess
import sys
import os
import tempfile
import threading
import time
from importlib import util as importlib_util

st.set_page_config(page_title="Internship Finder", page_icon="🧠", layout="wide")

REQUIRED_PKGS = [
    "requests>=2.31",
    "beautifulsoup4>=4.12",
    "lxml>=4.9",
    "spacy==3.7.2",
    "en-core-web-sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl",
    "PyPDF2>=3.0.1",
    "PyMuPDF==1.24.9",
    "python-docx>=1.1.2",
    "openai>=1.30.0",
    "python-dotenv>=1.0.1",
    "urllib3<2.3",
]

def need_install():
    checks = {
        "requests": "requests",
        "bs4": "beautifulsoup4",
        "lxml": "lxml",
        "spacy": "spacy",
        "PyPDF2": "PyPDF2",
        "fitz": "PyMuPDF",
        "docx": "python-docx",
        "openai": "openai",
    }
    missing = []
    for mod, pkg in checks.items():
        if importlib_util.find_spec(mod) is None:
            missing.append(pkg)
    return bool(missing)

def bootstrap_install():
    st.write("📦 Installing required packages (first run may take a few minutes)…")
    cmd = [sys.executable, "-m", "pip", "install", "--no-input"]
    cmd.extend(REQUIRED_PKGS)
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode != 0:
        st.error("Package install failed. Logs:")
        st.code(proc.stdout + "\n" + proc.stderr)
        st.stop()
    st.success("Dependencies installed successfully.")

# --- Bootstrap deps if needed ---
if need_install():
    bootstrap_install()

# Double-check spaCy model import (name is 'en_core_web_sm' as a module)
try:
    import en_core_web_sm  # noqa: F401
except Exception:
    # Try one more time just for the model
    subprocess.run([sys.executable, "-m", "pip", "install", "--no-input",
                    "en-core-web-sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl"],
                   check=False)

st.title("🎯 Internship Finder (AI-Driven)")
st.write(
    "Upload your resume, and this app will find and rank matching internships "
    "in Dallas or remote. It may take quite a while to run, so please keep this "
    "tab open until completion."
)

uploaded_file = st.file_uploader(
    "Upload your resume (.pdf, .docx, or .txt)", type=["pdf", "docx", "txt"]
)

if uploaded_file is not None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp:
        tmp.write(uploaded_file.read())
        resume_path = tmp.name

    min_evals = st.number_input("Minimum job evaluations", 10, 2000, 50, step=10)
    min_approved = st.number_input("Minimum approved matches", 1, 50, 1, step=1)
    top_n = st.number_input("Show top N results", 1, 50, 5, step=1)

    if st.button("🚀 Run Searcher"):
        st.info("Running the internship searcher... this may take up to an hour ⏳")

        # ---------------- Heartbeat thread ----------------
        stop_flag = False
        def heartbeat():
            while not stop_flag:
                st.write("🫀 Still working... please wait...")
                time.sleep(60)  # every 60 seconds keeps Streamlit alive
        hb_thread = threading.Thread(target=heartbeat)
        hb_thread.start()
        # --------------------------------------------------

        cmd = [
            sys.executable if sys.executable else "python3",
            "internship_matcher_deep.py",
            resume_path,
            f"--min-evals={int(min_evals)}",
            f"--min-approved={int(min_approved)}",
            f"--top={int(top_n)}",
        ]

        try:
            # allow up to two hours for completion
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)

            stop_flag = True
            hb_thread.join()

            st.text_area(
                "Console Output",
                result.stdout + "\n" + result.stderr,
                height=300,
            )

            # Locate the most recent CSV result file
            csv_files = [
                f
                for f in os.listdir(".")
                if f.startswith("internship_results_") and f.endswith(".csv")
            ]
            if csv_files:
                latest_csv = max(csv_files, key=os.path.getmtime)
                with open(latest_csv, "rb") as f:
                    st.download_button(
                        "📥 Download Results CSV",
                        f,
                        file_name=latest_csv,
                        mime="text/csv",
                    )
            else:
                st.warning("No CSV file found. Check logs above for issues.")
        except Exception as e:
            stop_flag = True
            hb_thread.join()
            st.error(f"Error running script: {e}")

else:
    st.info("Please upload your resume to begin.")
