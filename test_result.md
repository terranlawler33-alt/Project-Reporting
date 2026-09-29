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
        - working: "NA"
          agent: "main"
          comment: "See earlier entry."
        - working: true
          agent: "testing"
          comment: |
            Iteration 10 — 18/18 pytest tests PASS.
            All weather features verified end-to-end against live Open-Meteo:
            - POST /visits auto-attaches weather snapshot with numeric fields.
            - POST /visits/{id}/refresh-weather: 200 fresh, 404 unknown, 403 non-author.
            - GET /geocode: 200 with 1..8 results, 400 empty q, 401 no auth.
            - GET /weather auth-gated correctly.
            - Reports auto-derive projects with per-visit weather; ai_summary has
              WEATHER IMPACT block. Explicit weather in projects roundtrips.
            - Regression: parse-project/tts/customer-history/reports all green.
            Report: /app/test_reports/iteration_10.json.

frontend:
  - task: "Home — Multi-Location Weather widget + Report per-site weather + Refresh from pin sheet"
    implemented: true
    working: "NA"
    file: "/app/frontend/src/components/MultiLocationWeather.tsx, /app/frontend/app/(tabs)/index.tsx, /app/frontend/app/(tabs)/map.tsx, /app/frontend/app/report/[id].tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: |
            NEW. `<MultiLocationWeather>` replaces the old fixed weather hero. Features:
            - Always shows "Current location" (GPS) as the first card.
            - + button opens a search modal that hits GET /api/geocode; tap a result
              to save that location. Persisted per-device via AsyncStorage
              (paintops.weather.locations.v1).
            - ‹ › arrows and pagination dots to swipe between locations.
            - Each card fetches its own snapshot from GET /api/weather.
            - Remove (×) button on saved cards.
            Report detail: new "Weather by site" MetaCard renders one row per project
            that has a weather snapshot.
            Map pin-tap sheet: shows the visit's captured weather + a refresh button
            that hits POST /visits/{id}/refresh-weather and updates the sheet.

metadata:
  created_by: "main_agent"
  version: "1.4"
  test_sequence: 10
  run_ui: false

test_plan:
  current_focus:
    - "Weather — geocoding, per-visit auto-fetch, refresh endpoint, projects carry weather to reports"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: |
        Iteration 10 — Backend test focus:
        1. POST /api/visits at valid coords → 200; response body has non-null
           `weather` snapshot with temperature_f/wind_mph/precipitation/conditions and
           `weather_refreshed_at` timestamp.
        2. POST /api/visits/{visit_id}/refresh-weather on an existing visit → 200
           with an updated weather snapshot and refreshed timestamp. 404 for unknown
           id. 403 for a non-author, non-full-role user.
        3. GET /api/geocode?q=Boston → 200 with `results` array (length up to 8),
           each entry has label/latitude/longitude. Empty query → 400. Auth required
           (401/403).
        4. GET /api/weather now requires auth — hit without token → 401/403.
        5. POST /api/reports with visits that have `weather` snapshots — backend
           derived projects should carry `weather` through, and ai_summary should
           mention weather at least once. Also submitting explicit `projects` with
           `weather` inline should round-trip.
        6. Regression: parse-project, TTS, customer history unchanged.
        Do NOT test frontend UI.
        Credentials: admin@paintops.com / Admin@12345.



