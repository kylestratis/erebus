# Erebus v2 Architecture Design

## Summary

Erebus v2 redesigns the agent from a single Letta-managed entity into a **hub-and-spoke orchestrator**: a lean control loop that classifies user intent and delegates to isolated, task-specific subagents, each invoked as a direct, provider-agnostic model call. The orchestrator is the sole component that reads and writes memory, talks to the user, and opens tunnels to external peer agents. Subagents never communicate with each other, with external services directly, or with memory — the orchestrator mediates everything. This mediation boundary enforces information separation across domains (email, writing, research) and is the primary security mechanism of the design.

The framework choice is a deliberate hybrid: Letta is retained as a memory backend only (core, archival, and recall tiers), while a custom orchestrator built on the project's existing provider-agnostic model abstraction replaces Letta's hidden control loop. The design activates several dormant patterns already in the codebase — a `ModelProvider` ABC, an MCP multi-server client, and an async per-task context — rather than introducing new abstractions. Interfaces (Discord, CLI, and a web dashboard) are decoupled from the core behind a neutral `ChatRequest`/`ChatResponse`/`AgentEvent` contract, making the orchestrator transport-agnostic. Delivery is phased across four increments: orchestrator core and provider seam first, then memory scoping and observability surfaces, then peer tunneling and autonomous scheduled behavior, and finally semantic knowledge management.

## Definition of Done

1. **Orchestrator architecture design** defining Erebus as a hub agent that delegates to isolated, task-specific subagents with tiered memory access. Subagents have scoped views of user memory based on their role (e.g., email agent sees contacts but not essay drafts). Some subagents are persistent (email, writing), others ephemeral (one-off research).

2. **Memory system design** covering persistent user knowledge across conversations, scoped sharing between orchestrator and subagents, and a phased path toward semantic search, active knowledge graph, and research workflows. Must address the gap where Letta memory blocks exist as templates but are never actually updated.

3. **Inter-agent protocol design** for communicating with peer agents (language tutor, future external agents). Peer agents are independent projects that communicate via a shared protocol, not submodules of Erebus.

4. **Interface abstraction design** that decouples Erebus from Discord, enabling a CLI REPL for interactive testing and a web observability dashboard for monitoring agent state, memory contents, subagent activity, and tool call logs.

5. **Framework recommendation** (Letta vs Agent SDK vs hybrid vs alternative) grounded in the architectural requirements above, with concrete rationale tied to each design decision.

The design must be phased: what to build now vs later, with clear boundaries between phases.

## Acceptance Criteria

### erebus-v2-arch.AC1: Orchestrator delegates to isolated subagents
- **erebus-v2-arch.AC1.1 Success:** A user message is routed through `Orchestrator.handle()` and dispatched to the correct subagent based on classified intent.
- **erebus-v2-arch.AC1.2 Success:** A subagent is invoked as a provider-agnostic model call with only its allowlisted memory view in the prompt.
- **erebus-v2-arch.AC1.3 Success:** A persistent subagent (email) retains its recall history across sessions; an ephemeral subagent (research) does not.
- **erebus-v2-arch.AC1.4 Failure:** A subagent cannot invoke a tool absent from its `tools` allowlist.
- **erebus-v2-arch.AC1.5 Failure:** A subagent cannot reach an MCP server absent from its `mcp_servers` allowlist.
- **erebus-v2-arch.AC1.6 Edge:** Unclassifiable intent falls back to a default handler rather than erroring.

### erebus-v2-arch.AC2: Memory is scoped, persistent, and orchestrator-written
- **erebus-v2-arch.AC2.1 Success:** The orchestrator writes a validated update to a Letta core block (proving the template-never-updated gap is closed).
- **erebus-v2-arch.AC2.2 Success:** A subagent's assembled prompt contains only its allowlisted core blocks and archival namespaces.
- **erebus-v2-arch.AC2.3 Failure:** The email subagent cannot retrieve data from the `essays/`, `notes/`, or `research/` archival namespaces.
- **erebus-v2-arch.AC2.4 Failure:** A subagent-suggested memory write outside its allowed scope is rejected and not persisted.
- **erebus-v2-arch.AC2.5 Edge:** A subagent with `archival_namespaces=None` performs no archival retrieval.

