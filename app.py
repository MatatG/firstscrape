from flask import Flask, render_template, request, jsonify, Response
import anthropic
import requests
from bs4 import BeautifulSoup
import json
import time
import csv
from io import StringIO
from datetime import datetime

app = Flask(__name__)

def get_webpage_content(url):
    try:
        response = requests.get(url)
        if response.status_code == 429:
            print("Rate limited. Waiting 60 seconds...")
            time.sleep(60)
            response = requests.get(url)
        response.raise_for_status()
        return clean_html_content(response.text)
    except Exception as e:
        print(f"Error fetching webpage: {e}")
        return None

def clean_html_content(html):
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove unnecessary elements
    for element in soup(["script", "style", "head", "iframe"]):
        element.decompose()
    
    # Get main content and navigation elements
    main_content = soup.find('main') or soup.find('div', {'role': 'main'}) or soup
    nav_elements = soup.find_all(['nav', 'a'])
    
    # Extract navigation links and their text
    navigation_info = []
    for link in nav_elements:
        if link.name == 'a' and link.get('href'):
            href = link.get('href')
            text = link.get_text(strip=True)
            if text and href and not href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                navigation_info.append(f"{text}: {href}")
    
    # Get main content text
    content_text = main_content.get_text(separator=' ', strip=True)
    
    # Combine navigation and content with clear separation
    final_text = "NAVIGATION OPTIONS:\n" + "\n".join(navigation_info[:20]) + "\n\nPAGE CONTENT:\n" + content_text
    
    return final_text[:15000]  # Still maintain token limit

def analyze_with_claude(html_content, url, context=""):
    client = anthropic.Anthropic()
    
    system_prompt = """You are a focused web scraping assistant. Your goal is to find hotel room names and details.
    If you see room information on the current page, extract it. If not, suggest where to look next on the site.
    Keep responses brief and direct. Make sure to extract ALL accomadation types (rooms, suites, apartments, etc.)
    Return hotel name, room name, room type, description, size, view, bed type."""

    message = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1000,
        temperature=0,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": f"""Looking at {url}

                Should I extract room info from this page or navigate elsewhere? If navigation needed, provide the specific URL to check.
                
                Page content:
                {html_content}"""
            }
        ]
    )
    
    # Modify to return both the message and thinking process
    return {
        "analysis": message.content[0].text,
        "thinking": f"Analyzing page at {url}\nLooking for room information or navigation links..."
    }

def structure_room_data(analysis_text):
    client = anthropic.Anthropic()
    
    system_prompt = """You are a data structuring assistant. Convert the hotel room information into a CSV format with the following fields:
    hotel_name,room_name,room_type,description,size,view,bed_type
    
    If any field is not available, use 'N/A'. Keep the data clean and consistent.
    Only respond with the CSV data, no additional text."""
    
    message = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1000,
        temperature=0,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": f"""Please convert this room information into structured CSV data:
                
                {analysis_text}

                """
            }
        ]
    )
    
    # Modify to return both the structured data and thinking process
    return {
        "data": message.content[0].text,
        "thinking": "Converting unstructured room data to CSV format..."
    }

def scrape_rooms(initial_url):
    visited_urls = set()
    rooms_data = []
    urls_to_visit = [initial_url]
    logs = []
    thinking_steps = []
    structured_results = []
    
    while urls_to_visit and len(visited_urls) < 10:
        current_url = urls_to_visit.pop(0)
        
        if current_url in visited_urls:
            continue
            
        logs.append(f"Checking: {current_url}")
        visited_urls.add(current_url)
        
        html_content = get_webpage_content(current_url)
        if not html_content:
            logs.append("Failed to fetch page content")
            continue
        
        analysis_result = analyze_with_claude(html_content, current_url)
        thinking_steps.append(analysis_result["thinking"])
        logs.append(f"Analysis: {analysis_result['analysis']}")
        
        if "http" not in analysis_result["analysis"].lower():
            structure_result = structure_room_data(analysis_result["analysis"])
            thinking_steps.append(structure_result["thinking"])
            logs.append(f"Structured Data:\n{structure_result['data']}")
            structured_results.append(structure_result["data"])
        
        if "http" in analysis_result["analysis"].lower():
            new_urls = [url for url in analysis_result["analysis"].split() if url.startswith("http")]
            urls_to_visit.extend(new_urls)
        
        time.sleep(1)
    
    return {
        "logs": logs,
        "thinking": thinking_steps,
        "results": structured_results
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/scrape', methods=['POST'])
def scrape():
    url = request.json.get('url')
    if not url:
        return jsonify({"error": "URL is required"}), 400
    
    results = scrape_rooms(url)
    return jsonify(results)

@app.route('/download-csv')
def download_csv():
    # Assuming the last scrape results are stored in a global variable or session
    # You might want to implement proper storage
    results = request.args.get('data', '')
    
    si = StringIO()
    cw = csv.writer(si)
    
    # Write data rows
    for row in csv.reader(results.split('\n')):
        if row:  # Skip empty rows
            cw.writerow(row)
    
    output = si.getvalue()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename=hotel_rooms_{timestamp}.csv"}
    )

if __name__ == "__main__":
    app.run(debug=True)