import argparse
import os
import json
from pathlib import Path
from typing import Dict, List, Optional
import textract
from openai import OpenAI
from dotenv import load_dotenv
import logging
from datetime import datetime
from dateutil import parser
import re
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
import random

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Constants for chunking
INITIAL_CHUNK_SIZE = 800  # Reduced for reliability
SUBCHUNK_SIZE = 400  # Reduced for reliability
MAX_RETRIES = 3
API_TIMEOUT = 20  # Increased for reliability
SECTION_TIMEOUT = 240  # Increased for large files
BACKOFF_FACTOR = 2.0
MAX_REQUESTS_PER_MINUTE = 20
REQUEST_INTERVAL = 3.0  # Minimum seconds between requests
JITTER_MAX = 2.0  # Up to 2 seconds random jitter

# Rate limiting
last_request_time = 0

def extract_text(file_path: str) -> str:
    """
    Extract text from a document using textract.
    
    Args:
        file_path: Path to the document file
        
    Returns:
        Extracted text as string
    """
    try:
        return textract.process(file_path).decode("utf-8", errors="ignore")
    except Exception as e:
        logger.error(f"Error extracting text from {file_path}: {str(e)}")
        return ""

def extract_grants_sections(text: str) -> list:
    """
    Extract all grant-related sections from the CV text, from each grant header to the next all-caps section or end of document.
    Returns a list of section strings.
    """
    patterns = [
        r'EXTERNAL GRANTS & CONTRACTS[:\n]',
        r'INTERNAL GRANTS & CONTRACTS[:\n]',
        r'CAREER DEVELOPMENT AWARD MENTORSHIP[:\n]',
        r'GRANT SUPPORT[:\n]',
        r'GRANTS[:\n]',
        r'GRANT FUNDING[:\n]',
        r'RESEARCH SUPPORT[:\n]',
        r'RESEARCH FUNDING[:\n]',
        r'CURRENT AND PAST GRANT SUPPORT[:\n]',
        r'FUNDING[:\n]',
        r'EXTRAMURAL FUNDING[:\n]',
        r'ACTIVE GRANTS[:\n]',
        r'CURRENT GRANTS[:\n]',
        r'PENDING GRANTS[:\n]',
        r'PAST GRANTS[:\n]',
        r'COMPLETED[:\n]',
        r'FUNDED GRANTS[:\n]',
        r'GRANT AWARDS[:\n]',
        r'RESEARCH GRANTS[:\n]',
        r'FEDERAL GRANTS[:\n]',
        r'NON-FEDERAL GRANTS[:\n]',
        r'INDUSTRY GRANTS[:\n]',
        r'FOUNDATION GRANTS[:\n]'
    ]
    sections = []
    for pat in patterns:
        for match in re.finditer(pat, text, re.IGNORECASE):
            start = match.end()
            # Find the next all-caps section header or end of text
            end_match = re.search(r'\n[A-Z][A-Z\s]{3,}[:\n]', text[start:])
            end = start + end_match.start() if end_match else len(text)
            section = text[start:end].strip()
            if section:
                sections.append(section)
    return sections if sections else [text]

def chunk_text(text: str, max_length: int = 9000) -> list:
    """Split text into chunks of max_length, trying to split at paragraph boundaries."""
    if len(text) <= max_length:
        return [text]
    paras = text.split('\n\n')
    chunks = []
    current = ''
    for para in paras:
        if len(current) + len(para) + 2 > max_length:
            if current:
                chunks.append(current)
            current = para
        else:
            current += ('\n\n' if current else '') + para
    if current:
        chunks.append(current)
    return chunks

