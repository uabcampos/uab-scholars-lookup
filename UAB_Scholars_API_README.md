# UAB Scholars API (2025 revision)

> Last verified: June 2025

This document captures **only the current, working endpoints** that the Scholars@UAB REST API exposes after the June-2025 contract change, together with tested JSON payloads and example Python snippets. Older paths such as `/display/…`, `/individual/…`, or top-level `/pub{ID}` pages are deprecated and should not be generated.

---
## 1. Base URL
```
https://scholars.uab.edu/api
```
All paths below are appended to this base.

---
## 2. Search for users (`POST /users`)
Retrieve a paginated list of users that match free-text criteria.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `params.by` | string | yes | Must be `"text"` for full-text search. |
| `params.category` | string | yes | Must be `"user"`. |
| `params.text` | string | yes | Case-insensitive query string. |
| `pagination.startFrom` | int | yes | 0-based offset. |
| `pagination.perPage` | int | yes | Page size (≤ 100 recommended). |

Example payload (search **exact** name first!):
```json
{
  "params": {
    "by": "text",
    "category": "user",
    "text": "Gareth Dutton"
  },
  "pagination": {
    "startFrom": 0,
    "perPage": 25
  }
}
```
Important response keys:
* `pagination.total`   total hits.
* `resource[]`         array of user objects. Each object contains:
  * `discoveryId`         numeric id (string or int).
  * `discoveryUrlId`     canonical slug, _e.g._ `"453-gareth-dutton"`.
  * `positions[]`        department/position details.

### 2.1  Filtering search results (NEW July 2025)

The `/users` endpoint now accepts an optional **`filters`** array to perform
server-side facet filtering.  The API still returns a 200 with `resource[]` and
`pagination` keys, but the result set is narrowed _before_ pagination, so you
don't need to post-filter on the client.

#### Department filter

Payload structure:

```json
{
  "params": {
    "by": "text",
    "category": "user",
    "text": ""        // leave blank to fetch *all* users within a department
  },
  "pagination": {
    "startFrom": 0,
    "perPage": 25
  },
  "sort": "lastNameAsc",
  "filters": [
    {
      "name": "tags",
      "matchDocsWithMissingValues": true,
      "useValuesToFilter": false
    },
    {
      "name": "department",
      "matchDocsWithMissingValues": false,
      "useValuesToFilter": true,
      "values": ["Med - Preventive Medicine"]
    }
  ]
}
```

Key points:

* `name` must be exactly **`"department"`** (case-sensitive).
* `values` accepts **full department path strings** as displayed in the UI
  (example: `"Med - Preventive Medicine"`).  You can pass multiple strings to
  match any of them.
* Set `useValuesToFilter` → `true` to activate the filter.
* When filtering, leave `params.text` blank or set your usual keyword(s)—the
  filter combines **AND** with the free-text search.

This is the same structure used for other facets such as `tags`, `positions`,
or `school`.  Only facets that exist in the Scholars UI autocomplete are
supported.

#### Tag filter & combining facets

