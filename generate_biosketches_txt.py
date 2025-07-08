import json
import os
from glob import glob
from openai import OpenAI
from dotenv import load_dotenv
import csv

# Load environment variables from .env file
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Core mission/aims summaries for prompt context
DATA_SCIENCE_CORE_SUMMARY = (
    "The Data Science & Analytics Core supports the translation of evidence-based approaches for diabetes prevention and treatment "
    "to improve population health in the Deep South. The Core expands the availability and usability of data sources and provides "
    "methodologic expertise in traditional and novel approaches to data management and analysis that advance diabetes translational research. "
    "It offers expertise in biostatistics, epidemiology, health services, health informatics, data transformation, and data management, "
    "serving clinicians, research scientists, and community collaborators to foster T3-T4 diabetes research collaborations."
)

TRANSLATIONAL_DESIGN_CORE_SUMMARY = (
    "The Translational Design & Intervention Core provides consultation, expertise, and resources to facilitate the development and delivery "
    "of scalable, technology-enhanced, and contextually-tailored translational interventions for diabetes prevention and management in real-world settings. "
    "It supports rigorous, implementation-informed study designs and validated, feasible measures, and facilitates engagement of multisector partners "
    "to advance diabetes translation research and improve health outcomes in the Deep South."
)

# ARCH CDTR mission statement for prompt context
ARCH_CDTR_MISSION = (
    "The mission of the ARCH CDTR is to support the translation of evidence-based approaches for diabetes prevention and treatment "
    "to improve population health in the Deep South, a region with significant diabetes burden. The Center's theme is applying a precision public health "
    "approach across the diabetes care continuum to achieve better health for all."
)

LANGUAGE_GUIDANCE = '''
LANGUAGE STRATEGIES AND ALTERNATE TERMS:
- Do NOT use any words or phrases from the flagged word list below.
- Use these alternate terms and strategies:
  • Instead of "health equity," use "ensuring optimal health outcomes for all populations through targeted interventions."
  • Replace "underserved communities" with "populations with limited access to healthcare and preventive services."
  • Instead of "diversity, equity, and inclusion (DEI)," use "broad participation in research and healthcare solutions."
  • For "health disparities," use "health challenges affecting communities with limited access to healthcare and preventive services," "barriers to optimal health outcomes," or "differences in health outcomes across populations."
  • For "racial disparities," use "differences in health outcomes across populations with varied access to care."
  • For "socioeconomic inequities," use "the impact of economic and environmental factors on health access and outcomes."
  • For "historically marginalized communities," use "communities with systemic barriers to healthcare access."
  • Use objective, outcome-oriented language (e.g., "expanding participation in healthcare and research," "ensuring research reflects the experiences and needs of diverse populations," "collaborative efforts to inform policy and practice based on scientific findings").
  • Frame research in terms of scientific rigor, not social justice (e.g., "applying a precision public health approach to identify and close gaps in care," "enhancing the effectiveness of healthcare delivery across populations").
  • Use clear, population-specific language instead of broad identity terms (e.g., "Black and Hispanic populations in the Deep South, who experience a higher burden of cardiometabolic diseases").

FLAGGED WORD LIST (DO NOT USE):
accessible, activism, activists, advocacy, advocate, advocates, affirming care, all-inclusive, allyship, antiracism, antiracist, assigned at birth, assigned female at birth, assigned male at birth, at risk, barrier, barriers, belong, bias, biased, biased toward, biases, biases towards, biologically female, biologically male, BIPOC, Black, breastfeed + people, breastfeed + person, chestfeed + people, chestfeed + person, clean energy, climate crisis, climate science, commercial sex worker, community diversity, community equity, confirmation bias, cultural competence, cultural differences, cultural heritage, cultural sensitivity, culturally appropriate, culturally responsive, DEI, DEIA, DEIAB, DEIJ, disabilities, disability, discriminated, discrimination, discriminatory, disparity, diverse, diverse backgrounds, diverse communities, diverse community, diverse group, diverse groups, diversified, diversify, diversifying, diversity, enhance the diversity, enhancing diversity, environmental quality, equal opportunity, equality, equitable, equitableness, equity, ethnicity, excluded, exclusion, expression, female, females, feminism, fostering inclusivity, GBV, gender, gender based, gender based violence, gender identity, gender ideology, gender-affirming care, genders, Gulf of Mexico, hate speech, health disparity, health equity, hispanic minority, historically, identity, immigrants, implicit bias, implicit biases, inclusion, inclusive, inclusive leadership, inclusiveness, inclusivity, increase diversity, increase the diversity, indigenous community, inequalities, inequality, inequitable, inequities, inequity, injustice, institutional, intersectional, intersectionality, key groups, key people, key populations, Latinx, LGBT, LGBTQ, marginalized, men who have sex with men, mental health, minorities, minority, most risk, MSM, multicultural, Mx, Native American, non-binary, nonbinary, oppression, oppressive, orientation, people + uterus, people-centered care, person-centered, person-centered care, polarization, political, pollution, pregnant people, pregnant person, pregnant persons, prejudice, privilege, privileges, promote diversity, promoting diversity, pronoun, pronouns, prostitute, race, race and ethnicity, racial, racial diversity, racial identity, racial inequality, racial justice, racially, racism, segregation, sense of belonging, sex, sexual preferences, sexuality, social justice, sociocultural, socioeconomic, status, stereotype, stereotypes, systemic, systemically, they/them, transgender, transsexual, trauma, traumatic, tribal, unconscious bias, underappreciated, underprivileged, underrepresentation, underrepresented, underserved, undervalued, victim, victims, vulnerable populations, women, women and underrepresented, Climate, Diverse, Equity, Justice, LGBT, Minority, Racism, Religion, Underrepresented, Under-represented, Non-Binary, Non Binary, Transgender, SDOH, Social Determinants of Health, Underserved, Under-served, Inequalities, Affirming, Hesitancy
'''

