#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: |
  Daily reporting mobile app (Expo + FastAPI + MongoDB) for management/owners.
  Current session task: Fix bug in "Read Aloud" (TTS) function — user reports HTTP 502.

backend:
  - task: "Read Aloud (TTS) — ElevenLabs with OpenAI fallback"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "testing"
          comment: |
            Iteration 7 — 11/11 pytest tests PASS. Fully verified.

  - task: "Multi-Project reports + backward compat + Touch-Ups flag + customer history"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "See earlier entry."
        - working: true
          agent: "testing"
          comment: |
            Iteration 8 — 15/15 pytest tests PASS. Verified: visits accept project_id;
            reports accept projects with all fields (round-trip + AI summary refs);
            backward-compat auto-derives projects from legacy visits on GET; customer
            history endpoint returns visits/reports/customer/photos/counts, case-insensitive
            match, 400 on empty name, 401 unauth. Touch-Ups flag persists + AI summary
            contains "TOUCH-UP" marker. Regression: TTS (200 via openai fallback),
            regenerate-summary, /customers all unchanged. No blockers. Report:
            /app/test_reports/iteration_8.json.

frontend:
  - task: "Compose Report — Projects section with Add Another Project"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/report/new.tsx, /app/frontend/src/components/ProjectsSection.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: |
            NEW. `<ProjectsSection>` component inserted immediately after Material Notes
            input in the Compose Report screen. Auto-populates from today's visits on
            mount (grouped by project_id). Each project card has: customer name,
            address (matches pin drop location), project code+name, start/end time,
            work notes, materials used, Touch-Ups toggle, and a horizontal
            flag-picker chip strip. "+ Add another Project" button at the bottom
            appends an empty card. Payload sent as `projects: []` in POST /reports.
            Also added "Touch-Ups" to PRIORITY_FLAGS in priority.ts.

  - task: "Map — Attach-to-Project modal on pin drop + Pin-tap detail sheet + Customer history navigation"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/(tabs)/map.tsx, /app/frontend/app/customer/[name].tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: |
            NEW. Two new modals on Map screen:
            1. Save Visit → if today already has 1+ projects, shows a bottom-sheet modal
               asking which project to attach this pin to (list existing + "Start a new
               project" button). If no projects yet today, the visit is saved as a new
               project directly. The chosen `project_id` is passed to POST /visits.
               When attaching to an existing project, the visit inherits customer /
               address / project_code from that project (unless the form has values).
            2. Pin tap on the map opens a detail sheet showing address, project code,
               time in/out, notes, photos, plus a "See customer history →" button
               that navigates to `/customer/<name>`.
            NEW screen `/app/frontend/app/customer/[name].tsx` — fetches
            `GET /api/customers/history?name=` and shows stats (visits/reports/photos),
            directory contact info, list of visits, tappable list of reports mentioning
            this customer, and photo grid.

metadata:
  created_by: "main_agent"
  version: "1.2"
  test_sequence: 8
  run_ui: false

test_plan:
  current_focus:
    - "Multi-Project reports + backward compat + Touch-Ups flag + customer history"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: |
        NEW FEATURE (iteration 8): Multi-project reports + Touch-Ups flag + customer history.
        Backend test focus:
        1. POST /api/visits accepts optional `project_id` and stores it.
        2. POST /api/reports accepts `projects: List[ProjectEntry]` — verify one saved
           and returned back, and that AI summary references projects (bullet under
           WORK COMPLETED should include "Project 1" or the customer/address).
        3. GET /api/reports (and single GET) — legacy reports (no projects field) get
           auto-derived projects from visits; new reports keep their explicit projects.
        4. GET /api/customers/history?name=<name> — returns visits, reports, photos,
           customer record. Case-insensitive match. 400 if name empty.
        5. Touch-Ups flag: send a report with priority_flags=[{type:"Touch-Ups"}] and
           a project with touch_up=true — AI summary should mention [TOUCH-UP: address]
           (best-effort — LLM may vary; check the presence of "TOUCH-UP" token OR the
           bullet under DELAY / CONSTRAINTS).
        6. Regression: TTS endpoint, GET /reports basic list, existing visit creation.
        Do NOT test frontend UI in this iteration (backend only for now).
        Credentials: admin@paintops.com / Admin@12345.

