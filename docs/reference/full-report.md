# Deming: Project Report and PRD (APU Cloud Innovation Hackathon 2026)

Nov 8, 2026 · @Harsh Mahendra Kudu

## Executive summary

Deming is a scheduled Gemini Enterprise agent that makes sure risky or end-of-life connected devices get fixed or replaced instead of being forgotten. It reads a spreadsheet of devices, checks each one against exploited-vulnerability and end-of-life data, tells the right owner what to do, waits for a human to approve, and later checks that the fix happened. It is named after the Deming Cycle (Plan-Do-Check-Act), the improvement loop it runs on every device.

**Status on 9 November 2026:** selected as our best-supported idea for the APU Cloud Innovation Hackathon 2026. It is not built yet and has not been validated with any real user. The prototype deadline is now Friday 13 November 2026, 12:00 PM, extended from Tuesday 10 November at 23:59 MYT. The prototype does not need Gemini Enterprise, but the final product for the 17 November pitch must use it.

**Why we chose it**

- It fits what the sponsor's reviewers said they will look at: a real problem, first-party and third-party connectors, a scheduled workflow, research and impact.
- The problem has measured evidence: a 43-day median time to fix exploited vulnerabilities, and 42.5% of the vulnerabilities exploited in 2025 hitting end-of-life devices.
- It needs no hardware, it gives a live interactive demo, and we can measure it against a baseline.
- It is portable: one spreadsheet goes in, so APU or any other organization can reuse it later.

**Three things a new reader must know**

1. Gemini Enterprise is not required for the 13 November prototype but must be used in the final product on 17 November, according to the organizers' 9 November notice. Licenses are expected on 10 November, with no guarantee.
2. The judging rubric is unpublished. We only know what one speaker said in the briefing.
3. Deming is not proven unique. Commercial products already cover most of this ground, for example Eolix (end-of-life checks on inventory exports) and Xeol (end-of-life detection). Our edge is the closed loop, the measured evaluation and the portable no-code design.

**Where to find things:** the name, the hackathon facts, how we got here, the evidence, the solution, the requirements, the architecture, what we take from big tech, the evaluation plan, hackathon alignment and demo, the plan and risks, honest limits, and the sources are the sections below, in that order.

## The name: Deming

We named the project after W. Edwards Deming because the Plan-Do-Check-Act loop that carries his name is exactly what the system runs on every device.

### What the Deming Cycle is

