# Overall Client Workflow for Stability 360

## Client Entry Points

The client can initiate contact through multiple channels:

- **"Kiosks"** — Universal Intake Form, interaction via chatbot
- **Call**
- **Text**
- **Website**

---

## Two Primary Paths

### Referral Path (Light Touch)

1. **Provide client with referral info** (via API to 211 hotline)
2. **Follow-Up with client** to see if Basic Need is Addressed
3. If client needs/wants further assistance → route to **Direct Support**

### Direct Support Path (High Touch)

1. **Client speaks with live agent** (TUW Coalition Partners)
2. **Client performs assessment with live agent**
3. **Client and provider complete programming**
4. **Follow-Up until financial stability reached**

- Live agents input client notes and goals
- Data feeds into **TUW Coalition partners' CRM systems**

---

## Data Lake

- Constantly Saving and Sharing Data to remember clients and analyze historical data for trends
- Receives data from both paths and CRM systems

---

## Running Definitions

**Referral** = Services a case manager would be okay with a client seeking on their own. Referrals will just fill out the short intake form and sent referrals.

**Direct Support** = Services a case manager would like to help support clients with. Direct Supports will fill out an extended form and set up an appointment with a case manager.

**TUW Coalition Partners** = TUW has convened a group of nonprofit and quasi-government organizations to work collaboratively through aligned services, shared data, joint funding opportunities, and other coordinated support. Currently there are 12 organizations participating in the coalition and will be participating as live agents.

**Assessment** = TUW uses a tool (Self-Sufficiency Matrix) to measure a client's financial stability at that point in time. This tool is twofold: 1) to help the live agent assess the client's immediate goals and 2) to help evaluate a client's upward mobility long-term.

**211 Hotline** = a free, confidential, and 24/7 information and referral service that connects South Carolinians to essential health and human services. Can access here: https://www.sc211.org/#/

**CRM Systems** = TUW Coalition Partners use multiple different CRM systems to input and track client data and case management notes. The primary CRM system used in TUW's service area is CharityTracker.

**Data Lake** = an interface that will track incoming data from the universal intake form as well as data from CRM systems.

---

## Key Features of Solution

**Universal Intake Form:** The intake form will appear simple and easy to use on the user side with minimal invasive questions and accessible through multiple omnichannels. On the backend, there will be a logic model the AI solution follows to figure out what program(s) would be most suitable for the client.

**Data Repository:** All data collected in 211 and CharityTracker will be stored in one location and AI will analyze the data together to help with providing referrals to clients. The solution will house all organizations, their programs, eligibility requirements, client profiles, service outcomes, and availability of nonprofit resources. From this, AI can make informed decisions on referrals while analyzing client and service patterns at the community and organization level.

**Client & Case Manager Assistant:** The solution will be able to schedule meetings with clients and direct service providers, refer clients to services, follow-up with clients, and proactively suggest new services to clients based off previous services. On the other hand, the solution will support the case manager in finding/recommending services for the clients, reminders about meetings/when to contact clients, answer questions via chatbot, and provide insights based off historical trends.

---

## Decision-Making Trees Associated with Overall Workflow

### Referral / Direct Support Split

**Reference:** Appendix A, Appendix B

**Deciding Factor:** Client answers the question: **VA = How can I help you today? Please check all that apply. (Appendix A)** Once the client has chosen their subcategories, chatbot will reference Appendix B and place client down the referral or direct support path.

### Direct Support Intake

**Reference:** Appendix A, Appendix B

Before meeting with a direct service provider, a client will fill out an intake form, Appendix A, all questions below the prompt: **VA = Please answer the questions below so I can connect you with the most helpful services for your needs.**

**Deciding Factor:** These questions focus on major eligibility guidelines for nonprofit services. By answering these questions, the chatbot can determine what potential programs the client may be eligible for, which will be presented to the direct service provider for confirmation prior to meeting the client. An example for how the chatbot can determine if a client is eligible for TUW's services can be found at Appendix B.

### Client Assessment with Direct Service Provider

**Reference:** Appendix C

When meeting with a client for the first time, the direct service provider will use the screening questions (Appendix C) to score a client on the self-sufficiency matrix. The Self-Sufficiency Matrix is a standard tool to assess a client's financial stability.

