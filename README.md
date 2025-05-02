# Scheduling Agent

This project implements a simple AI-powered scheduling assistant for small businesses.  
It uses OpenAI's GPT-4o model to interact with users, gather constraints, and generate employee shift schedules.

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

---

## How It Works

1. If no schema exists, the agent asks structured initial questions.
2. It builds a draft schema and validates it.
3. The user can edit or regenerate parts.
4. A scheduling function is invoked using the schema.
5. If no feasible solution is found, the agent suggests constraint relaxation.

---

## Example Interaction

```text
Agent: Please describe your company.
User: We are a pizza place open 11am–11pm with 12 employees.

Agent: Please list your employees, employment percentage, and roles.
User: Anna (full-time baker), James (part-time driver)...

Agent: Please describe your shift structure.
User: Two shifts, day 11am–6pm, night 5pm–11pm.

Agent: Any special conditions?
User: Mason is a student, prefers night shifts.

Agent: (builds schema)
Agent: Would you like to edit anything or create a schedule?
```

User options:
- Type edit to edit schema.
- Type create basic to create a basic schedule.
- Type create partial to create a partial schedule.
- Type create optimized to create an optimized schedule.

⸻

Technologies
- Python 3.10+
- OpenAI GPT-4o
- Google OR-Tools CP-SAT
- JSON schema-based modeling

⸻

Requirements

pip install -r requirements.txt



⸻

Future Ideas
- Support for multi-location or multi-week scheduling
- Agent-generated optimization functions
- Visual web interface for schema interaction
- Export to Google Calendar, Excel, or PDF
- MCP (Model Context Protocol) integration