def build_prompt(text: str, grants_text: str = None, mode: str = 'all') -> str:
    """Build a prompt for the LLM to extract structured information from the CV."""
    if mode == 'general':
        return f"""Extract the following general information from this academic CV. Return the information in JSON format:
1. Full name (including any titles like PhD, MD)
2. Degrees (list of objects with degree, year, and institution)
3. Current role/title
4. Division
5. Department
6. School
7. University

Return the data in this JSON format:
{{
    \"full_name\": \"string\",
    \"degrees\": [{{\"degree\": \"string\", \"year\": \"string\", \"institution\": \"string\"}}],
    \"current_role\": \"string\",
    \"division\": \"string\",
    \"department\": \"string\",
    \"school\": \"string\",
    \"university\": \"string\"
}}\n\nCV text:\n{text[:12000]}"""
    elif mode == 'grants':
        return f"""Extract all grant information from the following section of an academic CV. Return a JSON array of grant objects, each with:
- title
- grant_number (look for numbers like R01, K01, etc.)
- principal_investigator(s)
- role (PI, Co-I, etc.)
- period_funding (object with start_date and end_date)
- total_cost (look for amounts with $ or numbers)
- direct_cost (if available)
- agency (NIH, NSF, etc.)
- status (Active, Pending, etc.)
- grant_type (R01, K01, etc.)
- is_diabetes_related (boolean)
- related_to (list of keywords if diabetes-related)

Extract every grant listed, even if the list is long or in a table. Return only the grants array, not general info.

Section text:\n{grants_text[:12000]}"""
    else:
        # fallback to previous behavior
        return f"""Extract structured information from this academic CV. The CV text is:\n\n{text}\n\nFor grant information, specifically look at this section:\n\n{grants_text}\n\nExtract the following information in JSON format:\n1. Full name (including any titles like PhD, MD)\n2. Degrees (list of objects with degree, year, and institution)\n3. Current role/title\n4. Division\n5. Department\n6. School\n7. University\n8. Grants (list of objects with):\n   - title\n   - grant_number (look for numbers like R01, K01, etc.)\n   - principal_investigator(s)\n   - role (PI, Co-I, etc.)\n   - period_funding (object with start_date and end_date)\n   - total_cost (look for amounts with $ or numbers)\n   - direct_cost (if available)\n   - agency (NIH, NSF, etc.)\n   - status (Active, Pending, etc.)\n   - grant_type (R01, K01, etc.)\n   - is_diabetes_related (boolean)\n   - related_to (list of keywords if diabetes-related)\n\nFor grants, look for:\n- Grant numbers in formats like R01, K01, P30, etc.\n- Funding periods in formats like \"2020-2025\" or \"2020 to 2025\"\n- Amounts in formats like \"$1,234,567\" or \"1.2M\"\n- Agency names like NIH, NSF, CDC, etc.\n- Grant types in the grant number or description\n- Diabetes-related keywords in title or description\n- Extract every grant listed, even if the list is long or in a table.\n\nReturn the data in this JSON format:\n{{\n    \"full_name\": \"string\",\n    \"degrees\": [\n        {{\n            \"degree\": \"string\",\n            \"year\": \"string\",\n            \"institution\": \"string\"\n        }}\n    ],\n    \"current_role\": \"string\",\n    \"division\": \"string\",\n    \"department\": \"string\",\n    \"school\": \"string\",\n    \"university\": \"string\",\n    \"grants\": [\n        {{\n            \"title\": \"string\",\n            \"grant_number\": \"string\",\n            \"principal_investigator\": \"string\",\n            \"role\": \"string\",\n            \"period_funding\": {{\n                \"start_date\": \"string\",\n                \"end_date\": \"string\"\n            }},\n            \"total_cost\": \"string\",\n            \"direct_cost\": \"string\",\n            \"agency\": \"string\",\n            \"status\": \"string\",\n            \"grant_type\": \"string\",\n            \"is_diabetes_related\": boolean,\n            \"related_to\": [\"string\"]\n        }}\n    ]\n}}"""

