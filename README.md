# UAB Scholars API Data Puller

This collection of Python scripts automates the process of pulling faculty data from the UAB Scholars API. You can:

- Pull full profiles (bio, roles, contact, research interests, teaching summary)  
- Export publications, grants and teaching activities  
- Search by a list of faculty names  
- Search by department (concurrent and non-concurrent)  
- Pull a single user’s complete profile and write separate CSVs  

All outputs are CSV files so you can load them into Excel, a database or your favorite analysis tool.

---

## 📋 Requirements

- **Python 3.9+**  
- **requests** library  
- (Optional) **pandas** and **openpyxl** if you want Excel output  
- Internet access to `scholars.uab.edu`

---

## 🛠 Installation

1. Clone or download this repo  
2. Create and activate a virtual environment  
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```  
3. Install dependencies  
   ```bash
   pip install requests
   # If you plan to export to Excel:
   pip install pandas openpyxl
   ```

---

## 📂 File Overview

- **faculty_fullnames.py**  
  A Python file exporting `faculty_fullnames`, a list of full names (First [M.] Last).

- **pull_master_scholars_by_faculty_list.py**  
  Pulls profiles, publications, grants and teaching activities for each name in `faculty_fullnames.py`.  
  Cleans mojibake and curly quotes/dashes.

- **pull_master_scholars_by_dept_concurrent.py**  
  Two-phase concurrent scanner:  
  1. Scan numeric IDs up to `MAX_ID` in parallel, find matching department  
  2. Fetch each user’s profile, publications, grants and teaching activities in parallel  
  Outputs four CSVs.

- **search_by_department_concurrent.py**  
  Query the API search endpoint in parallel to find every user whose `positions.department` contains your department substring. Writes a single CSV of `objectId`, name, email, departments and positions.

- **pull_scholar_profile_by_user_csvs.py**  
  Given a single numeric `USER_ID`, fetches that user’s profile, research interests, teaching summary, publications, grants, and teaching activities. Cleans all text fields and writes four separate CSVs:  
  - `<slug>_profile.csv`  
  - `<slug>_publications.csv`  
  - `<slug>_grants.csv`  
  - `<slug>_teaching_activities.csv`

---

## ⚙️ Configuration

Each script has a “CONFIG” section at the top where you can adjust:

- **DEPARTMENT** – substring used for department searches  
- **MAX_ID** – upper bound on numeric user IDs (for ID scanners)  
- **PER_PAGE_PUBS**, **PER_PAGE_GRANTS**, **PER_PAGE_TEACHING** – pagination sizes  
- **PAUSE**, **PAUSE_SECONDS** – delay between requests to avoid rate limiting  

Example in `pull_master_scholars_by_dept_concurrent.py`:

```python
DEPARTMENT     = "Med - Preventive Medicine"
MAX_ID         = 6000
SCAN_WORKERS   = 20
FETCH_WORKERS  = 10
PAUSE_SECONDS  = 0.1
```

---

## 🚀 Usage

Activate your virtual environment:

```bash
source venv/bin/activate
```

### 1. Pull a fixed list of faculty

```bash
python pull_master_scholars_by_faculty_list.py
```

Produces four CSVs:

- `profiles.csv`  
- `publications.csv`  
- `grants.csv`  
- `teaching_activities.csv`

### 2. Search by department (concurrent)

```bash
python pull_master_scholars_by_dept_concurrent.py
```

Produces four CSVs for every user whose department matches:

- `profiles.csv`  
- `publications.csv`  
- `grants.csv`  
- `teaching_activities.csv`

### 3. Search by department only (basic)

```bash
python search_by_department_concurrent.py
```

Produces:

- `users_by_department.csv`  
  with `objectId`, first and last name, email, departments and positions.

### 4. Pull a single user’s profile, pubs and grants

```bash
python pull_scholar_profile_by_user_csvs.py
```

Produces four files for the specified `USER_ID`:
  - `<slug>_profile.csv`  
  - `<slug>_publications.csv`  
  - `<slug>_grants.csv`  
  - `<slug>_teaching_activities.csv`

---

## 🛠 Troubleshooting

- **Empty CSVs**  
  - Verify your department substring matches the API’s `department` fields (case-insensitive).  
  - Increase `PAUSE` or `PAUSE_SECONDS` if you suspect rate limiting.

- **Unicode or mojibake issues**  
  - All scripts include a `clean_text` function to normalize Unicode, replace `‚Äì` and convert curly quotes/dashes to plain ASCII.

- **Connection errors**  
  - Ensure you have internet access and the API is reachable.  
  - Increase timeouts or pause delays.

---

## ❤️ Contributing

Contributions are welcome. Feel free to open issues or submit pull requests.

---

## 📄 License

This project is released under the MIT License.
