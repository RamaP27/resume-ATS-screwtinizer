#!/usr/bin/env python3
import json
import csv
import sys
import argparse
from datetime import datetime
import os
from tqdm import tqdm

# Constants for ranking
CURRENT_DATE = datetime(2026, 6, 11)

CONSULTING_FIRMS = {
    'tcs', 'infosys', 'wipro', 'accenture', 'cognizant', 'capgemini', 
    'tech mahindra', 'genpact', 'mphasis', 'hcl', 'l&t', 'lnt', 
    'mindtree', 'hexaware', 'ust global', 'tata consultancy', 'cognizant technologies'
}

COMPANY_FOUNDING_YEARS = {
    'sarvam': 2023,
    'krutrim': 2023,
    'cred': 2018,
    'razorpay': 2014,
    'swiggy': 2014,
    'zomato': 2008,
    'paytm': 2010,
    'ola': 2010,
    'phonepe': 2015,
    'meesho': 2015,
    'nykaa': 2012,
    'flipkart': 2007,
    'inmobi': 2007,
    'freshworks': 2010,
    'byju': 2011,
    'unacademy': 2015,
    'dream11': 2008,
    'pharmeasy': 2015,
    'upgrad': 2015,
    'vedantu': 2011,
    'policybazaar': 2008,
    'yellow': 2016,
    'haptik': 2013,
    'rephrase': 2019,
    'wysa': 2015,
    'observe': 2017,
    'saarthi': 2018,
    'mad street den': 2013,
    'aganitha': 2017
}

TIER_1_INDIAN_CITIES = {
    'pune', 'noida', 'bangalore', 'bengluru', 'bengaluru', 'hyderabad', 
    'mumbai', 'delhi', 'gurgaon', 'gurugram', 'ncr', 'chennai', 'kolkata'
}

CORE_AI_SKILLS = {
    'nlp', 'retrieval', 'rag', 'embeddings', 'vector search', 'dense retrieval',
    'vector databases', 'pinecone', 'qdrant', 'milvus', 'weaviate', 'faiss', 
    'information retrieval', 'search', 'fine-tuning llms', 'llms', 
    'sentence-transformers', 'lora', 'qlora', 'learning to rank', 
    'evaluation frameworks', 'ndcg', 'mrr', 'map', 'precision@k'
}

GENERAL_ML_SKILLS = {
    'machine learning', 'data science', 'pytorch', 'tensorflow', 'scikit-learn', 
    'mlops', 'mlflow', 'weights & biases', 'databricks', 'spark', 'pyspark', 
    'airflow', 'sql', 'python', 'deep learning', 'pandas', 'numpy', 'git'
}

NEGATIVE_ML_SKILLS = {
    'image classification', 'object detection', 'speech recognition', 'tts', 
    'gans', 'computer vision', 'robotics'
}

IRRELEVANT_SKILLS = {
    'tailwind', 'react', 'photoshop', 'figma', 'excel', 'tally', 'salesforce', 
    'html', 'css', 'javascript', 'typescript', 'node.js', 'angular', 'vue.js', 
    'content writing', 'marketing', 'project management', 'accounting', 'seo', 
    'six sigma', 'scrum', 'agile'
}

def is_honeypot(c):
    # Rule 1: Expert skill with 0 duration
    for skill in c.get('skills', []):
        if skill.get('proficiency') == 'expert' and skill.get('duration_months', 0) == 0:
            return True
            
    # Rule 2: Career job duration mismatch
    for job in c.get('career_history', []):
        start_s = job.get('start_date')
        end_s = job.get('end_date')
        dur = job.get('duration_months', 0)
        if start_s:
            try:
                start_d = datetime.strptime(start_s, "%Y-%m-%d")
                if end_s:
                    end_d = datetime.strptime(end_s, "%Y-%m-%d")
                    calc_dur = (end_d.year - start_d.year) * 12 + (end_d.month - start_d.month)
                else:
                    calc_dur = (CURRENT_DATE.year - start_d.year) * 12 + (CURRENT_DATE.month - start_d.month)
                
                if abs(calc_dur - dur) > 2:
                    return True
            except Exception:
                pass

    # Rule 3: Company founding year violation
    for job in c.get('career_history', []):
        comp = job.get('company', '').lower()
        start_s = job.get('start_date')
        if start_s:
            try:
                start_year = int(start_s.split('-')[0])
                for name, year in COMPANY_FOUNDING_YEARS.items():
                    if name in comp and start_year < year:
                        return True
            except Exception:
                pass
                
    return False