### erebus-v2-arch.AC3: Peer tunnel relays safely with a guaranteed exit
- **erebus-v2-arch.AC3.1 Success:** The orchestrator opens a `PeerSession` and relays user↔peer turns verbatim without running its own LLM/tools/memory writes.
- **erebus-v2-arch.AC3.2 Success:** A peer-initiated handback (`status=complete`) closes the tunnel and returns the user to orchestrator mode.
- **erebus-v2-arch.AC3.3 Failure:** The user escape token breaks the tunnel even when the peer is unresponsive.
- **erebus-v2-arch.AC3.4 Failure:** A peer timeout / transport error force-closes the tunnel and recovers the user gracefully.
- **erebus-v2-arch.AC3.5 Success:** A close-summary is ingested as untrusted input and does not auto-trigger a tool call or unvalidated memory write.
- **erebus-v2-arch.AC3.6 Edge:** A peer that returns no close-summary results in zero memory crossing back.

### erebus-v2-arch.AC4: Interfaces are decoupled from the core
- **erebus-v2-arch.AC4.1 Success:** The Discord adapter produces a `ChatRequest` with a canonical `user_id` (no `discord.*` types reach the core).
- **erebus-v2-arch.AC4.2 Success:** The CLI REPL drives the orchestrator and renders the `AgentEvent` stream inline.
- **erebus-v2-arch.AC4.3 Success:** The dashboard subscribes to the `AgentEvent` stream and displays memory contents, active subagents, and tool logs.
- **erebus-v2-arch.AC4.4 Failure:** An unauthenticated/non-whitelisted Discord request is rejected at the adapter, before the core.
- **erebus-v2-arch.AC4.5 Edge:** The same `ChatRequest` produces equivalent core behavior regardless of originating channel.

### erebus-v2-arch.AC5: Model calls are provider-agnostic
- **erebus-v2-arch.AC5.1 Success:** A `ModelRef` resolves through `ProviderRegistry` to a `ModelProvider` and completes a call.
- **erebus-v2-arch.AC5.2 Success:** Two subagents configured with different `ModelRef`s are invoked through the identical orchestrator code path.
- **erebus-v2-arch.AC5.3 Success:** Changing a logical tier's `ModelRef` in config reroutes the affected subagents with no code change.
- **erebus-v2-arch.AC5.4 Failure:** An unknown provider name in a `ModelRef` raises a clear resolution error.

### erebus-v2-arch.AC6: Autonomous scheduled behavior
- **erebus-v2-arch.AC6.1 Success:** An existing `ScheduledJob` invokes `Orchestrator.handle_autonomous()` with a goal and completes without a user turn.
- **erebus-v2-arch.AC6.2 Success:** At least one autonomous behavior (self-directed research or essay draft) runs end-to-end and persists its output.

## Glossary

