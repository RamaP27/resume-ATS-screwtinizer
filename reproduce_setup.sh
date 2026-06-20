#!/bin/bash
# Exit on error
set -e

echo "=== Intelligent Candidate Discovery Engine Setup ==="
echo "Creating python virtual environment..."
python3 -m venv venv

echo "Activating virtual environment and installing dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "=== Setup Completed Successfully ==="
echo "To execute the candidate ranking pipeline:"
echo "  python3 rank.py --candidates ./candidates.jsonl --out ./team_antigravity.csv"
echo ""
echo "To launch the recruiter dashboard UI:"
echo "  python3 app.py"
echo "===================================================="
