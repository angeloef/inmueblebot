# Inmobot — Product Document

> Single source of truth for product vision, users, features, and principles.
> Intended audience: designers, developers, AI agents, and collaborators.
> Last updated: May 2026

---

## 1. What is Inmobot?

Inmobot is a B2B SaaS product for real estate agencies in Argentina and Paraguay. It consists of two components:

1. **A 24/7 WhatsApp AI agent** that attends prospective buyers and renters, searches available properties, schedules visits, answers FAQs, and hands off to a human agent when needed.
2. **A web-based admin dashboard** where the agency manages their property catalog, views their lead pipeline, handles their calendar, and configures the bot.

The product is designed specifically for the interior of Argentina (Misiones province and the NEA region), not for Buenos Aires or international markets.

---

## 2. The Problem

Real estate agents in Argentina's interior spend 15–20 hours per week answering repetitive WhatsApp messages, manually coordinating visits, and losing leads that arrive outside business hours. Agencies have no CRM, no shared calendar, and no visibility into their pipeline.

**Agent-level pain:**
- Responds to the same questions every day, including weekends and nights.
- Loses leads that don't get a reply within 5 minutes.
- Schedules visits manually, creating conflicts.
- Has no record of what each client was looking for or when they last interacted.

**Agency-level pain:**
- Cannot see the pipeline: no idea how many leads exist, at what stage, or who owns them.
- No coordination between agents: duplicate visits, missed opportunities.
- Client data lives with each agent individually. If an agent leaves, the data leaves too.
- No market data: no way to know what types of properties are in demand, at what price, in which zones.

---

## 3. The Solution

Inmobot automates the first stage of the real estate sales funnel — from initial WhatsApp inquiry to scheduled visit — while giving the agency full visibility through a real-time dashboard.

**What the bot does autonomously:**
- Understands natural language queries in Rioplatense Spanish.
- Searches the property database with flexible matching (accent-insensitive, fuzzy location).
- Shows property details and photo galleries via WhatsApp.
- Schedules, reschedules, and cancels visits with Google Calendar sync.
- Remembers each user's preferences across sessions (zone, budget, property type, number of rooms).
- Scores leads automatically based on interaction quality.
- Answers FAQs about the agency without human intervention.
- Transfers to a human agent on request or when out of scope.
- Recommends properties based on accumulated user profile.

**What the dashboard provides:**
- Real-time KPIs: visits today, active leads, available properties, upcoming appointments.
- Full property catalog management (CRUD with photos).
- Client/lead CRM with interaction history and lead scores.
- Shared calendar with Google Calendar sync.
- Configurable FAQ editor.
- Bot configuration: agency name, business hours, human agent WhatsApp number.

---

## 4. Target Users

### Persona 1 — The Solo Agent
- Licensed real estate broker working independently.
- 10–25 properties in their portfolio.
- Works alone or with a part-time assistant.
- Located in Posadas, Oberá, Eldorado, or any city in Misiones/NEA.
- **Core need:** Automate WhatsApp responses without losing the personal touch.
- **Key message:** "$55/month so leads don't go cold at 11pm."

### Persona 2 — The Agency Owner
- Runs an agency with 2–5 agents.
- 30–80 active properties.
- Has a physical office, an outdated website, and data scattered across WhatsApp chats.
- **Core need:** Visibility and coordination. Wants to see the whole business from their phone.
- **Key message:** "New lead at 9am. Visit confirmed at 10am. Weekly summary on Monday morning."

### Persona 3 — The Developer / Investor
- Operates large-scale development projects or manages a large asset portfolio.
- Makes data-driven decisions. Can pay more if ROI is clear.
- **Core need:** Market intelligence. Wants to know what's being searched, where, and at what price.
- **Key message:** "Market data no real estate agency in the NEA has yet."

---

## 5. Feature Set by Plan

### Plan Básico — $55 USD/month
*For the solo agent or small agency.*