def is_consulting_only(c):
    career = c.get('career_history', [])
    if not career:
        return True
    
    all_consulting = True
    for job in career:
        comp = job.get('company', '').lower()
        is_consulting_job = False
        for firm in CONSULTING_FIRMS:
            if firm in comp:
                is_consulting_job = True
                break
        if not is_consulting_job:
            all_consulting = False
            break
            
    return all_consulting

def is_academic_only(c):
    # Check if candidate has only worked in academic/research positions
    career = c.get('career_history', [])
    if not career:
        return True
    
    academic_keywords = {'researcher', 'fellow', 'postdoc', 'research assistant', 'phd student', 'ph.d student', 'academic'}
    all_academic = True
    for job in career:
        title = job.get('title', '').lower()
        is_academic_job = False
        for kw in academic_keywords:
            if kw in title:
                is_academic_job = True
                break
        if not is_academic_job:
            all_academic = False
            break
    return all_academic

def is_non_technical_profile(c):
    # Check if current title is completely non-technical
    title = c.get('profile', {}).get('current_title', '').lower()
    non_tech_titles = {'marketing manager', 'hr manager', 'accountant', 'graphic designer', 'sales executive', 'operations manager', 'customer support'}
    if title in non_tech_titles:
        # Check if they have past ML engineering jobs
        has_ml_history = False
        for job in c.get('career_history', []):
            jtitle = job.get('title', '').lower()
            if any(term in jtitle for term in ['engineer', 'developer', 'scientist', 'ml', 'ai']):
                has_ml_history = True
                break
        if not has_ml_history:
            return True
    return False

