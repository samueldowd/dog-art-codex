# Research sources and provenance

Research was performed for this documentation package on **2026-10-22**. Online documentation and product capabilities can change. The future builder must verify relevant interfaces against the installed service versions and selected API model; reading a source is not evidence that the user's infrastructure has been tested.

## Requested prior build reference

| Source | Use in this package |
|---|---|
| [Formula Pro actual initiating build spec, pinned revision](https://github.com/samueldowd/fpa/blob/f418e53cc700e65f2c5351f8f5c11a935ad46de0/docs/BUILD_SPEC.md) | Primary structural reference: explicit execution contract, requirements, phases, delegation, decisions, testing and handoff. |
| [Commit introducing that specification](https://github.com/samueldowd/fpa/commit/e785976983c71e69f7aca470f2f46b1b9fd231db) | Establishes provenance of the initiating artifact. |
| [FPA implementation validation at the reviewed revision](https://github.com/samueldowd/fpa/blob/f418e53cc700e65f2c5351f8f5c11a935ad46de0/docs/IMPLEMENTATION_VALIDATION.md) | Supporting evidence that the original requirements were tracked through implementation; not the kickoff source. |

The user confirmed the main-branch location of the exact kickoff file. [The source review](10-PRIOR-BUILD-REVIEW.md) identifies the reviewed commit and explains the adaptations. The new pipeline is not implemented in, or published to, the FPA repository.

## Codex build-document practices

| Primary source | Applied practice |
|---|---|
| [Codex AGENTS.md guidance](https://learn.chatgpt.com/docs/agent-configuration/agents-md) | Keep automatically loaded instructions concise; account for hierarchy and explicitly read referenced modules. |
| [Codex subagents guidance](https://learn.chatgpt.com/docs/agent-configuration/subagents) | Explicit delegation authorization, primary orchestration, bounded ownership and inherited permission limits. |
| [Running long-horizon tasks with Codex](https://developers.openai.com/blog/run-long-horizon-tasks-with-codex) | Concrete milestones, persistent project state and iterative observable validation. |
| [Execution plans for long-running work](https://developers.openai.com/cookbook/articles/codex_exec_plans) | A living plan with progress, decisions, discoveries and outcomes that survives context continuation. |
| [Codex security overview](https://learn.chatgpt.com/docs/security) | Tool and environment restrictions remain real boundaries; a prompt cannot grant missing machine access. |

These sources inform execution practices. The future launch prompt explicitly requests subagents; the current document-authoring task has not created a team of implementation agents. Check actual availability rather than assuming a particular Codex client implements every feature.

## Application interfaces to verify during the build

| Primary source | Required verification |
|---|---|
| [OpenAI image-generation guide](https://developers.openai.com/api/docs/guides/image-generation) | Available model, image-input support, PNG transparency, valid size/quality parameters, official Python SDK request/response behavior, errors and current pricing references. |
| [Ollama vision](https://docs.ollama.com/capabilities/vision) | Exact installed Gemma tag accepts images, supported input encoding, actual capability and resource behavior. |
| [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs) | Structured response constraints supported by the chosen model/server; schema validation remains application-owned. |
| [Frigate MQTT integration](https://docs.frigate.video/integrations/mqtt/) | Configured prefix, tracked-event payload and completed-event semantics on the installed Frigate version. |
| [Frigate event-clip API](https://docs.frigate.video/integrations/api/event-clip-events-event-id-clip-mp-4-get/) | Authenticated clip endpoint, availability delay, status/error behavior and recording requirements. |
| [Home Assistant Samba app documentation](https://github.com/home-assistant/apps/blob/master/samba/DOCS.md) | Actual configured share, allowed hosts and mapping to the user's media directory. |
| [smbprotocol Python project](https://github.com/jborean93/smbprotocol) | High-level `smbclient` operations, authentication, safe replacement and error behavior for the installed library/server. |
| [systemd.timer documentation](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html) | Installed Debian support for calendar/timezone scheduling, persistence and catch-up behavior. |
| [Proxmox pct manual](https://pve.proxmox.com/pve-docs/pct.1.html) | Existing permissions and actual `pct status`, `pct exec` and `pct push` syntax on the target host. Verify through on-host help before mutations. |

The renderer and matching/queue/state contracts are project-specific engineering decisions. This document does not assert that a general image encoder already achieves the recognition target. That requires the actual labeled evaluation.

## Handling documentation drift

Prefer the installed service's supported API and the official SDK interface. Record versions and material deviations. If a source redirects, resolve the official replacement and record it; a broken link alone does not justify abandoning a required feature. If selected model capabilities cannot satisfy a requirement, prepare an evidence-backed alternative and escalate the material tradeoff rather than silently changing the model or quality target.

No live image price, current account model entitlement, user's Frigate release, Ollama model tag, CT112 OS version, Samba configuration or Home Assistant slideshow implementation has been verified by authoring this document.


Frontend lifecycle continuation references: [official custom-card contract](https://contributors.home-assistant.io/frontend/custom-ui/card/), [HA card host](https://github.com/home-assistant/frontend/blob/dev/src/panels/lovelace/cards/hui-card.ts), [official WebSocket connection](https://github.com/home-assistant/home-assistant-js-websocket/blob/master/lib/connection.ts). These document mutable connection readiness and hass assignment; actual foreground DOM/image verification remains the acceptance evidence.