def load_json_data(faculty_name):
    """Load the scholar profile JSON data for a faculty member from scholar_data, matching files with timestamps."""
    # Split faculty_name into last_name and first_name
    parts = faculty_name.split(',')
    if len(parts) != 2:
        print(f"Invalid name format for {faculty_name}. Expected 'Last, First' format.")
        return None
    
    last_name = parts[0].strip().lower().replace(" ", "_")
    first_name = parts[1].strip().lower().replace(" ", "_")
    
    # Try different patterns
    patterns = [
        f'scholar_data/{last_name}_{first_name}_profile_*.json',
        f'scholar_data/{first_name}_{last_name}_profile_*.json',
        f'scholar_data/{last_name}_profile_*.json'
    ]
    
    # Add specific cases
    if faculty_name == "Dutton, Gareth R.":
        patterns.insert(0, 'scholar_data/gareth_dutton_profile_*.json')
    elif faculty_name == "Garvey, W. Timothy":
        patterns.insert(0, 'scholar_data/garvey_w_timothy_profile_*.json')
    elif faculty_name == "Hidalgo, Bertha A.":
        patterns.insert(0, 'scholar_data/hidalgo_bertha_a_profile_*.json')
    elif faculty_name == "Judd, Suzanne E.":
        patterns.insert(0, 'scholar_data/judd_suzanne_e_profile_*.json')
    
    # Try each pattern
    for pattern in patterns:
        matches = sorted(glob(pattern))
        if matches:
            # Use the most recent file (last in sorted list)
            json_file = matches[-1]
            print(f"\nDEBUG: Loading JSON file: {json_file}")
            with open(json_file, 'r') as f:
                data = json.load(f)
                print(f"DEBUG: Found grant IDs in profile: {data.get('profile', {}).get('linkedObjectIds', {}).get('grants', [])}")
                
                # Find the most recent grants CSV file
                grants_files = sorted(glob('grants_*.csv'))
                if grants_files:
                    grants_file = grants_files[-1]  # Use the most recent file
                    print(f"DEBUG: Using grants file: {grants_file}")
                    grants_data = []
                    with open(grants_file, 'r') as grants_f:
                        reader = csv.DictReader(grants_f)
                        for row in reader:
                            grant_id = row.get('objectId')
                            if grant_id and str(grant_id) in [str(g) for g in data.get('profile', {}).get('linkedObjectIds', {}).get('grants', [])]:
                                print(f"DEBUG: Found matching grant in CSV: {grant_id} - {row.get('title', '')}")
                                grants_data.append({
                                    'objectId': grant_id,
                                    'title': row.get('title', ''),
                                    'funderName': row.get('funder', ''),
                                    'date1': {'dateTime': row.get('startDate', '')},
                                    'labels': [],
                                    'description': row.get('description', ''),
                                    'abstract': row.get('description', ''),
                                    'keywords': '',
                                    'objectTypeDisplayName': row.get('role', '')
                                })
                    
                    print(f"DEBUG: Total grants loaded: {len(grants_data)}")
                    # Add grants data to the JSON data
                    data['grants'] = grants_data
                return data
    
    print(f"Warning: No data found for {faculty_name} in scholar_data")
    return None

