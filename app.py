from flask import Flask, render_template, request, jsonify, session
import anthropic, json, os, traceback, copy
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = "classroom-v4-2024"
client = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY")
)
STORE = {}
def gs(): return STORE.get("main", {})
def ss(d): STORE["main"] = d

DEFAULT_AGENTS = [
    {
        "id": "rohit", "name": "Rohit", "emoji": "🧑", "seat": 0,
        "present": True, "emotion": "bored", "action": "slouching, scrolling phone",
        "attention": 25, "speech": "",
        "personality": "Chronically distracted, always on phone. Ignores class unless called by name. Gets defensive if confronted. May ask to go to washroom to escape boring content.",
    },
    {
        "id": "priya", "name": "Priya", "emoji": "👩", "seat": 1,
        "present": True, "emotion": "focused", "action": "pen ready, attentive",
        "attention": 92, "speech": "",
        "personality": "Overachiever, always attentive, asks smart topic-related questions. Gets impatient if pace is too slow. Answers questions first. Very enthusiastic.",
    },
    {
        "id": "arjun", "name": "Arjun", "emoji": "🧑", "seat": 2,
        "present": True, "emotion": "confused", "action": "staring blankly",
        "attention": 50, "speech": "",
        "personality": "Genuinely confused most of the time. Hesitant to ask but eventually does. May whisper to Sneha. Gets overwhelmed easily. Sometimes asks to leave.",
    },
    {
        "id": "sneha", "name": "Sneha", "emoji": "👩", "seat": 3,
        "present": True, "emotion": "distracted", "action": "whispering to Arjun",
        "attention": 35, "speech": "",
        "personality": "Social butterfly, always whispering to neighbors. May ask to go washroom with a friend. Charming when called out. Drags others off-task.",
    },
    {
        "id": "vikram", "name": "Vikram", "emoji": "🧑", "seat": 4,
        "present": True, "emotion": "skeptical", "action": "arms crossed",
        "attention": 75, "speech": "",
        "personality": "Challenger, fact-checker. Argues if instructor says something wrong. Debates confidently. Respects only knowledgeable teachers. Will correct Arjun rudely.",
    },
]

EMO_LIST = ["bored","focused","confused","distracted","angry","excited","anxious","skeptical","engaged","sleepy","amused","surprised","happy"]

@app.route("/")
def index(): return render_template("index.html")

@app.route("/session")
def session_page(): return render_template("session.html")

@app.route("/report")
def report_page(): return render_template("report.html")

@app.route("/api/start", methods=["POST"])
def start():
    data = request.json
    session["sid"] = "main"
    ss({
        "config":  data,
        "agents":  copy.deepcopy(DEFAULT_AGENTS),
        "history": [],
        "log":     [],
        "report":  None,
    })
    print(f"[START] {data.get('subject')}")
    return jsonify({"ok": True, "agents": copy.deepcopy(DEFAULT_AGENTS)})