**Deciding Factor:** TBD. This tool is primarily to show upward economic mobility for clients. At the start the clients' self-sufficiency status may help determine what level of services they need at the moment and their immediate goals.

---
---

## Appendix A – Intake Logic Branching

Virtual Assistant = VA
-> = branching in questions

**VA = Hello! To get started, could you please tell me your name?**

> *Comment [NL1]: Things to note: on the chatbot, has to remember person. Put name first.*

**VA = How can I help you today? Please check all that apply.**

> *Comment [NL2]: after answering this question, AI will make decision of referral services or direct services. referral will have condensed intake, direct will have longer intake*

> *Comment [NL3R2]: Q - if client selects multiple referrals or if client selects a referral and direct service, where are they navigated to?*

> *Comment [NL4R2]: Q - what is the least amount of info needed to make an accurate referral? in 211 just need zipcode and need area but that leads to a large pool of options - how can we shorten the list of possibilities with the least amount of questions?*

**Housing** -> Rental Assistance, Utilities, Housing Repairs, Mortgage Assistance, Eviction, Shelter, Homelessness, Other

**Transportation** -> Car Payments and Insurance, Car Repairs, Bus Tickets, Driver's Education, Gas, Ride-Sharing, Other

**Food** -> Food Pantries, Baby Food, Application Assistance for SNAP, WIC, Nutritional Assistance, Other

**Health** -> Medical and Prescription Bills, Dental Appointments, Free Clinics, Urgent Care, Health Screenings, Counseling and Mental Health Services, Substance Abuse Treatment, Other

**Child Care** -> Child Care Subsidies, After School Programs, School Supplies, Developmental Screenings, Other

**Disaster** -> Disaster Relief, Disaster Recovery, Disaster Shelter, Disaster Preparedness

**Employment and Education** -> Job Training, Unemployment Services, GED and Other Adult Education, Job Search, College and Trade Schools, English as a Second Language, Other

**Legal Aid** -> Immigration Legal Assistance, Eviction Prevention, Elder Law, Family Law, Discrimination Legal Assistance, Heirs Property, Other

**Financial Literacy** -> Budgeting Courses, Debt Reduction, Asset Building, Banking Assistance, Other

**Hygiene** -> Clothing, Diapers, Showers, Other

**Other** -> \*\*After all others, there will be the option for short answer\*\*

**VA = Are there any other details you would like to provide on how I can best support you?**

*\*opportunity for long answer\**

**VA = Please answer the questions below so I can connect you with the most helpful services for your needs.**

> *Comment [NL5]: Full intake form for direct support*

> *Comment [NL6R5]: Is household income needed to ensure most accurate eligibility?*

**What ZIP code do you live in?** -> generates county

> *Comment [NL7]: Separate county Q*

> *Comment [NL8R7]: \*how to be redirected out of service area? Is/ employees?*

**How would you like to be contacted?**

- Call -> phone number
- Text -> phone number
- Email -> email

**Which day(s) are you available to be contacted? Please check all that apply.**

Monday, Tuesday, Wednesday, Thursday, Friday

**What time(s) of day are you available to be contacted? Please check all that apply.**

8AM, 9AM, 10AM, 11AM, 12PM, 1PM, 2PM, 3PM, 4PM, 5PM, 6PM, 7PM

> *Comment [NL9]: Make more general (weekends/weekdays, morning/nights)*

**What is your age?**

**Do you have children under 18 living at home?**

- YES
- NO

**What is your current employment status?**

- Employed full-time -> Who is your current employer?
- Employed part-time -> Who is your current employer?

> *Comment [NL10]: Able to list multiple positions*

- Self-employed
- Unemployed
- Looking for work
- Not looking for work
- Retired
- Student
- Unable to work

**Do you have a military or service affiliation?**

- Veteran of U.S. Armed Forces (prior service)
- Currently serving — Active Duty
- Currently serving — Reserve / National Guard
- First Responder (law enforcement, fire, EMS)
- None of the above
- Prefer not to answer

**Do you or anyone in your household currently receive any of the following types of public assistance? Please check all that apply.**

- SNAP (Food Stamps)
- WIC (Women, Infants, and Children)
- Family Independence (TANF)
- Medicaid or CHIP (Healthy Connections)
- SSI or SSDI (Disability Benefits)
- None
- Other

