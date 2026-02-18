# Stability360 — Manual Test Cases

Test cases for validating AI bot behavior through Amazon Connect chat.
Each test includes example messages a tester can send.

---

## Step 1: Thrive@Work Bot

### T1.1 — Employee Lookup (Valid ID)

**Example messages (pick any):**
- "I'd like to check my benefits. My employee ID is EMP-001."
- "Can you look up employee EMP-001?"
- "Hi, I work at one of your partner companies. My ID is EMP-001."
- "Check eligibility for employee ID EMP-001 please"

**Measures:**
- Whether the bot calls the employeeLookup tool
- Whether it returns the employer name and partnership status
- Whether eligible programs are listed
- Response tone and clarity

---

### T1.2 — Employee Lookup (Unknown ID)

**Example messages (pick any):**
- "My employee ID is FAKE-999"
- "Look up employee XYZ-000"
- "Can you check benefits for ID NOTREAL-123?"
- "I think my employee ID is 00000"

**Measures:**
- Whether the bot handles a non-matched employee gracefully
- Whether it suggests next steps (e.g., contact HR, verify ID)
- Whether it avoids exposing internal error details

---

### T1.3 — General Knowledge (KB Retrieval)

**Example messages (pick any):**
- "What is the Thrive@Work program?"
- "Tell me about Thrive at Work"
- "What services does Thrive@Work offer?"
- "How does the employee wellness program work?"
- "What benefits are available through Stability360?"

**Measures:**
- Whether the bot retrieves information from the knowledge base
- Whether the response is accurate to seeded KB content
- Response length and relevance

---

### T1.4 — Out-of-Scope Question

**Example messages (pick any):**
- "What's the weather today?"
- "Can you book me a flight to New York?"
- "Tell me a joke"
- "Who won the Super Bowl?"
- "What is the capital of France?"

**Measures:**
- Whether the bot stays within its domain
- Whether it redirects the user to relevant services
- Whether it avoids hallucinating answers

---

## Step 2: Stability360 Actions Bot (Aria)

### T2.1 — Consent Flow

**Example messages to start (pick any):**
- "I need help with housing"
- "Hi, I'm struggling to pay my bills"
- "I need assistance with rent"
- "Can you help me find resources?"
- "I'm looking for help with utilities"
- "I lost my job and need support"

**Measures:**
- Whether Aria asks for consent before collecting any personal data
- Whether it waits for an explicit "yes" before proceeding
- Whether NO tools are called before consent is given

---

### T2.2 — Consent Denial

**Start with any T2.1 message, then when asked for consent, reply:**
- "No"
- "I don't want to share my information"
- "No thanks, just give me general info"
- "I'd rather not"

**Measures:**
- Whether Aria respects the denial
- Whether it offers alternatives (general info, 211 resources)
- Whether it does not proceed with data collection

---

### T2.3 — Full Scoring Flow (Direct Support Path)

**Conversation sequence:**

| Turn | Example messages |
|------|-----------------|
| 1 — Ask for help | "I need help with housing" / "I'm about to lose my home" / "I need emergency assistance" |
| 2 — Give consent | "Yes" / "Sure, go ahead" / "Yes I consent" |
| 3 — Name | "My name is Maria Johnson" / "I'm David Smith" / "Sarah Williams" |
| 4 — Contact info | "My email is maria@email.com and phone is 803-555-1234" / "You can reach me at 803-555-0000" |
| 5 — Housing | "I'm homeless" / "I'm living in my car" / "I'm staying in a shelter" / "I have no stable housing" |
| 6 — Income | "I have no income" / "Zero dollars" / "$0 per month" / "I'm not earning anything right now" |
| 7 — Employment | "I'm unemployed" / "I don't have a job" / "I lost my job last month" / "Not working" |

**Measures:**
- Whether Aria collects ALL data before calling any tool
- Whether scoringCalculate is the FIRST tool called
- Whether it returns a priority flag for crisis-level inputs
- Whether it presents the recommended path (direct_support) and waits for client choice
- Whether there are NO blank messages during the flow

---

### T2.4 — Full Scoring Flow (Referral Path)

**Conversation sequence:**

| Turn | Example messages |
|------|-----------------|
| 1 — Ask for help | "I'd like to learn about available programs" / "What resources do you have?" |
| 2 — Give consent | "Yes" / "Sure" |
| 3 — Name | "John Anderson" / "My name is Lisa Park" |
| 4 — Contact info | "john@company.com, 803-555-9999" / "lisa.park@email.com" |
| 5 — Housing | "I own my home" / "Homeowner, no issues" / "I have a mortgage, everything is current" |
| 6 — Income | "$5000 per month" / "I make about $60,000 a year" / "My monthly income is around $5000" |
| 7 — Employment | "I work full time" / "I have a full-time job" / "Employed full time as an engineer" |

**Measures:**
- Whether scoring returns a high composite score
- Whether the recommended path is referral
- Whether Aria presents appropriate referral options
- Whether the tone matches a self-sufficient client

