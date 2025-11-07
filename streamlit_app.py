import streamlit as st
import subprocess
import os
import tempfile
import threading
import time
from datetime import datetime

st.set_page_config(page_title="Internship Finder", page_icon="🧠", layout="wide")

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

    min_evals = st.number_input("Minimum job evaluations", 50, 500, 200, step=50)
    min_approved = st.number_input("Minimum approved matches", 1, 20, 8, step=1)
    top_n = st.number_input("Show top N results", 5, 50, 25, step=5)

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
            "python3",
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
                latest_csv = max(csv_files, key=os.path.getctime)
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
