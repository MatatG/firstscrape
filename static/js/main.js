// Feature detection and polyfills
const supportsEventSource = 'EventSource' in window;
const supportsTextDecoder = 'TextDecoder' in window;

if (!supportsEventSource) {
    console.error('EventSource not supported');
}

if (!supportsTextDecoder) {
    console.error('TextDecoder not supported');
}

// Global variables
let structuredData = null;

// DOM Elements
const urlInput = document.getElementById('urlInput');
const analyzeBtn = document.getElementById('analyzeBtn');
const loadingIndicator = document.querySelector('.loading');
const rawContentEl = document.getElementById('rawContent');
const analysisEl = document.getElementById('analysis');
const resultsEl = document.getElementById('results');
const downloadBtn = document.getElementById('download-btn');

// Event Listeners
analyzeBtn.addEventListener('click', scrapeUrl);
downloadBtn.addEventListener('click', downloadCSV);

// Main functions
async function scrapeUrl() {
    const url = urlInput.value;
    if (!url) return;

    try {
        // Show loading state
        setLoadingState(true);

        // Clear previous content
        clearContent();

        const response = await fetch('/stream_scrape', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ url: url })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const {done, value} = await reader.read();
            
            if (done) {
                setLoadingState(false);
                break;
            }

            const chunk = decoder.decode(value);
            processChunk(chunk);
        }
    } catch (error) {
        console.error('Error:', error);
        setLoadingState(false);
        showError('An error occurred while analyzing the URL');
    }
}

function processChunk(chunk) {
    const lines = chunk.split('\n');
    
    lines.forEach(line => {
        if (line.startsWith('data: ')) {
            try {
                const data = JSON.parse(line.slice(6));
                updateUI(data);
            } catch (e) {
                console.error('Error parsing JSON:', e);
            }
        }
    });
}

function updateUI(data) {
    if (data.error) {
        showError(data.error);
        return;
    }

    if (data.step === 'final') {
        structuredData = data.structured_data;
        downloadBtn.style.display = 'block';
        return;
    }

    // Add step indicator and URL
    resultsEl.innerHTML += `
        <div class="step-indicator">Step ${data.step}</div>
        <div class="url-display">${data.url}</div>
    `;

    // Update content panels
    if (data.raw_content) {
        rawContentEl.innerHTML = `<div class="code-text">${escapeHtml(data.raw_content)}</div>`;
    }

    if (data.analysis) {
        analysisEl.innerHTML = `<div class="code-text">${escapeHtml(data.analysis)}</div>`;
    }

    // Auto-scroll results
    resultsEl.scrollTop = resultsEl.scrollHeight;
}

async function downloadCSV() {
    if (!structuredData) return;
    
    try {
        const response = await fetch('/download_csv', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(structuredData)
        });

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'hotel_rooms.csv';
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    } catch (error) {
        console.error('Error downloading CSV:', error);
        showError('Failed to download CSV file');
    }
}

// Utility functions
function setLoadingState(isLoading) {
    loadingIndicator.style.display = isLoading ? 'flex' : 'none';
    analyzeBtn.disabled = isLoading;
}

function clearContent() {
    rawContentEl.innerHTML = '';
    analysisEl.innerHTML = '';
    resultsEl.innerHTML = '';
    downloadBtn.style.display = 'none';
}

function showError(message) {
    resultsEl.innerHTML += `
        <div class="error" style="color: red; margin: 10px 0;">
            Error: ${escapeHtml(message)}
        </div>`;
}

function escapeHtml(unsafe) {
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
} 