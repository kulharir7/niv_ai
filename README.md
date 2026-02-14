<div align="center">

<img src="docs/logo.svg" width="120" alt="Niv AI Logo"/>

# Niv AI (v0.6.1-alpha)

### The First Cognitive OS for ERPNext

*Next-generation multi-agent AI system with A2A protocol, built natively for Frappe/ERPNext.*

[![Version](https://img.shields.io/badge/version-0.6.1--alpha-purple?style=for-the-badge)](CHANGELOG.md)
[![A2A](https://img.shields.io/badge/A2A-Protocol-FFD700?style=for-the-badge)](https://a2a-protocol.org)
[![MCP](https://img.shields.io/badge/MCP-Standard-FF6B6B?style=for-the-badge)](https://modelcontextprotocol.io)
[![Frappe](https://img.shields.io/badge/Frappe-v14%20|%20v15-0089FF?style=for-the-badge)](https://frappeframework.com)

<br/>

**Orchestrated Intelligence** · **Visual Data Analytics** · **Zero-Configuration Onboarding** · **Pure Frappe**

<br/>

[🚀 Getting Started](#-getting-started) · [🤖 Multi-Agent System](#-the-multi-agent-factory) · [📊 Artifacts & Charts](#-artifacts--visual-analytics) · [🏗️ Architecture](#-technical-architecture)

---

</div>

## 🌟 Why Niv AI v0.6.x?

Traditional AI chatbots for ERPNext often hallucinate or fail at complex tasks because one single prompt has too many tools and too much context. **Niv AI v0.6.1** introduces a decentralized "Virtual Office" approach.

- **No more Mock Data**: Strictly enforced real-data fetching via specialized agents.
- **Zero Hallucination**: Agents only see tools relevant to their specific role.
- **Visual Intelligence**: Beautiful interactive charts using `frappe-charts` integrated into a side-panel.
- **Self-Learning**: A background discovery engine that maps your system logic automatically.

---

## 🔥 Key Features

### 1. 🤖 The Multi-Agent Factory (A2A Protocol)
Built on `google-adk`, Niv AI delegates tasks between specialized agents:
- **Orchestrator**: The "Brain" that understands intent and routes tasks.
- **Frappe Coder**: Expert in DocTypes, Server Scripts, and UI logic.
- **Data Scientist**: Specializes in SQL queries, data aggregation, and report generation.
- **NBFC Specialist**: Pre-configured for NBFC/Lending logic (LOS, LMS, Co-Lending).

### 2. 📊 Artifacts & Visual Analytics
Visualizing ERP data has never been easier.
- **Interactive Charts**: Powered by `frappe-charts`. Just ask for a "Disbursement Trend".
- **Live Preview Panel**: A side-panel that renders HTML/JS code or charts instantly (Claude-style).
- **Auto-Panel Detection**: Panel opens automatically when visual data is detected.

### 3. 🧠 Smart Discovery Engine
- **Auto-Onboarding**: Scans your instance for Custom DocTypes, active Workflows, and NBFC context.
- **Cognitive Map**: Builds a persistent mental map of your site so you don't have to explain your process.
- **Self-Correction**: Logs tool calling mistakes and updates RAG to avoid them in future turns.

### 4. 🎤 Premium Voice Mode
- **Pipecat-inspired UI**: Sleek, glassmorphism interface with real-time waveform.
- **Continuous Conversation**: Interrupt the AI, and it listens immediately.
- **Dual Engine**: Browser STT -> Mistral Voxtral -> Piper TTS (Local) / Edge TTS.

---

## 🚀 Getting Started

### 📦 Installation

```bash
# 1. Fetch the app
bench get-app https://github.com/kulharir7/niv_ai.git

# 2. Install on your site
bench --site [your-site] install-app niv_ai

# 3. Install AI Dependencies (Critical for v0.6.x)
./env/bin/pip install google-adk[extensions] google-genai==1.3.0

# 4. Migrate & Clear Cache
bench --site [your-site] migrate
bench --site [your-site] clear-cache
bench restart
```

### 🐳 Docker Deployment
If you are running ERPNext in Docker, ensure you install the dependencies in **all** containers:
```bash
docker exec -u 0 [backend-container] pip install google-adk[extensions]
# Repeat for all workers
```
*Note: Use the included `scripts/deploy_production.sh` for a one-click server update.*

---

## 🏗️ Technical Architecture

Niv AI is a **"Cognitive OS"** layer sitting on top of Frappe:

1.  **Transport Layer**: SSE (Server-Sent Events) for real-time token streaming.
2.  **Orchestration Layer**: `google-adk` (Agent Development Kit) managing the A2A (Agent-to-Agent) handovers.
3.  **Tooling Layer**: MCP (Model Context Protocol). 100% of Niv tools are decoupled from the core engine.
4.  **Presentation Layer**: Modern React-inspired UI with custom Markdown rendering for "Thinking" blocks.

---

## 🛠️ Configuration

1.  **AI Provider**: Setup your provider (Mistral/Ollama Cloud/OpenAI) in **Niv AI Provider**.
2.  **Default Settings**: Select your default provider in **Niv Settings**.
3.  **Enable A2A**: In Niv Settings -> Capabilities, toggle **"Enable A2A (ADK)"** for the multi-agent experience.

---

## 🗺️ Roadmap to v1.0

- [x] v0.6.1: Multi-Agent Orchestration (A2A)
- [ ] v0.7.0: Autonomous Triggers (Event-driven AI actions)
- [ ] v0.8.0: Multi-Language Prompts (Hindi/Regional)
- [ ] v1.0.0: Stable Enterprise Release

---

<div align="center">

**Built with ❤️ for the Frappe community by [Ravi Kulhari](https://github.com/kulharir7)**

[⭐ Star on GitHub](https://github.com/kulharir7/niv_ai) · [💬 Report a Bug](https://github.com/kulharir7/niv_ai/issues)

</div>