- **Orchestrator**: The central control-loop component of Erebus. It owns intent classification, memory access, subagent invocation, peer relay, and the `AgentEvent` event stream. Nothing else writes to memory or talks directly to a subagent or peer.
- **Subagent**: An isolated, task-specific model call invoked by the orchestrator. Declared as a data record (`SubagentDefinition`) rather than a class; receives only the memory view its `MemoryScope` allows; cannot write to memory directly.
- **SubagentDefinition**: A data record that fully describes a subagent — its system prompt, model reference, memory scope, tool and MCP allowlists, persistence flag, and turn budget.
- **MemoryScope**: A per-subagent allowlist that specifies which core blocks, archival namespaces, and recall history a subagent may see. Uses an allowlist (opt-in) rather than a denylist (opt-out).
- **ModelRef**: A provider-qualified reference to a model (e.g., `anthropic / claude-opus-4-8`). Resolved at runtime by `ProviderRegistry` to a concrete `ModelProvider`.
- **ProviderRegistry**: A registry that maps a `ModelRef`'s provider name to a `ModelProvider` implementation, making every model call provider-agnostic.
- **ModelProvider ABC**: An abstract base class (in `agents/models/base.py`) that defines a uniform `complete()` interface over different LLM providers. `AnthropicProvider` is the only current implementation.
- **Letta**: An open-source agent memory framework used here strictly as a memory backend. Provides the core, archival, and recall memory tiers. Its own hidden control loop is not used.
- **Core memory**: The always-in-context memory tier, stored as named blocks (e.g., `persona`, `human`, `context`, `contacts`). Present in every orchestrator prompt.
- **Archival memory**: Namespaced, semantic-search memory (e.g., `email/`, `notes/`, `essays/`, `research/`). Retrieved on demand; never surfaced unless the requesting subagent's `MemoryScope` explicitly allows the namespace.
- **Recall memory**: Conversation history, namespaced per surface (Discord, CLI, etc.).
- **AgentEvent**: A structured event emitted by the orchestrator representing observable activity — tool calls, subagent invocations, memory reads/writes, tunnel state changes. Consumed by interface adapters and the observability dashboard.
- **ChatRequest / ChatResponse**: Transport-neutral data contracts exchanged between an interface adapter and the orchestrator core. `ChatRequest` carries a canonical `user_id`, text, and channel; `ChatResponse` carries the reply text, an event list, and session state.
- **InterfaceAdapter**: A component that translates between a transport (Discord, CLI, HTTP) and the neutral `ChatRequest`/`ChatResponse`/`AgentEvent` contracts. Each adapter owns its own authentication; no transport-specific types reach the core.
- **DiscordAdapter**: The interface adapter for the Discord bot. Replaces the current direct wiring in `bot/client.py`; moves whitelist and DM-only security checks to the adapter edge.
- **CLIAdapter / CLI REPL**: A command-line interface adapter for interactive local testing. Drives the orchestrator and renders the `AgentEvent` stream inline.
- **PeerSession**: A relay session to an external, independent peer agent (e.g., a language tutor). Erebus acts as a transparent pipe — no LLM inference, no memory writes — while the tunnel is open. Closed by peer handback, user escape token, or timeout.
- **Peer tunnel**: The Streamable HTTP relay mechanism used by `PeerSession`. Has a separate out-of-band control plane (`open` / `relay` / `status` / `close` / `heartbeat`) and a user escape token that bypasses the peer entirely.
- **Escape token**: A user-typed string (e.g., `/exit`) intercepted by the orchestrator before it reaches the peer agent. Guarantees the user can always exit a peer session, even if the peer is unresponsive.
- **Close-summary**: The single, optional payload a peer agent may return when a session ends. Treated as untrusted input; cannot directly trigger a tool call or unvalidated memory write.
- **Lethal trifecta**: The cross-domain information leakage risk the design is built to prevent: email content surfacing in an essay draft (or similar contamination across privacy-sensitive domains) because all memory was globally shared.
- **Streamable HTTP**: The transport protocol used for peer agent communication (the MCP Streamable HTTP transport). Chosen for its support of both request/response and server-sent event (SSE) streaming.
- **MCPClientManager**: The existing multi-server MCP client in `agents/mcp/client.py`. Currently exposes all MCP tools to all agents; the new design routes MCP servers per-subagent via `SubagentDefinition.mcp_servers`.
- **MCP (Model Context Protocol)**: A protocol for connecting language model agents to external tools and data sources. MCP servers expose tools that agents can call.
- **APScheduler**: The Python job scheduling library backing `bot/scheduler/`. Existing scheduled jobs will call the orchestrator's `handle_autonomous()` entry point instead of `eidolon.chat()`.
- **ScheduledJob**: An abstract base class in `bot/scheduler/` that defines the interface for autonomous cron-driven behaviors (daily note, end-of-day sync, weekly review, journal).
- **Prompt caching**: An Anthropic-specific optimization where stable system prompt prefixes are cached between requests at approximately 10% of the normal token cost. Relevant to the cost argument for short, stable subagent prompts; not a portable cross-provider feature.
- **Provider-agnostic**: Describes model calls that are expressed through the `ModelProvider` ABC and `ProviderRegistry` seam, so they work identically regardless of which LLM provider backs them.
- **Ephemeral subagent**: A subagent with `persistent=False`; its recall history is not retained across sessions (e.g., a one-off research task).
- **Persistent subagent**: A subagent with `persistent=True`; its recall history carries over across sessions (e.g., the email triage agent).
- **Memory suggestion**: A structured item a subagent may include in its response proposing a memory write. The orchestrator validates it against the subagent's `MemoryScope` before deciding whether to persist it.
- **Autonomous entry point (`handle_autonomous()`)**: An orchestrator method that accepts a goal and runs the full subagent pipeline without a user turn, called by the scheduler.
- **`contextvars`**: The Python standard-library module used for async-safe, per-task scoped state. Currently used for `user_id` and timezone; the design adds `agent_id` via the same mechanism.
- **YAGNI**: "You Aren't Gonna Need It" — a software design principle cited in this document to justify shipping only the `AnthropicProvider` now and adding further provider implementations when a real need arises.

