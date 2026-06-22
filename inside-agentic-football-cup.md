# Inside Agentic Football Cup: 10 Strands Agents, 1 Second to Decide

> **Published:** June 6, 2026 · 9 min read  
> **Authors:** [Ian Holtz](https://strandsagents.com/blog/authors/ian-holtz/), [Ed Fraga](https://strandsagents.com/blog/authors/ed-fraga/)  
> **Source:** [strandsagents.com/blog/inside-agentic-football-cup/](https://strandsagents.com/blog/inside-agentic-football-cup/)

How we use Strands Agents and the model-driven approach to run 5v5 autonomous football matches inside a 4-hour developer workshop, with a hard latency contract, structured outputs, and multi-agent coordination.

---

[Agentic Football Cup](https://agenticfootballcup.com) is a hands-on technical workshop where developers learn to build production agents with Amazon Bedrock AgentCore and the Strands Agents SDK. It's designed for developers of all levels, across every geo and segment — startup engineers, enterprise builders, partners, students. The 4-hour, hands-on session is where the work happens. Live demos at AWS Summits and at re:Invent are how people first see it.

The deliverable is football: each participant ships five Strands agents (four outfielders and a goalkeeper) and plays 5v5 against another participant's team in a live, 2-minute match. Every goal scored is the output of a foundation model deciding `SHOOT` inside one second. But the patterns participants learn — the model-driven loop, structured output, multi-agent coordination, hard latency budgets — are the same ones they take back to call-center agents, supply-chain agents, code-review agents, and claims agents.

This post walks through how we use Strands Agents, deployed and invoked through Amazon Bedrock AgentCore, to make ten autonomous agents play coherent football together under hard runtime constraints. The football is the vehicle, but the architecture patterns map cleanly onto the agents you'd build for production.

---

## The Setup

A match is two teams of five Strands agents. Every two seconds, the game server emits a *decision point* and calls all ten agents in parallel with the full game state: ball position, every player's position and velocity, stamina, score, and clock. Each agent has **1 second** to return one of eleven structured commands:

| Command | Description |
|---|---|
| `MOVE_TO` | Move to a target position |
| `PASS` | Pass to a target player |
| `SHOOT` | Shoot at goal |
| `DRIBBLE` | Dribble towards a target |
| `PRESS_BALL` | Press the ball carrier |
| `MARK` | Mark a target player |
| `INTERCEPT` | Intercept a pass/run |
| `TACKLE` | Tackle the ball carrier |
| `CLEAR` | Clear the ball |
| `IDLE` | Do nothing |
| *(goalkeeper-specific actions)* | |

Anything slower IDLEs that player for the tick, and there are no retries during a match.

That contract — parallel multi-agent invocation, structured output, hard timeout — is exactly what production agentic workloads look like, except we play it out at 60 frames per second on a football pitch.

---

## Why Model-Driven

A football match is the wrong place to write `if/else` because the state space is too large: eleven command types, five players, a ball, the clock, stamina, opponents, and a teammate distribution that changes every tick. A rules-based controller can cover the obvious cases and ship something that *almost* plays football, but it will freeze the moment play does something the rules didn't anticipate.

The model-driven approach handles this naturally. The system prompt describes the team's identity ("you press high, you favor through-balls, you shoot from distance"), the tools expose game-state queries, and the model picks the next command. When play goes somewhere unexpected — a 2-on-1 break, a tired defender, a goalkeeper off the line — the model reasons about it instead of falling back to a default branch.

This mirrors the lesson the Strands team has written about before: orchestration logic that worked for older models gets in the way of what modern LLMs can do natively. The football pitch is just a particularly visible place to see it.

---

## What an Agent Looks Like

Each player is a Strands `Agent` with a Bedrock model, a system prompt that encodes the team's tactics, and a Pydantic schema for its command:

```python
from typing import Literal
from pydantic import BaseModel, Field
from strands import Agent
from strands.models.bedrock import BedrockModel

class AgentCommand(BaseModel):
    type: Literal[
        "MOVE_TO", "PASS", "SHOOT", "DRIBBLE", "PRESS_BALL",
        "MARK", "INTERCEPT", "TACKLE", "CLEAR", "IDLE",
    ]
    target_player_id: str | None = None
    target: tuple[float, float] | None = None
    rationale: str = Field(..., description="One short line, for the replay log.")

striker = Agent(
    model=BedrockModel(model_id="amazon.nova-micro-v1:0"),
    system_prompt=(
        "You are the striker for Crimson Rovers. "
        "Press high. Take shots when the lane is open. "
        "Conserve stamina when you are off the ball."
    ),
)
```

Every two seconds, the game server hands the agent a snapshot of the field and asks it for one structured command:

```python
command = striker.structured_output(AgentCommand, game_state_json)
```

The Pydantic schema is doing real work here. It bounds what the model is allowed to return, gives the game server something it can deserialize without parsing a free-form essay, and gives a clean event log when replaying the match later. Same structured-output pattern any production tool-calling agent should use.

---

## Multi-Agent Coordination, the Soccer Version

Two patterns are at work in every match.

### Human Guidance Through a Free-Text Channel

During the match, participants can type messages to their team in real time ("press higher," "stop pulling our striker out wide," "stay compact"), but these aren't commands. The agents are autonomous. The free-text input simply becomes part of the context they reason over on their next decision cycle, alongside the full game state, and they may or may not act on it. Tell your defender to push up while the opposition is breaking on you, and the agent will rightly ignore you.

This is a clean expression of the model-driven principle: the human contributes intent, and the model decides whether and how that intent applies given everything else it can see. It's the same shape as a production agent receiving a hint from an upstream system or a user-provided constraint that may or may not be reachable from the current state.

### Swarm Dynamics on the Pitch

Among the five players themselves, nobody is the orchestrator. Each agent reads the same game state, sees the same teammates, and decides what its role should be on this tick. If your striker is out of position, your midfielder picks up the runner. The handoff is implicit, driven by what the model sees, not by a routing table.

We expected to write an orchestrator, but didn't need one. The model-driven approach, applied to five agents looking at the same world, produced coherent team play without coding the coordination at all.

---

## The 1-Second Hard Contract

Agents that don't have to be fast won't be, so we force the issue. Every agent has **1 second per decision**, end-to-end including network. Miss the deadline and the player IDLEs for that tick. The match doesn't pause.

A few things this forces:

- **Pick the right model for the job.** Smaller, faster models like Amazon Nova Micro are well-suited to the per-tick command decision because the latency budget is tight and the action space is bounded. Larger models can earn their slot when the decision genuinely needs it. Letting the model match the role is exactly the kind of tuning Strands makes easy.
- **Keep the prompt tight.** A short, well-shaped system prompt outperforms a long one inside this budget. Participants tend to iterate on their prompts more than their code, which is the right instinct.
- **Validate ruthlessly.** Pydantic catches malformed commands before they reach the game server. A malformed command in production is an outage; here, it's a missed pass.

The thing participants tune is almost never the code. It's the prompt and the model choice.

---

## Running It on AgentCore

Each participant deploys their five agents into their own AWS account using Amazon Bedrock AgentCore. The match platform calls those endpoints cross-account over HTTPS with bearer tokens. The platform never sees the agent code or the model choice — which is the same isolation pattern enterprises need for multi-tenant agentic platforms.

The full match event stream — every tick and every agent decision — is appended to an NDJSON event log in S3. After the match, a participant can replay every command their agent issued and see exactly why their striker passed when they should have shot. Strands' clean separation between agent invocation and observability makes that log essentially free to produce.

---

## Going Further with AgentCore Memory, Gateway, and Observability

The base agents in the workshop are stateless. Every tick is a fresh inference. That works, but it leaves a lot on the field. The advanced track of the workshop layers three AgentCore features onto the same Strands agents. Each one maps directly to a production pattern participants take back with them.

### Memory

**AgentCore Memory** gives an agent recall across ticks and across matches. With it wired in, a defender can notice that the opposing striker has cut left on every shot in the previous match and adjust its positioning this match.

In production, this is the same primitive you'd use to give a customer-service agent recall of a user's last three sessions, or a code-review agent recall of a team's prior style decisions.

### Gateway

**AgentCore Gateway** turns external systems into MCP tools the agent can call mid-decision. In the workshop, participants stand up an analytics service exposed through Gateway that returns pass-success rates between any two players based on prior matches. The agent calls it inside its 1-second budget, sees that "pass to Player 3 succeeds 82% of the time, pass to Player 4 succeeds 31% of the time," and chooses accordingly.

The production analogue is the same: a single managed front door over your internal APIs, exposed as MCP tools, callable by any Strands agent without bespoke client code.

### Observability

**AgentCore Observability** surfaces every reasoning step, tool call, and timing trace through OpenTelemetry. After a confusing moment in a match (a defender sprinting forward when they shouldn't), the participant opens the trace and sees the agent's reasoning chain, the tool calls it made, and the prompt fragment that misled it. Same workflow you'd want when debugging a production agent at 2 a.m.

Participants don't have to add all three. The workshop encourages picking the one that solves the biggest problem in their current team and shipping it:

- **Memory** — for teams that lose because they can't adapt
- **Gateway** — for teams whose decisions are guesses
- **Observability** — for teams who can't explain why their agents do what they do

The choice itself is part of the lesson.

---

## What We've Learned So Far

Across the workshops run so far, a few patterns hold up every time:

1. **Command diversity is the single biggest lever.** Teams whose agents over-rely on one command type (usually `PASS`) lose to teams whose agents reach for the full eleven. Same lesson production agents teach: tool diversity matters.

2. **Structured output is non-negotiable.** Every team that tries to skip Pydantic and parse free-form responses ships late and plays poorly.

3. **The model-driven approach scales to multi-agent without extra plumbing** — no orchestrator was written because the model writes it, every tick, in five places at once.

4. **Learning feels like play.** Participants come for the football and stay for the architecture. By the time they've tuned a pressing strategy or debugged a passing chain, they've internalized prompt engineering, structured output, latency budgets, and observability. The skills transfer directly to production agent work.

---

## Try It Yourself

The workshop is free, instructor-led, and runs in major cities worldwide. To express interest in attending a future session, visit [agenticfootballcup.com](https://agenticfootballcup.com).

If you want to dig into the building blocks today:

- **Strands Agents quickstart:** [strandsagents.com](https://strandsagents.com/)
- **Bedrock AgentCore documentation:** [docs.aws.amazon.com/bedrock-agentcore/](https://docs.aws.amazon.com/bedrock-agentcore/)

If you ship a team, we'd love to see it. Tag us when you do, because every match is a Strands story.

---

*Content sourced from [strandsagents.com/blog/inside-agentic-football-cup/](https://strandsagents.com/blog/inside-agentic-football-cup/) and paraphrased/reformatted for compliance with licensing restrictions.*