async def rate_limit():
    """Ensure we don't exceed rate limits, with random jitter."""
    global last_request_time
    current_time = time.time()
    time_since_last = current_time - last_request_time
    jitter = random.uniform(0, JITTER_MAX)
    wait_time = max(REQUEST_INTERVAL - time_since_last, 0) + jitter
    if wait_time > 0:
        await asyncio.sleep(wait_time)
    last_request_time = time.time()

async def process_chunk(chunk: str, chunk_idx: int, total_chunks: int, max_retries: int = MAX_RETRIES, subchunk: bool = False, depth: int = 0) -> List[dict]:
    """Process a single chunk of text asynchronously with retries and dynamic splitting."""
    if depth > 2:  # Prevent infinite recursion
        logger.error(f"Maximum recursion depth reached for chunk {chunk_idx}. Skipping.")
        return []
        
    label = f"sub-chunk {chunk_idx}" if subchunk else f"chunk {chunk_idx}/{total_chunks}"
    logger.info(f"\n{'-'*40}")
    logger.info(f"Processing {label} (depth {depth})")
    logger.info(f"Chunk size: {len(chunk)} characters")
    
    # Show first few lines of the chunk
    chunk_preview = chunk.split('\n')[:3]
    logger.info("Chunk preview:")
    for line in chunk_preview:
        logger.info(f"  {line}")
    
    prompt = build_prompt('', chunk, mode='grants')
    
    for attempt in range(max_retries + 1):
        try:
            # Calculate backoff time
            backoff_time = (BACKOFF_FACTOR ** attempt) - 1
            if attempt > 0:
                logger.info(f"Waiting {backoff_time:.1f} seconds before retry...")
                await asyncio.sleep(backoff_time)
            
            # Rate limit requests
            await rate_limit()
            
            logger.info(f"Making API call for {label} (attempt {attempt + 1}/{max_retries + 1})...")
            start_time = time.time()
            
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.chat.completions.create,
                    model="gpt-4-turbo-preview",
                    messages=[
                        {"role": "system", "content": "You are an expert at extracting structured information from academic CVs. Extract the information exactly as requested in the prompt."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    response_format={"type": "json_object"}
                ),
                timeout=API_TIMEOUT
            )
            
            elapsed_time = time.time() - start_time
            logger.info(f"API call completed in {elapsed_time:.2f} seconds")
            
            grants = json.loads(response.choices[0].message.content)
            if isinstance(grants, dict) and 'grants' in grants:
                grants = grants['grants']
            if isinstance(grants, list):
                logger.info(f"\nExtracted {len(grants)} grants from {label}")
                if grants:
                    logger.info("Grant titles found:")
                    for i, grant in enumerate(grants, 1):
                        title = grant.get('title', 'No title')
                        logger.info(f"  {i}. {title}")
                return grants
                
        except asyncio.TimeoutError:
            logger.error(f"API call timed out after {API_TIMEOUT} seconds for {label} (attempt {attempt + 1})")
            if attempt < max_retries:
                logger.info(f"Retrying {label}...")
                continue
        except Exception as e:
            logger.error(f"Error processing {label} (attempt {attempt + 1}): {str(e)}")
            logger.error(f"Error type: {type(e).__name__}")
            # Log full API error if available
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"API Response: {e.response}")
            if hasattr(e, 'body') and e.body is not None:
                logger.error(f"API Error Body: {e.body}")
            if attempt < max_retries:
                logger.info(f"Retrying {label}...")
                continue
    
    # If chunk fails after all retries, split and retry as sub-chunks
    if len(chunk) > SUBCHUNK_SIZE:
        logger.warning(f"{label} failed after {max_retries + 1} attempts. Splitting into sub-chunks of {SUBCHUNK_SIZE} characters.")
        subchunks = chunk_text(chunk, max_length=SUBCHUNK_SIZE)
        logger.info(f"Split into {len(subchunks)} sub-chunks")
        
        all_grants = []
        for i, sub in enumerate(subchunks):
            grants = await process_chunk(sub, i+1, len(subchunks), max_retries=max_retries, subchunk=True, depth=depth+1)
            all_grants.extend(grants)
        return all_grants
    
    logger.error(f"Failed to process {label} after {max_retries + 1} attempts. Skipping this chunk.")
    logger.error(f"Skipped chunk content (first 200 chars): {chunk[:200]}")
    return []