## Architecture

Erebus becomes an **orchestrator**: a hub agent that owns a lean control loop and delegates work to isolated, task-specific subagents. The orchestrator is the only component that talks to memory, to the user, and to external peers. Subagents never talk to each other, to the outside world, or directly to memory. This mediation boundary is the primary security mechanism — it is how email content is prevented from surfacing in an essay (the "lethal trifecta" concern).

The framework decision follows from the architecture: **hybrid — Letta as a memory backend only, plus a custom lean orchestrator built on the provider-agnostic model abstraction.** The Claude Code Agent SDK was rejected because its subprocess opacity cannot satisfy three hard requirements: emitting a custom observability event stream, owning the peer relay loop (including the escape hatch), and Letta-style always-in-context memory. Pure Letta was rejected because its ~4k-token per-request overhead, single-model-per-agent constraint, and hidden loop lose cost control, model routing, and observability.

### Components

- **Orchestrator** (`agents/orchestrator/`, new): owns the control loop. Loads user context from Letta, classifies intent, scopes memory, invokes subagents, mediates peer sessions, processes responses, and emits an `AgentEvent` stream. The only writer to memory.
- **SubagentRegistry + SubagentDefinition** (new): subagents are declared as data, not classes. Each definition carries a name, description, system prompt, model reference, memory scope, tool allowlist, MCP server allowlist, persistence flag, max turns, and temperature.
- **MemoryScope** (new): declares which core blocks, archival namespaces, and recall history a subagent may see. Allowlist, not denylist.
- **ProviderRegistry + ModelRef** (new, built on the existing `ModelProvider` ABC): resolves a provider-qualified model reference to a concrete provider implementation. Makes every model call provider-agnostic.
- **Letta memory layer** (`agents/eidolon/`, retained): provides core memory (always-in-context blocks), archival memory (namespaced semantic search), and recall memory (conversation history). Consumed by the orchestrator only.
- **PeerSession tunnel client** (new): opens a relay session to an external peer agent over Streamable HTTP, forwards conversation turns verbatim, enforces an out-of-band control plane and a user escape token, and ingests a single close-summary.
- **InterfaceAdapters** (new): Discord, CLI REPL, and web dashboard adapters that translate between their transport and the neutral `ChatRequest`/`ChatResponse`/`AgentEvent` contracts. Each owns its own authentication.
- **MCPClientManager** (`agents/mcp/`, retained): tool/data access for the orchestrator; different MCP servers can be allowlisted to different subagents.
- **Scheduler** (`bot/scheduler/`, retained): existing APScheduler jobs call the orchestrator's autonomous entry point instead of `eidolon.chat()`. No scheduler changes required.

### Core Contracts

Subagent and memory-scope declaration:

```python
@dataclass
class MemoryScope:
    core_blocks: list[str]            # e.g. ["persona", "preferences"]
    archival_access: bool
    archival_namespaces: list[str] | None   # None = no archival access
    recall_access: bool
    recall_window: int | None

@dataclass
class ModelRef:
    provider: str                     # "anthropic" | "openai" | "google" | "local" | ...
    model: str                        # provider-native id, e.g. "claude-opus-4-8"
    max_tokens: int | None = None

@dataclass
class SubagentDefinition:
    name: str
    description: str
    system_prompt: str
    model: ModelRef
    memory_scope: MemoryScope
    tools: list[str]                  # allowlist
    mcp_servers: list[str]            # allowlist
    persistent: bool
    max_turns: int
    temperature: float
```

