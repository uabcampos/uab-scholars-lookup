# UAB Scholars API Data Puller

This collection of Python scripts automates pulling faculty data from the UAB Scholars API. You can:

- Pull full profiles (bio, roles, contact, research interests, teaching summary)  
- Export publications, grants and teaching activities  
- Search by a list of faculty names  
- Search by department and export matching profiles  

All outputs are written to CSV files so you can load them into Excel, a database or your favorite analysis tool.

---

## 📋 Requirements

- **Python 3.9+**  
- **requests** library  
- (Optional) **pandas** & **openpyxl** if you want Excel output  
- Internet access to `scholars.uab.edu`

---

## 🛠 Installation

1. Clone or download this repo.  
2. Create and activate a virtual environment:

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   pip install requests
   # If you plan to export to Excel:
   pip install pandas openpyxl
   ```

---

## 📂 File Overview

- **faculty_fullnames.py**  
  A Python file exporting a list of faculty full names, used by `pull_master_scholars_by_faculty_list.py`.

- **pull_master_scholars_by_faculty_list.py**  
  Pulls profiles, publications, grants and teaching activities for each name in `faculty_fullnames.py`.

- **search_by_department.py**  
  Scans all numeric user IDs up to `MAX_ID`, filters by a department substring, and exports basic contact info.

- **pull_department_scholars.py**  
  Combines profile, publication, grant and teaching‐activity pulls for everyone in a given department.

- **README.md**  
  This document.

---

## ⚙️ Configuration

Each script has a small “CONFIG” section at the top where you can adjust:

- **DEPARTMENT** – exact or substring match for department searches  
- **PER_PAGE_PUBS**, **PER_PAGE_GRANTS**, **PER_PAGE_TEACHING** – pagination sizes  
- **MAX_ID** – upper bound on numeric user IDs (for department scanners)  
- **PAUSE_SECONDS** – delay between requests to avoid rate limiting  

Example in `search_by_department.py`:

```python
DEPARTMENT     = "Med - Preventive Medicine"
MAX_ID         = 6000
PAUSE_SECONDS  = 0.1
```

---

## 🚀 Usage

Activate your venv:

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

### 2. Find faculty by department only

```bash
python search_by_department.py
```

Produces:

- `users_by_department.csv`  
  with object ID, first and last name, email, departments and positions.

### 3. Pull everything for a department

```bash
python pull_department_scholars.py
```

Produces the same four CSVs as the master pull, but only for users whose positions include your `DEPARTMENT` string.

---

## 🛠 Troubleshooting

- **Empty CSVs**  
  - Verify your `DEPARTMENT` matches the API’s `department` fields (case-insensitive substring).  
  - Increase `PAUSE_SECONDS` if you suspect rate limiting.

- **“Could not resolve slug” errors**  
  - Check name formatting in `faculty_fullnames.py`.  
  - Remove middle initials or use exact first/last matches.

- **Connection errors**  
  - Ensure you have internet access and the API is reachable.  
  - Increase timeouts or `PAUSE_SECONDS`.

---

## ❤️ Contributing

Contributions and improvements are welcome. Feel free to open issues or submit pull requests.

---

## 📄 License

This project is released under the MIT License.