@app.route("/api/speak", methods=["POST"])
def speak():
    try:
        store   = gs()
        config  = store.get("config", {})
        agents  = store.get("agents", [])
        history = store.get("history", [])
        text    = request.json.get("text", "").strip()
        elapsed = request.json.get("elapsed", 0)

        if not text:
            return jsonify({"error": "No text"}), 400

        # Build history string (last 14 exchanges)
        hist_str = "\n".join([f"[{h['who']}]: {h['text']}" for h in history[-14:]]) or "Class just started."

        # Agent states
        agent_states = "\n".join([
            f"- {a['name']}: present={a['present']}, emotion={a['emotion']}, attention={a['attention']}%, action={a['action']}"
            for a in agents
        ])

        prompt = f"""You are simulating a LIVE classroom of 5 students for instructor training. This is a real flowing conversation — students respond naturally just like real students would, based on their unique personalities.

Subject being taught: {config.get('subject', 'General')}
Learning objectives: {config.get('objectives', '')}
Student type: {config.get('studentType', 'undergraduate')}
Difficulty: {config.get('difficulty', 'medium')}
Session time: {elapsed // 60}m {elapsed % 60}s into class

STUDENT PERSONALITIES (never change these):
- Rohit: always distracted/on phone, ignores unless called by name, defensive when confronted, may ask washroom
- Priya: overachiever, sharp questions about real content, answers first, enthusiastic greetings
- Arjun: genuinely confused, hesitant, whispers to Sneha, may ask to leave, gets overwhelmed
- Sneha: social butterfly, whispering constantly, may ask washroom, pulls others off-task
- Vikram: challenges everything, fact-checks, argues if wrong info given, debates confidently

CURRENT STUDENT STATES:
{agent_states}

CONVERSATION SO FAR:
{hist_str}

INSTRUCTOR JUST SAID:
"{text}"

RULES — follow these strictly:
1. Only PRESENT students (present=true) can respond
2. NOT every student responds every time — only the ones who naturally would
3. If instructor says "good morning" → all present students greet back (naturally, each differently)
4. If instructor asks a question → Priya answers fast, Arjun might guess wrong, Rohit ignores
5. If instructor says a student's name → that student MUST respond in character
6. Students can initiate actions themselves — Sneha might whisper, Rohit get caught on phone, Vikram challenge
7. If a student asks to go washroom/leave → set their present=false, action="left class - washroom"
8. If an absent student was gone long enough → they can return (present=true, action="returned to seat")
9. Situation note: describe any notable classroom event (student left, argument started, etc.)
10. Conversations must feel REAL — short natural responses, not formal

Respond ONLY with valid JSON, no markdown:
{{
  "responses": [
    {{
      "id": "priya",
      "speech": "Good morning sir!",
      "emotion": "happy",
      "action": "smiling, sitting up straight",
      "attention": 95,
      "present": true
    }}
  ],
  "classroom_mood": "engaged",
  "situation_note": "",
  "instructor_evaluation": {{
    "score": 8,
    "note": "Warm greeting, set positive tone"
  }}
}}

Only include agents who respond OR whose state changes. Agents with no change = omit from responses array.
situation_note = short description if something notable happened, else empty string "".
"""

        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=900,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"): raw = raw[4:]
        result = json.loads(raw.strip())

        responses = result.get("responses", [])
        responding_ids = {r["id"] for r in responses}

        # Update agent states
        for r in responses:
            for a in agents:
                if a["id"] == r["id"]:
                    a["speech"]   = r.get("speech", "")
                    a["emotion"]  = r.get("emotion", a["emotion"])
                    a["action"]   = r.get("action", a["action"])
                    a["attention"]= r.get("attention", a["attention"])
                    a["present"]  = r.get("present", a["present"])

        # Clear speech for non-responding agents
        for a in agents:
            if a["id"] not in responding_ids:
                a["speech"] = ""

        # Update history
        history.append({"who": "Instructor", "text": text})
        for r in responses:
            if r.get("speech"):
                history.append({"who": r["id"].capitalize(), "text": r["speech"]})

        # Log evaluation
        ev = result.get("instructor_evaluation", {})
        if ev:
            store.setdefault("log", []).append({
                "instructor_said": text,
                "score": ev.get("score", 5),
                "note": ev.get("note", ""),
                "situation": result.get("situation_note", ""),
            })

        store["agents"]  = agents
        store["history"] = history
        ss(store)

        print(f"[SPEAK] '{text[:50]}...' → {len(responses)} response(s) | mood={result.get('classroom_mood')} | sit={result.get('situation_note','')[:40]}")

        return jsonify({
            "agents":   agents,
            "responses": responses,
            "classroom_mood": result.get("classroom_mood", "calm"),
            "situation_note": result.get("situation_note", ""),
            "instructor_evaluation": ev,
        })

    except Exception as e:
        print(f"[SPEAK ERROR] {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/final-report", methods=["POST"])
def final_report():
    try:
        store   = gs()
        config  = store.get("config", {})
        agents  = store.get("agents", [])
        history = store.get("history", [])
        log     = store.get("log", [])
        elapsed = request.json.get("elapsed", 0)

        if not history:
            return jsonify({"error": "No session data"}), 400

        avg_score = round(sum(e["score"] for e in log) / len(log), 1) if log else 0
        hist_str  = "\n".join([f"[{h['who']}]: {h['text']}" for h in history[-30:]])
        agent_final = "\n".join([
            f"- {a['name']}: attention={a['attention']}%, emotion={a['emotion']}, present={a['present']}"
            for a in agents
        ])

        prompt = f"""Analyse this classroom session and generate a detailed instructor performance report.

Subject: {config.get('subject', '')}
Duration: {elapsed // 60}m {elapsed % 60}s
Student type: {config.get('studentType', '')}
Average interaction score: {avg_score}/10
Total exchanges: {len(history)}

CONVERSATION LOG:
{hist_str}

FINAL STUDENT STATES:
{agent_final}

Respond ONLY with valid JSON, no markdown:
{{
  "overall_score": 72,
  "grade": "B",
  "grade_label": "Competent Instructor",
  "dimension_scores": {{
    "classroom_management": 70,
    "communication": 75,
    "student_engagement": 68,
    "subject_knowledge": 80,
    "adaptability": 65
  }},
  "agent_analysis": {{
    "rohit": "2 sentence analysis of how instructor handled Rohit",
    "priya": "2 sentence analysis",
    "arjun": "2 sentence analysis",
    "sneha": "2 sentence analysis",
    "vikram": "2 sentence analysis"
  }},
  "best_moment": "best moment in session",
  "worst_moment": "weakest moment in session",
  "strengths": ["strength 1", "strength 2", "strength 3"],
  "improvements": ["improvement 1", "improvement 2", "improvement 3"],
  "recommendations": ["rec 1", "rec 2", "rec 3"],
  "overall_feedback": "4 sentence holistic assessment"
}}"""

        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"): raw = raw[4:]
        report = json.loads(raw.strip())
        report["session"] = {
            "subject":   config.get("subject", ""),
            "duration":  elapsed,
            "exchanges": len(history),
            "avg_score": avg_score,
            "agents":    agents,
            "log":       log,
        }
        store["report"] = report
        ss(store)
        print(f"[REPORT] Overall={report.get('overall_score')}")
        return jsonify(report)

    except Exception as e:
        print(f"[REPORT ERROR] {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/session-state")
def session_state():
    store = gs()
    return jsonify({"agents": store.get("agents", []), "config": store.get("config", {})})

@app.route("/api/report-data")
def report_data():
    return jsonify(gs().get("report", {}))

if __name__ == "__main__":
    app.run(debug=True, port=5000)