---

### T2.5 — Full Scoring Flow (Mixed Path)

**Conversation sequence:**

| Turn | Example messages |
|------|-----------------|
| 1 — Ask for help | "I need some help but I'm managing okay" / "I could use some support" |
| 2 — Give consent | "Yes" / "I agree" |
| 3 — Name | "Carlos Rivera" / "My name is Aisha Brown" |
| 4 — Contact info | "carlos.r@email.com, 803-555-4567" |
| 5 — Housing | "I'm renting, it's stable for now" / "I rent an apartment, no issues currently" |
| 6 — Income | "$2000 a month" / "About $2000" / "I bring in around $24,000 a year" |
| 7 — Employment | "I work part time" / "Part-time job at a retail store" / "I have a part-time position" |

**Measures:**
- Whether scoring returns a mid-range composite score
- Whether the recommended path is mixed
- Whether Aria presents both direct and referral options

---

### T2.6 — Case Submission

**After completing any scoring flow (T2.3, T2.4, or T2.5), when Aria presents options:**

**Example messages (pick any):**
- "Yes, connect me now"
- "I'd like to submit my case"
- "Please go ahead and create a case for me"
- "Yes, I want direct support"
- "Submit it please"
- "Let's proceed with the case"

**Measures:**
- Whether customerProfileLookup is called (one turn)
- Whether charityTrackerSubmit is called (next turn)
- Whether a case reference number is returned to the client
- Whether an email is sent (check inbox)
- Whether there are NO blank messages between tool calls

---

### T2.7 — Case Status Lookup

**Example messages (pick any):**
- "I want to check my case status. My reference is CS-20260218-AB12"
- "Can you look up case CS-20260218-AB12?"
- "What's the status of my case? The number is CS-20260218-AB12"
- "I submitted a case last week, the reference is CS-20260218-AB12"
- "Check on case CS-20260218-AB12 for me"

*(Replace CS-20260218-AB12 with an actual case reference from T2.6)*

**Measures:**
- Whether the caseStatusLookup tool is called
- Whether the case status and description are returned
- Whether no consent is required for status checks

---

### T2.8 — Resource Lookup (by County)

**Example messages (pick any):**
- "I need food assistance in Richland County"
- "What food banks are in Lexington County?"
- "Find me housing help in Greenville County"
- "Are there any utility assistance programs in Charleston County?"
- "Show me shelters in Spartanburg County"
- "I need help with childcare in York County"
- "What mental health resources are available in Richland County?"

**Measures:**
- Whether the resourceLookup tool is called
- Whether providers are returned with name, phone, address
- Whether results are filtered by the specified county
- Whether the bot formats results clearly

---

### T2.9 — Resource Lookup (by ZIP Code)

**Example messages (pick any):**
- "What housing resources are available near 29201?"
- "Find food banks near ZIP code 29063"
- "I live in 29223, what help is nearby?"
- "Are there any job training programs near 78666?"
- "Show me resources near 29201"
- "I need help near 29036"

**Measures:**
- Whether the bot passes the ZIP code to resourceLookup
- Whether results are relevant to the area
- Whether multiple providers are returned

---

### T2.10 — Resource Lookup (by Keyword)

**Example messages (pick any):**
- "I need help paying my electric bill"
- "Where can I get free meals?"
- "Are there any job training programs?"
- "I need help with prescription medications"
- "Where can I find free legal help?"
- "I need transportation assistance"
- "Are there any domestic violence shelters?"

**Measures:**
- Whether the bot extracts the keyword from natural language
- Whether results match the requested service type
- Whether the bot asks for location if not provided

---

### T2.11 — Follow-up Scheduling

**After completing a case submission (T2.6):**

**Example messages (pick any):**
- "Can you schedule a follow-up?"
- "I'd like someone to check on me in a week"
- "Please set up a follow-up call"
- "Can I get a reminder to follow up?"
- "Schedule a follow-up for next week"

**Measures:**
- Whether the followupSchedule tool is called
- Whether a follow-up date is returned
- Whether it links to the existing case

---

### T2.12 — Escalation Request

**Example messages (pick any):**
- "I need to speak to someone right now, this is urgent"
- "Can I talk to a real person?"
- "I want to be transferred to an agent"
- "This is an emergency, I need help now"
- "Please connect me with a case manager"
- "I'd like to speak to a human"
- "I'm in crisis and need immediate help"

**Measures:**
- Whether Aria recognizes the escalation request
- Whether it offers to connect to a live agent
- Whether it does not block the user with more questions

---

### T2.13 — Returning Client

**Example messages (pick any):**
- "I called before, my case reference is CS-20260218-AB12"
- "I'm following up on an existing case, reference CS-20260218-AB12"
- "I already have a case open. Number is CS-20260218-AB12"
- "I spoke to someone last week, can you check my case CS-20260218-AB12?"

*(Replace CS-20260218-AB12 with an actual case reference from T2.6)*

