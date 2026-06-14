# Carlos
When no LLM key is provided in the docker call, a mock is used. I want to create a fallback when there are issues using real LLMs instead of a mock approach. Help me build a prompt to request Claude Cowork to build a plan to create a fallback if it doesn't already exists. Reinforce the mix of BDD and TDD approaches and the usage of loging and observability structure

---
# Gemini
To ensure your pipeline handles real-world API instabilities gracefully, implementing a structured resilient fallback framework—rather than just a local mock toggle—is an excellent Next Step.

For a critical core backend component, blending **BDD (Behavior-Driven Development)** for high-level business expectations with **TDD (Test-Driven Development)** for unit isolation ensures your failover logic behaves exactly as expected when live production keys encounter unexpected errors.

Here is a highly precise, context-aware prompt you can copy and paste directly into your Claude CoWork thread to map out this architectural layer.

---

### Copy and Paste into Claude CoWork:

```markdown
Act as a Staff Backend & Reliability Engineer. We want to design an architectural plan and implementation strategy to handle LLM Provider Outages gracefully. 

Current Context:
Right now, our docker-compose ecosystem supports a hardcoded `LLM_BACKEND` switch (`mock` | `openai` | `anthropic`). If `openai` is chosen and fails, the request currently bubbles up an unhandled exception or retries indefinitely via tenacity. 

Target Goal:
Instead of a simple environment switch, we need to implement an Automated Resilience Fallback Framework. If our primary engine (e.g., OpenAI `gpt-4o-mini`) experiences repeated rate limits, network timeouts, or sudden 5xx outages, the system should gracefully degrade down to a secondary provider (e.g., Anthropic `claude-haiku-4-5-20251001`) to complete the resume evaluation without failing the recruiter's upload request.

Please build a comprehensive execution plan incorporating the following principles:

1. Double-Loop Testing Paradigm (BDD + TDD):
   - Define BDD Scenarios (using Given/When/Then syntax) specifying what happens to a candidate application's pipeline evaluation status when a primary provider fails and a fallback triggers successfully.
   - Outline the TDD implementation cycle, detailing how we will write failing unit tests using pytest-mock to safely simulate network timeouts, context-length crashes, and rate limits across providers without hitting live APIs.

2. Deterministic Telemetry & Observability:
   - Detail the structured logging JSON pattern to emit when a fallback occurs. We need explicit event logs tracking the degradation event (e.g., `{"event": "primary_llm_failed", "provider": "openai", "error_type": "RateLimitError", "retry_attempt": 3}`) and the handoff resolution (e.g., `{"event": "fallback_llm_engaged", "target_provider": "anthropic", "candidate_id": "..."}`).
   - Ensure the final metrics output preserves an audit trail flag (`is_evaluated_via_fallback=True`) on the application database row so users interacting with the frontend can see a visual alert that a backup model evaluated the metrics.

3. Clean Integration with Instructor + Tenacity:
   - Explain how our current orchestration logic (`PipelineOrchestrator`) will balance tenacity retries (e.g., retry 3 times on the primary) before bubbling down to the alternative wrapper.

Provide the clear architectural blueprints, the BDD scenarios, and the testing scaffolding steps so I can implement this cleanly on top of our existing Docker stack.

```