> *Comment [NL11]: What if someone is not on call? Receive referrals?*

> *Comment [NL12R11]: Schedule call back?*

---
---

## Appendix B – Questions That Lead to AI Decision-Making

> Note: Will only show branches for TUW funding when an eligibility restriction is decided upon.

### ZIP Code → County → Agency Routing

```
ZIP Code
  └→ Generate County
       ├→ Berkeley County → Eligible for Santee Cooper Basic Needs, BRCC Basic Needs
       ├→ Charleston County → Eligible for NCRCC & CRCC Basic Needs, Rental Reserve
       └→ Dorchester County → Eligible for DRCC Basic Needs
```

AI will filter first through agencies within the client's county for the service they need. Priority will be given to a different agency outside of the client's county if it is closer to the zip code listed.

→ Eligible for Help of Summerville (cross-county)

---

### "How Can We Help You Today?" – Referral vs Direct Support Branching

*Color Key:*
- 🔴 `[REFERRAL]` = Referral Path (Light Touch / Self-Directed)
- 🟠 `[DIRECT SUPPORT]` = Direct Support Path (High Touch / Case Managed)

```
How Can We Help You Today?
│
├── Housing ─────────────────────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│   ├── Rental Assistance ──────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│   ├── Shelter ────────────────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│   ├── Homelessness ───────────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│   ├── Eviction Prevention ────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│   ├── Housing Repairs ────────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│   └── Utilities ──────────────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│       └── → Eligible for Help of Summerville
│
├── Transportation
│   ├── Bus Tickets ────────────────────────────────────────────── 🔴 [REFERRAL]
│   ├── Driver's Education ─────────────────────────────────────── 🔴 [REFERRAL]
│   ├── Gas ────────────────────────────────────────────────────── 🔴 [REFERRAL]
│   ├── Ride-Sharing ───────────────────────────────────────────── 🔴 [REFERRAL]
│   ├── Car Payments/Insurance ─────────────────────────────────── 🟠 [DIRECT SUPPORT]
│   ├── Car Repairs ────────────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│   └── Car Down Payments ──────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│
├── Food
│   ├── Food Pantries ──────────────────────────────────────────── 🔴 [REFERRAL]
│   ├── Food Distributions ─────────────────────────────────────── 🔴 [REFERRAL]
│   ├── Baby Food ──────────────────────────────────────────────── 🔴 [REFERRAL]
│   ├── SNAP/WIC Application Assistance ────────────────────────── 🟠 [DIRECT SUPPORT]
│   └── Nutritional Counseling ─────────────────────────────────── 🟠 [DIRECT SUPPORT]
│
├── Health
│   ├── Dental Appointments ────────────────────────────────────── 🔴 [REFERRAL]
│   ├── Free Clinics ───────────────────────────────────────────── 🔴 [REFERRAL]
│   ├── Urgent Care ────────────────────────────────────────────── 🔴 [REFERRAL]
│   ├── Health Screenings ──────────────────────────────────────── 🔴 [REFERRAL]
│   ├── Medical and Prescription Bills ─────────────────────────── 🟠 [DIRECT SUPPORT]
│   ├── Counseling/Mental Health ───────────────────────────────── 🟠 [DIRECT SUPPORT]
│   └── Substance Abuse ────────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│
├── Child Care
│   ├── After School Programs ──────────────────────────────────── 🔴 [REFERRAL]
│   ├── School Supplies ────────────────────────────────────────── 🔴 [REFERRAL]
│   └── Child Care Subsidies ───────────────────────────────────── 🟠 [DIRECT SUPPORT]
│
├── Disaster
│   ├── Disaster Recovery ──────────────────────────────────────── 🔴 [REFERRAL]
│   ├── Disaster Shelter ───────────────────────────────────────── 🔴 [REFERRAL]
│   ├── Disaster Preparedness ──────────────────────────────────── 🔴 [REFERRAL]
│   └── Disaster Financial Relief ──────────────────────────────── 🟠 [DIRECT SUPPORT]
│
├── Employment/Education
│   ├── GED/Adult Education ────────────────────────────────────── 🔴 [REFERRAL]
│   ├── College/Trade Schools ──────────────────────────────────── 🔴 [REFERRAL]
│   ├── ESL ────────────────────────────────────────────────────── 🔴 [REFERRAL]
│   ├── Job Training ───────────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│   ├── Unemployment Services ──────────────────────────────────── 🟠 [DIRECT SUPPORT]
│   └── Job Search ─────────────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│       └── → Eligibility for Barriers to Employment
│
├── Legal Aid ──────────────────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│   ├── Immigration Legal Assistance ───────────────────────────── 🟠 [DIRECT SUPPORT]
│   ├── Eviction Prevention ────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│   ├── Elder Law ──────────────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│   ├── Family Law ─────────────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│   ├── Discrimination Legal Assistance ────────────────────────── 🟠 [DIRECT SUPPORT]
│   └── Heirs Property ────────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│
├── Financial Literacy ─────────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│   ├── Budgeting Courses ──────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│   ├── Debt Reduction ─────────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│   ├── Asset Building ─────────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│   └── Banking Assistance ─────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│
├── Hygiene ────────────────────────────────────────────────────── 🔴 [REFERRAL]
│   ├── Clothing ───────────────────────────────────────────────── 🔴 [REFERRAL]
│   ├── Diapers ────────────────────────────────────────────────── 🔴 [REFERRAL]
│   └── Showers ────────────────────────────────────────────────── 🔴 [REFERRAL]
│
└── Other
    └── [BEST CASE JUDGMENT] Will use best case judgement based
        off how other things are sorted. Will become better once
        more historical data on what falls in the "Other" category.
```

