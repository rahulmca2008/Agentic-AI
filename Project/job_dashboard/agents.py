import asyncio
from playwright.async_api import async_playwright
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
import database
import json
import os
from dotenv import load_dotenv
import re

load_dotenv()
API_KEY = os.getenv("api_key")
client = genai.Client(api_key=API_KEY)

class Job(BaseModel):
    title: str = Field(description="Job title")
    company: str = Field(description="Company name")
    experience_level: str = Field(description="Experience required, e.g., '2-5 years', 'Entry level', 'Senior'. Default to 'Not Specified' if not found.")
    posted_age_days: int = Field(description="How many days ago the job was posted. 0 if today, 30 if older. If it says '3 days ago', return 3.")
    job_url: str = Field(description="URL to the job posting")
    
class JobExtraction(BaseModel):
    jobs: list[Job]

async def scrape_portal(portal_name, search_url, container_selector):
    print(f"[{portal_name}] Starting scraping...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(search_url, wait_until="networkidle", timeout=60000)
            # Give it some time to load job cards
            await page.wait_for_timeout(5000)
            
            # Scroll down to load more
            for _ in range(3):
                await page.mouse.wheel(0, 1000)
                await page.wait_for_timeout(1000)
            
            # Extract HTML
            html_content = await page.content()
            
            # Since LLM context window might be an issue with huge HTML,
            # Let's try to extract text from the body
            # Using innerText to strip tags
            page_text = await page.evaluate('document.body.innerText')
            
            # If there's a specific container, we try to grab it
            if container_selector:
                elements = await page.query_selector_all(container_selector)
                cards_text = []
                for el in elements:
                    text = await el.inner_text()
                    cards_text.append(text)
                
                if cards_text:
                    page_text = "\\n---\\n".join(cards_text)
                    
            print(f"[{portal_name}] Extracted {len(page_text)} chars of text.")
            
        except Exception as e:
            print(f"[{portal_name}] Playwright error: {e}")
            page_text = ""
        finally:
            await browser.close()
            
    if not page_text:
        return
        
    # Process with Gemini
    prompt = f"""
    You are an expert data extraction agent. Extract all job postings for 'AI Engineer' or related AI/ML roles from the text below.
    The text is scraped from {portal_name}.
    Extract the title, company, experience level, and posted age in days (integer). If a URL is not present, use a placeholder 'N/A' or try to guess based on the portal.
    Text:
    {page_text[:100000]}
    """
    
    print(f"[{portal_name}] Sending to Gemini...")
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=JobExtraction,
                temperature=0.1
            ),
        )
        
        result_json = response.text
        # Log interaction to SQLite
        database.log_llm_interaction(portal_name, prompt, result_json)
        
        # Parse and save to DB
        data = json.loads(result_json)
        jobs = data.get('jobs', [])
        for j in jobs:
            database.insert_job(
                portal=portal_name,
                title=j.get('title', ''),
                company=j.get('company', ''),
                experience_level=j.get('experience_level', 'Not Specified'),
                posted_age_days=j.get('posted_age_days', 0),
                job_url=j.get('job_url', search_url)
            )
        print(f"[{portal_name}] Successfully saved {len(jobs)} jobs.")
    except Exception as e:
        print(f"[{portal_name}] Gemini error: {e}")

async def run_naukri():
    await scrape_portal("Naukri", "https://www.naukri.com/ai-engineer-jobs", ".srp-jobtuple-wrapper")

async def run_talent500():
    await scrape_portal("Talent500", "https://talent500.co/jobs?q=AI%20Engineer", None)

async def run_hirist():
    await scrape_portal("Hirist", "https://www.hirist.tech/search/ai-engineer", None)
    
async def run_all():
    await asyncio.gather(
        run_naukri(),
        run_talent500(),
        run_hirist()
    )

if __name__ == "__main__":
    asyncio.run(run_all())