def generate_personal_statement(research_interests):
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {"role": "system", "content": "You are a professional biosketch writer. Create a concise, impactful personal statement based on the research interests provided."},
                {"role": "user", "content": f"Create a personal statement based on these research interests: {research_interests}"}
            ],
            temperature=0.7,
            max_tokens=200
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error generating personal statement: {str(e)}")
        return ""

def generate_cdtr_relationship(research_interests):
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {"role": "system", "content": "You are a professional biosketch writer. Create a concise statement about how the research relates to the CDTR mission of advancing diabetes research and translation."},
                {"role": "user", "content": f"Create a statement about how these research interests relate to diabetes research and translation: {research_interests}"}
            ],
            temperature=0.7,
            max_tokens=200
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error generating CDTR relationship: {str(e)}")
        return ""

def build_core_usage_narrative(core_usage):
    sentences = []
    # Translational Design & Intervention Core
    td = core_usage.get('translational_design', {})
    if td.get('will_use'):
        usage = td.get('usage', '').strip()
        if usage:
            sentences.append(
                f"The Translational Design & Intervention Core ({TRANSLATIONAL_DESIGN_CORE_SUMMARY}) Faculty will collaborate as described: {usage}"
            )
    # Data Science & Analytics Core
    ds = core_usage.get('data_science', {})
    if ds.get('will_use'):
        usage = ds.get('usage', '').strip()
        if usage:
            sentences.append(
                f"The Data Science & Analytics Core ({DATA_SCIENCE_CORE_SUMMARY}) Faculty will collaborate as described: {usage}"
            )
    return " ".join(sentences)

def post_process_text(text):
    """Post-process text to replace flagged terms with approved alternatives."""
    replacements = {
        # Health equity related
        "health equity": "ensuring optimal health outcomes for all populations through targeted interventions",
        "underserved communities": "populations with limited access to healthcare and preventive services",
        "diversity, equity, and inclusion": "broad participation in research and healthcare solutions",
        "DEI": "broad participation in research and healthcare solutions",
        
        # Disparities related
        "health disparities": "health challenges affecting communities with limited access to healthcare and preventive services",
        "racial disparities": "differences in health outcomes across populations with varied access to care",
        "socioeconomic inequities": "the impact of economic and environmental factors on health access and outcomes",
        "historically marginalized communities": "communities with systemic barriers to healthcare access",
        
        # Diversity related
        "diverse populations": "populations with varied healthcare needs",
        "diverse communities": "communities with varied healthcare needs",
        "diverse backgrounds": "varied professional and research backgrounds",
        
        # Other flagged terms
        "vulnerable populations": "populations with limited access to healthcare and preventive services",
        "healthcare disparities": "differences in health outcomes across populations",
        "healthcare inequities": "differences in health outcomes across populations",
        "healthcare access gaps": "limited access to healthcare and preventive services",
        
        # Specific population terms
        "BIPOC": "populations experiencing higher burdens of cardiometabolic diseases",
        "Black and Latinx": "Black and Hispanic populations in the Deep South, who experience a higher burden of cardiometabolic diseases",
        "underrepresented investigators": "investigators from backgrounds with historically lower participation in health research",
        "multicultural": "engaging perspectives from multiple backgrounds to inform research"
    }
    
    # Process the text
    processed_text = text
    for flagged, replacement in replacements.items():
        processed_text = processed_text.replace(flagged, replacement)
    
    return processed_text