---

### Current Employment Status → Eligibility Routing

```
Current Employment Status
│
├── Employed Full-Time/Part-Time ───────────────────────────────── 🔴 [ELIGIBILITY CHECK]
│   └── Who is Your Current Employer?
│       └── IF ESP employer → eligible for funding
│
├── Unemployed ─────────────────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│   └── Note: Employment Services Needed
│
├── Looking for Employment ─────────────────────────────────────── 🟠 [DIRECT SUPPORT]
│   └── Eligible for Barriers to Employment
│
├── Self-Employed ──────────────────────────────────────────────── 🔵 [NOTES/PATHWAYS TBD]
├── Not Looking for Work ───────────────────────────────────────── 🔵 [NOTES/PATHWAYS TBD]
├── Retired ────────────────────────────────────────────────────── 🔵 [NOTES/PATHWAYS TBD]
├── Student ────────────────────────────────────────────────────── 🔵 [NOTES/PATHWAYS TBD]
└── Unable to Work ─────────────────────────────────────────────── 🔵 [NOTES/PATHWAYS TBD]
```

> *Note: Self-Employed, Not Looking for Work, Retired, Student, and Unable to Work currently have no defined pathways — Notes/Pathways for these are TBD.*

---

### Age → Eligibility Routing

```
Age
│
├── 65+ ────────────────────────────────────────────────────────── 🔴 [ELIGIBILITY MATCH]
│   └── Eligible for BCDCOG
│
└── 65 Below ───────────────────────────────────────────────────── 🔵 [PATHWAYS TBD]
```

---

### Children at Home → Eligibility Routing

```
Children at Home
│
├── Yes ────────────────────────────────────────────────────────── 🔴 [ELIGIBILITY MATCH]
│   └── Eligible for Siemer / Rental Reserve
│
└── No ─────────────────────────────────────────────────────────── 🔵 [PATHWAYS TBD]
```

---

### Military Affiliation → Eligibility Routing

```
Military Affiliation
│
├── Veteran ────────────────────────────────────────────────────── 🔴 [ELIGIBILITY MATCH]
│   └── Eligible for Mission United, other veteran services
│
├── Currently Serving (Active Duty) ────────────────────────────── 🔴 [ELIGIBILITY MATCH]
│   └── Eligible for Mission United, other veteran services
│
├── Currently Served (Reserve) ─────────────────────────────────── 🔴 [ELIGIBILITY MATCH]
│   └── Eligible for Mission United, other veteran services
│
├── First Responder ────────────────────────────────────────────── 🔵 [PATHWAYS TBD]
│
└── None of the Above / Prefer not to respond ──────────────────── 🔵 [PATHWAYS TBD]
```

---
---

## Appendix C: Self-Sufficiency Matrix + Associated Screening Questions