**Measures:**
- Whether Aria looks up the case before starting a new intake
- Whether it recognizes the client as returning
- Whether it skips redundant data collection

---

### T2.14 — One Tool Per Turn Rule

**Run any multi-tool flow (e.g., T2.3 → T2.6)**

**Measures:**
- Whether each agent turn contains at most ONE tool call
- Whether every turn that calls a tool also includes visible text
- Whether there are NO blank/empty messages in the chat

---

## Intake Bot (Lex V2)

### T3.1 — Menu Display

**Example messages (pick any):**
- "hello"
- "hi"
- "help"
- "get started"
- "menu"
- "options"
- "services"

**Measures:**
- Whether the ListPicker menu appears with two options
- Whether "Community Resources" and "Thrive@Work" are listed
- Whether the menu title and subtitles display correctly

---

### T3.2 — Route to Community Resources

**Click "Community Resources" from the ListPicker, or type:**
- "Community Resources"
- "community"
- "resources"
- "211"
- "housing"
- "food"
- "assistance"

**Measures:**
- Whether the bot closes the session
- Whether the contact flow routes to the Aria AI agent
- Whether the selectedRoute session attribute is set to "CommunityResources"

---

### T3.3 — Route to Thrive@Work

**Click "Thrive@Work" from the ListPicker, or type:**
- "Thrive@Work"
- "thrive"
- "employee"
- "employer"
- "benefits"
- "thrive at work"

**Measures:**
- Whether the bot closes the session
- Whether the contact flow routes to the Thrive@Work AI agent
- Whether the selectedRoute session attribute is set to "ThriveAtWork"

---

### T3.4 — Unrecognized Input

**Example messages (pick any):**
- "asdfghjkl"
- "12345"
- "what is this?"
- "I don't understand"
- "blah blah blah"

**Measures:**
- Whether the bot re-shows the ListPicker menu
- Whether it does not crash or disconnect
- Whether the FallbackIntent handles it gracefully

---

### T3.5 — Typed Selection (No Click)

**Type any of these instead of clicking the ListPicker:**
- "community resources" (lowercase)
- "COMMUNITY RESOURCES" (uppercase)
- "Community resources" (mixed case)
- "thrive@work" (lowercase)
- "Thrive at Work" (with spaces)

**Measures:**
- Whether the bot recognizes typed input as a valid selection
- Whether it routes correctly without requiring a ListPicker click
- Whether case sensitivity is handled properly

---

## Tools Reference

### Thrive@Work Bot — 1 MCP Tool + KB Retrieve

| Tool | Operation ID | What it does | Required inputs |
|------|-------------|--------------|-----------------|
| Employee Lookup | `employeeLookup` | Searches the employee database by ID to check partnership status and eligible programs | `employee_id` |
| KB Retrieve | *(built-in)* | Searches the Thrive@Work knowledge base for program info, FAQ, and eligibility details | *(automatic — triggered by general questions)* |

---

### Stability360 Actions Bot (Aria) — 6 MCP Tools + KB Retrieve

| Tool | Operation ID | What it does | Required inputs |
|------|-------------|--------------|-----------------|
| Scoring Calculator | `scoringCalculate` | Computes housing (1–5), employment (1–5), and financial resilience (1–5) scores. Returns composite score, priority flag, and recommended path (direct_support / mixed / referral) | `housing_situation`, `monthly_income`, `monthly_housing_cost`, `employment_status` |
| CharityTracker Submit | `charityTrackerSubmit` | Builds an HTML email payload from intake data, sends it via SES to the CharityTracker inbox, and creates an Amazon Connect Case with a reference number | `client_name`, `need_category`, `zip_code`, `county` |
| Follow-up Scheduler | `followupSchedule` | Schedules a follow-up reminder — creates a Connect Task (direct support) or SES email reminder (referral) | `contact_info`, `contact_method`, `referral_type`, `need_category` |
| Customer Profile | `customerProfileLookup` | Searches Amazon Connect Customer Profiles by name/email/phone. Creates a new profile if not found | `first_name`, `last_name`, `email`, `phone_number` |
| Case Status | `caseStatusLookup` | Looks up a case by reference number and returns the current status and description | `case_reference` |
| Resource Lookup | `resourceLookup` | Searches the SC 211 community resource directory (sophia-app.com) for providers by keyword, county, city, or ZIP | `keyword` + at least one of: `county`, `zip_code`, `city` |
| KB Retrieve | *(built-in)* | Searches the knowledge base for program details, eligibility rules, routing guides, FAQ, and 211 resource documents | *(automatic — triggered by general questions)* |

---

### Intake Bot (Lex V2) — No MCP Tools

| Component | What it does |
|-----------|--------------|
| ListPicker menu | Displays two service options: "Community Resources" and "Thrive@Work" |
| Lambda code hook | Parses the user's selection, sets `selectedRoute` session attribute, closes the session |
| Session attribute: `selectedRoute` | Set to `CommunityResources` or `ThriveAtWork` — used by the contact flow to branch to the correct AI agent |
