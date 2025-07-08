# UAB Scholars Lookup

Thin Python client for the [Scholars@UAB](https://scholars.uab.edu/) REST API.

```bash
pip install uab-scholars-lookup   # soon on PyPI

# Search by name
uab-scholars search "Andrea Cherrington"

# List faculty in Preventive Medicine
uab-scholars department "Med - Preventive Medicine" --max 10
```

See `UAB_Scholars_API_README.md` for full endpoint docs and advanced filter payloads.

---

## Development

```bash
git clone https://github.com/your-org/uab-scholars-lookup && cd uab-scholars-lookup
python -m venv venv && source venv/bin/activate
pip install -e .[cli] -r requirements-dev.txt
pytest
```

# UAB Scholars API Data Puller

A collection of Python scripts to pull data from the Scholars@UAB API.

## Overview

These scripts provide various ways to pull faculty data from the Scholars@UAB API:

1. `pull_master_scholars_by_faculty_list.py`: Pull complete profiles, publications, grants, and teaching activities for a list of faculty by name
2. `pull_scholar_profile_by_user_csvs.py`: Pull complete profile for a specific user by ID
3. `search_by_department_concurrent.py`: Scan all user IDs concurrently and filter by department
4. `pull_master_scholars_by_dept_concurrent.py`: Pull complete data for all faculty in a department
5. `search_by_research_interest.py`: Scan all user IDs concurrently and filter by research interest

## Requirements

- Python 3.6+
- Required packages:
  - requests
  - concurrent.futures (built-in)
  - csv (built-in)
  - datetime (built-in)
  - unicodedata (built-in)

## Installation

1. Clone this repository
2. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```  
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## File Overview

### 1. pull_master_scholars_by_faculty_list.py
- Pulls complete Scholars@UAB profiles, publications, grants, and teaching activities for a list of faculty by name
- Outputs four CSV files with timestamps:
  - `profiles_YYYYMMDD_HHMMSS.csv`
  - `publications_YYYYMMDD_HHMMSS.csv`
  - `grants_YYYYMMDD_HHMMSS.csv`
  - `teaching_activities_YYYYMMDD_HHMMSS.csv`
- Features:
  - Handles name variations (nicknames, hyphenated names, Jr./Sr.)
  - Cleans text data (normalizes unicode, replaces fancy punctuation)
  - Includes research interests and teaching summaries
  - Concurrent processing with ThreadPoolExecutor
  - Improved error handling and logging
  - Consistent field naming across all outputs
  - Includes URLs for publications, grants, and teaching activities

### 2. pull_scholar_profile_by_user_csvs.py
- Pulls complete profile for a specific user by ID
- Outputs four CSV files with timestamps:
  - `profiles_YYYYMMDD_HHMMSS.csv`
  - `publications_YYYYMMDD_HHMMSS.csv`
  - `grants_YYYYMMDD_HHMMSS.csv`
  - `teaching_activities_YYYYMMDD_HHMMSS.csv`
- Features:
  - Cleans text data
  - Includes research interests and teaching summaries
  - Improved error handling and logging
  - Consistent field naming across all outputs
  - Includes URLs for publications, grants, and teaching activities

### 3. search_by_department_concurrent.py
- Scans all user IDs concurrently and filters by department
- Outputs a single CSV file with timestamp:
  - `users_by_department_YYYYMMDD_HHMMSS.csv`
- Features:
  - Uses ThreadPoolExecutor for concurrent scanning
  - Sorts results by last name, first name
  - Improved error handling and logging
  - Consistent field naming across all outputs
  - Text cleaning for department names and positions

### 4. pull_master_scholars_by_dept_concurrent.py
- Pulls complete data for all faculty in a department
- Outputs four CSV files with timestamps:
  - `profiles_YYYYMMDD_HHMMSS.csv`
  - `publications_YYYYMMDD_HHMMSS.csv`
  - `grants_YYYYMMDD_HHMMSS.csv`
  - `teaching_activities_YYYYMMDD_HHMMSS.csv`
- Features:
  - Uses ThreadPoolExecutor for concurrent scanning and data fetching
  - Cleans text data
  - Includes research interests and teaching summaries
  - Improved error handling and logging
  - Consistent field naming across all outputs
  - Includes URLs for publications, grants, and teaching activities

### 5. search_by_research_interest.py
- Scans all user IDs concurrently and filters by research interest substring
- Outputs a single CSV file with timestamp:
  - `users_by_research_interest_YYYYMMDD_HHMMSS.csv`
- Features:
  - Uses ThreadPoolExecutor for concurrent scanning
  - Sorts results by last name, first name
  - Improved error handling and logging
  - Consistent field naming across all outputs
  - Text cleaning for research interests, department names, and positions
  - Flexible substring search (case-insensitive) in research interests

## Configuration

Each script has configurable parameters at the top:

- `DEPARTMENT`: Department name to search for (in department scripts)
- `RESEARCH_INTEREST`: Research interest substring to search for (in research interest script)
- `MAX_ID`: Upper bound on numeric user IDs to scan
- `WORKERS`: Number of threads to use for concurrent operations
- `PER_PAGE_*`: Page size for API calls (increased to 500 for better performance)
- `PAUSE`: Delay between API calls

## Usage

1. Pull data for a list of faculty:
```bash
python pull_master_scholars_by_faculty_list.py
```

2. Pull data for a specific user:
```bash
   python pull_scholar_profile_by_user_csvs.py
   ```

3. Search by department:
```bash
python search_by_department_concurrent.py
```

4. Pull all data for a department:
```bash
   python pull_master_scholars_by_dept_concurrent.py
   ```

5. Search by research interest:
   ```bash
   python search_by_research_interest.py
   ```
   - Edit the `RESEARCH_INTEREST` variable at the top of the script to set your search term.

## Output Files

All scripts generate CSV files with consistent field names and timestamps:

### Profiles CSV Fields
- objectId
- discoveryUrlId
- firstName
- lastName
- email
- orcid
- department
- positions
- bio
- researchInterests
- teachingSummary

### Users by Research Interest CSV Fields
- objectId
- discoveryUrlId
- firstName
- lastName
- email
- department
- positions
- researchInterests

### Publications CSV Fields
- userObjectId
- publicationObjectId
- title
- journal
- doi
- pubYear
- pubMonth
- pubDay
- volume
- issue
- pages
- issn
- labels
- authors
- url

### Grants CSV Fields
- userObjectId
- grantObjectId
- title
- funder
- awardType
- year
- month
- day
- labels
- url

### Teaching Activities CSV Fields
- userObjectId
- teachingActivityObjectId
- type
- startYear
- startMonth
- startDay
- endYear
- endMonth
- endDay
- title
- url

## Recent Improvements

1. Reserved Key Conflict Resolved (type → result_type):
   - In LLM environments like Open WebUI, "type" is often a reserved field that causes runtime errors.
   - All occurrences of "type" in JSON responses were renamed to "result_type".

2. Safer and More Consistent JSON Schema:
   - Responses are now better structured with:
     - result_type
     - status
     - message
     - results (always a list, even if empty)
     - error_details only when relevant
   - This prevents key mismatches and simplifies downstream handling by consumers (like LLMs or web apps).

3. Internal Method Error Guarding:
   - Methods that return data (_get_scholar_profile, _get_publications, etc.) now ensure that returned values are of the expected types.
   - This prevents cascading failures from bad API responses and makes the tool more robust in production.

4. Event Emission Fully Optional and Safe:
   - All _emit_* functions now silently skip emission if __event_emitter__ is None.
   - This avoids runtime errors when running standalone or outside of WebUI.

5. Async/Await Hygiene Improvements:
   - Cleaned up inconsistent await usage across internal and external methods.
   - This reduces unnecessary concurrency overhead and makes behavior more predictable.

6. Improved Error Reporting and Debug Output:
   - Enhanced error blocks now include:
     - "error_details" for debugging
     - "suggestion" fields for LLMs to suggest next steps
   - This improves UX for end users and AI agents.

7. Response Size Optimization:
   - Publication, grant, and teaching lists now return:
     - Just the first few most relevant items
     - Full counts in a total key
   - This keeps output manageable for LLM context limits and faster rendering.

8. Code Structure Simplified for Maintenance:
   - Removed redundancies across sync/async versions.
   - Modularized JSON response construction.
   - This makes future changes faster and safer.

## Troubleshooting

1. Empty CSVs:
   - Check if the faculty list or department name is correct
   - For research interest search, check if the search term is correct
   - Verify API access and rate limits
   - Check for network connectivity
   - Look for error messages in the console output

2. Name Matching Issues:
   - The scripts handle various name formats (nicknames, hyphenated names, Jr./Sr.)
   - If a faculty member is not found, try their full name or alternative name format
   - For research interest search, try alternative or broader search terms
   - Check the console output for name matching attempts

3. API Rate Limits:
   - The scripts include built-in delays between API calls
   - Adjust the `PAUSE` parameter if needed
   - Monitor the console output for rate limit errors

4. Network Issues:
   - The scripts now handle network timeouts gracefully
   - Check your internet connection
   - Verify that the Scholars@UAB API is accessible

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
