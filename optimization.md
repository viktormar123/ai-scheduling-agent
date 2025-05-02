Optimization Strategy for Scheduling Agent

⸻

1. Overview

This project builds an AI scheduling agent for small businesses with up to 50 employees.

Our goal is to automatically create fair, feasible work shift schedules based on a structured JSON schema containing employees, shift structures, and company constraints.

Scheduling must:
	•	Cover all required shifts.
	•	Respect employee availability.
	•	Match employee work contracts (percentages).
	•	Be fair in distributing shifts across employees.

We focus on finding schedules that strictly satisfy all “hard constraints” whenever possible, while allowing optional “soft constraints” (preferences) to be optimized but relaxed when necessary.

⸻

2. Optimization Methods Considered

We reviewed several possible optimization methods:

Method	Decision
Constraint Programming (CP)	Selected
Mixed Integer Programming (MIP)	Not selected: Harder for dynamic constraint modeling by agents.
Linear Programming (LP)	Not selected: Cannot directly produce valid integer (binary) shift assignments.
Greedy Heuristics	Good for simple fallback solutions, but no optimality guarantee.
Evolutionary Algorithms (GA, SA, etc.)	Interesting for scaling later, but not necessary for small company size.



⸻

3. Why Constraint Programming (CP)

We selected Constraint Programming (CP) for the following reasons:
	•	Natural fit for complex scheduling constraints.
	•	Easy to model hard and soft constraints directly.
	•	Highly flexible: Adding new types of rules (e.g., “no 3 nights in a row”) is simple.
	•	Works very well for small companies (<50 employees) with modern solvers.
	•	Google OR-Tools CP-SAT solver is free, powerful, and fast.
	•	Easy for a language model agent to generate/update constraints dynamically.

Overall, CP gives us more flexibility and robustness while keeping implementation manageable.

⸻

4. Hard vs Soft Constraints

Hard constraints are rules that must be satisfied for a schedule to be acceptable:
	•	Employees must not work during unavailable times.
	•	Employees must be assigned shifts matching their contract percentages.
	•	All required shifts must be covered.

Soft constraints are desirable but can be violated if necessary, with a penalty:
	•	Prefer assigning employees to their preferred shifts.
	•	Prefer distributing night shifts evenly.
	•	Prefer minimizing consecutive night shifts.

In our system:
	•	Hard constraints are modeled strictly by default.
	•	If no feasible schedule exists, some hard constraints can be relaxed (converted into soft constraints) based on user choice.

⸻

5. Human in the Loop Design

We keep a human-in-the-loop by:
	•	Notifying the user if no feasible schedule exists under current hard constraints.
	•	Offering options to:
	•	Update the schema (correct missing or wrong data).
	•	Relax specific constraints (e.g., allow work percentage deviation).
	•	Proceed with soft constraints and generate the best approximate schedule.

This ensures the user is always informed and retains control over critical decisions.

⸻

6. Fallback Strategy if No Feasible Solution

If no schedule satisfies all hard constraints:
	1.	Inform the user clearly.
	2.	Offer relaxation options:
	•	Relax work percentage constraints slightly (e.g., ±5%).
	•	Allow uncovered shifts (with a penalty).
	•	Allow minor availability violations.
	3.	Re-run scheduling with relaxed soft constraints.
	4.	Present the best approximate solution.

This process minimizes frustration and provides usable schedules even in difficult situations.

⸻

7. Future Expansions
	•	Supporting multiple location scheduling.
	•	Adding multi-week schedule planning.
	•	Incorporating preferences, seniority, or shift rotations.
	•	Hybrid approaches (CP + local search for tweaking).
	•	Automated infeasibility analysis to suggest the cause of problems.