def calculate_relevance_scores(c):
    # 1. Experience score: Target 5-9 years
    yoe = c.get('profile', {}).get('years_of_experience', 0)
    if 5.0 <= yoe <= 9.0:
        exp_score = 1.0
    elif 4.0 <= yoe < 5.0:
        exp_score = 0.8
    elif 9.0 < yoe <= 11.0:
        exp_score = 0.8
    elif 3.0 <= yoe < 4.0:
        exp_score = 0.5
    elif 11.0 < yoe <= 13.0:
        exp_score = 0.5
    else:
        exp_score = 0.1

    # 2. Role Score (based on current and past titles)
    curr_title = c.get('profile', {}).get('current_title', '').lower()
    role_score = 0.0
    
    # Check current title
    if any(term in curr_title for term in ['ai engineer', 'ml engineer', 'machine learning engineer', 'nlp engineer', 'search engineer', 'retrieval engineer']):
        role_score = 1.0
    elif 'data scientist' in curr_title or 'data engineer' in curr_title:
        role_score = 0.7
    elif any(term in curr_title for term in ['backend', 'software', 'developer', 'systems engineer']):
        role_score = 0.5
        # If their career history shows they built search/recommender/NLP, bump it up
        for job in c.get('career_history', []):
            desc = job.get('description', '').lower()
            if any(term in desc for term in ['recommend', 'retrieval', 'search', 'vector database', 'embeddings']):
                role_score = 0.8
                break
    else:
        role_score = 0.1

    # Apply penalty if they hold a "lead" or "architect" title and haven't written code
    # (JD: "Senior engineer who hasn't written production code in the last 18 months")
    if 'architect' in curr_title or 'manager' in curr_title or 'lead' in curr_title:
        # Check if the job description mentions hands-on coding or implementation
        curr_desc = c.get('career_history', [{}])[0].get('description', '').lower()
        if not any(term in curr_desc for term in ['code', 'implement', 'build', 'write', 'develop', 'python', 'ship']):
            role_score *= 0.5

    # 3. Skill Fit Score
    skills = c.get('skills', [])
    skill_score = 0.0
    core_count = 0
    neg_count = 0
    
    prof_mults = {'beginner': 0.5, 'intermediate': 1.0, 'advanced': 1.5, 'expert': 2.0}
    
    for s in skills:
        name = s.get('name', '').lower()
        prof = s.get('proficiency', 'intermediate')
        dur = s.get('duration_months', 0) / 12.0
        ends = s.get('endorsements', 0)
        
        mult = prof_mults.get(prof, 1.0)
        dur_weight = 1.0 + min(dur / 5.0, 2.0) # Cap duration weight to prevent massive outliers
        ends_weight = 1.0 + min(ends / 20.0, 1.5)
        
        if name in CORE_AI_SKILLS:
            skill_score += 3.0 * mult * dur_weight * ends_weight
            core_count += 1
        elif name in GENERAL_ML_SKILLS:
            skill_score += 1.0 * mult * dur_weight * ends_weight
        elif name in NEGATIVE_ML_SKILLS:
            neg_count += 1
            skill_score += 0.2 * mult * dur_weight * ends_weight
            
    # Apply CV/Speech penalty if they only have those and no Core AI NLP/IR skills
    if core_count == 0 and neg_count > 0:
        skill_score *= 0.2
        
    # Normalize skill score to a 0-1 scale (arbitrary max pool of 40)
    norm_skill_score = min(skill_score / 40.0, 1.0)

    # 4. Behavioral Signals Modifier
    behav = c.get('redrob_signals', {})
    behav_mult = 1.0
    
    # Recency of activity
    last_act_s = behav.get('last_active_date')
    if last_act_s:
        try:
            last_act_d = datetime.strptime(last_act_s, "%Y-%m-%d")
            days_inactive = (CURRENT_DATE - last_act_d).days
            if days_inactive <= 30:
                behav_mult *= 1.2
            elif days_inactive <= 90:
                behav_mult *= 1.0
            elif days_inactive <= 180:
                behav_mult *= 0.6
            else:
                # Disqualifying inactive: "last active date > 6 months... down-weight them"
                behav_mult *= 0.1
        except Exception:
            behav_mult *= 0.5
            
    # Recruiter response rate
    rr = behav.get('recruiter_response_rate', 0.0)
    if rr >= 0.70:
        behav_mult *= 1.2
    elif rr >= 0.40:
        behav_mult *= 1.0
    elif rr < 0.10:
        # Inactive response rate: "has a 5% response rate... down-weight them"
        behav_mult *= 0.15
    else:
        behav_mult *= (0.2 + (rr - 0.10) * 8/3) # Linear interpolation from 0.2 to 1.0

    # Open to work flag
    if behav.get('open_to_work_flag', False):
        behav_mult *= 1.15
    else:
        behav_mult *= 0.90
        
    # Notice period
    notice = behav.get('notice_period_days', 60)
    if notice <= 30:
        behav_mult *= 1.25
    elif notice <= 60:
        behav_mult *= 1.0
    elif notice <= 90:
        behav_mult *= 0.75
    else:
        # Long notice period penalty
        behav_mult *= 0.40

    # Location & Relocation
    loc = c.get('profile', {}).get('location', '').lower()
    country = c.get('profile', {}).get('country', '').lower()
    relocate = behav.get('willing_to_relocate', False)
    
    if country != 'india' and country != 'in':
        # Relocation from outside India is not sponsored
        behav_mult *= 0.05
    else:
        is_pune_noida = 'pune' in loc or 'noida' in loc
        is_tier_1 = any(city in loc for city in TIER_1_INDIAN_CITIES)
        
        if is_pune_noida:
            behav_mult *= 1.25
        elif is_tier_1 and relocate:
            behav_mult *= 1.0
        elif is_tier_1 and not relocate:
            behav_mult *= 0.40
        else:
            behav_mult *= 0.20 # Rural or not willing to relocate

    # Calculate final composite score
    base_score = (role_score * 0.4 + exp_score * 0.3 + norm_skill_score * 0.3)
    final_score = base_score * behav_mult
    
    # Cap final score between 0.0 and 1.0
    final_score = max(0.0, min(1.0, final_score))
    
    return final_score