def generate_narrative_with_llm(data):
    profile = data.get('profile', {})
    core_usage = data.get('core_usage', {})
    # Build a compact JSON for the LLM prompt, excluding large arrays like 'publications'
    compact_data = {
        'profile': profile,
        'research_overview': data.get('research_overview', ''),
        'core_usage': core_usage,
        'recent_diabetes_grants': data.get('recent_diabetes_grants', [])[:3]  # Only 2-3 most recent grants
    }
    research_prompt = f"""
ARCH CDTR Mission: {ARCH_CDTR_MISSION}

LANGUAGE GUIDANCE (STRICTLY FOLLOW):
{LANGUAGE_GUIDANCE}

Researcher JSON:
{json.dumps(compact_data, indent=2)}

You are a scientific writer generating the 'Research and Relationship to CDTR Mission' section for a CDTR faculty profile. Write a concise, outcome-oriented narrative that:
- Is between 130 and 140 words in length.
- Describes the investigator's research focus, expertise, and impact, and how their work relates to the ARCH CDTR mission.
- Do NOT mention core usage, core names, or core aims in this section.
- Use only information present in the JSON.
- STRICTLY AVOID all flagged words and phrases. Use only the alternate terms and strategies provided above.
- Avoid flagged words (e.g., 'underserved,' 'equity,' etc.) and use 'precision public health' and 'populations with limited access to healthcare and preventive services' as appropriate.
- Match the style and length of this example:
Dr. Cherrington is a physician-scientist trained in community-engaged research methods, focusing on diabetes prevention and management in underserved communities with special emphasis on health disparities. Her research interests include patient-reported outcomes in diabetes and hypertension, and interventions that bridge community and health systems/population health. She specializes in interventions utilizing the Community Health Worker (CHW) model - an approach leveraging 'natural helpers' from within the community. As MPI of a large cluster-randomized trial, she studies the impact of CHWs and practice facilitation on hypertension control among African Americans across 69 practices in AL and NC. Dr. Cherrington has published extensively on diabetes-related research in over 46 scholarly journals and books, including contributions to the ADA's Standards of Diabetes Care. She serves as medical director of a multidisciplinary diabetes clinic in the county's safety net health system.
"""
    cdtr_activities_prompt = f"""
ARCH CDTR Mission: {ARCH_CDTR_MISSION}

LANGUAGE GUIDANCE (STRICTLY FOLLOW):
{LANGUAGE_GUIDANCE}

Researcher JSON:
{json.dumps(compact_data, indent=2)}

You are a scientific writer generating the 'CDTR Activities and Core Usage' section for a CDTR faculty profile. Synthesize a concise, outcome-oriented narrative that:
- Is approximately 100 words in length.
- Accurately describes the researcher's planned or ongoing activities with the CDTR cores, using all available information in the JSON.
- Clearly connects these activities to the ARCH CDTR mission and the relevant core(s) aims (see below).
- Do not invent or add information not present in the JSON.
- STRICTLY AVOID all flagged words and phrases. Use only the alternate terms and strategies provided above.
- Avoid flagged words (e.g., 'underserved,' 'equity,' etc.) and use 'precision public health' and 'populations with limited access to healthcare and preventive services' as appropriate.
- Keep the section direct and focused, similar in length and style to the example provided.

Core Missions/Aims:
Translational Design & Intervention Core: {TRANSLATIONAL_DESIGN_CORE_SUMMARY}
Data Science & Analytics Core: {DATA_SCIENCE_CORE_SUMMARY}
"""
    try:
        research_narrative = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {"role": "system", "content": "You are a scientific writer. Follow the user's instructions exactly. Do not invent or summarize."},
                {"role": "user", "content": research_prompt}
            ],
            temperature=0.0
        ).choices[0].message.content.strip()
        cdtr_activities = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {"role": "system", "content": "You are a scientific writer. Follow the user's instructions exactly. Do not invent or summarize."},
                {"role": "user", "content": cdtr_activities_prompt}
            ],
            temperature=0.0
        ).choices[0].message.content.strip()
        
        # Post-process both narratives
        research_narrative = post_process_text(research_narrative)
        cdtr_activities = post_process_text(cdtr_activities)
        
        return research_narrative, cdtr_activities
    except Exception as e:
        print(f"Error generating narratives: {e}")
        research_text = profile.get('bio', '') or profile.get('researchInterests', '') or data.get('research_overview', '') or ""
        cdtr_text = build_core_usage_narrative(core_usage)
        return research_text, cdtr_text

def get_research_section(data):
    """Generate only the research section as a single synthesized narrative."""
    if not data:
        return "No research data available.\n"
    research_narrative, _ = generate_narrative_with_llm(data)
    section = "Research and Relationship to CDTR Mission\n"
    section += research_narrative + "\n"
    return section