- WhatsApp AI chatbot (up to 1,000 conversations/month)
- Up to 25 properties in the system
- Lead dashboard: score, history, saved preferences
- WhatsApp notifications to agent: new qualified lead, visit scheduled/cancelled
- Automatic visit scheduling with Google Calendar + client confirmation
- Configurable 24/7 FAQ
- Human handoff
- Support via WhatsApp, response within 4 business hours

### Plan Profesional — $195 USD/month
*For the established agency that wants full digital presence and team coordination.*

- Everything in Básico, unlimited properties
- Professional website with auto-synced property catalog
- Chatbot embedded in the website (same bot on WhatsApp + web)
- Advanced dashboard: conversion funnel, weekly trends, exportable reports
- Multi-agent support (up to 5 agents) with individual profiles and shared calendar
- Automatic weekly activity summary sent to the owner's WhatsApp every Monday
- Customized lead scoring by zone and property type
- Automatic cold lead follow-up: re-engagement message after 7 days of inactivity
- Priority support, response within 1 business hour

### Plan Enterprise — $420 USD/month
*For the large agency or developer that wants market intelligence.*

- Everything in Profesional, unlimited agents
- Advanced analytics: ETL pipeline, analytics tables, market trend dashboard
- Predictive scoring: AI model that predicts which leads will convert (available after 20+ clients on the platform)
- Full conversion funnel: Lead → Qualification → Property Details → Scheduled → Visit → Close
- Predictive WhatsApp alerts: "hot lead without reply for 2h", "property with no visits in 7 days"
- Cross-sell recommendations: "users who viewed this also viewed..."
- Monthly executive reports with month-over-month comparisons
- API access for integration with existing agency systems
- 99.9% SLA
- VIP support: dedicated channel, response within 30 minutes, personalized onboarding

---

## 6. Feature Comparison Matrix

| Feature | Básico | Profesional | Enterprise |
|---|:---:|:---:|:---:|
| WhatsApp AI chatbot | ✓ | ✓ | ✓ |
| Property limit | 25 | Unlimited | Unlimited |
| Lead dashboard | ✓ | ✓ | ✓ |
| Advanced dashboard (funnel, trends) | — | ✓ | ✓ |
| Automatic lead scoring | ✓ | ✓ | ✓ |
| WhatsApp notifications | ✓ | ✓ | ✓ |
| Visit scheduling + Google Calendar | ✓ | ✓ | ✓ |
| Configurable FAQ | ✓ | ✓ | ✓ |
| Human handoff | ✓ | ✓ | ✓ |
| Multi-agent | — | Up to 5 | Unlimited |
| Professional website with catalog | — | ✓ | ✓ |
| Bot embedded in website | — | ✓ | ✓ |
| Automatic weekly report | — | ✓ | ✓ |
| Cold lead follow-up | — | ✓ | ✓ |
| Predictive lead scoring (AI) | — | — | ✓ |
| Predictive WhatsApp alerts | — | — | ✓ |
| Market analytics dashboard | — | — | ✓ |
| Cross-sell recommendations | — | — | ✓ |
| API access | — | — | ✓ |
| SLA | 99.5% | 99.7% | 99.9% |
| Support response time | <4h | <1h | <30min VIP |
| Price (USD/month) | $55 | $195 | $420 |
| Price (ARS/month approx.) | ~$66,000 | ~$234,000 | ~$504,000 |

---

## 7. Key Differentiators

1. **Real conversational AI, not a scripted flow.** The bot understands natural language in Rioplatense Spanish. There are no menus or decision trees — the client types naturally and the bot responds intelligently.

2. **WhatsApp-native.** No apps to install. No links to click. The client uses the app they already have. WhatsApp has a 98% open rate.

3. **Google Calendar included.** Visits sync automatically. No manual data entry across tools. The agent sees everything in their existing calendar.

4. **Cross-session memory.** The bot remembers each client between conversations. It doesn't ask what it already knows. Experience is personalized from the second interaction.

