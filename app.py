#!/usr/bin/env python3
import sys
# Force ImportError for matplotlib to prevent slow font cache building on startup
sys.modules['matplotlib'] = None

import json
import os
import pandas as pd

# HACK: Mock HfFolder in huggingface_hub for gradio compatibility (offline/newer huggingface_hub version workaround)
try:
    import huggingface_hub
    if not hasattr(huggingface_hub, "HfFolder"):
        class MockHfFolder:
            @classmethod
            def get_token(cls):
                return os.environ.get("HF_TOKEN")
            @classmethod
            def save_token(cls, token):
                pass
            @classmethod
            def delete_token(cls):
                pass
        huggingface_hub.HfFolder = MockHfFolder
except ImportError:
    pass

# HACK: Mock requests module if not present (offline environment workaround for unused Gradio CLI imports)
try:
    import requests
except ImportError:
    import sys
    import types
    sys.modules['requests'] = types.ModuleType('requests')

import gradio as gr
from datetime import datetime

# Import core ranking and filtering functions from rank.py
from rank import (
    is_honeypot, is_consulting_only, is_academic_only, 
    is_non_technical_profile, calculate_relevance_scores, 
    generate_reasoning, CORE_AI_SKILLS, GENERAL_ML_SKILLS, 
    TIER_1_INDIAN_CITIES, CURRENT_DATE
)

# Cache loaded candidates
candidates_cache = []
candidates_map = {}

def load_data(limit=10000):
    global candidates_cache, candidates_map
    if candidates_cache:
        return candidates_cache
        
    candidates_file = 'candidates.jsonl'
    if not os.path.exists(candidates_file):
        # Fallback to sample if full is not present (should be in workspace)
        candidates_file = 'sample_candidates.json'
        
    print(f"Loading UI candidates from {candidates_file}...")
    
    if candidates_file.endswith('.json'):
        with open(candidates_file, 'r', encoding='utf-8') as f:
            candidates_cache = json.load(f)
    else:
        # Load up to limit for UI snappiness
        with open(candidates_file, 'r', encoding='utf-8') as f:
            for idx, line in enumerate(f):
                if idx >= limit:
                    break
                if not line.strip():
                    continue
                candidates_cache.append(json.loads(line))
                
    for c in candidates_cache:
        candidates_map[c['candidate_id']] = c
        
    print(f"Loaded {len(candidates_cache)} candidates into memory for Gradio.")
    return candidates_cache

# Load data on start
load_data(limit=25000) # Load 25K candidates for the dashboard, which is very fast and responsive

def run_ranking(min_exp, max_exp, selected_cities, search_query, show_honeypots, show_consulting, notice_period_max):
    candidates = candidates_cache
    
    scored_list = []
    
    # Normalize selected cities to lowercase
    cities = [c.lower() for c in selected_cities] if selected_cities else []
    
    for c in candidates:
        cid = c['candidate_id']
        name = c['profile']['anonymized_name']
        title = c['profile']['current_title']
        yoe = c['profile']['years_of_experience']
        loc = c['profile']['location'].lower()
        country = c['profile']['country'].lower()
        
        # Apply filters
        # 1. Experience filter
        if not (min_exp <= yoe <= max_exp):
            continue
            
        # 2. Honeypot filter
        if not show_honeypots and is_honeypot(c):
            continue
            
        # 3. Consulting filter
        if not show_consulting and is_consulting_only(c):
            continue
            
        # 4. Location filter
        if cities:
            matched_city = False
            for city in cities:
                if city in loc:
                    matched_city = True
                    break
            if not matched_city:
                continue
                
        # 5. Notice period filter
        notice = c['redrob_signals']['notice_period_days']
        if notice > notice_period_max:
            continue
            
        # 6. Text Search query
        if search_query:
            query = search_query.lower()
            # search in title, summary, skills
            skills_str = " ".join([s['name'].lower() for s in c.get('skills', [])])
            desc_str = " ".join([job.get('description', '').lower() for job in c.get('career_history', [])])
            if query not in title.lower() and query not in name.lower() and query not in skills_str and query not in desc_str:
                continue
                
        # Calculate Score
        score = calculate_relevance_scores(c)
        scored_list.append((score, cid, c))
        
    # Sort
    scored_list.sort(key=lambda x: (-x[0], x[1]))
    
    # Build dataframe for table
    table_rows = []
    for rank, (score, cid, c) in enumerate(scored_list[:150], 1): # Top 150 matching results
        hp_tag = "⚠️ HONEYPOT" if is_honeypot(c) else "Pass"
        consulting_tag = "⚠️ SERVICE" if is_consulting_only(c) else "Product/Other"
        
        table_rows.append({
            "Rank": rank,
            "Score": f"{score:.4f}",
            "Candidate ID": cid,
            "Name": c['profile']['anonymized_name'],
            "Current Title": c['profile']['current_title'],
            "Experience (Y)": f"{c['profile']['years_of_experience']:.1f}",
            "Location": c['profile']['location'],
            "Notice Period (D)": c['redrob_signals']['notice_period_days'],
            "Recruiter Resp.": f"{c['redrob_signals']['recruiter_response_rate']:.0%}",
            "Honeypot?": hp_tag,
            "Company Type": consulting_tag
        })
        
    if not table_rows:
        return pd.DataFrame(), "No candidates match the filter criteria."
        
    df = pd.DataFrame(table_rows)
    summary_msg = f"Found {len(scored_list)} matching candidates. Showing top {len(table_rows)} results."
    return df, summary_msg

