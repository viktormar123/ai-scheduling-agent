# Scheduling Agent

This project implements a simple AI-powered scheduling assistant for small businesses.  
It uses OpenAI's GPT-4o model to interact with users, gather constraints, and generate employee shift schedules. The current recommended entry‑point is **`agent2.py`**, a conversational CLI that guides you through schema creation and schedule generation via natural language.

The agent:
- Gathers company information via structured conversation.
- Builds a structured JSON scheduling schema.
- Generates schedules using optimization strategies.
- Supports fallback suggestions when no feasible solution is found.

---

## Features

- Human-in-the-loop schedule building
- Dynamic schema collection through natural language
- Support for hard and soft constraints
- Basic, partial, and optimized scheduling modes
- Conversational CLI (`agent2.py`) – no rigid command syntax required  
- JSON schema persisted between runs (stored in *data/current_schema.json*)

---

## Quick Start

1. Install dependencies  
   ```bash
   pip install -r requirements.txt
   export OPENAI_API_KEY=<your‑key>
   ```
2. Launch the agent  
   ```bash
   python agent2.py
   ```
3. Chat naturally – the agent will ask follow‑up questions until it has enough information to build a schedule, then call the appropriate optimisation tool.

**Tips**
- *Enter* sends a message, *Shift + Enter* inserts a newline.  
- If the optimiser cannot find a feasible schedule the agent will suggest relaxing constraints or (after three attempts) offer a greedy fallback.

---

## Example Interaction

```text
User: We run a café open 08‑18, Mon–Fri.  
Agent: Great! How many shifts and what roles do you need per shift?  
…(dialog continues)…  
Agent: Here’s your weekly schedule – does it look good?
```

---

## Repository Structure
- `agent2.py` – main conversational agent  
- `tools.py`  – scheduling backend (greedy + CP‑SAT)  
- `data/`     – saved schemas  
- legacy: `agent.py`, `run.py`

---

## Technologies
- Python 3.10+
- OpenAI GPT-4o
- Google OR-Tools CP-SAT
- JSON schema-based modeling

---

## Installation

```bash
pip install -r requirements.txt
```



---

Future Ideas
- Support for multi-location or multi-week scheduling
- Agent-generated optimization functions
- Visual web interface for schema interaction
- Export to Google Calendar, Excel, or PDF
- MCP (Model Context Protocol) integration