def get_header(data):
    """Generate the header section of the biosketch."""
    profile = data['profile']
    name = f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip()
    
    # Get institutional information from the most recent appointment
    institutional_info = {}
    if 'institutionalAppointments' in profile and profile['institutionalAppointments']:
        # Sort by start date, most recent first
        sorted_appointments = sorted(
            profile['institutionalAppointments'],
            key=lambda x: x.get('startDate', {}).get('dateTime', ''),
            reverse=True
        )
        latest_appointment = sorted_appointments[0]
        institutional_info = latest_appointment.get('institution', {})
    
    # Extract credentials from multiple possible locations
    credentials = set()
    
    # Check direct credentials field first
    if 'credentials' in profile and profile['credentials']:
        credentials.add(profile['credentials'])
    
    # Check degrees array
    if 'degrees' in profile:
        # Filter for doctoral and master's degrees
        doctoral_degrees = set()
        other_degrees = set()
        
        for degree in profile['degrees']:
            degree_name = degree.get('name', '').upper()
            # Check for various forms of doctoral degrees
            if any(x in degree_name for x in [
                'PH.D.', 'DOCTOR OF PHILOSOPHY', 'DOCTOR OF MEDICINE', 'M.D.',
                'DOCTOR OF MEDICINE & SURGERY', 'DOCTOR OF MEDICINE AND SURGERY'
            ]):
                doctoral_degrees.add(degree_name)
            # Check for various forms of master's degrees
            elif any(x in degree_name for x in [
                'MASTER', 'MPH', 'MS', 'M.S.', 'M.A.', 'MA', 'M.P.H.'
            ]):
                other_degrees.add(degree_name)
        
        # Format doctoral degrees with periods
        for degree in doctoral_degrees:
            if any(x in degree for x in ['PH.D.', 'DOCTOR OF PHILOSOPHY']):
                credentials.add('Ph.D.')
            elif any(x in degree for x in ['DOCTOR OF MEDICINE', 'M.D.', 'DOCTOR OF MEDICINE & SURGERY', 'DOCTOR OF MEDICINE AND SURGERY']):
                credentials.add('M.D.')
        
        # Format other degrees without periods
        for degree in other_degrees:
            if 'MPH' in degree or 'M.P.H.' in degree:
                credentials.add('MPH')
            elif 'MS' in degree or 'M.S.' in degree:
                credentials.add('MS')
            elif 'MA' in degree or 'M.A.' in degree:
                credentials.add('MA')
    
    # Check academic appointments for additional credentials
    if 'academicAppointments' in profile:
        for appointment in profile['academicAppointments']:
            position = appointment.get('position', '').upper()
            if 'PH.D.' in position or 'DOCTOR OF PHILOSOPHY' in position:
                credentials.add('Ph.D.')
            elif 'M.D.' in position or 'DOCTOR OF MEDICINE' in position:
                credentials.add('M.D.')
    
    # Custom sorting function to ensure Ph.D. and M.D. come first
    def credential_sort(cred):
        if cred == 'Ph.D.':
            return 0
        elif cred == 'M.D.':
            return 1
        else:
            return 2
    
    # Join credentials with commas, using custom sort
    credentials_str = ', '.join(sorted(credentials, key=credential_sort)) if credentials else ''
    
    # Get position and department
    position = profile.get('positions', [{}])[0].get('position', '')
    department = profile.get('positions', [{}])[0].get('department', '')
    
    # Get institutional details
    organization = institutional_info.get('organisation', '')
    suborganization = institutional_info.get('subOrganisation', '')
    city = institutional_info.get('city', '')
    state = institutional_info.get('state', '')
    
    # Construct the header
    header = []
    if credentials_str:
        header.append(f"{name}, {credentials_str}")
    else:
        header.append(name)
    
    if position:
        header.append(position)
    
    if department:
        header.append(department)
    
    if suborganization:
        header.append(suborganization)
    
    if organization:
        header.append(organization)
    
    if city and state:
        header.append(f"{city}, {state}")
    
    return '\n'.join(header)