Another frequently-used facet is **`tags`**, which represents topical
classifications (e.g. *"Science, Technology and Engineering Curriculum and
Pedagogy"*).  You can combine multiple facet objects in the `filters` array –
the API applies them with logical **AND**.

Example: list faculty in **Preventive Medicine** who are tagged with
*Science, Technology and Engineering Curriculum and Pedagogy*:

```jsonc
{
  "params": {"by": "text", "category": "user", "text": ""},
  "pagination": {"startFrom": 0, "perPage": 25},
  "sort": "lastNameAsc",
  "filters": [
    {
      "name": "tags",
      "matchDocsWithMissingValues": false,
      "useValuesToFilter": true,
      "values": ["Science, Technology and Engineering Curriculum and Pedagogy"]
    },
    {
      "name": "department",
      "matchDocsWithMissingValues": false,
      "useValuesToFilter": true,
      "values": ["Med - Preventive Medicine"]
    }
  ]
}
```

You may include additional facet objects (e.g. `school`, `positions`) to hone
the search further.  Remember that `matchDocsWithMissingValues` is mandatory
for every filter object.

> ⚠️ As of July 2025 `matchDocsWithMissingValues` **must be provided**; if you
> omit it, the API returns HTTP 400.

Example: fetch every scholar in **Preventive Medicine** ordered by last name:

```python
payload = {
    "params": {"by": "text", "category": "user", "text": ""},
    "pagination": {"startFrom": 0, "perPage": 100},
    "sort": "lastNameAsc",
    "filters": [
        {"name": "department", "matchDocsWithMissingValues": False,
         "useValuesToFilter": True, "values": ["Med - Preventive Medicine"]}
    ]
}
resp = requests.post(f"{BASE}/users", json=payload).json()
print(resp["pagination"]["total"])  # total faculty in that department
```

##### Quick-start via cURL

```bash
# Preventive Medicine – return first 50 faculty sorted by last name
curl -s \
  -H 'Content-Type: application/json' \
  -X POST https://scholars.uab.edu/api/users \
  -d '{
        "params": {"by": "text", "category": "user", "text": ""},
        "pagination": {"startFrom": 0, "perPage": 50},
        "sort": "lastNameAsc",
        "filters": [
          {"name": "department", "matchDocsWithMissingValues": false,
           "useValuesToFilter": true, "values": ["Med - Preventive Medicine"]}
        ]
      }' | jq '.resource[] | "\(.firstName) \(.lastName)"'
```

##### Python one-liner

```python
import requests, json, pprint, textwrap
payload = json.loads(textwrap.dedent('''{
  "params": {"by": "text", "category": "user", "text": ""},
  "pagination": {"startFrom": 0, "perPage": 100},
  "sort": "lastNameAsc",
  "filters": [{"name": "department", "matchDocsWithMissingValues": false,
                "useValuesToFilter": true, "values": ["Med - Preventive Medicine"]}]
}'''))
users = requests.post('https://scholars.uab.edu/api/users', json=payload).json()['resource']
print([f"{u['firstName']} {u['lastName']}" for u in users])
```

These examples fetch a paginated list of faculty **already filtered** by department, so no post-processing is required.

---
## 3. Fetch user detail (`GET /users/{discoveryId}`)
Simple `GET` returning a JSON object for **one** user.

Key fields:
* `firstName`, `lastName`
* `discoveryUrlId` – the **only** value to append after `https://scholars.uab.edu/` for profile links.
* `positions[]` → `department`, `position`.
* `overview`    (biography).
* `linkedObjectIds.{publications|grants|teachingActivities}`

---
## 4. Linked item endpoints
All follow the same pattern: **POST** with payload:
```json
{
  "objectId": "<discoveryId>",
  "category": "user",
  "pagination": { "startFrom": 0, "perPage": 50 },
  "sort": "dateDesc"   // only for publications
}
```

| Endpoint | Returns | Notes |
|----------|---------|-------|
| `/publications/linkedTo` | Publications authored by the scholar. | If `resource[i].url` is absent you may fall back to DOI. |
| `/grants/linkedTo` | Grants on which the scholar is PI/Co-I. | The API **does not** supply a grant-level URL. |
| `/teachingActivities/linkedTo` | Teaching records. | |

Each response includes `pagination.total` and a `resource[]` array.

---
## 5. Pagination logic
Iterate while `startFrom + perPage < pagination.total`.

---
## 6. URL construction rules
1. **Profile pages**   `https://scholars.uab.edu/<discoveryUrlId>` (nothing else).
2. **Publications**    Use `resource[i].url` **as is** if it starts with `http`. If blank and a DOI exists → `https://doi.org/<doi>`.
3. **Grants**          No individual URL; reference the scholar profile when needed.

---
## 7. Helper snippets
### Name → profile
```python
from openwebui_uab_scholars import fetch_profile_by_name, NameLookup
prof = fetch_profile_by_name(NameLookup(faculty_name="Ryan Melvin", include_publications=False))
print(prof["profile"]["url"])  # https://scholars.uab.edu/16565-ryan-melvin
```
### Quick discoveryId lookup
```python
from openwebui_uab_scholars_stripped import _find_numeric_id
print(_find_numeric_id("Gareth Dutton"))  # '453'
```
### Back-compat search_by_name
```python
from openwebui_uab_scholars_stripped import search_by_name
print(search_by_name("Gareth Dutton"))
```
---
## 8. Retrying & error handling
* Retry once on network errors (timeout / 5xx). Back-off 0.5 s. 
* Always check `pagination.total`—empty `resource` does not always mean no data (could be pagination end).

---
## 9. Deprecated / removed endpoints
* `/display/<slug>` and `/individual/<slug>` HTML pages are not present in the 2025 API.
* Any JSON endpoint that relied on `objectType` / `type` → replaced by `category`.

---
## 10. Changelog (internal)
* 2025-06-20  Contract change (`type`→`category`, mandatory `pagination`).
* 2025-06-28  Discovered `discoveryUrlId` slug now includes numeric id.

Feel free to extend this README as additional endpoints are discovered. 

## Appendix A – Department counts (July 2025)

> Snapshot of the number of active faculty profiles returned by the Scholars@UAB API per department during July 2025. These counts are provided as a quick reference for building department-level queries.

| Department | Count |
| --- | --- |
| Accounting and Finance | 16 |
| Anatomic Pathology | 27 |
| Anesthesiology | 173 |
| Anthropology | 10 |
| Art and Art History | 21 |
| Biochemistry & Molecular Genetics | 41 |
| Biology | 37 |
| Biomedical Engineering | 11 |
| Biostatistics | 25 |
| Cell, Developmental and Integrative Biology (CDIB) | 49 |
| Chemistry | 28 |
| Civil, Construction & Environmental Engineering | 17 |
| Communication Studies | 10 |
| Computer Science | 20 |
| Criminal Justice | 17 |
| Curriculum Instruction | 42 |
| Dept Of Biomedical Informatics & Data Science | 10 |
| Dept of Biomedical Engineering | 10 |
| Dept of Medical Education | 10 |
| Dept of Optometry & Vision Science | 68 |
| Dermatology | 24 |
| Electrical & Computer Engineering | 11 |
| Emergency Medicine | 69 |
| English | 35 |
| Environmental Health Sciences | 13 |
| Epidemiology | 29 |
| Family & Community Medicine | 72 |
| Foreign Languages | 14 |
| General Dentistry | 20 |
| Genetics Research Division | 28 |
| Government | 17 |
| Health Behavior | 21 |
| Health Policy & Organization | 40 |
| Health Services Administration | 42 |
| History | 18 |
| Human Studies | 39 |
| Huntsville Medical - Family Med Program | 41 |
| Huntsville Medical - Internal Med Program | 43 |
| Huntsville Medical - Pediatrics Program | 27 |
| Huntsville Medical - Psychiatry Program | 13 |
| Huntsville Medical - Surgery Program | 29 |
| Laboratory Medicine | 25 |
| Management, Information Systems and Quantitative Methods | 26 |
| Mathematics | 30 |
| Med - Preventive Medicine | 153 |
| Medicine - Cardiovascular Disease | 75 |
| Medicine - Endocrinology, Diabetes, and Metabolism | 31 |
| Medicine - Gastroenterology | 36 |
| Medicine - General Internal Medicine | 13 |
| Medicine - Gerontology, Geriatrics, and Palliative Care | 55 |
| Medicine - Hematology & Oncology | 85 |
| Medicine - Immunology and Rheumatology | 41 |
| Medicine - Infectious Diseases | 68 |
| Medicine - Nephrology | 63 |
| Medicine - Pulmonary, Allergy, & Critical Care Medicine | 118 |
| Microbiology | 42 |
| Mktg, Ind Distr, & Econ | 18 |
| Molecular & Cellular Pathology | 35 |
| Montgomery Internal Medicine | 18 |
| Music | 23 |
| Neurobiology | 32 |
| Neurology | 106 |
| Neuropathology | 10 |
| Neurosurgery | 16 |
| Nursing Academic Affairs | 10 |
| Nursing Academic Support | 118 |
| Nursing Acute, Chronic & Continuing Care | 73 |
| Nursing Clinical Practice & Partnerships | 10 |
| Nursing Family, Community & Health Systems | 55 |
| Nutrition Sciences | 29 |
| OB/GYN - Gyn Oncology | 10 |
| OB/GYN - Maternal & Fetal Medicine | 19 |
| OB/GYN - Women's Reproductive Healthcare | 15 |
| Occupational Therapy | 19 |
| Ophthalmology | 67 |
| Oral & Maxillofacial Surgery | 16 |
| Orthopaedic Surgery | 36 |
| Otolaryngology | 31 |
| Ped - Endocrinology | 13 |
| Pediatric - Academic General Pediatrics | 30 |
| Pediatric - Allergy & Immunology | 10 |
| Pediatric - Cardiology | 11 |
| Pediatric - Critical Care | 16 |
| Pediatric - Emergency Medicine | 31 |
| Pediatric - Gastroenterology, Hepatology, & Nutrition | 20 |
| Pediatric - Hematology-Oncology | 33 |
| Pediatric - Hospital Medicine | 21 |
| Pediatric - Infectious Disease | 17 |
| Pediatric - Neonatology | 33 |
| Pediatric - Neurology | 24 |
| Pediatric - Pulmonary & Sleep Medicine | 19 |
| Pediatric Dentistry | 13 |
| Periodontology | 9 |
| Philosophy | 11 |
| Physical Medicine & Rehabilitation | 29 |
| Physical Therapy | 25 |
| Physician Assistant Studies | 13 |
| Physics | 23 |
| Prosthodontics | 9 |
| Psychiatry - Adult | 50 |
| Psychiatry - Behavioral Neurobiology | 28 |
| Psychiatry - Child & Adolescent | 9 |
| Psychology | 39 |
| Radiation Oncology | 36 |
| Radiology | 135 |
| School of Medicine - Montgomery | 111 |
| Selma Family Medicine | 14 |
| Social Work | 16 |
| Sociology | 18 |
| Surgery - Cardiovascular/Thoracic | 20 |
| Surgery - General Surgery Gastrointestinal Section | 26 |
| Surgery - General Surgery Oncology Section | 15 |
| Surgery - General Surgery Trauma Section | 32 |
| Surgery - General Surgery Vascular Section | 12 |
| Surgery - Pediatric | 9 |
| Surgery - Transplantation | 15 |
| Theatre | 15 |
| UAB Libraries | 42 |
| University of Alabama Health Services Foundation (UAHSF) | 109 |
| Urology | 26 |

## Appendix B – Tag counts (July 2025)

| Tag | Count |
| --- | --- |
| Accounting, Auditing and Accountability | 0 |
| Aerospace Engineering | 0 |
| Aged Health Care | 0 |
| Agriculture, Land and Farm Management | 0 |
| Analysis of Algorithms and Complexity | 0 |
| Analytical Chemistry | 0 |
| Animal Cell and Molecular Biology | 0 |
| Animal Neurobiology | 0 |
| Animal Nutrition | 0 |
| Animal Production | 0 |
| Animal Reproduction | 0 |
| Anthropology | 0 |
| Applied Economics | 4 |
| Applied Ethics | 2 |
| Applied Mathematics | 0 |
| Applied Statistics | 0 |
| Aquaculture | 0 |
| Archaeology | 0 |
| Art Theory and Criticism | 0 |
| Artificial Intelligence and Image Processing | 1 |
| Artificial Intelligence and Image Processing not elsewhere classified | 0 |
| Arts and Cultural Policy | 0 |
| Astronomical and Space Sciences | 0 |
| Atmospheric Sciences | 0 |
| Atomic, Molecular, Nuclear, Particle and Plasma Physics | 0 |
| Automotive Engineering | 0 |
| Autonomic Nervous System | 0 |
| Banking, Finance and Investment | 0 |
| Basic Pharmacology | 0 |
| Biochemistry and Cell Biology | 3 |
| Bioethics (human and animal) | 0 |
| Bioinformatics | 0 |
| Bioinformatics Software | 0 |
| Biological Psychology (Neuropsychology, Psychopharmacology, Physiological Psychology) | 0 |
| Biological Sciences | 0 |
| Biomaterials | 0 |
| Biomedical Engineering | 1 |
| Bioremediation | 0 |
| Biostatistics | 0 |
| Building | 0 |
| Business Information Management (incl. Records, Knowledge and Information Management, and Intelligence) | 0 |
| Business Information Systems | 0 |
| Business and Management | 1 |
| Cancer Cell Biology | 0 |
| Cancer Diagnosis | 0 |
| Cancer Genetics | 0 |
| Cancer Therapy (excl. Chemotherapy and Radiation Therapy) | 0 |
| Cardiology (incl. Cardiovascular Diseases) | 0 |
| Cardiorespiratory Medicine and Haematology | 12 |
| Cell Development, Proliferation and Death | 0 |
| Cell Metabolism | 0 |
| Cellular Immunology | 0 |
| Cellular Interactions (incl. Adhesion, Matrix, Cell Wall) | 0 |
| Cellular Nervous System | 0 |
| Central Nervous System | 0 |
| Chemical Engineering | 0 |
| Civil Engineering | 0 |
| Classical Physics | 0 |
| Clinical Microbiology | 0 |
| Clinical Pharmacology and Therapeutics | 0 |
| Clinical Sciences | 46 |
| Clinical and Sports Nutrition | 0 |
| Coding and Information Theory | 0 |
| Cognitive Sciences | 2 |
| Commercial Services | 0 |
| Communication Technology and Digital Media Studies | 0 |
| Communication and Media Studies | 0 |
| Communications Technologies | 0 |
| Community Child Health | 0 |
| Comparative Government and Politics | 0 |
| Comparative Physiology | 0 |
| Comparative and Cross-Cultural Education | 0 |
| Complementary and Alternative Medicine | 0 |
| Composite and Hybrid Materials | 0 |
| Computation Theory and Mathematics | 0 |
| Computational Linguistics | 0 |
| Computer Hardware | 0 |
| Computer Software | 0 |
| Computer System Security | 0 |
| Computer Vision | 0 |
| Computer-Human Interaction | 0 |
| Condensed Matter Physics | 0 |
| Continuing and Community Education | 0 |
| Creative Arts, Media and Communication Curriculum and Pedagogy | 0 |
| Criminology | 0 |
| Crop and Pasture Production | 0 |
| Cultural Studies | 0 |
| Culture, Gender, Sexuality | 0 |
| Curriculum and Pedagogy | 20 |
| Database Management | 0 |
| Decision Making | 0 |
| Decision Support and Group Support Systems | 0 |
| Demography | 0 |
| Dentistry | 1 |
| Design Practice and Management | 0 |
| Developmental Genetics (incl. Sex Determination) | 0 |
| Developmental Psychology and Ageing | 0 |
| Distributed Computing | 0 |
| Earth Sciences | 0 |
| Ecological Applications | 0 |
| Ecological Impacts of Climate Change | 0 |
| Ecological Physiology | 0 |
| Ecology | 0 |
| Econometrics | 0 |
| Economic Theory | 0 |
| Economics | 0 |
| Education | 0 |
| Education Assessment and Evaluation | 0 |
| Education Policy | 0 |
| Education Systems | 3 |
| Educational Administration, Management and Leadership | 0 |
| Electrical and Electronic Engineering | 0 |
| Emergency Medicine | 0 |
| Endocrinology | 0 |
| Engineering Systems Design | 0 |
| English and Literacy Curriculum and Pedagogy (excl. LOTE, ESL and TESOL) | 0 |
| Entrepreneurship | 0 |
| Environmental Biotechnology | 0 |
| Environmental Education and Extension | 0 |
| Environmental Engineering | 0 |
| Environmental Science and Management | 0 |
| Environmental Sciences | 0 |
| Epidemiology | 0 |
| Epigenetics (incl. Genome Methylation and Epigenomics) | 0 |
| Evolutionary Biology | 0 |
| Evolutionary Impacts of Climate Change | 0 |
| Exercise Physiology | 0 |
| Film, Television and Digital Media | 0 |
| Finance | 0 |
| Fisheries Sciences | 0 |
| Food Sciences | 0 |
| Forensic Chemistry | 0 |
| Functional Materials | 0 |
| Gastroenterology and Hepatology | 0 |
| Gene Expression (incl. Microarray and other genome-wide approaches) | 0 |
| Gene and Molecular Therapy | 0 |
| Genetically Modified Animals | 0 |
| Genetics | 0 |
| Genomics | 0 |
| Geochemistry | 0 |
| Geology | 0 |
| Geomatic Engineering | 0 |
| Geophysics | 0 |
| Geriatrics and Gerontology | 0 |
| Globalisation and Culture | 0 |
| Haematological Tumours | 0 |
| Haematology | 0 |
| Health Care Administration | 0 |
| Health Economics | 0 |
| Health Informatics | 1 |
| Health Information Systems (incl. Surveillance) | 0 |
| Health Policy | 0 |
| Health Promotion | 0 |
| Health and Community Services | 0 |
| Health, Clinical and Counselling Psychology | 0 |
| Higher Education | 0 |
| Historical Studies | 0 |
| History and Philosophy of Science (incl. Non-historical Philosophy of Science) | 0 |
| History and Philosophy of Specific Fields | 1 |
| Horticultural Production | 0 |
| Human Geography | 0 |
| Human Movement and Sports Sciences | 5 |
| Human Resources Management | 0 |
| Immunology | 5 |
| Industrial Biotechnology | 0 |
| Industrial and Organisational Psychology | 0 |
| Infectious Diseases | 0 |
| Information Systems | 1 |
| Information Systems Development Methodologies | 0 |
| Information Systems Theory | 0 |
| Innovation and Technology Management | 0 |
| Inorganic Chemistry | 0 |
| Intensive Care | 0 |
| Interdisciplinary Engineering | 0 |
| International Relations | 0 |
| Invasive Species Ecology | 0 |
| Journalism and Professional Writing | 0 |
| Knowledge Representation and Machine Learning | 0 |
| Language Studies | 0 |
| Language in Culture and Society (Sociolinguistics) | 0 |
| Law | 0 |
| Learning Sciences | 0 |
| Legal Institutions (incl. Courts and Justice Systems) | 0 |
| Library and Information Studies | 1 |
| Linguistics | 0 |
| Literary Studies | 0 |
| Logistics and Supply Chain Management | 0 |
| Macromolecular and Materials Chemistry | 0 |
| Manufacturing Engineering | 0 |
| Marketing | 0 |
| Marketing Management (incl. Strategy and Customer Relations) | 0 |
| Materials Engineering | 0 |
| Mathematical Physics | 0 |
| Mechanical Engineering | 0 |
| Medical Biochemistry and Metabolomics | 0 |
| Medical Biochemistry: Proteins and Peptides (incl. Medical Proteomics) | 0 |
| Medical Biotechnology | 0 |
| Medical Devices | 0 |
| Medical Genetics (excl. Cancer Genetics) | 0 |
| Medical Infection Agents (incl. Prions) | 0 |
| Medical Microbiology | 1 |
| Medical Molecular Engineering of Nucleic Acids and Proteins | 0 |
| Medical Physics | 0 |
| Medical Physiology | 2 |
| Medical and Health Sciences | 0 |
| Medicinal and Biomolecular Chemistry | 0 |
| Medicine, Nursing and Health Curriculum and Pedagogy | 0 |
| Mental Health | 0 |
| Microbial Genetics | 0 |
| Microbiology | 0 |
| Mineralogy and Crystallography | 0 |
| Mobile Technologies | 0 |
| Molecular Evolution | 0 |
| Molecular Medicine | 0 |
| Molecular Targets | 0 |
| Museum Studies | 0 |
| Music Therapy | 0 |
| Nanotechnology | 0 |
| Natural Language Processing | 0 |
| Nephrology and Urology | 0 |
| Neurocognitive Patterns and Neural Networks | 0 |
| Neurogenetics | 0 |
| Neurology and Neuromuscular Diseases | 0 |
| Neurosciences | 4 |
| Nuclear Medicine | 0 |
| Nuclear Physics | 0 |
| Numerical and Computational Mathematics | 0 |
| Nursing | 11 |
| Nutrition and Dietetics | 1 |
| Nutritional Physiology | 0 |
| Obstetrics and Gynaecology | 0 |
| Oceanography | 0 |
| Oncology and Carcinogenesis | 14 |
| Operations Research | 0 |
| Opthalmology and Optometry | 9 |
| Optical Physics | 0 |
| Optical Properties of Materials | 0 |
| Optimisation | 0 |
| Organic Chemistry | 0 |
| Organisation and Management Theory | 0 |
| Organisational Behaviour | 0 |
| Other Biological Sciences | 0 |
| Other Chemical Sciences | 0 |
| Other Commerce, Management, Tourism and Services | 0 |
| Other Economics | 0 |
| Other Education | 0 |
| Other History and Archaeology | 0 |
| Other Information and Computing Sciences | 0 |
| Other Mathematical Sciences | 0 |
| Other Medical and Health Sciences | 2 |
| Other Philosophy and Religious Studies | 0 |
| Other Physical Sciences | 1 |
| Other Studies in Human Society | 1 |
| Other Technology | 0 |
| Paediatrics | 0 |
| Paediatrics and Reproductive Medicine | 3 |
| Pathology (excl. Oral Pathology) | 0 |
| Pattern Recognition and Data Mining | 0 |
| Performing Arts and Creative Writing | 0 |
| Pharmaceutical Sciences | 0 |
| Pharmacogenomics | 0 |
| Pharmacology and Pharmaceutical Sciences | 8 |
| Philosophical Psychology (incl. Moral Psychology and Philosophy of Action) | 0 |
| Philosophy | 1 |
| Physical Chemistry (incl. Structural) | 0 |
| Physical Geography and Environmental Geoscience | 0 |
| Physiology | 1 |
| Plant Biology | 0 |
| Police Administration, Procedures and Practice | 0 |
| Policy and Administration | 2 |
| Policy and Administration not elsewhere classified | 0 |
| Political Science | 0 |
| Population, Ecological and Evolutionary Genetics | 0 |
| Primary Health Care | 0 |
| Protein Trafficking | 0 |
| Proteins and Peptides | 0 |
| Psychiatry (incl. Psychotherapy) | 0 |
| Psychology | 7 |
| Psychology and Cognitive Sciences | 0 |
| Public Administration | 0 |
| Public Health and Health Services | 34 |
| Public Health and Health Services not elsewhere classified | 0 |
| Public Nutrition Intervention | 0 |
| Pure Mathematics | 0 |
| Quantitative Genetics (incl. Disease and Trait Mapping Genetics) | 0 |
| Quantum Chemistry | 0 |
| Quantum Information, Computation and Communication | 0 |
| Quantum Physics | 0 |
| Radiation Therapy | 0 |
| Radiation and Matter | 0 |
| Radiology and Organ Imaging | 0 |
| Receptors and Membrane Biology | 0 |
| Regenerative Medicine (incl. Stem Cells and Tissue Engineering) | 0 |
| Rehabilitation Engineering | 0 |
| Rehabilitation and Therapy (excl. Physiotherapy) | 0 |
| Religion and Religious Studies | 0 |
| Resources Engineering and Extractive Metallurgy | 0 |
| Respiratory Diseases | 0 |
| Rheumatology and Arthritis | 0 |
| Science, Technology and Engineering Curriculum and Pedagogy | 0 |
| Secondary Education | 0 |
| Sensory Processes, Perception and Performance | 0 |
| Sensory Systems | 0 |
| Signal Processing | 0 |
| Signal Transduction | 0 |
| Simulation and Modelling | 0 |
| Social Policy | 0 |
| Social Work | 1 |
| Sociological Methodology and Research Methods | 0 |
| Sociology | 1 |
| Soil Sciences | 0 |
| Special Education and Disability | 1 |
| Specialist Studies in Education | 1 |
| Sport and Exercise Psychology | 0 |
| Statistical Theory | 0 |
| Statistics | 1 |
| Structural Biology (incl. Macromolecular Modelling) | 0 |
| Structural Chemistry and Spectroscopy | 0 |
| Stylistics and Textual Analysis | 0 |
| Surgery | 0 |
| Systems Biology | 0 |
| Teacher Education and Professional Development of Educators | 0 |
| Theoretical and Computational Chemistry | 0 |
| Tourism | 0 |
| Tourist Behaviour and Visitor Experience | 0 |
| Toxicology (incl. Clinical Toxicology) | 0 |
| Transportation and Freight Services | 0 |
| Tumour Immunology | 0 |
| Urban and Regional Planning | 0 |
| Veterinary Sciences | 0 |
| Virology | 0 |
| Vision Science | 0 |
| Visual Arts and Crafts | 0 |
| Water Quality Engineering | 0 |
| Zoology | 0 |
| f-Block Chemistry | 0 |