def generate_reasoning(c, rank):
    # Extract facts from profile
    name = c['profile']['anonymized_name']
    title = c['profile']['current_title']
    company = c['profile']['current_company']
    yoe = c['profile']['years_of_experience']
    loc = c['profile']['location']
    
    # Top skills matching core AI
    skills = [s['name'] for s in c.get('skills', []) if s['name'].lower() in CORE_AI_SKILLS]
    if not skills:
        skills = [s['name'] for s in c.get('skills', []) if s['name'].lower() in GENERAL_ML_SKILLS]
    top_skills = ", ".join(skills[:3])
    
    notice = c['redrob_signals']['notice_period_days']
    rr = c['redrob_signals']['recruiter_response_rate']
    relocate = c['redrob_signals']['willing_to_relocate']
    
    # Format current company type and location details
    loc_phrase = f"based in {loc}"
    if 'pune' in loc.lower() or 'noida' in loc.lower():
        loc_phrase += " (no relocation needed)"
    elif relocate:
        loc_phrase += " (willing to relocate to Pune/Noida)"
        
    notice_phrase = f"a short {notice}-day notice period" if notice <= 30 else f"a {notice}-day notice period"
    
    # Detect potential concerns
    concerns = []
    if notice >= 90:
        concerns.append(f"a longer {notice}-day notice period")
    if rr < 0.30:
        concerns.append(f"lower platform activity (response rate: {rr:.0%})")
    if 'pune' not in loc.lower() and 'noida' not in loc.lower() and not relocate:
        concerns.append(f"location constraint in {loc}")
        
    concern_text = ""
    if concerns:
        concern_text = "; minor concern is " + " and ".join(concerns)
        
    # Generate rank-based templates to ensure variation
    if rank <= 10:
        templates = [
            f"Exceptional Senior AI Engineer with {yoe:.1f} years of experience, currently working at {company} as a {title}. Expert in {top_skills}, {loc_phrase} with {notice_phrase}{concern_text}.",
            f"Top-tier ML candidate offering {yoe:.1f} years of expertise, including shipping systems at {company}. Strong technical fit with {top_skills}; {loc_phrase} and active on the platform{concern_text}.",
            f"Prime match for the founding team with {yoe:.1f} years of experience in product environments. Demonstrates hands-on proficiency in {top_skills}; {loc_phrase} ({notice_phrase}){concern_text}."
        ]
    elif rank <= 50:
        templates = [
            f"Strong technical candidate with {yoe:.1f} years of experience, currently working as a {title} at {company}. Solid experience in {top_skills}, {loc_phrase} and has {notice_phrase}{concern_text}.",
            f"Product-focused engineer with {yoe:.1f} years of applied ML experience at {company}. Relevant skill set including {top_skills}; {loc_phrase} ({notice_phrase}){concern_text}.",
            f"Experienced {title} with {yoe:.1f} years of history. Proven work in {top_skills} at {company}; fits Pune/Noida location requirements ({notice_phrase}){concern_text}."
        ]
    else:
        templates = [
            f"Competent engineer with {yoe:.1f} years of experience, currently a {title} at {company}. Demonstrates background in {top_skills}; {loc_phrase} ({notice_phrase}){concern_text}.",
            f"Solid ML/software professional with {yoe:.1f} years of experience. Experienced in {top_skills}; candidate is {loc_phrase} with {notice_phrase}{concern_text}.",
            f"Good fit for the technical role with {yoe:.1f} years in the field. Background includes working with {top_skills} at {company}; active profile ({notice_phrase}){concern_text}."
        ]
        
    # Select template based on candidate ID to ensure deterministic variation
    idx = int(c['candidate_id'].split('_')[1]) % len(templates)
    return templates[idx]

def main():
    parser = argparse.ArgumentParser(description="Rank candidates for the Redrob Senior AI Engineer role.")
    parser.add_argument("--candidates", required=True, help="Path to candidates.jsonl file.")
    parser.add_argument("--out", required=True, help="Path to write the output CSV.")
    args = parser.parse_args()
    
    print(f"Reading candidates from {args.candidates}...")
    candidates = []
    
    with open(args.candidates, "r", encoding="utf-8") as f:
        for line in tqdm(f, desc="Ingesting profiles"):
            if not line.strip():
                continue
            try:
                c = json.loads(line)
                candidates.append(c)
            except Exception as e:
                print(f"Error parsing line: {e}")
                
    print(f"Loaded {len(candidates)} candidates. Filtering and scoring...")
    
    scored_candidates = []
    
    # Process line-by-line
    for c in tqdm(candidates, desc="Scoring"):
        cid = c['candidate_id']
        
        # 1. Filter out honeypots (impossible dates/expert skills)
        if is_honeypot(c):
            continue
            
        # 2. Filter out consulting-only career histories
        if is_consulting_only(c):
            continue
            
        # 3. Filter out academic-only profiles
        if is_academic_only(c):
            continue
            
        # 4. Filter out completely non-technical profiles
        if is_non_technical_profile(c):
            continue
            
        # 5. Calculate score
        score = calculate_relevance_scores(c)
        
        if score > 0.05: # ignore extremely low matches
            scored_candidates.append((score, cid, c))
            
    print(f"Scored {len(scored_candidates)} candidates. Sorting and selecting top 100...")
    
    # Sort: Descending by score, then ascending by candidate_id to break ties deterministically
    scored_candidates.sort(key=lambda x: (-x[0], x[1]))
    
    top_100 = scored_candidates[:100]
    
    # Generate output rows
    output_rows = []
    for rank, (score, cid, c) in enumerate(top_100, 1):
        reasoning = generate_reasoning(c, rank)
        output_rows.append({
            "candidate_id": cid,
            "rank": rank,
            "score": round(score, 4),
            "reasoning": reasoning
        })
        
    print(f"Writing top 100 to {args.out}...")
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["candidate_id", "rank", "score", "reasoning"])
        writer.writeheader()
        writer.writerows(output_rows)
        
    print("Done! Ranking complete.")

if __name__ == "__main__":
    main()