The Deming Cycle, also called the Deming Wheel or PDCA, is a four-step loop for continuous improvement: plan a change, do it, check the result, then act by standardizing the change if it worked or going round again if not. Walter Shewhart developed the first repeating improvement cycle (specify, produce, inspect) in the 1920s. Deming expanded it and introduced it in Japan in the 1950s, and in 1951 the Japanese Union of Scientists and Engineers reshaped it into the Plan-Do-Check-Act form. One account adds that Deming taught "study" rather than "check" and later called the simplified wording a corruption. So we say "the Deming Cycle" and never claim he invented it. Sources: [Lean Enterprise Institute](https://www.lean.org/lexicon-terms/pdca/) and [BusinessBalls](https://www.businessballs.com/business-development/plan-do-check-act/), both opened on 8 November 2026.

### How the loop maps to the system

&#91;embedded content: the Deming loop on every device · 4 steps, loops back each run\]

Check is the step that makes the loop closed, so the demo has to show it working: a flagged device is fixed in the Sheet, and the next run closes its ticket and updates the log. The tagline is Patch or Retire, the two outcomes the loop drives toward.

### Using the name in the demo

The opening takes about 30 seconds, and the demo script later in this report is timed around it.

1. State the problem in one sentence with the two key numbers (about 10 seconds).
2. Say "So we named it Deming", show one slide with the four steps, and say in one sentence who he was.
3. Say "That is exactly what this system does, for every device, every week."
4. Go straight into the live demo.

### How we chose the name

- PatchLoop was a working title. It read as generic, because "patch" plus a noun is a crowded naming pattern in this category.
- Web searches on 8 November 2026 found no IT or security product named Deming. They were not trademark searches, and surnames are generally weaker trademarks than invented words, so check the domain and the GitHub handle before publishing.
- The runner-up is Recura, a coined name from the Latin recurare, "to restore by taking care of". It stays in reserve.

## The hackathon

The APU Cloud Innovation Hackathon 2026 asks APU students to build a prototype where cloud, IoT and networking meet, and the prototype is due Friday 13 November 2026 at 12:00 PM, extended from Tuesday 10 November at 23:59 MYT. Sources: the organizers' 9 November notice, the [official event page](https://apu-cloud-innovation-hackathon.gdgocapu.com/) (opened 8 November 2026) and the 3 November briefing transcript.

### Event facts

| Item | Detail |
| --- | --- |
| Organizer | APU School of Technology, with GDGoC APU supporting event execution |
| Sponsor and partners | NTT DATA (sponsor), Google Cloud, NexConnect 2026 |
| Theme | When Cloud, IoT, and Network Converge |
| Tracks | Smart Campus & Student Experience; Intelligent Automation & Digital Transformation; Data-Driven Research & Intelligent Decision Making. Teams can explore any track. |
| Eligibility | APU students only. Teams of 2 to 5 including the leader. |
| Format | Online build, per a GDGoC APU LinkedIn post. Location listed as APU, Kuala Lumpur. |
| Dates (MYT) | Registration opens 26 Oct. Briefing and Gemini training 3 Nov, 6 to 9 PM. Registration closes Sun 8 Nov, 23:59. Prototype deadline extended on 9 Nov to Fri 13 Nov, 12:00 PM (was Tue 10 Nov, 23:59). The 9 November notice does not restate the assessment window (11 to 14 Nov) or the top-five announcement (Sun 15 Nov), so both are unconfirmed. |
| In-person final | The organizers' 9 November notice confirms a final pitch for the top five on 17 November, and the final product must use Gemini Enterprise tools. A LinkedIn post said in person at APU. The notice does not say, so the format is unconfirmed. |
| Prizes | RM4,000 total: RM2,000, RM1,000, RM700, RM150, RM150 |
| Submission | Project title, chosen track, summary of at least 50 characters, HTTPS repository link, PDF pitch deck up to 10 MB. Demo link is optional. Only the team leader submits, and final submission locks the project and PDF. |
| Judging | The official page says criteria will be released soon (as of 8 Nov). |

### What the briefing added

The 3 November briefing was run by NTT DATA solution architects, with the organizers' coordinator answering logistics. The transcript is auto-generated and garbles some words ("Germany enterprise" means Gemini Enterprise). Timestamps follow the transcript: minutes:seconds in the first hour, then hours:minutes:seconds.

| Topic | What was said | Time |
| --- | --- | --- |
| Gemini Enterprise | Mandatory. Agents should be built inside it as chat agents or workflow agents. Update, 9 November: the organizers say the 13 November prototype does not need Gemini Enterprise tools, but the 17 November final product must use them. | 1:29:40, 1:36:40, 1:41:36 |
| Antigravity | Called something they need to see used (1:10:04), then "a supporting tool" (1:41:36). The two statements conflict. | 1:10:04, 1:41:36 |
| Code | Low-code or no-code platform. Coding is not expected. Deliverables are slides or a PDF plus a GitHub repo with a README. | 9:08, 1:32:44 |
| Connectors | Main focus is first-party (Google) and third-party connectors. MCP servers count as an add-on. | 1:36:16 to 1:36:32 |
| Review | Reviewers will be invited into each team's Gemini Enterprise app to see the project working. | 1:30:56 |
| What to cover | Five things: problem statement, how you solved it, research, teamwork, impact. | 1:26 to 1:27 |
| Video | A 3 to 4 minute video covering problem, solution, research and impact. Earlier they said "a 10 minute video or a repo". Unclear if required. The official page lists no video field. | 1:27:32, 10:44 |
| Licenses | Google-sponsored Gemini Enterprise licenses. Whether per person or per team is unknown. Allocated by organizer admins. Update, 9 November: distribution is delayed. The notice expects licenses on Tue 10 Nov, after the Diwali holidays, with no guarantee. APU and Google run distribution, and GDGoC APU has no control over it. | 1:31:36, 1:34:48 |
| Cloud credits | Unknown. | 1:21:24 |
| Example ideas given | Admission-analyst agent, scholarship eligibility, study-planning agents, trending-repo digest, filtering open telemetry data. Other teams are likely to copy these. | 26:56 to 1:25:40 |

### Judging criteria stated in the briefing

In answer to a student's question, the NTT DATA speaker listed what reviewers look at (1:35:20 to 1:36:32). These are topics, not weights.

1. **Impact:** how the solution affects the current environment (students, the whole university, or operations) and how long that would take to realize, for example 3 or 6 months.
2. **Technical build:** how it was put together and which connectors were used. First-party and third-party connectors are the main focus. MCP is an add-on.
3. **Research:** how well the problem and solution were researched.
4. **Day-to-day workflow value:** for scheduled or autonomous workflows, how well they work in everyday productivity.

### Still unconfirmed

- Gemini Enterprise: the 9 November notice answers this. It is not needed for the 13 November prototype and is required for the 17 November final.
- Whether Antigravity is required or optional.
- Whether a video is required.
- Whether synthetic or simulated data is acceptable.
- Whether licenses are per person or per team.
- The format of the 17 November pitch, and whether it is in person.
- The rubric weights.

## How we got here

We changed direction several times, and the briefing on 3 November forced the biggest change. This log lists every idea we seriously considered, in order, with the reason it was kept or dropped.

| Stage | Idea | Verdict | Why |
| --- | --- | --- | --- |
| 1 | Initial opportunity research: 20 ideas across the three tracks, including NetProof, SensorTrust and RouteProof | Reference only | Scores were an assistant's subjective ratings, not evidence of demand or judging results. It assumed an open build with simulated hardware, which the briefing later contradicted. Files: research-report.md and opportunity-scores.csv. |
| 2 | ExperimentPilot: AI that runs experiments to find the best edge-cloud settings for IoT | Parked | No documented demand. The search space is small enough to sweep exhaustively. Standard Bayesian optimization is the real competitor. Results depend on a simulated network. Saved in special-shortlist.md. |
| 3 | Eleven documented real-world problems (research-code reproducibility, research-data access, cloud outages, campus connectivity, and others) | Input material | Used to look for problem-first ideas. None proves demand at APU. File: verified-real-world-problems.md. |
| 4 | Live incident agent: "AI fixes the network" | Dropped | Crowded category. A public entry for this hackathon (APU-Nexus) already pitches a five-agent Gemini controller that self-heals incidents, with a judge crisis-injection bar. Its savings figures appear to come from its own simulator. |
| 5 | Flood-station telemetry: what should a station send first when its link is failing | Dropped | Documented Malaysian problem (telecom and transmission stations disrupted in floods), but it needs custom code and real-time behavior. The briefing requires a no-code Gemini Enterprise agent, and scheduled agents run hourly at best. |
| 6 | Briefing transcript reviewed on 8 November | Changed the rules | Gemini Enterprise mandatory, no-code, connectors, judging topics, a five-part write-up. Earlier custom-code ideas no longer fit. |
| 7 | DataReady: a scheduled agent that checks IoT research datasets are ready to hand over | Demoted | Evidence was general, and it sits closest to the briefing's own admission-analyst example, which other teams are likely to copy. |
| 8 | Deming (first called PatchLoop): a scheduled agent that chases risky and end-of-life connected devices until fixed or replaced | Selected | Best fit to the briefing's criteria, measured problem evidence, no hardware, interactive demo, portable. |
| 9 | Market research on Google, ServiceNow, Salesforce, Atlassian, Tenable, Qualys, AWS, Microsoft, Nokia, Cisco and NTT DATA | Adopted as method | The same pattern appears everywhere: scheduled investigation, context, routing, human approval, verification. We borrow one feature from each. See the section on big tech. |
| 10 | Name: the working title PatchLoop read as generic, so replacement names were checked for existing products | Selected: Deming | Named after the Deming Cycle (Plan-Do-Check-Act), the loop the system runs on every device. No IT or security product with this name turned up in web searches on 8 November. Runner-up: Recura. See the section on the name. |
| 11 | Organizers' 9 November notice: deadline extended to Fri 13 Nov, 12:00 PM, and Gemini Enterprise needed only for the final pitch | Changed the plan | Removes the no-license risk for the prototype. We build the logic and the evaluation now on the Sheet, keep prompts portable, and move into Gemini Enterprise when licenses arrive. The notice does not restate the assessment or results dates. |

### Why Deming over the nearest alternatives

- **Quiet NOC (alert triage):** mirrors the sponsor's network alarm products, but it sits in the lane where large vendors already ship similar agents, and the public test data labels log lines rather than incidents.
- **DataReady:** weaker problem evidence and the closest to an example the speaker gave.
- **IoT CostGuard (cloud cost spikes from device behavior):** the IoT-specific cost evidence is thin, mostly vendor blogs, and the Data Insights agent needs administrator setup.

These three remain fallbacks if the Deming feasibility test fails.

### Corrections made along the way

- We first read the hackathon context as having no 17 November event. A later search excerpt suggested an in-person top-five pitch. Still unconfirmed.
- We recommended the live incident agent, then withdrew it after finding the public rival.
- We recommended the flood project before reading the briefing, then dropped it.

## The problem and the evidence

Organizations are slow to fix weaknesses that attackers already exploit, and some connected devices can never be fixed because the maker stopped supporting them. Finding the weakness is largely solved, since free feeds exist. The gap is getting the right person to act and proving that they did.

**Problem statement:** people who run connected devices (IT staff, lab technicians, facilities teams) have no reliable, low-effort way to learn which of their devices are exposed or unsupported, who owns each one, what to do about it, and whether it was done.

### What the evidence says

| Finding | Detail | Source and how we read it |
| --- | --- | --- |
| Fixes take weeks | In the 2026 Verizon DBIR, the median time to fully fix a known-exploited vulnerability was 43 days, up from 32. Only 26% were fully fixed, down from 38%. At day 7, 60 to 70% were still open. | [watchTowr summary](https://watchtowr.com/resources/verizon-dbir-2026-vulnerability-exploitation/). Secondary coverage. We did not open the Verizon PDF. |
| Many exploited devices are end of life | 42.5% of vulnerabilities exploited in 2025 affected end-of-life or likely end-of-life devices. 65% of those exploited by botnets did. Consumer routers and similar networking products made up 56% of exploited edge-device vulnerabilities. | [VulnCheck 2026 report](https://www.vulncheck.com/blog/network-edge-device-report-2026), opened. Vendor research. "Likely end of life" is its own heuristic. |
| The public exploited list is incomplete | Only 23.7% of the exploited edge-device vulnerabilities VulnCheck identified appear in CISA's list (KEV). | Same report. We treat KEV as a baseline, not the full picture. |
| The feed is free and machine-readable | KEV is published as JSON with no login, with fields such as vendor, product, date added, required action, due date and ransomware use. It held about 1,750 entries in October 2026. | Third-party mirrors and guides: [Socket](https://socket.dev/glossary/cisa-kev), [fastCRW](https://fastcrw.com/playground/pergamon/cisakev), [a practitioner guide](https://dev.to/adam_lewandowski_59674796/cisa-kev-catalog-a-working-sysadmins-guide-to-actually-using-it-2o15). We did not open CISA's own page. |
| Some entries have no fix | For some end-of-life routers, CISA's required action is to stop using the product. Example: the D-Link DIR-823X, end of life in early 2025, added to KEV on 24 April 2026. | [endoflife.ai analysis](https://endoflife.ai/article-dlink-eol-routers-kev) and [a news summary](https://cipherwatch.pages.dev/articles/2026-04-29-dlink-dir823x-cve-2025-29635-mirai-cisa-kev). Vendor advisories not opened. Used as an illustration. |
| Policy benchmark | CISA directive BOD 26-02 (5 February 2026) orders US federal civilian agencies to inventory and replace end-of-support edge devices. It applies only to federal agencies, and CISA's device list is not public. | [BleepingComputer](https://bleepingcomputer.com/news/security/cisa-orders-federal-agencies-to-replace-end-of-life-edge-devices) and [Washington Technology](https://www.washingtontechnology.com/contracts/2026/02/cisa-orders-agencies-patch-and-replace-end-life-devices-citing-active-exploitation/411261/), search excerpts. We cite it as a benchmark only. |
| Matching is hard | Joining an inventory to vendor product strings by name misses matches, because inventory names rarely match the strings in vulnerability databases. | [Practitioner article](https://patchdayalert.pages.dev/blog/inventory-vulnerable-software-basic-tools/). Illustrative, not research. |
| Malaysian context | CyberSecurity Malaysia reported 6,209 cases in 2024, up 5%, mostly against government, finance and business. A Malaysian university campus publicly confirmed a ransomware incident. | [Intelligent CISO excerpt](https://magazine.intelligentciso.com/intelligent-ciso-issue-86/0021152001748963835/p25) and [Swinburne Sarawak statement](https://www.swinburne.edu.my/?p=54256). Context only. |
| APU context | APU's facilities page lists a CyberSecurity Talent Zone, a Robotics Lab, IT Labs and a Google Center of Excellence. APU also offers a BSc IT with an IoT specialism. | [APU campus facilities](https://www.apu.edu.my/campus-facilities). We read only the first 100,000 of about 175,000 characters. It shows APU runs connected labs. It says nothing about the patch status of its devices. |

### Why a scheduled workflow agent fits

- Detection feeds are free, so the repetitive part is chasing owners and following up.
- Verification is simple: a version number in the inventory changes, or it does not.
- Large vendors are building the same pattern, which suggests the approach is sound. It also means we are not first.

### What we could not verify

- That APU has unpatched or end-of-life devices, how many, or who owns them.
- That an agent like this reduces time to fix in practice.
- The Verizon figures against the original PDF.
- How often the matching approach errs on messy device names. This is what the evaluation tests.

## The solution in plain language

Deming works like a recall system for the connected gadgets in an organization. It keeps checking, tells the right person what to do, and makes sure it got done.

### How it works, step by step

1. A person keeps one spreadsheet of devices: name, location, owner, firmware version, whether it faces the internet, and how critical it is.
2. On a schedule, the agent reads the spreadsheet and turns messy names into a clean vendor, product and version.
3. It checks each device against two things: the public list of exploited vulnerabilities, and end-of-life dates.
4. It puts each device in a lane: patch it, retire it, fine, or unknown.
5. It drafts the right action for the owner: update instructions with a deadline, or a replacement request with interim steps such as isolating the device.
6. It waits for a human to approve before sending anything. The approval appears in the Gemini Enterprise Inbox and is recorded in a log.
7. After approval it sends the email, books a maintenance window in Calendar and opens a ticket.
8. On the next run it checks the spreadsheet again. If the version changed or the device was removed, it closes the ticket. If not, it reminds the owner and escalates.

### The four lanes

| Lane | When | What the agent does |
| --- | --- | --- |
| Patch | A fix exists | Update instructions, a deadline, a maintenance window, then verify the new version |
| Retire | The vendor no longer supports the device | Replacement request, interim mitigation such as isolating it, then verify removal |
| Fine | No known issue | Log only |
| Unknown | It cannot match the device with confidence | Ask a human. It never guesses. |

### Worked example (illustrative)

A lab technician adds a D-Link DIR-823X router to the spreadsheet. The agent matches it to a product that its sources describe as end of life with no patch, and listed in KEV. It labels the device "Retire" and drafts a replacement request plus a note to isolate the device until then. Both land in the approver's Inbox with a confidence score and the evidence. The approver approves. The agent sends the email, books a window and opens a ticket. The technician replaces the router and updates the spreadsheet. On the next run the agent sees the device is gone and closes the ticket.

The product facts in this example come from secondary sources and are used only as an illustration.

### What the agent never does

- It never scans, changes or reaches into a real device.
- It never sends an email, opens a ticket or books a slot without approval, in the default mode.
- It never guesses on an ambiguous device. It asks.
- It never records a fix without evidence in the spreadsheet.

## Product requirements (PRD)

Deming v1, the hackathon prototype, must run one complete closed loop on a spreadsheet of devices, with human approval before every outward action, and report measured results against a naive baseline.

### Goals

1. Show the full loop: detect, enrich, route, approve, act, verify.
2. Handle both lanes: patch and retire.
3. Make every decision explainable, with evidence, confidence, approver and outcome kept in a durable log.
4. Measure it against a labeled test set and a naive baseline, and report the failures.
5. Stay reusable, with no organization-specific details hard-coded.

### Non-goals for v1

- No scanning, discovery or changes on real devices.
- No automatic remediation and no real-time alerting. Runs are scheduled.
- No claim of real-world savings or accuracy beyond our own test set.
- No replacement for a vulnerability scanner or an IT service-management platform.
- No production security controls such as agent identity or runtime policy enforcement. We describe these as the production path only.

### Users

| Role | Needs | Uses |
| --- | --- | --- |
| Device owner (lab technician, facilities) | A clear instruction and deadline, with little noise | Email, Calendar |
| Approver (IT security lead, lab manager) | Evidence and confidence, and a one-click approve or reject | Gemini Enterprise Inbox, Chat |
| Administrator (IT) | Keep the inventory and settings current | Google Sheets |
| Reviewer (judge) | See it work, add a device, watch the loop close | Invitation to our Gemini Enterprise app |

### User stories

- As an owner, I get one message per device saying what is wrong, what to do and by when.
- As an approver, I see each proposed action with its lane, evidence and confidence, and can approve or reject it.
- As an administrator, I add a row for a new device and see it handled on the next run.
- As an approver, I see a summary of open, overdue and closed items.
- As a reviewer, I add a device live and watch it flagged, approved and closed.

### Functional requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| FR1 | Read the device inventory from a Google Sheet on a schedule | Must |
| FR2 | Normalize each device name to vendor, product and version, with a confidence score | Must |
| FR3 | Check each device against a refreshed copy of the exploited-vulnerability list (KEV) | Must |
| FR4 | Check each device against end-of-life data from vendor notices or a lifecycle dataset | Must |
| FR5 | Assign each device a lane (patch, retire, fine, unknown) with evidence | Must |
| FR6 | Draft the owner message with the exact action and deadline | Must |
| FR7 | Require human approval before any email, calendar or ticket action (default mode) | Must |
| FR8 | Record every decision in a Decision Log: device, lane, evidence, confidence, approver, time, outcome | Must |
| FR9 | Check for an open ticket on the same device and issue before creating a new one | Must |
| FR10 | Run a verification pass that re-reads the Sheet and closes, reminds or escalates | Must |
| FR11 | Send approved emails through Gmail | Must |
| FR12 | Book maintenance windows in Calendar | Should |
| FR13 | Create tickets through the Jira connector, with a Tickets tab in the Sheet as fallback | Should |
| FR14 | Post a daily or weekly digest to Google Chat | Should |
| FR15 | Keep rules in a Settings tab: what counts as urgent, days to reminder and escalation, suggest-only versus auto per risk tier | Should |
| FR16 | Use the internet-facing flag and criticality to rank priority | Should |
| FR17 | Produce a weekly manager report | Could |
| FR18 | Offer an auto mode for low-risk steps only, never for disconnects or replacements | Could |

### Draft acceptance criteria

These are proposals to revise after the first test run. We have no measurements yet, so we set no numeric targets.

- Zero outward actions without a recorded approval in default mode.
- Every decision has a Decision Log row.
- No duplicate ticket for the same device and issue across runs.
- A ticket closes only when the Sheet shows the fixed version or removal.
- On the test set, Deming beats the naive-matching baseline on normalization accuracy, and every failure is listed.

### Scope tiers

- **Must (the MVP):** FR1 to FR11.
- **Should:** FR12 to FR16.
- **Could:** FR17 and FR18.
- **Won't in v1:** scanning, discovery, auto-disconnect, real-time alerts, agent identity.

## Architecture

Deming is one scheduled main agent in Gemini Enterprise that calls four narrow subagents, keeps its data in Google Sheets, acts through Gmail, Calendar and Jira, and asks for approval in the Inbox.

&#91;embedded content: architecture and approval flow · 4 subagents, 1 human gate\]

The top row runs left to right, the bottom row runs right to left, and the Verifier feeds the next scheduled run.

### Subagents

| Subagent | Job | Reads | Writes |
| --- | --- | --- | --- |
| Normalizer | Turn messy device names into vendor, product and version, score its confidence, and ask when unsure | Inventory | Normalized fields and confidence |
| Checker | Compare each normalized device with the exploited-vulnerability list and lifecycle data, and assign a lane with evidence | Normalized inventory, KEV copy, lifecycle copy | Lane and evidence |
| Planner | Draft owner messages, tickets and calendar proposals, rank priority, and avoid duplicates against open tickets | Lane, owner, criticality, Settings, Tickets | Proposed actions |
| Verifier | On the next run, check whether versions changed or devices were removed, then close, remind or escalate. This is inventory-confirmed: it shows the record changed, not that the device itself is fixed | Inventory, Tickets, Decision Log | Ticket status and reminders |

### Connectors and feeds

| Piece | Type | Role | Status or risk |
| --- | --- | --- | --- |
| Google Sheets | First-party | Inventory, Decision Log, Settings and Tickets tabs | Core |
| Google Drive | First-party | Holds refreshed copies of the KEV and lifecycle data | Core |
| Gmail | First-party | Sends approved owner messages | Needs OAuth consent-screen setup |
| Calendar | First-party | Maintenance windows | Needs OAuth consent-screen setup |
| Google Chat | First-party | Daily or weekly digest | Should-have |
| Jira Cloud | Third-party, native connector | Tickets | Action support unconfirmed. Fallback: a Tickets tab in the Sheet. |
| Feed refresh | A small helper script, for example Apps Script or one written with Antigravity | Copies the KEV JSON and lifecycle data into Drive on a schedule | Untested. We have not confirmed whether a no-code agent can fetch live feeds itself. |
| Custom MCP server | Third-party | Not planned | Public Preview, and it needs an administrator to enable it |

### Data model

Agent-written columns are marked with an asterisk.

| Sheet tab | Columns |
| --- | --- |
| Inventory | device\_id, device\_name\_raw, location, owner\_email, firmware\_version\_raw, internet\_facing, criticality, do\_not\_touch, last\_updated, vendor\*, product\*, version\*, match\_confidence\* |
| Decision Log | timestamp, run\_id, device\_id, lane, evidence (CVE id, due date, end-of-life date), confidence, proposed\_action, approver, decision, action\_taken, outcome, verification\_note |
| Settings | what counts as urgent, days until reminder, days until escalation, suggest-only or auto per tier, approver address, digest channel |
| Tickets | ticket\_id, device\_id, issue, status, opened, due, last\_reminder |

### Autonomy tiers and approvals

| Tier | Actions | Mode |
| --- | --- | --- |
| 0, read-only | Read the Sheet and feeds | Automatic |
| 1, draft | Normalize, classify, draft messages and tickets, write the log | Automatic |
| 2, outward | Send email, book a window, open or update a ticket | Approval required by default |
| 3, consequential | Isolate, disconnect or replace a device | The agent only drafts the request. A named approver decides. The agent never executes it. |

- Every approval leaves a durable record: a Decision Log row and the ticket status, not just a chat reply.
- Below a confidence threshold, the device goes to the Unknown lane and a human decides. We set the threshold during testing.
- A device flagged do\_not\_touch is never proposed for disconnection. It is escalated to a human.

### Platform constraints we know about

- Schedules run hourly at best, need a manual refresh every 14 days, and can start up to 5 minutes late. Source: [Google schedule docs](https://docs.cloud.google.com/gemini/enterprise/docs/agent-designer/schedule-agent).
- Scheduled runs can pause for a human to approve before completing. Source: [Google schedule docs](https://docs.cloud.google.com/gemini/enterprise/docs/agent-designer/schedule-agent?authuser=1).
- Agent Designer is no-code and low-code, builds multi-step agents with subagents, and connects to Gmail, Drive and Jira. Source: [Agent Designer overview](https://docs.cloud.google.com/gemini/enterprise/docs/agent-designer?hl=pl).
- Gmail and Calendar actions need a consent-screen configuration. Source: [Google codelab](https://codelabs.developers.google.com/ge-gws-agents?authuser=5).
- A license is required for the final product. The organizers expect to distribute licenses on 10 November, after the Diwali holidays, but do not guarantee it.

## What we take from big tech, and what is ours

Every large vendor we checked builds the same loop: scheduled investigation, added context, routing to an owner, human approval, then verification. We copy the pattern and take one specific feature from each, then add what none of them gives a student team: an open, portable, no-code and measured version.

We borrow publicly described patterns, not code, branding or proprietary material, and we cite each source. All vendor behavior below comes from announcements and secondary coverage. We have tested none of these products, and vendor results are self-reported.

| Source | What they do | What we take | Where it lands in Deming |
| --- | --- | --- | --- |
| Google Gemini Enterprise ([Inbox article](https://pasqualepillitteri.it/en/news/1431/gemini-enterprise-2026-agent-designer-inbox-practical-examples)) | An Inbox sorts agent activity into Needs your input, Errors and Completed. Scheduled runs can pause for approval. | The approval cockpit | Inbox plus a scheduled-run approval step |
| ServiceNow AI Control Tower ([Royal Cyber](https://www.royalcyber.com/resources/white-papers/ai-governance-framework-servicenow-ai-control/), [ServiceNow community](https://www.servicenow.com/community/admin-experience-blogs/introducing-the-servicenow-ai-control-tower-from-intelligent/ba-p/3261185)) | A unified audit trail of agent actions, and explanations of why a decision was made | A Decision Log and a one-line reason per decision | Decision Log tab with an evidence column |
| Salesforce Agentforce Testing Center ([Tectonic](https://gettectonic.com/?p=34221), [Vantage Point](https://vantagepoint.io/blog/sf/spring-26-agentforce-out-of-box-agent-templates-service-teams?hs_amp=true)) | Generates test cases at scale. Escalates to a human when confidence is low. | Our labeled test set with tricky cases, and a low-confidence rule | Evaluation plan and the Unknown lane |
| Atlassian Jira Triage Agent ([Atlassian update](https://jimiwikman.se/atlassian/atlassian-resources/atlassian-app-updates/triage-work-items-with-the-jira-triage-agent-r1226/), [Rovo guide](https://clearfeed.ai/blogs/atlassian-rovo-agent-guide)) | Suggests priority, labels and assignee. Finds duplicate work items. Offers suggest-only or auto modes. | Duplicate check before ticketing, structured output, suggest-only by default | Planner subagent |
| Tenable Hexa AI ([Tenable](https://www.cxodigitalpulse.com/tenable-delivers-the-industrys-first-always-on-agentic-fleet-for-exposure-management/)) and Qualys Agent Val ([Qualys](https://www.pulse.bot/cto-pulse/news/qualys-unveils-agent-val-first-ai-agent-for-safe-exploit-validation-and-autonomous-remediation-cc9ee3d3-f44e-4d43-8171-cb9b03a1d6da)) | Daily scans, triage by exploitability and reachability, triggered fixes, and a check that the patch landed. Qualys validates exploitability first. | The verification run, an internet-facing field, tiered autonomy | Verifier subagent and the Inventory tab |
| AWS FinOps Agent ([SiliconANGLE](https://siliconangle.com/2026/06/11/aws-launches-finops-agent-bring-ai-cost-governance-cloud-spend-finopsx/), [launch report](https://siliconangle.com/2026/06/09/aws-debuts-aws-finops-agent-help-customers-optimize-cloud-spending/)) | Scheduled recurring workflows. Routes alerts to the responsible team through Slack or Jira. Shows the responsible business unit. | An owner on every action, and a weekly manager report | Gmail, Chat and the Inventory owner column |
| Microsoft Copilot Studio and Network Operations Agent framework ([approval gates](https://radar.firstaimovers.com/copilot-studio-human-in-loop-governance-smes-2026), [Entra Agent ID](https://spaces.collab365.com/posts/microsoft-entra-tracks-copilot-studio-agents-like--Ddy6PG), [NOA](https://techcommunity.microsoft.com/t5/telecommunications-industry-blog/evolving-the-network-operations-agent-framework-driving-the-next/ba-p/4496607)) | Approval gates with a durable audit log, not just a chat confirmation. Each agent linked to a named human sponsor. Agents work inside Teams and Outlook. | Approvals recorded durably, and an agent card naming sponsor, scope and allowed actions | Decision Log, Chat and Gmail |
| Nokia with Google ([Futurum](https://futurumgroup.com/insights/can-nokias-gemini-based-network-agents-make-autonomous-networks-practical/)) and Cisco ([Cisco](https://www.cisco.com/c/en/us/products/collateral/networking/software/internet-cloud-intelligence/agentic-actions-so.pdf)) | Narrow specialist agents (a router agent and an event-triage agent). A closed loop of signal, root cause, action and validation, inside policies and approvals. | Four narrow subagents and rule settings | Main agent with subagents, and the Settings tab |
| NTT DATA, our sponsor ([announcement](https://www.nttdata.com/en-ae/news/2025/ntt-data-unveils-smart-ai-agent-ecosystem)) | Readiness and risk assessments, responsible AI, and "assured outcomes" in its agent ecosystem | A readiness and risk slide: what the agent may and may not do, and how to roll back | Pitch deck |
| Persistent, telecom practitioners ([blog](https://www.persistent.com/blogs/autonomous-networks-closing-the-distance-between-detection-and-action/)) | A telecom leader is quoted as saying that without a confidence score, autonomy is a guess | A confidence score on every decision | Normalizer and Checker outputs |
| Gartner ([press release](https://www.gartner.com/en/newsroom/press-releases/2025-06-25-gartner-predicts-over-40-percent-of-agentic-ai-projects-will-be-canceled-by-end-of-2027)) | Predicts more than 40% of agentic AI projects will be canceled by the end of 2027 and ties success to clear value in cost, speed, quality or scale | Measure value and keep humans in the loop | Evaluation plan and approvals |

### What is ours

1. **Two outcomes, not one.** Many demos only patch. Deming also handles "no patch will ever come, so replace it and isolate it meanwhile".
2. **Portable.** One spreadsheet goes in, and the rules sit in a Settings tab, so another organization can reuse it.
3. **Measured.** A labeled test set, a naive baseline, and the failures published.
4. **Interactive demo.** A reviewer adds a device live and watches the loop close.
5. **Research made visible.** One slide on what we learned from each company and what we adopted.

### What we leave out

- Agent identity, runtime policy enforcement and prompt-injection screening at the platform level. These need administrator setup. We describe them as the production path.
- Safe exploit validation, as Qualys does. It needs scanners we do not have.
- Anything that changes a real device.
- A fully autonomous mode.

## Evaluation plan

We will test Deming on a labeled set of about 60 synthetic devices, compare it with a naive matching baseline, and publish the failures. The exploited-vulnerability and lifecycle data are real, but the inventory is synthetic, so results show behavior on our test set and not real-world accuracy or savings.

### Test set design

The counts are our plan, not findings.

| Group | About | What it checks |
| --- | --- | --- |
| Clear patch cases: in KEV, a fix exists | 15 | The patch lane |
| Clear retire cases: end of life, no patch | 12 | The retire lane |
| Supported, no known issue | 15 | That it stays quiet |
| Messy names: typos, abbreviations, model variants, missing versions | 10 | Normalization |
| Name collisions: a different product with a similar name | 4 | False matches |
| Critical or do-not-touch devices | 4 | Safe handling |

Ground truth: two team members label each device independently from the KEV catalog and vendor lifecycle notices, then reconcile differences.

### Baseline

A naive join of inventory names to KEV vendor and product fields, using lowercase substring or fuzzy string matching as described in [public guides](https://www.decryptiondigest.com/blog/cross-reference-asset-inventory-cisa-kev-catalog).

### Metrics

| Metric | What it shows |
| --- | --- |
| Normalization accuracy | Vendor, product and version correct against ground truth |
| Exposure precision and recall | How many flags are right, and how many real exposures were caught |
| Correct lane | Patch, retire, fine or unknown |
| Unknown rate and correctness | Whether asking a human was the right call |
| Owner routing accuracy | The right person gets the message |
| Duplicate tickets | Should be zero |
| Approval compliance | Outward actions without approval. Should be zero. |
| Verification correctness | Tickets close only when the Sheet shows the fix or removal |
| Stability | The same input run three times, and how often the answers agree |
| Time | Run time, plus a small timing test of a person doing 10 devices by hand |

### Tricky cases

- Typos, abbreviations and a missing firmware version.
- Two products with similar names.
- A do-not-touch device that appears in KEV.
- A ticket already open for the same device.
- An owner who ignores the reminder, to test escalation.
- A device updated to a version that is still vulnerable, to check that any change is not mistaken for a fix.
- Instruction-like text inside a device name field, such as "ignore previous instructions", to check that the agent treats data as data.

### How we report

- A table of results by lane, with every wrong case listed and explained.
- A plain statement that the devices are synthetic and that we make no claim about real-world time saved or accuracy.
- If the baseline ties or wins on a group, we say so.
- The test set, the prompts and the run log are published in the repository.

## Hackathon alignment, demo and submission

Deming is designed to meet every requirement the briefing stated and to give reviewers something they can touch. Since the 9 November notice, the prototype may run outside Gemini Enterprise, and the final product must use it.

### Requirement check

| Requirement | How Deming meets it | Status |
| --- | --- | --- |
| Built in Gemini Enterprise as a chat or workflow agent | A scheduled multi-step workflow agent with subagents | Required for the 17 November final, not for the 13 November prototype. Needs a license, expected on 10 November but not guaranteed. Until then the same steps run on the Sheet. |
| Use first-party connectors | Sheets, Drive, Gmail, Calendar, Chat | Planned |
| Use a third-party connector | Jira Cloud, a native connector | Planned. Sheet fallback if actions are limited. |
| Show how Antigravity was used | Use it to generate the synthetic inventory, the evaluation script and the feed-refresh helper, and keep a usage log | Planned |
| Problem, solution, research, teamwork and impact write-up | Outline below | Planned |
| GitHub repository with a README, a PDF deck, a demo link | Repository with README, test set, prompts and run log. Deck as a PDF under 10 MB. Demo as reviewer access to the app plus a short video. | Planned |
| Reviewers can see it working | Invite them to our Gemini Enterprise app | Needs a license and organizer instructions. For the 13 November prototype, a recorded demo and the repository stand in. |
| Track | Track 2, Intelligent Automation & Digital Transformation. This is our interpretation: devices connected to useful actions. | Chosen at submission |

### Judging topics mapped to our answer

| Topic the speaker named | Our answer |
| --- | --- |
| Impact | Fixes happen sooner and unsupported devices get a retirement path. Measured on the test set. A rollout idea of 1, 3 and 6 months is a hypothesis. |
| Technical build and connectors | Four subagents. Sheets, Drive, Gmail, Calendar, Chat and Jira. |
| Research | The evidence table, the big-tech comparison and the labeled test set |
| Day-to-day workflow | Scheduled runs, approvals in the Inbox, a verification pass and a summary |

### Five-part write-up outline

1. **Problem statement:** the 43-day median fix time, unsupported devices, and why owners are chased by hand.
2. **Solution:** the loop, the four lanes and the four subagents, with a screenshot of each stage.
3. **Research:** the evidence table, what we learned from each large vendor, and what we left out and why.
4. **Teamwork:** who did what, and how we used AI tools including Antigravity. The team fills this in.
5. **Impact:** test-set results with failures, the portability argument, and the rollout idea marked as a hypothesis.

### Three-minute demo script

1. 0:00. State the problem in one sentence with the two key numbers (about 10 seconds). Then name the project: say who Deming was, show the four-step Plan-Do-Check-Act loop on one slide, and say that this system runs that loop on every device (about 20 seconds).
2. 0:30. Show the inventory Sheet and say plainly that it is synthetic.
3. 0:45. A reviewer adds a device row, for example an old router.
4. 1:00. Run the agent. Show the lane, evidence and confidence in the Inbox.
5. 1:25. Approve. Show the email sent, the maintenance window and the ticket.
6. 1:50. Mark the device as replaced in the Sheet, run again, and show the ticket close and the log update.
7. 2:20. Show the evaluation summary, including one failure, and the honest limits.
8. 2:45. Close with the portability point: APU or any organization can reuse it.

Record a backup video of the full run in case the live demo fails.

### Draft submission summary

Deming is a scheduled Gemini Enterprise agent that checks a device inventory against exploited-vulnerability and end-of-life data, routes fixes to owners with human approval, and verifies that each fix happened.

### Submission checklist

- [ ] Team registered before Sunday 8 November, 23:59 MYT
- [ ] Gemini Enterprise license confirmed (needed for the 17 November final, not for the prototype)
- [ ] Project title, track and summary of at least 50 characters
- [ ] HTTPS repository link
- [ ] PDF deck under 10 MB
- [ ] Reviewers invited to the app if we have a license, and a demo video link
- [ ] Team leader submits by 10:00 on Friday 13 November, two hours before the 12:00 PM deadline (the workspace shows the enforced window)

## Plan, risks and open questions

We have about 92 hours from the afternoon of 9 November to the prototype deadline on Friday 13 November at 12:00 PM, and seven gates decide whether Deming continues. The dates below are our proposed schedule, not organizer dates.

&#91;embedded content: proposed build schedule · 7 gates, 1 deadline\]

Only the 13 November deadline and the 17 November final pitch come from the organizers' 9 November notice. The assessment window and results date come from the original event page and are not restated in the notice, so treat them as unconfirmed.

### Priorities from the 10/10 review

A 20-row improvement chart sets the order: finish the end-to-end loop first, then accuracy and the benchmark, then the dashboard and presentation. The chart is a target, not a guaranteed score or win.

| Priority | Work | Chart rows |
| --- | --- | --- |
| 1. Must | The full loop: Patch, Retire, Fine and Unknown lanes, evidence on every decision (CVE, source, timestamp), human approval before any send, next-run verification, and a demo with one Patch, one Retire and one Unknown case | 5, 6, 7, 8, 9, 11, 17 |
| 2. Must | The 60-device test against the naive baseline, with every failure listed | 3, 4, 13 |
| 3. Light | Security (the approval gate, the Decision Log, one prompt-injection test in a device name), reliability (the duplicate-ticket check and a repeated run), and a Summary tab as the dashboard | 10, 12, 14 |
| 4. Light | README with limits, an honest competitor comparison, a final submission checklist, and impact stated only as test-set accuracy and loop behavior | 15, 16, 18, 19, 20 |
| 5. Skip | Extra integrations, advanced analytics, cosmetic polish, failure injection, and access controls beyond Sheet sharing | none |

Three claims are worded carefully on purpose. The Verifier confirms the inventory record changed, which is not proof the device itself was fixed. The differentiation is the KEV match, patch and retire in one decision, owner approval and a verified close, not end-of-life detection alone. Impact is measured as accuracy against the baseline, not real time saved.

### Build gates

| Gate | What must be true | If it fails |
| --- | --- | --- |
| G1 | The agent logic reads the inventory Sheet (inside Gemini Enterprise once the license arrives) | Run the same steps with any tool we can reach and move them into Gemini Enterprise when the license arrives. Keep prompts and output formats identical. |
| G2 | Normalization works on 20 devices and reports confidence | Simplify the names, or add a lookup tab for hard cases |
| G3 | An email draft with an approval step works | Approve through a Chat message plus a Sheet cell if the Inbox flow is unavailable |
| G4 | A ticket is created | Use the Tickets tab in the Sheet instead of Jira |
| G5 | The verification run closes the loop | Cut Calendar and Chat features to protect this gate |
| G6 | Evaluation numbers exist for the test set | Shrink the test set from 60 to 30 devices |
| G7 | Write-up, video and deck are done | Submit by 10:00 on Friday 13 November, two hours before the deadline |

### Risk register

Likelihood and impact are our judgment, not measurements.

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Licenses arrive late or not at all | Unknown | Medium for the prototype, high for the final | The prototype does not need it, per the 9 November notice. Build on the Sheet now, keep prompts portable, and move into Gemini Enterprise when licenses arrive. Tell the coordinators if they have not arrived by Wednesday evening. |
| The agent cannot fetch live feeds | Medium | High | A helper script copies the feeds into Drive |
| Jira actions are limited | Medium | Low | The Tickets tab fallback |
| Matching errors on messy names | High | Medium | Confidence scores, the Unknown lane, testing, and honest reporting |
| Gmail and Calendar consent-screen setup takes time | Medium | Medium | Set it up early. Fall back to email only. |
| Output varies from run to run | Medium | Medium | Structured output, repeated runs, and a reported stability figure |
| Another team builds something similar | Unknown | Medium | Lead with the measurement and the retire lane |
| Schedule expires after 14 days | Low | Low for the hackathon | Refresh before the demo |
| Time runs out | High | High | Follow the gates and cut Should-have items first |
| Rules turn out different (for example synthetic data not allowed, or new final-pitch requirements) | Medium | High | Ask the organizers on Discord |
| Licenses arrive too late to move into Gemini Enterprise before the 17 November pitch | Medium | High | Keep subagent prompts and structured outputs ready to paste into Agent Designer, and rehearse the move on the first day of access |
| A prototype built outside Gemini Enterprise scores lower on the technical build criterion | Medium | Medium | Show the Gemini-ready prompts and outputs, say plainly what runs where, and ask the organizers whether the criterion changes |

### Open questions to confirm with the organizers

- [ ] Gemini Enterprise: answered on 9 November (not needed for the prototype, required for the final). Does a prototype built outside it score lower on the connectors criterion?
- [ ] Is Antigravity required or optional?
- [ ] Is a video required, and how long?
- [ ] Is synthetic data acceptable for the demo?
- [ ] Are licenses per person or per team, and who allocates them?
- [ ] Is there an in-person pitch on 17 November, and in what format?
- [ ] Will the rubric weights be published?
- [ ] Is a Jira sandbox available?
- [ ] Can reviewers outside our domain be invited to the app?
- [ ] Is the new deadline 12:00 PM Malaysian time?
- [ ] What are the new dates for the assessment window and the top-five announcement?

### Rollout idea for APU (hypothesis)

The speaker asked how long impact would take, for example 3 or 6 months. This is a plan, not a result.

- **Month 1:** import the inventory of one lab and run in suggest-only mode.
- **Months 2 to 3:** pilot with real approvers and compare time to notify with current practice.
- **Month 6:** extend to more labs, tune the settings, and review every miss.

It needs an APU data owner, approval to use the device list, and a privacy check.

## Honest limits

This section separates what we know from what we believe and what we do not know, so nobody mistakes a plan for a result.

| Category | What it covers |
| --- | --- |
| Verified, with the caveats given in each section | The event dates, submission fields and prizes on the official page. What the briefing speakers said, as the transcript records it. The problem statistics as named sources report them (several through secondary coverage). The Gemini Enterprise features listed in Google's documentation excerpts. |
| Hypotheses, plausible but untested | An agent like this shortens time to fix. APU has unpatched or end-of-life devices worth tracking. An LLM matches messy names better than naive matching. Reviewers will value the closed loop and the retire lane. A no-code agent can do everything described. Inbox approvals and Jira actions work as documented. |
| Unknown | The rubric weights. What other teams are building. Whether licenses arrive in time. Whether Gemini Enterprise is truly mandatory. Whether synthetic data is accepted. The format of the 17 November pitch. |

### What this document does not claim

- That Deming is unique, or that it will win.
- That any real user has validated the problem.
- That vendor figures are correct. They are self-reported, and we did not test the products.
- That the test results will reflect real-world performance. The inventory is synthetic.
- That the Verifier proves a device is secure. It confirms the inventory record changed, not that the device itself was fixed.
- That the prototype runs inside Gemini Enterprise. Until licenses arrive, it runs the same steps on the Sheet.

### What would make us change course

- **No license by Wednesday evening.** The prototype does not depend on it, so we keep building on the Sheet and tell the coordinators the final pitch is at risk.
- **Gate 1 fails.** If the agent cannot reliably read a Sheet, reason about it and draft an email, we switch to a fallback idea. The fallbacks share the same platform dependencies, so we would check them first.
- **The organizers' answers change the rules.** For example, synthetic data is not allowed, or the final-pitch requirements change.
- **A real stakeholder offers a better-evidenced problem.** We would listen.
- **Normalization does not beat the baseline.** We would reframe around the workflow and the retire lane, or switch.

## Appendix: sources and glossary

Sources are current as of 8 November 2026. Most were read as search excerpts, not opened in full, and the table says which were opened.

### Sources

| Source | Used for | How we read it |
| --- | --- | --- |
| [Official event page](https://apu-cloud-innovation-hackathon.gdgocapu.com/) | Dates, tracks, prizes, submission fields | Opened |
| [VulnCheck 2026 network edge report](https://www.vulncheck.com/blog/network-edge-device-report-2026) | End-of-life and KEV coverage figures | Opened |
| [APU campus facilities](https://www.apu.edu.my/campus-facilities) | APU labs and IoT programme | Opened, first 100,000 of about 175,000 characters |
| [APU-Nexus repository](https://github.com/Rodrick-Sara7/APU-Nexus-Autonomous-Campus-Digital-Twin) | A public rival entry | Opened |
| Briefing transcript, 3 November 2026 | Requirements and judging topics | Provided by the team, read in full. Auto-generated, so some words are garbled. |
| Earlier project files: research-report.md, research-report.html, hackathon-context-for-another-model.md, verified-real-world-problems.md, special-shortlist.md, opportunity-scores.csv | Earlier research and the parked ideas | Provided by the team. Scores and rankings in them are subjective. |
| [watchTowr DBIR 2026 summary](https://watchtowr.com/resources/verizon-dbir-2026-vulnerability-exploitation/) | Time-to-fix figures | Search excerpt of secondary coverage |
| [Socket KEV glossary](https://socket.dev/glossary/cisa-kev), [fastCRW KEV sample](https://fastcrw.com/playground/pergamon/cisakev) | KEV size and fields | Search excerpts of third-party mirrors |
| [BleepingComputer](https://bleepingcomputer.com/news/security/cisa-orders-federal-agencies-to-replace-end-of-life-edge-devices), [Washington Technology](https://www.washingtontechnology.com/contracts/2026/02/cisa-orders-agencies-patch-and-replace-end-life-devices-citing-active-exploitation/411261/) | CISA directive BOD 26-02 | Search excerpts |
| [endoflife.ai D-Link analysis](https://endoflife.ai/article-dlink-eol-routers-kev) | End-of-life routers in KEV | Search excerpt |
| [Google schedule docs](https://docs.cloud.google.com/gemini/enterprise/docs/agent-designer/schedule-agent), [Agent Designer overview](https://docs.cloud.google.com/gemini/enterprise/docs/agent-designer?hl=pl), [third-party data sources](https://docs.cloud.google.com/gemini/enterprise/docs/connect-third-party-data-source?authuser=110) | Platform capabilities and limits | Search excerpts of Google documentation |
| Vendor sources for the big-tech comparison | Features adopted | Linked in the big-tech table. All read as search excerpts. |
| [Lean Enterprise Institute: PDCA resource guide](https://www.lean.org/lexicon-terms/pdca/) | The Deming Cycle: steps, Shewhart origin, Deming in Japan, the 1951 PDCA wording | Opened |
| [BusinessBalls: Plan-Do-Check-Act](https://www.businessballs.com/business-development/plan-do-check-act/) | Shewhart's 1920s cycle, and Deming's later view of the Check wording | Opened. A single account of Deming's view. |
| Organizers' announcement of the deadline extension, 9 November 2026 | New deadline, licensing delay, prototype and final-pitch requirements | Provided by the team, read in full |
| [Eolix on G2](https://www.g2.com/products/eolix/discuss) | Competitor: end-of-life checks on inventory exports | Search excerpt |
| [HeroDevs acquires Xeol (Dealroom news)](https://malta.dealroom.co/news/feed/herodevs-acquires-xeol-for-nes-solutions) | Competitor: end-of-life detection | Search excerpt |

### Glossary

| Term | Meaning |
| --- | --- |
| KEV | CISA's Known Exploited Vulnerabilities catalog: weaknesses with evidence of real-world exploitation |
| CVE | A public identifier for one vulnerability |
| End of life, end of support | The maker no longer issues security fixes for the product |
| Edge device | A device at the network boundary, such as a router, firewall or gateway |
| Firmware | The software built into a device |
| Lane | The category Deming assigns: patch, retire, fine or unknown |
| Gemini Enterprise | Google's platform for building and running AI agents at work |
| Agent Designer | Gemini Enterprise's no-code and low-code agent builder |
| Subagent | A narrow agent called by a main agent |
| First-party and third-party connector | A link to a Google service, or to a non-Google service |
| MCP | Model Context Protocol, a standard way to connect agents to tools |
| Antigravity | Google's AI-assisted development tool, used for code and helper scripts |
| Inbox | The Gemini Enterprise panel where agent activity and approvals appear |
| Closed loop | A process that checks its own result and acts again if the fix did not happen |
| Human in the loop | A person approves consequential steps before they happen |
| BOD 26-02 | A February 2026 CISA directive on end-of-support edge devices, binding on US federal civilian agencies only |
| Deming Cycle (PDCA) | Plan, Do, Check, Act: a four-step improvement loop named after W. Edwards Deming, which this project's agent runs on every device |
