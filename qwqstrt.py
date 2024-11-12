import anthropic
import requests
from bs4 import BeautifulSoup
import json
import time

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
    If you see room information on the current page, extract it. Includ available information such as: hotel name, room name, room type, description, amenities, price, size, occupancy, view, bed type. If not, suggest where to look next on the site.
    Keep responses brief and direct."""

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
    
    return message.content[0].text

def structure_room_data(analysis_text):
    client = anthropic.Anthropic()
    
    system_prompt = """You are a data structuring assistant. Convert the hotel room information into a CSV format with the following fields:
    hotel_name,room_name,room_type,description,amenities,price,size,occupancy,view,bed_type
    
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
                
                {analysis_text}"""
            }
        ]
    )
    
    return message.content[0].text

def scrape_rooms(initial_url):
    visited_urls = set()
    rooms_data = []
    urls_to_visit = [initial_url]
    
    while urls_to_visit and len(visited_urls) < 10:  # Limit to 10 pages
        current_url = urls_to_visit.pop(0)
        
        if current_url in visited_urls:
            continue
            
        print(f"\nChecking: {current_url}")
        visited_urls.add(current_url)
        
        html_content = get_webpage_content(current_url)
        if not html_content:
            continue
        
        # Let Claude analyze the page
        analysis = analyze_with_claude(html_content, current_url)
        print(f"Analysis: {analysis}")
        
        # Only structure data if no URLs were found (meaning room data was extracted)
        if "http" not in analysis.lower():
            structured_data = structure_room_data(analysis)
            print(f"Structured Data:\n{structured_data}")
            # You might want to parse the CSV and append to rooms_data here
        
        # Extract URLs from Claude's response
        if "http" in analysis.lower():
            new_urls = [url for url in analysis.split() if url.startswith("http")]
            urls_to_visit.extend(new_urls)
        
        time.sleep(1)
    
    return rooms_data

def main():
    url = input("Please enter the hotel website URL: ")
    rooms = scrape_rooms(url)
    
    for room in rooms:
        print(json.dumps(room, indent=2))

if __name__ == "__main__":
    main()