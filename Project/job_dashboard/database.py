import sqlite3
import json
from datetime import datetime

DB_FILE = 'jobs.db'

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Table for Jobs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portal TEXT NOT NULL,
            title TEXT NOT NULL,
            company TEXT,
            experience_level TEXT,
            posted_age_days INTEGER,
            job_url TEXT,
            scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Table for LLM Logs to preserve proof
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS llm_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT,
            prompt TEXT,
            response TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def insert_job(portal, title, company, experience_level, posted_age_days, job_url):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO jobs (portal, title, company, experience_level, posted_age_days, job_url)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (portal, title, company, experience_level, posted_age_days, job_url))
    conn.commit()
    conn.close()

def log_llm_interaction(agent_name, prompt, response):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO llm_logs (agent_name, prompt, response)
        VALUES (?, ?, ?)
    ''', (agent_name, json.dumps(prompt), json.dumps(response)))
    conn.commit()
    conn.close()

def get_job_stats(portal=None):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = "SELECT * FROM jobs"
    params = ()
    if portal and portal.lower() != 'all':
        query += " WHERE portal = ?"
        params = (portal,)
        
    cursor.execute(query, params)
    jobs = cursor.fetchall()
    conn.close()
    
    # Calculate stats
    total_jobs = len(jobs)
    age_less_3 = sum(1 for j in jobs if j['posted_age_days'] is not None and j['posted_age_days'] < 3)
    age_3_to_7 = sum(1 for j in jobs if j['posted_age_days'] is not None and 3 <= j['posted_age_days'] <= 7)
    age_more_7 = sum(1 for j in jobs if j['posted_age_days'] is not None and j['posted_age_days'] > 7)
    
    # Collect experience levels
    experience_levels = {}
    for j in jobs:
        exp = j['experience_level']
        if not exp:
            exp = "Not Specified"
        experience_levels[exp] = experience_levels.get(exp, 0) + 1
        
    return {
        "total": total_jobs,
        "age_distribution": {
            "< 3 days": age_less_3,
            "3 - 7 days": age_3_to_7,
            "> 7 days": age_more_7
        },
        "experience_levels": experience_levels,
        "jobs": [dict(j) for j in jobs]
    }
    
if __name__ == "__main__":
    init_db()
    print("Database initialized.")
