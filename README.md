# UAB Scholars API Data Puller

A collection of Python scripts to pull data from the Scholars@UAB API.

## Overview

These scripts provide various ways to pull faculty data from the Scholars@UAB API:

1. `pull_master_scholars_by_faculty_list.py`: Pull complete profiles, publications, grants, and teaching activities for a list of faculty by name
2. `pull_scholar_profile_by_user_csvs.py`: Pull complete profile for a specific user by ID
3. `search_by_department_concurrent.py`: Scan all user IDs concurrently and filter by department
4. `pull_master_scholars_by_dept_concurrent.py`: Pull complete data for all faculty in a department

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

### 3. search_by_department_concurrent.py
- Scans all user IDs concurrently and filters by department
- Outputs a single CSV file with timestamp:
  - `users_by_department_YYYYMMDD_HHMMSS.csv`
- Features:
  - Uses ThreadPoolExecutor for concurrent scanning
  - Sorts results by last name, first name

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

## Configuration

Each script has configurable parameters at the top:

- `DEPARTMENT`: Department name to search for (in department scripts)
- `MAX_ID`: Upper bound on numeric user IDs to scan
- `WORKERS`: Number of threads to use for concurrent operations
- `PER_PAGE_*`: Page size for API calls
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

## Output Files

All scripts generate CSV files with consistent field names and timestamps:

### Profiles CSV Fields
- objectId
- discoveryUrlId (where applicable)
- firstName
- lastName
- email
- orcid
- department
- positions
- bio
- researchInterests
- teachingSummary

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

## Troubleshooting

1. Empty CSVs:
   - Check if the faculty list or department name is correct
   - Verify API access and rate limits
   - Check for network connectivity

2. Name Matching Issues:
   - The scripts handle various name formats (nicknames, hyphenated names, Jr./Sr.)
   - If a faculty member is not found, try their full name or alternative name format

3. API Rate Limits:
   - The scripts include built-in delays between API calls
   - Adjust the `PAUSE` parameter if needed

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