5. **Purpose-built for real estate in interior Argentina.** Not a generic CRM adapted for real estate. Designed around the actual workflow of an agency in Posadas or Oberá.

6. **Regional pricing.** Calculated for Misiones, not for Buenos Aires or international markets. 2–5x cheaper than assembling the equivalent with generic tools (WATI + Zapier + Calendly).

7. **30-day free trial, no credit card.** The client experiences results before paying. Trial includes the full plan and guided onboarding.

---

## 8. Product Principles

These principles guide every product and design decision:

1. **The bot should feel like an expert receptionist, not a search engine.** It remembers, anticipates, and adapts. It doesn't make the client repeat themselves.

2. **Zero friction for the client.** The client shouldn't have to learn anything new. WhatsApp is the channel because it's already there.

3. **Zero friction for the agent.** The dashboard should show the most important thing first. Fewer clicks to the most common actions.

4. **The agent always has control.** The bot escalates when it doesn't know something. Every conversation has a human handoff option. The agent can always override.

5. **Data belongs to the agency, not the agent.** Client history, preferences, and conversations are stored centrally. If an agent leaves, nothing is lost.

6. **Honest about limitations.** The bot should not hallucinate properties or fabricate information. When it doesn't find a match, it says so and proposes alternatives.

7. **Speed is a feature.** The bot responds in under 2 seconds. The dashboard loads key data without waiting. Latency erodes trust.

---

## 9. What Inmobot Is Not

- **Not a general-purpose chatbot platform.** It doesn't build flows for e-commerce, support, or other industries.
- **Not a property portal.** It doesn't aggregate listings from multiple agencies (like Zonaprop or Argenprop). Each instance serves one agency.
- **Not a replacement for the agent.** It handles the top of the funnel. High-value negotiations and closings still require human judgment.
- **Not an international product.** It's designed for Rioplatense Spanish, Argentine currency, and the workflow of agencies in the NEA region.

---

## 10. Technical Overview (for context)

| Layer | Technology | Role |
|---|---|---|
| Messaging | WhatsApp Business Cloud API (Meta) | Send and receive messages |
| AI engine | OpenAI GPT-5 | Natural language understanding, tool calling, response generation |
| Database | PostgreSQL | Properties, users, appointments, lead history, preferences |
| Session memory | Redis | Short-term conversation context |
| Calendar | Google Calendar API | Automatic event creation and reminders |
| Dashboard | React (Vite) SPA | Admin web interface |
| Backend | FastAPI (Python) | API, webhook processing, business logic |
| Infrastructure | Render (cloud) | Hosting, managed DB, Redis — zero maintenance for the client |

---

## 11. Pricing Summary

| Plan | USD/month | ARS/month | Target |
|---|---|---|---|
| Básico | $55 | ~$66,000 | Solo agent, 1-person agency |
| Profesional | $195 | ~$234,000 | Agency with 2–5 agents |
| Enterprise | $420 | ~$504,000 | Large agency or developer |

**Trial:** 30 days free, full plan, no credit card required.
**Annual discount:** 2 months free (pay 10, get 12).
**Referral discount:** 1 free month per referred client that converts to paid.

ARS prices indexed to USD exchange rate, reviewed quarterly.

---

## 12. Market Context

- **Region:** Misiones, Argentina. Expanding to Corrientes, Chaco, Formosa (NEA) in year 2.
- **Language:** Rioplatense Spanish.
- **Currency:** ARS invoiced (USD-pegged, adjusted quarterly for inflation).
- **Payment methods:** Mercado Pago (debit, credit, transfer) + USD stable transfer.
- **Competitive landscape:** No direct competitor with conversational AI + WhatsApp + real estate CRM + Google Calendar + regional pricing. Indirect competitors: WATI ($50+), Landbot ($60+), ManyChat ($45+), Inmobu ($50+).

---

*Inmobot · product.md · May 2026*