def determine_and_narrate_core_usage_with_llm(data):
    """LLM determines core usage booleans and drafts narrative for each core marked true."""
    compact_data = dict(data)  # Use all JSON contents
    prompt = f"""
ARCH CDTR Mission: {ARCH_CDTR_MISSION}

Faculty JSON:
{json.dumps(compact_data, indent=2)}

Core Aims:
Translational Design & Intervention Core: {TRANSLATIONAL_DESIGN_CORE_SUMMARY}
Data Science & Analytics Core: {DATA_SCIENCE_CORE_SUMMARY}

You are a scientific writer generating the 'CDTR Activities and Core Usage' section for a CDTR faculty profile. Read all the JSON contents and the aims of both cores. For each core, determine if it is appropriate for the investigator to use it (ideally at least one, and both if appropriate). For each core marked true, draft a concise, outcome-oriented narrative (2–4 sentences) describing how the investigator will use that core, referencing their research and the core's aims. Output the booleans for each core and the narrative(s) in the style of this example:
As Director of the Rural Health Core, Dr. Cherrington will work closely with CDTR leadership to ensure smooth operation of the center and related cores. The Rural Health Core will continue to build relationships among the CDTR Member Base and grow new research partnerships through the Deep South Regional CDTR Collaborative. Her work can be enhanced through collaborations with the Translational Design & Intervention Core for implementing community-based interventions, and with the Data Science & Analytics Core for evaluating outcomes in underserved populations.

Format your response as:
Translational Design & Intervention Core: true/false
Data Science & Analytics Core: true/false

Narrative:
[Your narrative for each core marked true, combined in a single section.]
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {"role": "system", "content": "You are a scientific writer. Follow the user's instructions exactly. Do not invent or summarize."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0
        ).choices[0].message.content.strip()
        # Parse booleans and narrative
        lines = response.splitlines()
        core_bools = {}
        narrative_lines = []
        in_narrative = False
        for line in lines:
            l = line.strip()
            if l.lower().startswith('translational design & intervention core:'):
                core_bools['translational'] = 'true' in l.lower()
            elif l.lower().startswith('data science & analytics core:'):
                core_bools['data_science'] = 'true' in l.lower()
            elif l.lower().startswith('narrative:'):
                in_narrative = True
            elif in_narrative:
                narrative_lines.append(line)
        narrative = '\n'.join(narrative_lines).strip()
        return core_bools, narrative
    except Exception as e:
        print(f"Error determining and narrating core usage: {e}")
        return {'translational': False, 'data_science': False}, "No core usage is currently recommended based on the investigator's research focus."

def is_diabetes_related(grant):
    """Determine if a grant is diabetes-related based on keywords in the title, description, or labels."""
    diabetes_keywords = [
        # Core diabetes terms
        "diabetes", "diabetic", "glucose", "insulin", "metabolic", "obesity", "weight", 
        "glycemic", "HbA1c", "A1C", "prediabetes", "type 1", "type 2", "T1D", "T2D",
        "metabolic syndrome", "cardiometabolic", "cardiovascular", "hypertension",
        "blood pressure", "cholesterol", "lipid", "dyslipidemia", "prevention",
        "lifestyle", "diet", "nutrition", "physical activity", "exercise", "weight loss",
        "bariatric", "gastric bypass", "metabolic surgery", "gestational diabetes",
        "GDM", "complications", "retinopathy", "nephropathy", "neuropathy",
        "foot care", "wound healing", "amputation", "kidney disease", "renal",
        "cardiovascular disease", "heart disease", "stroke", "peripheral vascular",
        
        # Related conditions and complications
        "inflammation", "inflammatory", "immune", "autoimmune", "metabolic disorder",
        "endocrine", "hormone", "pancreas", "pancreatic", "beta cell", "beta-cell",
        "insulin resistance", "insulin sensitivity", "glucose tolerance",
        "glucose metabolism", "glucose homeostasis", "glucose regulation",
        "glycemic control", "glycemic index", "glycemic load",
        
        # Treatment and management
        "treatment", "therapy", "therapeutic", "intervention", "management",
        "medication", "drug", "pharmaceutical", "clinical trial", "trial",
        "prevention", "preventive", "screening", "early detection", "risk factors",
        "behavioral", "psychosocial", "quality of life", "patient outcomes",
        
        # Research and healthcare
        "health services", "healthcare delivery", "implementation science",
        "translational research", "community health", "primary care",
        "chronic disease", "comorbidity", "multimorbidity", "population health",
        "public health", "preventive care", "health outcomes", "health research"
    ]
    
    # Get all text fields from the grant
    text_fields = [
        grant.get('title', ''),
        grant.get('funderName', ''),
        grant.get('description', ''),
        grant.get('abstract', ''),
        grant.get('keywords', ''),
        grant.get('objectTypeDisplayName', ''),
        ' '.join([l.get('value', '') for l in grant.get('labels', [])])
    ]
    
    # Combine all text and convert to lowercase
    text = ' '.join(str(field) for field in text_fields if field).lower()
    print(f"\nDEBUG: Checking grant: {grant.get('title', '')}")
    print(f"DEBUG: Combined text: {text}")
    
    # Check for any diabetes-related keywords
    is_related = any(keyword.lower() in text for keyword in diabetes_keywords)
    if is_related:
        print(f"DEBUG: Found diabetes-related keywords in grant")
    return is_related

def get_active_grants(data):
    """Generate the Active Grants section using the 3 most recent diabetes-related grants from the full grants array."""
    grants = get_recent_diabetes_grants_from_all(data.get('grants', []))
    if not grants:
        return "Active Grants\nNo diabetes-related grant data available.\n"
    section = "Active Grants\n"
    for grant in grants:
        title = grant.get('title', 'No title')
        funder = grant.get('funderName', 'Unknown funder')
        start = grant.get('date1', {}).get('dateTime') or grant.get('startDate', '')
        section += f"- {title} ({funder}, {start})\n"
    return section

def get_recent_diabetes_grants_from_all(grants_data):
    """Get the most recent diabetes-related grants from all grants data."""
    print(f"DEBUG: Starting get_recent_diabetes_grants_from_all with {len(grants_data)} grants")
    
    # First, normalize grant titles and group similar grants
    normalized_grants = {}
    for grant in grants_data:
        # Get the base title by removing common suffixes
        title = grant.get('title', '').strip()
        base_title = title
        for suffix in [' - Behavioral Science and Analytics', ' - Methodologic Core', 
                      ' - HIV Pilot Extension', ' - Freedom Plus']:
            if title.endswith(suffix):
                base_title = title[:-len(suffix)]
                break
        
        # Get the start date
        start_date = grant.get('date1', {}).get('dateTime') or grant.get('startDate', '')
        if not start_date:
            continue
            
        # If we haven't seen this base title before, or if this grant is more recent
        if base_title not in normalized_grants or start_date > normalized_grants[base_title]['startDate']:
            normalized_grants[base_title] = {
                'grant': grant,
                'startDate': start_date,
                'original_title': title
            }
    
    # Convert back to list of unique grants
    unique_grants = [data['grant'] for data in normalized_grants.values()]
    print(f"DEBUG: After deduplication: {len(unique_grants)} unique grants")
    
    # Filter for diabetes-related grants
    diabetes_grants = []
    for grant in unique_grants:
        if is_diabetes_related(grant):
            print(f"DEBUG: Found diabetes-related grant: {grant.get('title', '')}")
            diabetes_grants.append(grant)
    
    print(f"DEBUG: Found {len(diabetes_grants)} diabetes-related grants")
    
    # Sort by start date (most recent first)
    diabetes_grants.sort(key=lambda x: x.get('date1', {}).get('dateTime') or x.get('startDate', ''), reverse=True)
    
    # Return the 3 most recent grants
    return diabetes_grants[:3]

def generate_biosketch_txt(faculty_name):
    """Generate a complete biosketch for a faculty member."""
    data = load_json_data(faculty_name)
    if not data:
        return
    # Generate sections
    header = get_header(data)
    research = get_research_section(data)
    core_bools, cdtr_activities = determine_and_narrate_core_usage_with_llm(data)
    core_usage_lines = []
    core_usage_lines.append(f"Translational Design & Intervention Core: {str(core_bools.get('translational', False)).lower()}")
    core_usage_lines.append(f"Data Science & Analytics Core: {str(core_bools.get('data_science', False)).lower()}")
    core_usage = "\n".join(core_usage_lines) + "\n"
    active_grants = get_active_grants(data)
    # Write to file
    outdir = 'output_bios'
    os.makedirs(outdir, exist_ok=True)
    with open(f"{outdir}/{faculty_name} biosketch.txt", 'w') as f:
        f.write(header + "\n\n")  # Add extra line break after header
        f.write(research + "\n")
        f.write("Core Usage\n")
        f.write(core_usage + "\n")
        f.write("CDTR Activities and Core Usage\n")
        f.write(cdtr_activities + "\n\n")  # Add extra line break before active grants
        f.write(active_grants)

def main():
    """Main function to process all members from cdtr members.csv."""
    csv_file = "cdtr members.csv"
    with open(csv_file, 'r') as f:
        reader = csv.reader(f)
        next(reader)  # Skip header
        for row in reader:
            faculty_name = row[0].strip()
            print(f"Generating biosketch for {faculty_name}")
            generate_biosketch_txt(faculty_name)
    print("Done.")

if __name__ == "__main__":
    main() 