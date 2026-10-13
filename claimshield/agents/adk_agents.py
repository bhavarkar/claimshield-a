"""ADK agent graph.

    claimshield_orchestrator (SequentialAgent)
      ├─ intake_agent           Document AI -> normalised bill + policy, rows into BigQuery
      ├─ policy_agent           Vertex AI Search -> governing clauses -> structured terms
      ├─ findings_team (ParallelAgent)
      │    ├─ audit_agent       duplicates / arithmetic / stay / totals SQL + policy replay
      │    └─ benchmark_agent   reference-pricing and upcoding SQL
      ├─ reconciliation_agent   billed vs covered vs owed, recovery estimate
      └─ dispute_agent          Gemini explanations + letters, report PDFs to Cloud Storage

Each sub-agent is a custom BaseAgent: the work is deterministic and auditable, and Gemini is
called inside the steps where language is needed. Results travel between agents through ADK
session state (`EventActions.state_delta`), so the same graph runs under InMemoryRunner locally
and on Vertex AI Agent Engine.
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from google.adk.agents import BaseAgent, ParallelAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

from ..services import get_services
from ..trace import TRACES
from .steps import STEPS

DESCRIPTIONS = {
    "intake_agent": "Parses the hospital bill and insurance policy into structured data and loads line items into the warehouse.",
    "policy_agent": "Retrieves the policy clauses that govern the claim and extracts the limits, co-payments and exclusions.",
    "audit_agent": "Finds duplicate charges, arithmetic and length-of-stay errors, and settlement deductions that contradict the policy.",
    "benchmark_agent": "Compares charges with reference pricing and flags possible upcoding.",
    "reconciliation_agent": "Computes billed, covered, owed and recoverable amounts.",
    "dispute_agent": "Drafts plain-language explanations, dispute letters and the reconciliation report.",
}


class StepAgent(BaseAgent):
    """Runs one ClaimShield step against the session state and emits its result as state_delta."""

    step_name: str

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        state = dict(ctx.session.state)
        trace = TRACES.get(state["case_id"])
        delta = await asyncio.to_thread(STEPS[self.step_name], state, trace, get_services())
        summary = next((e["message"] for e in reversed(trace.events) if e["agent"] == self.name and e["kind"] == "result"), "done")
        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            content=types.Content(role="model", parts=[types.Part(text=summary)]),
            actions=EventActions(state_delta=delta),
        )


def build_root_agent() -> SequentialAgent:
    def step(name: str) -> StepAgent:
        return StepAgent(name=name, step_name=name, description=DESCRIPTIONS[name])

    return SequentialAgent(
        name="claimshield_orchestrator",
        description="Audits a hospital bill against an insurance policy on behalf of the policyholder.",
        sub_agents=[
            step("intake_agent"),
            step("policy_agent"),
            ParallelAgent(
                name="findings_team",
                description="Runs the audit and benchmark checks concurrently.",
                sub_agents=[step("audit_agent"), step("benchmark_agent")],
            ),
            step("reconciliation_agent"),
            step("dispute_agent"),
        ],
    )


root_agent = build_root_agent()