Provider resolution (built on the existing `ModelProvider` ABC in `agents/models/base.py`):

```python
class ProviderRegistry:
    """Maps a provider name to a ModelProvider instance."""
    def resolve(self, ref: ModelRef) -> ModelProvider: ...
```

Interface boundary — the orchestrator is transport-agnostic:

```python
@dataclass
class ChatRequest:
    user_id: str                      # canonical identity, not a Discord ID
    text: str
    channel: str                      # "discord" | "cli" | "dashboard"
    session_id: str | None            # for tunnel / multi-turn continuity
    metadata: dict                    # interface-specific; never read by core

@dataclass
class ChatResponse:
    text: str
    events: list[AgentEvent]          # tool calls, subagent hops, memory writes
    session_state: str                # "active" | "tunneled" | "awaiting_approval"

class InterfaceAdapter(Protocol):
    async def receive(self) -> ChatRequest: ...
    async def send(self, response: ChatResponse) -> None: ...
    async def stream(self, events: "AsyncIterator[AgentEvent]") -> None: ...
```

Peer tunnel — the only path to an external agent:

```python
@dataclass
class PeerSession:
    peer: str                         # "language-tutor"
    transport: str                    # "http-sse" (Streamable HTTP)
    user_token: str                   # opaque identity — NOT Erebus memory
    intent: str | None                # one-line handoff context, optional
    escape_token: str                 # e.g. "/exit" — intercepted, never relayed

# Control plane (out-of-band from relayed conversation data):
#   open(user_token, intent) -> session_id
#   relay(session_id, turn)  -> turn           # data plane
#   status(session_id)       -> active | complete | error
#   close(session_id)        -> summary | None  # single untrusted payload back
#   heartbeat                -> liveness for timeout detection
```

### Data Flow

**Interactive:** Interface adapter authenticates and emits a `ChatRequest` → orchestrator loads user context from Letta → intent classified by a cheap model → memory scoped for the selected subagent → subagent invoked as a direct, provider-agnostic model call with a lean assembled prompt → response processed, orchestrator performs any validated memory writes → `ChatResponse` (plus `AgentEvent` stream) returned to the adapter.

**Autonomous:** A scheduled job calls the orchestrator's autonomous entry point with a goal (e.g. "research a topic of interest," "draft an essay"). Same downstream flow; no user turn.

**Peer tunnel:** Orchestrator detects handoff intent → opens a `PeerSession` to the peer over Streamable HTTP → enters relay mode where Erebus is a transparent pipe (no LLM, no tools, no memory writes) → user turns and peer responses are forwarded verbatim → session ends on peer handback, user escape token, or timeout → optional close-summary is ingested as the single untrusted payload and may be stored as an observation.

### Memory Model

Four tiers, all owned by Letta, all mediated by the orchestrator:

- **Core memory** (always in orchestrator context): `persona`, `human`, `context`, plus domain blocks (e.g. `contacts`, `interests`, `writing_ctx`).
- **Archival memory** (semantic search, namespaced): `email/`, `notes/`, `research/`, `essays/`. Namespaces partition memory so a subagent cannot retrieve another domain's data.
- **Recall memory** (conversation history), namespaced per surface.
- **Scoping:** the orchestrator reads memory and assembles only the allowlisted view for each subagent. A subagent never learns that excluded memory exists.
- **Writes:** subagents cannot write to memory. They may return *memory suggestions* in their response; the orchestrator validates each against the subagent's allowed scope and performs the write. This closes the gap where Letta memory blocks currently exist as templates but are never updated — the orchestrator becomes the memory writer.

## Existing Patterns

Investigation of the current codebase found these patterns, which this design retains and builds on:

- **Provider abstraction already exists.** `agents/models/base.py` defines a `ModelProvider` ABC with a uniform `complete()` method and neutral data classes (`Message`, `Response`, `ToolDefinition`, `ToolUse`, `ToolResult`). `agents/models/anthropic.py` implements it as `AnthropicProvider` (default `claude-haiku-4-5-20251001`, with retry logic) but is currently dormant — not in the active Discord flow. This design activates it as the subagent engine and adds `ProviderRegistry`/`ModelRef` on top. No new abstraction is invented; the existing one is used as intended.
- **Letta memory layer.** `agents/eidolon/client.py` wraps Letta (`EidolonMemory`, `get_or_create_agent`, an approval-based tool-routing chat loop with `MAX_TOOL_ITERATIONS`). The approval+result pattern is adaptable to subagent delegation. `agents/eidolon/memory.py` defines `PERSONA_BLOCK`, `HUMAN_BLOCK`, `CONTEXT_BLOCK` templates that are never updated, and archival memory that is configured but unused — both addressed by making the orchestrator the memory writer.
- **Tool registry.** `agents/eidolon/tools.py` provides a `ToolRegistry` (`register`, `execute`, `can_handle`) with a `NativeToolExecutor` Protocol. It is a singleton, not per-agent scoped; this design introduces per-subagent tool allowlists via `SubagentDefinition.tools`.
- **MCP multi-server support.** `agents/mcp/client.py` (`MCPClientManager`) already supports multiple servers, but all agents see all MCP tools. This design routes servers to subagents via `SubagentDefinition.mcp_servers`.
- **Async per-task context.** `agents/context.py` uses `contextvars` (`_UserContext`) for async-safe per-task scoping (`user_id`, timezone). An `agent_id` context var fits the same pattern for subagent scoping.
- **Scheduler.** `bot/scheduler/base.py` defines a `ScheduledJob` ABC with a `JobContext` (config, eidolon, vault, mcp, discord_user) and `chat()`/`send_dm()` helpers. Four jobs run today (daily note 6am, end-of-day sync 11:55pm, weekly review Sun 6pm, journal 11:58pm). Jobs will call the orchestrator's autonomous entry point instead of `eidolon.chat()`.
- **Discord coupling (the pattern this design deliberately diverges from).** `bot/client.py` wires Discord directly into the agent flow (`on_message` → security/whitelist/DM-only checks → `_handle_ai_message` → `eidolon.chat()`), leaking `discord.*` types into the agent layer. This design extracts a `DiscordAdapter` and moves security to the adapter edge; the core only ever receives already-authenticated `ChatRequest`s.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Orchestrator Core + Provider Seam
**Goal:** Route the existing Discord experience through a new orchestrator built on a provider-agnostic model seam, with no user-visible change, and make the orchestrator the memory writer.

**Components:**
- `Orchestrator` in `agents/orchestrator/` — control loop implementing `handle()`; loads user context from Letta, classifies intent, invokes subagents, processes responses, performs validated memory writes, emits `AgentEvent`s.
- `SubagentRegistry`, `SubagentDefinition`, `MemoryScope`, `ModelRef` in `agents/orchestrator/` — data-driven subagent declaration and memory scoping.
- `ProviderRegistry` in `agents/models/` — resolves `ModelRef` to a `ModelProvider`; wires the dormant `AnthropicProvider` as the default subagent engine.
- `ChatRequest`/`ChatResponse`/`AgentEvent` contract types in `agents/orchestrator/`.
- `DiscordAdapter` in `bot/` — refactor of `bot/client.py` to emit `ChatRequest` and render `ChatResponse`; whitelist/DM-only security moves here.
- One real subagent: an intent classifier (cheap model, `tools=[]`, `max_turns=1`, `temperature=0.0`).

**Dependencies:** None (first phase).

**Done when:** Discord behaves as it does today but is routed through `Orchestrator.handle()`; the intent classifier runs as a provider-agnostic model call; the orchestrator performs at least one real memory write to a Letta block (proving the template-never-updated gap is closed); tests pass for the ACs this phase covers.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Isolation + Observability
**Goal:** Enforce tiered memory scoping, prove the lethal-trifecta boundary with a real isolated subagent, and add the debug/observability surfaces.