**Self-Sufficiency Matrix: Characteristics of Families with Different Levels of Financial Security**

> *\*Note: "Employed full-time or equivalent" implies that an individual is Employed full-time OR Retired OR Homemaker or caregiving full-time OR Unemployed and NOT currently looking for work OR Employed part-time and NOT actively looking for full-time work*

---

### HOUSING

| Score | Level | Criteria |
|-------|-------|----------|
| **1** | **Crisis** | Homeless or facing eviction |
| **2** | **Vulnerable** | Residing in temporary housing (i.e., in shelter or motel or with family or friends.) **OR** Spending more than 41% on monthly income on housing |
| **3** | **Stable** | Stable housing with or without subsidies **OR** Spending more than 35-40% on monthly income on housing **OR** At least 2 housing challenges |
| **4** | **Self-Sufficient** | Stable housing (rent without subsidies or own) **OR** Spending 31-35% of monthly income on housing **OR** At least 1 housing challenge |
| **5** | **Thriving** | Stable housing (rent without subsidies or own) **AND** Spending less than 30% of monthly income on housing **AND** No housing challenges |

---

### EMPLOYMENT

| Score | Level | Criteria |
|-------|-------|----------|
| **1** | **Crisis** | Unemployed and actively looking for work |
| **2** | **Vulnerable** | Employed part-time and actively looking for full-time work **OR** Employed in temporary or seasonal position |
| **3** | **Stable** | Employed full-time or equivalent\* **OR** Income below the self-sufficiency standard for household configuration **OR** Few or no benefits |
| **4** | **Self-Sufficient** | Employed full-time or equivalent\* **AND** Income above the self-sufficiency standard for household configuration **AND** Access to affordable benefits for entire household |
| **5** | **Thriving** | Employed full-time or equivalent\* for at least 6 months **AND** Income more than 10% above the self-sufficiency standard for household configuration **AND** Access to affordable benefits for entire household |

---

### FINANCIAL RESILIENCE

| Score | Level | Criteria |
|-------|-------|----------|
| **1** | **Crisis** | Monthly expenses exceed income **AND** No savings or ability to handle financial emergency |
| **2** | **Vulnerable** | Monthly income is sufficient to cover expenses **AND** No savings or ability to handle financial emergency |
| **3** | **Stable** | Monthly income is sufficient to cover expenses AND occasional non-essentials **AND** Limited savings of 1-4% monthly **AND** FICO score exceeding 620 |
| **4** | **Self-Sufficient** | Monthly income is sufficient to cover expenses AND non-essentials **AND** Savings of 5%+ monthly **AND** FICO score exceeding 740 |
| **5** | **Thriving** | Monthly expenses exceed income **AND** No savings or ability to handle financial emergency |

---

### Decision Logic Summary (for Agentic AI)

```
SCORING RULES:
  Score 1 (Crisis)          → Immediate escalation to Direct Support + priority routing
  Score 2 (Vulnerable)      → Direct Support recommended + employment/financial services flagged
  Score 3 (Stable)          → Direct Support or Referral based on specific need category
  Score 4 (Self-Sufficient) → Referral Path (Light Touch) unless client requests more help
  Score 5 (Thriving)        → Referral Path only if specific need identified

COMPOSITE SCORING:
  IF ANY domain = 1 (Crisis)       → overall flag as PRIORITY
  IF average score < 2.5           → recommend full Direct Support engagement
  IF average score 2.5 - 3.5       → mixed path (Direct Support for lowest domain, Referral for others)
  IF average score > 3.5           → Referral Path default
```

---

### Self-Sufficiency Matrix Questions

#### Initial Screening Questions

**Basic Housing and Income**

1. Which of the following best describes your current housing situation?
   - a. Homeless or facing eviction
   - b. Residing in temporary housing (i.e., in shelter or motel or with family or friends.)
   - c. Renting my home with the assistance of subsidies
   - d. Renting my home WITHOUT the assistance of subsidies
   - e. Own my home.
   - f. Other [Please specify]
2. What is your current monthly household income? [Numeric]

