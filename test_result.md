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
        - working: true
          agent: "testing"
          comment: "Iteration 8 — 15/15 pytest tests PASS."

  - task: "Voice-to-Project parse endpoint /api/parse-project"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "testing"
          comment: "Iteration 9 — 16/16 pytest tests PASS."

  - task: "Weather — geocoding, per-visit auto-fetch, refresh endpoint, projects carry weather to reports"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "testing"
          comment: "Iteration 10 — 18/18 pytest tests PASS."

  - task: "Hourly forecast endpoint /api/weather/hourly"
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
            Iteration 11 — 10/10 pytest tests PASS. Verified schema (hour_label
            regex, numeric fields, precip_prob 0..100), hours clamp (6→≤6, 99→≤24,
            0→≥1), auth gating (403 no header). Regression /weather + /geocode +
            /tts all healthy. Report: /app/test_reports/iteration_11.json.

frontend:
  - task: "Home — Multi-Location Weather widget + Report per-site weather + Refresh from pin sheet"
    implemented: true
    working: true
    file: "multiple"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "Verified via screenshot — Home widget + Boston search working."

  - task: "Hourly Forecast Sheet — tap weather card → 12h chart + list"
    implemented: true
    working: "NA"
    file: "/app/frontend/src/components/HourlyForecastSheet.tsx, /app/frontend/src/components/MultiLocationWeather.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: |
            NEW. Tap any weather card on Home → bottom sheet with SVG temp curve +
            rain-chance bars + hour labels + a scrollable compact list. Uses
            react-native-svg. Screenshot-verified working with live Open-Meteo data.

metadata:
  created_by: "main_agent"
  version: "1.5"
  test_sequence: 11
  run_ui: false

test_plan:
  current_focus:
    - "Hourly forecast endpoint /api/weather/hourly"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: |
        Iteration 11 — Backend test focus: new GET /api/weather/hourly endpoint.
        1. Happy path: lat=42.358&lon=-71.060 → 200; points length 1..12; each
           point has hour_label (HH:MM), numeric temperature_f, numeric precip_prob
           (0..100), numeric precipitation, string conditions, int weather_code,
           numeric wind_mph.
        2. hours=6 → response `hours` <= 6.
        3. hours=99 clamped → response `hours` <= 24.
        4. hours=0 clamped → at least 1 point (server enforces min 1).
        5. Auth required — no token → 401/403.
        6. Regression: /api/weather, /api/geocode still 200; /api/reports/{id}/tts
           unchanged.
        Credentials: admin@paintops.com / Admin@12345. Backend only.