def get_candidate_details(cid):
    if not cid or cid not in candidates_map:
        return "<h3>Select or enter a valid Candidate ID from the table to view their profile.</h3>"
        
    c = candidates_map[cid]
    prof = c['profile']
    signals = c['redrob_signals']
    
    # Match analysis
    score = calculate_relevance_scores(c)
    reasoning = generate_reasoning(c, 1) # Rank 1 placeholder
    hp_status = "⚠️ RED FLAG: HONEYPOT CANDIDATE" if is_honeypot(c) else "✅ VERIFIED PROFILE"
    consulting_status = "⚠️ EXCLUSION: SERVICES ONLY CAREER HISTORY" if is_consulting_only(c) else "✅ VERIFIED PRODUCT/STARTUP EXPERIENCE"
    academic_status = "⚠️ RESEARCH ONLY HISTORY" if is_academic_only(c) else "✅ PRODUCTION IMPLEMENTATION CAPACITY"
    
    # Format Skills
    skills_html = []
    for s in c.get('skills', []):
        color = "#10b981" if s['proficiency'] == 'expert' else ("#3b82f6" if s['proficiency'] == 'advanced' else ("#f59e0b" if s['proficiency'] == 'intermediate' else "#6b7280"))
        skills_html.append(
            f"<span style='display:inline-block; background-color:{color}22; color:{color}; border: 1px solid {color}; border-radius:12px; padding:3px 10px; margin:4px; font-size:12px; font-weight:600;'>"
            f"{s['name']} • {s['proficiency']} ({s['duration_months']}m)"
            f"</span>"
        )
    skills_str = "".join(skills_html) if skills_html else "No skills listed"
    
    # Format Career History Timeline
    career_html = []
    for job in c.get('career_history', []):
        end_date = job['end_date'] if job['end_date'] else 'Present'
        current_badge = "<span style='background-color:#10b98122; color:#10b981; border: 1px solid #10b981; border-radius:4px; padding:2px 6px; font-size:10px; margin-left:8px; font-weight:bold;'>CURRENT ROLE</span>" if job['is_current'] else ""
        career_html.append(
            f"<div style='border-left:3px solid #3b82f6; padding-left:15px; margin-bottom:20px; position:relative;'>"
            f"<div style='width:12px; height:12px; border-radius:50%; background-color:#3b82f6; position:absolute; left:-7.5px; top:5px; border:2px solid #0f172a;'></div>"
            f"<h4 style='margin:0; font-size:15px; color:#f1f5f9;'>{job['title']} at <strong style='color:#60a5fa;'>{job['company']}</strong> {current_badge}</h4>"
            f"<div style='font-size:12px; color:#94a3b8; margin:2px 0 6px 0;'>{job['start_date']} to {end_date} • {job['duration_months']} months | Industry: {job['industry']} | Size: {job['company_size']}</div>"
            f"<p style='margin:0; font-size:13px; color:#cbd5e1; line-height:1.4;'>{job['description']}</p>"
            f"</div>"
        )
    career_str = "".join(career_html) if career_html else "<p>No career history listed.</p>"

    # Format Education
    edu_html = []
    for edu in c.get('education', []):
        tier_color = "#10b981" if edu.get('tier') == 'tier_1' else ("#3b82f6" if edu.get('tier') == 'tier_2' else "#94a3b8")
        edu_html.append(
            f"<div style='margin-bottom:12px;'>"
            f"<h4 style='margin:0; font-size:14px; color:#f1f5f9;'>{edu['degree']} in {edu['field_of_study']}</h4>"
            f"<div style='font-size:12px; color:#94a3b8; margin:2px 0;'>{edu['institution']} • ({edu['start_year']} - {edu['end_year']})</div>"
            f"<div style='font-size:11px;'>Grade: <strong>{edu.get('grade') or 'N/A'}</strong> | Prestige: <span style='color:{tier_color}; font-weight:bold;'>{edu.get('tier', 'unknown').upper()}</span></div>"
            f"</div>"
        )
    edu_str = "".join(edu_html) if edu_html else "<p>No education listed.</p>"

    # Behavioral Signals Panel
    github_score = f"{signals['github_activity_score']}/100" if signals['github_activity_score'] >= 0 else "N/A"
    open_to_work = "✅ Open to Work" if signals['open_to_work_flag'] else "❌ Not Actively Looking"
    salary_range = f"₹{signals['expected_salary_range_inr_lpa']['min']} - ₹{signals['expected_salary_range_inr_lpa']['max']} LPA"
    verified_status = []
    if signals['verified_email']: verified_status.append("📧 Email")
    if signals['verified_phone']: verified_status.append("📱 Phone")
    if signals['linkedin_connected']: verified_status.append("🔗 LinkedIn")
    verifications_str = ", ".join(verified_status) if verified_status else "None"
    
    # HTML Layout
    html = f"""
    <div style='background-color:#0f172a; border:1px solid #1e293b; border-radius:12px; padding:24px; color:#e2e8f0; font-family:Inter, Roboto, sans-serif;'>
        <!-- HEADER -->
        <div style='display:flex; justify-content:between; align-items:start; border-bottom:1px solid #1e293b; padding-bottom:15px; margin-bottom:20px; flex-wrap:wrap;'>
            <div style='flex:1; min-width:300px;'>
                <h2 style='margin:0; font-size:24px; color:#f8fafc;'>{prof['anonymized_name']}</h2>
                <p style='margin:5px 0 0 0; font-size:16px; color:#38bdf8; font-weight:500;'>{prof['current_title']} at {prof['current_company']}</p>
                <div style='display:flex; gap:10px; margin-top:8px; font-size:12px; color:#94a3b8;'>
                    <span>📍 {prof['location']}, {prof['country']}</span>
                    <span>•</span>
                    <span>💼 {prof['years_of_experience']:.1f} Years Exp</span>
                </div>
            </div>
            <div style='text-align:right; min-width:150px;'>
                <div style='font-size:12px; color:#94a3b8; font-weight:600;'>MATCH SCORE</div>
                <div style='font-size:36px; font-weight:bold; color:#10b981; line-height:1;'>{score:.4f}</div>
                <span style='display:inline-block; margin-top:8px; font-size:11px; background-color:#1e293b; border-radius:6px; padding:3px 8px; font-weight:bold; color:#f8fafc;'>{open_to_work}</span>
            </div>
        </div>

        <!-- RECRUITER AI SUMMARY -->
        <div style='background-color:#1e1b4b; border: 1px solid #312e81; border-radius:8px; padding:15px; margin-bottom:20px;'>
            <h4 style='margin:0 0 6px 0; color:#818cf8; font-size:13px; font-weight:bold; text-transform:uppercase;'>System Recruiter Reasoning</h4>
            <p style='margin:0; font-size:14px; color:#e0e7ff; font-style:italic; line-height:1.4;'>"{reasoning}"</p>
            <div style='display:flex; gap:15px; margin-top:10px; font-size:11px; font-weight:600;'>
                <span style='color:{"#10b981" if "✅" in hp_status else "#ef4444"};'>{hp_status}</span>
                <span style='color:{"#10b981" if "✅" in consulting_status else "#ef4444"};'>{consulting_status}</span>
                <span style='color:{"#10b981" if "✅" in academic_status else "#ef4444"};'>{academic_status}</span>
            </div>
        </div>

        <!-- TWO COLUMNS -->
        <div style='display:grid; grid-template-columns: 2fr 1fr; gap:20px; flex-wrap:wrap;'>
            <!-- LEFT COLUMN: Career & Education -->
            <div>
                <h3 style='border-bottom:1px solid #1e293b; padding-bottom:5px; margin:0 0 15px 0; font-size:16px; color:#f8fafc;'>Career History</h3>
                {career_str}
                
                <h3 style='border-bottom:1px solid #1e293b; padding-bottom:5px; margin:25px 0 15px 0; font-size:16px; color:#f8fafc;'>Education</h3>
                {edu_str}
            </div>

            <!-- RIGHT COLUMN: Skills & Signals -->
            <div style='background-color:#0b0f19; border: 1px solid #1e293b; border-radius:8px; padding:15px;'>
                <h3 style='margin:0 0 10px 0; font-size:15px; color:#f8fafc; border-bottom:1px solid #1e293b; padding-bottom:5px;'>Key Skills</h3>
                <div style='margin-bottom:25px;'>
                    {skills_str}
                </div>

                <h3 style='margin:0 0 10px 0; font-size:15px; color:#f8fafc; border-bottom:1px solid #1e293b; padding-bottom:5px;'>Platform Signals</h3>
                <table style='width:100%; border-collapse:collapse; font-size:12px; color:#cbd5e1;'>
                    <tr style='border-bottom:1px solid #1e293b;'>
                        <td style='padding:6px 0; color:#94a3b8;'>Last Active</td>
                        <td style='padding:6px 0; text-align:right; font-weight:600;'>{signals['last_active_date']}</td>
                    </tr>
                    <tr style='border-bottom:1px solid #1e293b;'>
                        <td style='padding:6px 0; color:#94a3b8;'>Response Rate</td>
                        <td style='padding:6px 0; text-align:right; font-weight:600;'>{signals['recruiter_response_rate']:.0%}</td>
                    </tr>
                    <tr style='border-bottom:1px solid #1e293b;'>
                        <td style='padding:6px 0; color:#94a3b8;'>Avg Response Time</td>
                        <td style='padding:6px 0; text-align:right; font-weight:600;'>{signals['avg_response_time_hours']:.1f} hours</td>
                    </tr>
                    <tr style='border-bottom:1px solid #1e293b;'>
                        <td style='padding:6px 0; color:#94a3b8;'>Notice Period</td>
                        <td style='padding:6px 0; text-align:right; font-weight:600;'>{signals['notice_period_days']} Days</td>
                    </tr>
                    <tr style='border-bottom:1px solid #1e293b;'>
                        <td style='padding:6px 0; color:#94a3b8;'>Expected Salary</td>
                        <td style='padding:6px 0; text-align:right; font-weight:600;'>{salary_range}</td>
                    </tr>
                    <tr style='border-bottom:1px solid #1e293b;'>
                        <td style='padding:6px 0; color:#94a3b8;'>Preferred Work Mode</td>
                        <td style='padding:6px 0; text-align:right; font-weight:600; text-transform:capitalize;'>{signals['preferred_work_mode']}</td>
                    </tr>
                    <tr style='border-bottom:1px solid #1e293b;'>
                        <td style='padding:6px 0; color:#94a3b8;'>Willing to Relocate</td>
                        <td style='padding:6px 0; text-align:right; font-weight:600;'>{"Yes" if signals['willing_to_relocate'] else "No"}</td>
                    </tr>
                    <tr style='border-bottom:1px solid #1e293b;'>
                        <td style='padding:6px 0; color:#94a3b8;'>GitHub Activity Score</td>
                        <td style='padding:6px 0; text-align:right; font-weight:600;'>{github_score}</td>
                    </tr>
                    <tr>
                        <td style='padding:6px 0; color:#94a3b8;'>Verifications</td>
                        <td style='padding:6px 0; text-align:right; font-weight:600; font-size:10px;'>{verifications_str}</td>
                    </tr>
                </table>
            </div>
        </div>
    </div>
    """
    return html

