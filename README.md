# Intelligent Candidate Discovery & Ranking Engine

Automating talent discovery — from resume ingestion to ranked shortlists — powered by Python and behavioral platform signals. Designed for the Redrob Challenge.

## Project Structure
- `rank.py`: High-performance CLI tool that scores, filters, and ranks the candidate pool.
- `app.py`: Rich Gradio-based Recruiter Dashboard for interactive filtering, searching, and profile deep-dives.
- `submission_metadata.yaml`: Participant metadata and system reproducibility details.
- `requirements.txt`: Python dependencies.
- `reproduce_setup.sh`: Automated script to initialize the virtual environment and install requirements.

---

## Setup Instructions

We use a self-contained Python virtual environment to run the code. To initialize the environment, execute the setup helper script:

```bash
chmod +x reproduce_setup.sh
./reproduce_setup.sh
```

This will create a `venv` directory, upgrade pip, and install all dependencies specified in `requirements.txt`.

---

## 1. Candidate Ranking CLI (Reproduce Submission)

To reproduce the submission CSV, run the following command (under 12 seconds total runtime on CPU):

```bash
venv/bin/python3 rank.py --candidates ./candidates.jsonl --out ./team_antigravity.csv
```

### Format Validation
To check the compliance of the generated CSV file with the format validator, run:

```bash
python3 validate_submission.py team_antigravity.csv
```

---

## 2. Gradio Recruiter Dashboard UI

To run the interactive recruiter dashboard locally:

```bash
venv/bin/python3 app.py
```

Then, navigate to `http://localhost:7860` in your browser.

### Key Features of the Dashboard:
- **Interactive Matching Panel:** Filter the 100K candidate pool by experience range, location, notice period, or search query.
- **Rich Suitability Rankings:** Displays matching scores, rank, current role, location, notice period, and active indicators.
- **Profile Deep-Dive Viewer:** Click or search any candidate ID to view their full resume card (anonymized contact headers, recruiter reasoning, skills proficiency metrics, complete career timeline, education, and platform activity data).
- **Honeypot Diagnostics:** Toggle checkboxes to include/exclude honeypot candidates or services-only profiles to view system diagnostic information.

---

## Methodology & Architectural Highlights

The ranking engine employs a high-precision multi-factor algorithm running locally in $O(N)$ time:

1. **Honeypot Mitigation (0% Rate):** Automatically flags and filters out candidates with logically impossible profiles (duration mismatches, company founding year violations, and expert skill levels with 0 duration) to prevent the 10% honeypot rate penalty.
2. **Hard Exclusions:** Disqualifies academic-only research profiles, completely non-technical profiles, and services-only career backgrounds (e.g. candidates whose entire work history is spent at TCS, Infosys, Wipro, Accenture, Cognizant, or Capgemini) per the JD guidelines.
3. **Experience Bell Curve:** Scores candidate experience, peaking inside the requested 5-9 years sweet spot.
4. **Role Suitability:** Parses current and historical job titles to identify product-focused ML, AI, NLP, Search, and Retrieval roles.
5. **Skill Relevance:** Multiplies skill relevance weights (giving highest priority to NLP/IR/RAG/Vector Search/Embeddings/Evaluation) by proficiency level, duration, and endorsements.
6. **Platform Activity Multipliers:** Adjusts scores using behavioral signal weights (recency of login activity, recruiter response rate, open-to-work flags, notice period length, and Noida/Pune location/relocation preferences).
7. **Dynamic Reasonings:** Composes fact-based, non-templated reasoning strings reflecting actual candidate details, location, and potential recruiter concerns (e.g., long notice periods or low platform response rate).