**Components:**
- Memory scoping enforcement in `Orchestrator` — allowlisted core blocks, archival namespaces, recall window per `MemoryScope`; subagent-suggested writes validated against scope before persistence.
- Email triage subagent (persistent) with a scope that includes `contacts`/`preferences` and the `email/` archival namespace only — cannot read `essays/`, `notes/`, or `research/`.
- `CLIAdapter` in `bot/` (or `interfaces/`) — interactive REPL rendering the `AgentEvent` stream inline (subagent hops, tool calls, memory reads/writes).
- `DashboardAdapter` — read-mostly web surface subscribing to the `AgentEvent` stream; visualizes memory contents, active subagents, tunnel sessions, tool logs; can inject a `ChatRequest` for testing.

**Dependencies:** Phase 1.

**Done when:** Erebus is drivable from the CLI REPL and observable in the browser; a test proves the email subagent cannot retrieve data from a non-allowlisted archival namespace; scope-violating memory suggestions are rejected; tests pass for the ACs this phase covers.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Peers + Autonomy
**Goal:** Tunnel to an external peer agent, and run autonomous scheduled behaviors.

**Components:**
- `PeerSession` tunnel client in `agents/orchestrator/` (or `agents/peers/`) — Streamable HTTP relay; out-of-band control plane (`open`/`relay`/`status`/`close`/`heartbeat`); user escape token intercepted before relay; timeout/failure force-close; close-summary ingested as a single untrusted payload.
- Language tutor integration wiring (peer registry entry, transport config).
- `handle_autonomous()` on `Orchestrator` — goal-driven entry point for scheduled runs.
- Scheduler wiring: existing `ScheduledJob`s call `handle_autonomous()` instead of `eidolon.chat()`.
- Writing subagent (persistent) and research subagent (ephemeral).

**Dependencies:** Phase 2 (scoping + event stream).

**Done when:** Erebus opens a tunnel to the tutor, relays turns, and returns cleanly via handback, user escape token, and timeout; a close-summary is ingested and treated as untrusted; at least one autonomous cron-driven behavior runs end-to-end; tests pass for the ACs this phase covers.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Knowledge Management
**Goal:** Add semantic knowledge capabilities within the existing architecture (no structural change).

**Components:**
- Archival semantic search over namespaces (embeddings) in the memory layer.
- Research workflow agent — web search → synthesize → write vault notes.
- Knowledge graph over archival memory — entity/concept relationships.

**Dependencies:** Phase 2 (Phase 4 is independent of Phase 3 and may be reordered by priority).

**Done when:** A "what do I know about X" query returns semantically relevant archival results; the research workflow produces linked vault notes; tests pass for the ACs this phase covers.
<!-- END_PHASE_4 -->

## Additional Considerations

**Provider-specific optimizations are not cross-provider guarantees.** Anthropic prompt caching (stable system prompts cached at ~10% cost) underpins the token-efficiency argument for the orchestrator's lean, stable subagent prompts. Other providers have their own caching semantics or none. Caching is treated as a per-provider optimization, not a portable feature.

**Feature parity across providers is not uniform.** Tool use, structured output, and streaming differ by provider. The `ModelProvider` ABC is the contract; each implementation must satisfy it or explicitly declare a capability gap. Only `AnthropicProvider` is implemented now; additional providers are added behind the same interface on demand (YAGNI) — the seam ships in Phase 1, the second implementation ships when a real need appears.

**Peer output is untrusted input.** During a tunnel, Erebus relays to a human and takes no action on peer output, so there is nothing to exploit. The untrusted-input boundary collapses to exactly one payload — the optional close-summary — which receives full untrusted treatment before any memory write. The user escape token guarantees the human can always exit a peer session regardless of peer state (analogous to SSH's `~.`).

**Peers vs subagents are different trust and control domains.** Subagents are internal, in-process, provider-agnostic model calls with scoped prompts — no protocol. Peers are external, independent processes with their own memory and lifecycle, reachable only through the tunnel. The design keeps these paths separate by construction.
