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
        - working: "NA"
          agent: "main"
          comment: |
            User reported HTTP 502 on Read Aloud. Root cause: ElevenLabs quota exhausted
            (1,775 credits left, request needed 1,895–1,996). Old code labelled it "API key
            invalid" (wrong message). Fix:
            1. Added Emergent-managed OpenAI TTS fallback (`OpenAITextToSpeech`, model tts-1,
               voice onyx). If ElevenLabs fails or is unconfigured, automatically fall back.
            2. Strip markdown marks (*, _, #, `, urls) before TTS so voice does not read them.
            3. Response now returns `voice_provider` ("elevenlabs" or "openai") for
               transparency; cache stores it too.
            4. Better error message when both providers fail.
            Endpoint: POST /api/reports/{report_id}/tts
            Verified logs show ElevenLabs 401 → OpenAI TTS success on live request.
        - working: true
          agent: "testing"
          comment: |
            Iteration 7 — 11/11 pytest tests PASS. Confirmed:
              - ElevenLabs 401 (quota) → OpenAI TTS fallback → 200 with voice_provider="openai"
              - 2nd call returns cached=true with same URL
              - 400 for empty summary, 404 for missing report
              - RBAC: non-author non-full-role → 403; author/admin → 200
              - Regression: GET/POST reports, regenerate-summary all healthy (regen
                invalidates tts_cache correctly)
            Report: /app/test_reports/iteration_7.json

metadata:
  created_by: "main_agent"
  version: "1.1"
  test_sequence: 7
  run_ui: false

test_plan:
  current_focus:
    - "Read Aloud (TTS) — ElevenLabs with OpenAI fallback"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: |
        Bug fix: TTS endpoint POST /api/reports/{id}/tts was returning 502 because
        ElevenLabs quota is exhausted. Added transparent OpenAI TTS fallback via
        emergentintegrations.OpenAITextToSpeech(EMERGENT_LLM_KEY). Please test:
        1. Login as admin@paintops.com / Admin@12345
        2. Fetch existing reports via GET /api/reports (or create a new one)
        3. Call POST /api/reports/{id}/tts on a report that has an ai_summary
        4. Verify response is 200 with audio_data_url starting "data:audio/mpeg;base64,"
           and voice_provider field is either "elevenlabs" or "openai"
        5. Call it a second time on same report — expect cached=true
        6. Verify the endpoint returns 400 if report has no ai_summary
        7. Verify RBAC: non-author non-full-role user gets 403
        Do NOT test frontend UI — backend only.