async def analyze_cv(file_path: str) -> dict:
    """Analyze a CV file and return structured information."""
    try:
        logger.info(f"\n{'='*80}\nStarting analysis of {file_path}\n{'='*80}")
        
        # Extract text from the file
        logger.info("Step 1: Extracting text from file...")
        text = extract_text(file_path)
        if not text:
            logger.error(f"Could not extract text from {file_path}")
            return {}
        logger.info(f"Successfully extracted {len(text)} characters of text")

        # Extract grants sections first
        logger.info("\nStep 2: Extracting grants sections...")
        grants_sections = extract_grants_sections(text)
        logger.info(f"Found {len(grants_sections)} grant section(s)")
        
        # Process all chunks from all sections concurrently
        all_grants = []
        section_results = []
        
        for section_idx, grants_text in enumerate(grants_sections, 1):
            logger.info(f"\n{'='*40}")
            logger.info(f"Processing grant section {section_idx}/{len(grants_sections)}")
            logger.info(f"{'='*40}")
            
            # Show first few lines of the section
            preview_lines = grants_text.split('\n')[:5]
            logger.info("Section preview:")
            for line in preview_lines:
                logger.info(f"  {line}")
            
            # Start with smaller chunks
            chunks = chunk_text(grants_text, max_length=INITIAL_CHUNK_SIZE)
            logger.info(f"\nSplit section into {len(chunks)} chunk(s)")
            
            # Process chunks concurrently with timeout
            try:
                # Process chunks in smaller batches to avoid overwhelming the API
                batch_size = 2  # Reduced from 3
                for i in range(0, len(chunks), batch_size):
                    batch = chunks[i:i + batch_size]
                    logger.info(f"\nProcessing batch {i//batch_size + 1}/{(len(chunks) + batch_size - 1)//batch_size}")
                    
                    # Process chunks sequentially within each batch to respect rate limits
                    batch_grants = []
                    for j, chunk in enumerate(batch):
                        grants = await process_chunk(chunk, j+1, len(batch))
                        if grants:
                            batch_grants.extend(grants)
                            logger.info(f"Added {len(grants)} grants from chunk {i+j+1}")
                    
                    all_grants.extend(batch_grants)
                    logger.info(f"Total grants found so far: {len(all_grants)}")
                    
                    # Add a delay between batches
                    if i + batch_size < len(chunks):
                        await asyncio.sleep(REQUEST_INTERVAL)
                
                logger.info(f"Completed section {section_idx}/{len(grants_sections)}")
                logger.info(f"Total grants found so far: {len(all_grants)}")
                
            except asyncio.TimeoutError:
                logger.error(f"Section {section_idx} processing timed out after {SECTION_TIMEOUT} seconds")
                # Save partial results
                section_results.append({
                    'section_idx': section_idx,
                    'grants': all_grants[-len(chunks):] if all_grants else []
                })
            except Exception as e:
                logger.error(f"Error processing section {section_idx}: {str(e)}")
                # Save partial results
                section_results.append({
                    'section_idx': section_idx,
                    'grants': all_grants[-len(chunks):] if all_grants else []
                })

        # Extract general info from the full CV
        logger.info("\nStep 3: Extracting general information...")
        try:
            # Rate limit the general info request
            await rate_limit()
            
            prompt = build_prompt(text, mode='general')
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.chat.completions.create,
                    model="gpt-4-turbo-preview",
                    messages=[
                        {"role": "system", "content": "You are an expert at extracting structured information from academic CVs. Extract the information exactly as requested in the prompt."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    response_format={"type": "json_object"}
                ),
                timeout=API_TIMEOUT
            )
            
            general_info = json.loads(response.choices[0].message.content)
            logger.info("Successfully extracted general information:")
            logger.info(f"  Name: {general_info.get('full_name', 'Not found')}")
            logger.info(f"  Role: {general_info.get('current_role', 'Not found')}")
            logger.info(f"  Department: {general_info.get('department', 'Not found')}")
        except asyncio.TimeoutError:
            logger.error(f"General info extraction timed out after {API_TIMEOUT} seconds")
            general_info = {}
        except Exception as e:
            logger.error(f"Failed to extract general info: {str(e)}")
            general_info = {}

        # Merge and normalize
        logger.info("\nStep 4: Normalizing and merging results...")
        result = normalize_result({**general_info, 'grants': all_grants})
        
        # Log summary
        logger.info(f"\n{'='*80}")
        logger.info("Analysis Summary:")
        logger.info(f"  Total grants found: {len(result.get('grants', []))}")
        logger.info(f"  Diabetes-related grants: {len([g for g in result.get('grants', []) if g.get('is_diabetes_related', False)])}")
        
        # Show all grant titles in final result
        if result.get('grants'):
            logger.info("\nAll grants found:")
            for i, grant in enumerate(result['grants'], 1):
                title = grant.get('title', 'No title')
                logger.info(f"  {i}. {title}")
        
        logger.info(f"{'='*80}\n")
        
        return result
    except Exception as e:
        logger.error(f"Error analyzing CV {file_path}: {str(e)}")
        return {}