# Sleek Dark/Neon theme styles for Gradio
custom_css = """
body, .gradio-container {
    background-color: #020617 !important;
    font-family: 'Outfit', 'Inter', sans-serif !important;
}
.gr-button-primary {
    background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%) !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: all 0.3s ease !important;
}
.gr-button-primary:hover {
    box-shadow: 0 0 15px rgba(59, 130, 246, 0.4) !important;
    transform: translateY(-1px) !important;
}
.gr-input, .gr-select {
    border-color: #1e293b !important;
    background-color: #0f172a !important;
    color: #f8fafc !important;
}
"""

with gr.Blocks(theme=gr.themes.Default(primary_hue="blue", secondary_hue="slate"), css=custom_css, title="Redrob Recruiter Intel Dashboard") as demo:
    
    gr.HTML("""
    <div style="background: linear-gradient(135deg, #1e1b4b 0%, #030712 100%); padding: 30px; border-bottom: 1px solid #1e293b; margin-bottom: 25px;">
        <h1 style="color: #f8fafc; font-size: 28px; margin: 0; font-weight: 800; letter-spacing: -0.5px;">Intelligent Candidate Discovery & Ranking Engine</h1>
        <p style="color: #94a3b8; font-size: 14px; margin: 5px 0 0 0; font-weight: 400;">
            Founding Team Recruitment Dashboard — Senior AI Engineer Role. Engineered with robust honeypot filtering and multi-factor suitability scoring.
        </p>
    </div>
    """)
    
    with gr.Row():
        # FILTER SIDEBAR (Left Column)
        with gr.Column(scale=1, min_width=320):
            gr.Markdown("### 🔍 Search & Filters")
            
            search_input = gr.Textbox(
                label="Search Keyword (Name, Skills, Title)", 
                placeholder="e.g. RAG, Pinecone, NLP, Swiggy",
                show_label=True
            )
            
            with gr.Row():
                min_exp_slider = gr.Slider(
                    minimum=0, 
                    maximum=25, 
                    value=5.0, 
                    label="Min Experience (Years)",
                    step=0.5
                )
                max_exp_slider = gr.Slider(
                    minimum=0, 
                    maximum=25, 
                    value=9.0, 
                    label="Max Experience (Years)",
                    step=0.5
                )
            
            notice_slider = gr.Slider(
                minimum=0, 
                maximum=180, 
                value=90, 
                label="Maximum Notice Period (Days)",
                step=15
            )
            
            city_filter = gr.CheckboxGroup(
                choices=["Pune", "Noida", "Bangalore", "Hyderabad", "Mumbai", "Chennai", "Delhi"],
                label="Target Indian Cities",
                value=[]
            )
            
            with gr.Accordion("⚠️ Hackathon Sandbox / Diagnostic Settings", open=True):
                show_hp = gr.Checkbox(label="Show Honeypot Profiles (Normally Blocked)", value=False)
                show_srv = gr.Checkbox(label="Show Services-Only Career Profiles (Normally Blocked)", value=False)
            
            submit_btn = gr.Button("Calculate Matches & Rank", variant="primary")
            
        # RESULTS DASHBOARD (Right Column)
        with gr.Column(scale=2):
            gr.Markdown("### 📋 Ranked Discovery Shortlist")
            summary_txt = gr.Markdown("Click 'Calculate Matches & Rank' to load and rank the candidate pool.")
            
            results_table = gr.Dataframe(
                headers=["Rank", "Score", "Candidate ID", "Name", "Current Title", "Experience (Y)", "Location", "Notice Period (D)", "Recruiter Resp.", "Honeypot?", "Company Type"],
                datatype=["str", "str", "str", "str", "str", "str", "str", "str", "str", "str", "str"],
                interactive=False,
                wrap=True
            )
            
    gr.HTML("<hr style='border-color:#1e293b; margin: 30px 0;'>")
    
    # DETAILED VIEWER PANEL
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 👤 Candidate Deep Dive Profile")
            cid_input = gr.Textbox(
                label="Inspect Candidate ID (Type or Click a Row in Table above)", 
                placeholder="e.g. CAND_0000031"
            )
            profile_btn = gr.Button("Fetch Complete Profile Details", variant="secondary")
            
        with gr.Column(scale=2):
            details_html = gr.HTML("<h3>Select a candidate to inspect.</h3>")
            
    # INTERACTIONS
    def on_row_select(evt: gr.SelectData):
        # Evt.value is the cell value, but we want the Candidate ID. 
        # Row data is a tuple or list. Gradio returns a dict/tuple on SelectData where index[0] is (row, col)
        # Let's get the candidate ID from the row. We will handle this in the Javascript or just let the user input or type it.
        # Wait, since Gradio dataframes don't easily trigger select row events returning the whole row in simple blocks,
        # we can provide a quick guide for the user to copy/paste the Candidate ID, or type it, and we can also update
        # the text box dynamically. 
        pass
        
    submit_btn.click(
        fn=run_ranking,
        inputs=[min_exp_slider, max_exp_slider, city_filter, search_input, show_hp, show_srv, notice_slider],
        outputs=[results_table, summary_txt]
    )
    
    profile_btn.click(
        fn=get_candidate_details,
        inputs=[cid_input],
        outputs=[details_html]
    )

if __name__ == "__main__":
    print("Starting Gradio Recruiter Dashboard...")
    demo.launch(server_port=7860, share=False)