```
HOUSING SCORE MAPPING:
  Answer (a) → Score 1 (Crisis)
  Answer (b) → Score 2 (Vulnerable)
  Answer (c) → Score 3 (Stable)
  Answer (d) → Score 4 (Self-Sufficient) OR Score 5 (Thriving) — depends on income ratio
  Answer (e) → Score 4 (Self-Sufficient) OR Score 5 (Thriving) — depends on income ratio
  Answer (f) → Requires human review
```

---

#### Indicator Assessment Questions

**Household Characteristics**

1. What is the current configuration of your family? [e.g., Number of Adults, Teenagers, School-Aged Children, Toddlers, Infants, Seniors, etc.]
2. In which county do you currently reside? [Charleston, Berkeley, Dorchester]

```
COUNTY → AGENCY ROUTING:
  Charleston  → NCRCC, CRCC Basic Needs, Rental Reserve
  Berkeley    → Santee Cooper Basic Needs, BRCC Basic Needs
  Dorchester  → DRCC Basic Needs
```

---

**Housing**

1. How much is your household currently spending on housing per month (i.e., rent, mortgage, taxes, insurance, utilities)? [Numeric]
2. Are you currently experiencing any of the housing challenges related to the condition and/or location of your home? [Yes / No]
   - *Examples: Limited or no access to a functional kitchen, working bathroom, heating, cooling, or electricity; Overcrowding; Unsafe location; Unreasonably long or difficult commute.*

```
HOUSING SCORE CALCULATION:
  housing_ratio = monthly_housing_cost / monthly_household_income

  IF homeless OR facing eviction                          → Score 1 (Crisis)
  IF temporary housing OR housing_ratio > 0.41            → Score 2 (Vulnerable)
  IF housing_ratio 0.35–0.40 OR housing_challenges >= 2   → Score 3 (Stable)
  IF housing_ratio 0.31–0.35 OR housing_challenges == 1   → Score 4 (Self-Sufficient)
  IF housing_ratio < 0.30 AND housing_challenges == 0     → Score 5 (Thriving)
```

---

**Employment**

1. Which of the following best describes your current employment situation?
   - a. Homemaker or caregiving full-time
   - b. Retired
   - c. Unemployed and NOT currently looking for work
   - d. Unemployed and actively looking for work
   - e. Employed part-time and NOT actively looking for full-time work
   - f. Employed part-time and actively looking for full-time work
   - g. Employed full-time
2. Is your role temporary or seasonal? [Yes/No]
3. Do you and/or your household currently have access to affordable benefits, including medical insurance and paid time off?
   - a. Yes, for the entire household
   - b. Yes, but only for some members of the household
   - c. No

```
EMPLOYMENT SCORE MAPPING:
  Answer (d)                                                → Score 1 (Crisis)
  Answer (f) OR (temporary/seasonal == Yes)                 → Score 2 (Vulnerable)
  Answer (a/b/c/e/g) AND income < self_sufficiency_std
    OR benefits == "No"                                     → Score 3 (Stable)
  Answer (a/b/c/e/g) AND income > self_sufficiency_std
    AND benefits == "Yes, entire household"                 → Score 4 (Self-Sufficient)
  Answer (a/b/c/e/g) AND employed >= 6 months
    AND income > 110% self_sufficiency_std
    AND benefits == "Yes, entire household"                 → Score 5 (Thriving)

  *Equivalent to full-time: answers (a), (b), (c), (e)
```

---

**Financial Resilience**

1. What are your current monthly expenses? [Numeric]
2. Approximately how much are you able to save each month? [Numeric]
3. What is your current FICO score? [Numeric / Don't know]

```
FINANCIAL RESILIENCE SCORE CALCULATION:
  savings_rate = monthly_savings / monthly_household_income

  IF monthly_expenses > monthly_income AND savings_rate == 0    → Score 1 (Crisis)
  IF monthly_income >= monthly_expenses AND savings_rate == 0   → Score 2 (Vulnerable)
  IF monthly_income >= monthly_expenses + some_non_essentials
    AND savings_rate 0.01–0.04 AND fico > 620                  → Score 3 (Stable)
  IF monthly_income >= monthly_expenses + non_essentials
    AND savings_rate >= 0.05 AND fico > 740                    → Score 4 (Self-Sufficient)
  IF monthly_income > monthly_expenses + non_essentials
    AND savings_rate >= 0.10 AND fico > 740                    → Score 5 (Thriving)
```