def process_cv_directory(directory_path: str, output_dir: str) -> None:
    """
    Process all CV files in a directory and save results.
    
    Args:
        directory_path: Path to directory containing CV files
        output_dir: Path to save output JSON files
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Get list of supported file extensions
    supported_extensions = {'.pdf', '.doc', '.docx', '.txt'}
    
    # Process each file in the directory
    for file_path in Path(directory_path).glob('**/*'):
        if file_path.suffix.lower() in supported_extensions:
            logger.info(f"Processing {file_path}")
            
            # Generate output filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = Path(output_dir) / f"{file_path.stem}_analysis_{timestamp}.json"
            
            # Analyze CV
            result = asyncio.run(analyze_cv(str(file_path)))
            
            if result:
                # Save results to JSON file
                with open(output_file, 'w') as f:
                    json.dump(result, f, indent=2)
                logger.info(f"Results saved to {output_file}")
            else:
                logger.error(f"Failed to analyze {file_path}")

def parse_date(date_str):
    """Parse a date string into a sortable tuple (YYYY, MM, DD). Returns (0,0,0) if not parseable."""
    try:
        dt = parser.parse(date_str)
        return (dt.year, dt.month, dt.day)
    except Exception:
        return (0, 0, 0)

def normalize_grant_keys(grant):
    """Normalize grant dictionary keys to expected format (lowercase, underscores). Handles all observed variants."""
    key_map = {
        'Title': 'title',
        'title': 'title',
        'Principal Investigator': 'principal_investigator',
        'Principal Investigators': 'principal_investigator',
        'principal_investigator': 'principal_investigator',
        'principal_investigators': 'principal_investigator',
        'Role': 'role',
        'role': 'role',
        'Start Date': 'start_date',
        'start_date': 'start_date',
        'End Date': 'end_date',
        'end_date': 'end_date',
        'Period Funding': 'period_funding',
        'period_funding': 'period_funding',
        'Period': 'period_funding',
        'period': 'period_funding',
        'Total Cost': 'total_cost',
        'total_cost': 'total_cost',
        'Total Amount': 'total_cost',
        'total_amount': 'total_cost',
        'Agency': 'agency',
        'agency': 'agency',
        'Status': 'status',
        'status': 'status',
        'Related to Diabetes/Obesity/Metabolic Disorders/CDTR': 'is_diabetes_related',
        'related_to_diabetes_obesity_or_metabolic_disorders': 'is_diabetes_related',
        'is_diabetes_related': 'is_diabetes_related',
        'Related to': 'related_to',
        'related_to': 'related_to',
    }
    norm = {}
    for k, v in grant.items():
        key = key_map.get(k, k).lower().replace(' ', '_')
        norm[key] = v
    # If period/period_funding is a dict, ensure it has start_date and end_date
    pf = norm.get('period_funding', {})
    if isinstance(pf, dict):
        norm['period_funding'] = {
            'start_date': pf.get('start_date', '') or norm.get('start_date', ''),
            'end_date': pf.get('end_date', '') or norm.get('end_date', '')
        }
    elif 'start_date' in norm or 'end_date' in norm:
        norm['period_funding'] = {
            'start_date': norm.get('start_date', ''),
            'end_date': norm.get('end_date', '')
        }
    # Normalize diabetes-related field to boolean
    if 'is_diabetes_related' in norm:
        val = norm['is_diabetes_related']
        if isinstance(val, str):
            norm['is_diabetes_related'] = val.lower() == 'true'
        elif isinstance(val, (int, float)):
            norm['is_diabetes_related'] = bool(val)
    return norm

def normalize_general_info(result: dict) -> dict:
    """Normalize general info keys to expected format and handle variants. Validate plausibility. Map school_and_university to school/university if those are blank."""
    key_map = {
        'Full name': 'full_name',
        'full_name': 'full_name',
        'Name': 'full_name',
        'name': 'full_name',
        'Degrees': 'degrees',
        'degrees': 'degrees',
        'Degree': 'degrees',
        'degree': 'degrees',
        'Current role/title': 'current_role',
        'current_role': 'current_role',
        'Current Role': 'current_role',
        'Rank/Title': 'current_role',
        'rank/title': 'current_role',
        'Division': 'division',
        'division': 'division',
        'Department': 'department',
        'department': 'department',
        'School': 'school',
        'school': 'school',
        'School and university': 'school_and_university',
        'school_and_university': 'school_and_university',
        'University': 'university',
        'university': 'university',
        'Business Address': '', # ignore
        'Citizenship': '', # ignore
        'Foreign Languages': '', # ignore
        'Home Address': '', # ignore
        'Phone': '', # ignore
        'Email': '', # ignore
    }
    norm = {}
    for k, v in result.items():
        key = key_map.get(k, k).lower().replace(' ', '_')
        if key and key not in ['business_address', 'citizenship', 'foreign_languages', 'home_address', 'phone', 'email']:
            norm[key] = v
    # Ensure all expected fields are present
    for field in ['full_name', 'degrees', 'current_role', 'division', 'department', 'school', 'university']:
        if field not in norm:
            norm[field] = '' if field != 'degrees' else []
    # If school_and_university is present and school or university are blank, use it for both
    sau = norm.get('school_and_university', '')
    if sau:
        if not norm.get('school'):
            norm['school'] = sau
        if not norm.get('university'):
            norm['university'] = sau
    # Validate plausibility: name should not be 'U.S.' or similar
    if norm['full_name'].strip().upper() in ['U.S.', 'US', 'UNITED STATES', 'CITIZENSHIP']:
        norm['full_name'] = ''
    return norm

def write_txt_output(result: dict, txt_path: str):
    """Write a human-readable summary of the extracted data to a .txt file, with a diabetes-related grants section first."""
    logger.info(f"\nWriting output to {txt_path}...")
    lines = []
    # Handle degrees as list of strings or list of dicts
    degrees = result.get('degrees', [])
    formatted_degrees = []
    for d in degrees:
        if isinstance(d, dict):
            deg = d.get('degree', '')
            year = str(d.get('year', ''))  # Convert year to string
            inst = d.get('institution', '')
            parts = [deg, year, inst]
            formatted_degrees.append(', '.join([p for p in parts if p]))
        else:
            formatted_degrees.append(str(d))
    lines.append(f"Name: {result.get('full_name', '')}")
    lines.append(f"Degrees: {', '.join(formatted_degrees)}")
    lines.append(f"Current Role/Title: {result.get('current_role', '')}")
    lines.append(f"Division: {result.get('division', '')}")
    lines.append(f"Department: {result.get('department', '')}")
    lines.append(f"School: {result.get('school', '')}")
    lines.append(f"University: {result.get('university', '')}")
    lines.append("")

    # Helper to extract start date for sorting
    def get_start_date(grant):
        pf = grant.get('period_funding', '')
        if isinstance(pf, dict):
            return pf.get('start_date', '')
        elif isinstance(pf, str) and '–' in pf:
            return pf.split('–')[0].strip()
        elif isinstance(pf, str):
            return pf.strip()
        return grant.get('start_date', '')

    # Helper to check if grant is diabetes-related
    def is_diabetes_related(grant):
        # Check explicit flag
        if grant.get('is_diabetes_related', False):
            return True
        
        # Check related_to list
        related_to = grant.get('related_to', [])
        if isinstance(related_to, list):
            if any('diabetes' in str(x).lower() or 'metabolic' in str(x).lower() for x in related_to):
                return True
        
        # Check grant title and description
        grant_text = ' '.join(str(v) for v in grant.values()).lower()
        diabetes_keywords = [
            'diabetes', 'diabetic', 'metabolic', 'obesity', 'obese',
            'insulin', 'glucose', 'glycemic', 'hemoglobin a1c', 'hba1c',
            'type 1', 'type 2', 't1d', 't2d', 'prediabetes', 'pre-diabetes',
            'chronic disease', 'chronic condition', 'cdtr', 'center for diabetes',
            'diabetes center', 'diabetes research', 'diabetes prevention',
            'diabetes treatment', 'diabetes management', 'diabetes care',
            'diabetes control', 'diabetes intervention', 'diabetes program',
            'diabetes initiative', 'diabetes project', 'diabetes study',
            'diabetes trial', 'diabetes clinical', 'diabetes translational',
            'diabetes translational research', 'diabetes translational science',
            'diabetes translational center', 'diabetes translational program',
            'diabetes translational initiative', 'diabetes translational project',
            'diabetes translational study', 'diabetes translational trial',
            'diabetes translational clinical', 'diabetes translational research center',
            'diabetes translational research program', 'diabetes translational research initiative',
            'diabetes translational research project', 'diabetes translational research study',
            'diabetes translational research trial', 'diabetes translational research clinical'
        ]
        return any(keyword in grant_text for keyword in diabetes_keywords)

    # Diabetes-related grants section
    grants = result.get('grants', [])
    diabetes_grants = [g for g in grants if is_diabetes_related(g)]
    diabetes_grants_sorted = sorted(
        diabetes_grants,
        key=lambda g: parse_date(get_start_date(g)),
        reverse=True
    )
    lines.append("Diabetes-related Grants:")
    if not diabetes_grants_sorted:
        lines.append("  None found.")
    else:
        for i, grant in enumerate(diabetes_grants_sorted, 1):
            lines.append(f"  {i}. Title: {grant.get('title', '')}")
            lines.append(f"     PI(s): {grant.get('principal_investigator', grant.get('principal_investigators', ''))}")
            lines.append(f"     Role: {grant.get('role', '')}")
            pf = grant.get('period_funding', '')
            if isinstance(pf, dict):
                lines.append(f"     Period Funding: {pf.get('start_date', '')} to {pf.get('end_date', '')}")
            else:
                lines.append(f"     Period Funding: {pf}")
            lines.append(f"     Total Amount: {grant.get('total_cost', grant.get('total_amount', ''))}")
            if grant.get('direct_cost'):
                lines.append(f"     Direct Cost: {grant.get('direct_cost')}")
            lines.append(f"     Agency: {grant.get('agency', '')}")
            lines.append(f"     Status: {grant.get('status', '')}")
            lines.append(f"     Type: {grant.get('grant_type', '')}")
            if grant.get('grant_number'):
                lines.append(f"     Grant Number: {grant.get('grant_number')}")
            lines.append("")
    lines.append("")

    # All grants section
    all_grants_sorted = sorted(
        grants,
        key=lambda g: parse_date(get_start_date(g)),
        reverse=True
    )
    lines.append("All Grants:")
    if not all_grants_sorted:
        lines.append("  None found.")
    else:
        for i, grant in enumerate(all_grants_sorted, 1):
            lines.append(f"  {i}. Title: {grant.get('title', '')}")
            lines.append(f"     PI(s): {grant.get('principal_investigator', grant.get('principal_investigators', ''))}")
            lines.append(f"     Role: {grant.get('role', '')}")
            pf = grant.get('period_funding', '')
            if isinstance(pf, dict):
                lines.append(f"     Period Funding: {pf.get('start_date', '')} to {pf.get('end_date', '')}")
            else:
                lines.append(f"     Period Funding: {pf}")
            lines.append(f"     Total Amount: {grant.get('total_cost', grant.get('total_amount', ''))}")
            if grant.get('direct_cost'):
                lines.append(f"     Direct Cost: {grant.get('direct_cost')}")
            lines.append(f"     Agency: {grant.get('agency', '')}")
            lines.append(f"     Status: {grant.get('status', '')}")
            lines.append(f"     Type: {grant.get('grant_type', '')}")
            if grant.get('grant_number'):
                lines.append(f"     Grant Number: {grant.get('grant_number')}")
            lines.append(f"     Diabetes/CDTR-related: {is_diabetes_related(grant)}")
            lines.append("")
    with open(txt_path, 'w') as f:
        f.write('\n'.join(lines))
    logger.info("Output file written successfully")

def main():
    parser = argparse.ArgumentParser(description="CV Parsing Utility")
    parser.add_argument('--input', type=str, help='Path to CV file or directory')
    parser.add_argument('--output', type=str, default='CV extracted data', help='Path to output directory')
    parser.add_argument('--single', action='store_true', help='Treat input as a single file')
    args = parser.parse_args()

    print("\n" + "=" * 80)
    logger.info("Starting CV Parser")
    print("=" * 80)

    test_file = "CDTR Members.CVs/L Hearld CV 2_for distribution.docx"
    input_path = args.input if args.input else test_file
    output_dir = args.output

    logger.info(f"Test file: {input_path}")
    logger.info(f"Output directory: {output_dir}")
    print("=" * 80 + "\n")

    if os.path.isdir(input_path) and not args.single:
        for file_name in os.listdir(input_path):
            file_path = os.path.join(input_path, file_name)
            try:
                result = asyncio.run(analyze_cv(file_path))
                # Write output as JSON and TXT
                base_name = os.path.splitext(os.path.basename(file_path))[0]
                json_path = os.path.join(output_dir, base_name + '.json')
                txt_path = os.path.join(output_dir, base_name + '.txt')
                os.makedirs(output_dir, exist_ok=True)
                with open(json_path, 'w') as f:
                    json.dump(result, f, indent=2)
                write_txt_output(result, txt_path)
            except Exception as e:
                logger.error(f"Failed to process {file_name}: {str(e)}")
    else:
        result = asyncio.run(analyze_cv(input_path))
        # Write output as JSON and TXT
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        json_path = os.path.join(output_dir, base_name + '.json')
        txt_path = os.path.join(output_dir, base_name + '.txt')
        os.makedirs(output_dir, exist_ok=True)
        with open(json_path, 'w') as f:
            json.dump(result, f, indent=2)
        write_txt_output(result, txt_path)

if __name__ == "__main__":
    main()