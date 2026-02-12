const fs = require('fs');
const outPath = 'C:\\Users\\kulha\\.openclaw\\workspace\\niv_ai\\docs\\niv_ai_book_v2.html';

let html = '';
function w(s) { html += s + '\n'; }

// ============ HTML HEAD & CSS ============
w(`<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Niv AI — The Complete Documentation Book</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
@page { size: A4; margin: 2.5cm 2cm 2.5cm 2.5cm; }
@page :first { margin: 0; }
* { box-sizing: border-box; }
:root {
  --primary: #6C63FF;
  --primary-dark: #4A42E8;
  --secondary: #00D2FF;
  --accent: #FF6B6B;
  --success: #2ECC71;
  --warning: #F39C12;
  --info: #3498DB;
  --dark: #1a1a2e;
  --darker: #16213e;
  --text: #2c3e50;
  --text-light: #7f8c8d;
  --bg: #ffffff;
  --bg-alt: #f8f9fa;
  --border: #e9ecef;
  --code-bg: #1e1e2e;
  --code-text: #cdd6f4;
}
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 10.5pt;
  line-height: 1.7;
  color: var(--text);
  background: var(--bg);
  margin: 0; padding: 0;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}
h1 { font-size: 28pt; font-weight: 800; margin: 0 0 0.5em; line-height: 1.2; }
h2 { font-size: 20pt; font-weight: 700; margin: 1.5em 0 0.5em; color: var(--primary-dark); border-bottom: 3px solid var(--primary); padding-bottom: 0.3em; }
h3 { font-size: 15pt; font-weight: 600; margin: 1.2em 0 0.4em; color: var(--dark); }
h4 { font-size: 12pt; font-weight: 600; margin: 1em 0 0.3em; color: var(--text); }
h5 { font-size: 10.5pt; font-weight: 600; margin: 0.8em 0 0.3em; }
p { margin: 0.6em 0; text-align: justify; }
a { color: var(--primary); text-decoration: none; }
ul, ol { margin: 0.5em 0; padding-left: 1.5em; }
li { margin: 0.3em 0; }
table { width: 100%; border-collapse: collapse; margin: 1em 0; font-size: 9.5pt; }
th { background: var(--primary); color: white; padding: 10px 12px; text-align: left; font-weight: 600; }
td { padding: 8px 12px; border-bottom: 1px solid var(--border); }
tr:nth-child(even) { background: var(--bg-alt); }
tr:hover { background: #eef2ff; }
pre {
  background: var(--code-bg); color: var(--code-text);
  padding: 16px 20px; border-radius: 8px; overflow-x: auto;
  font-family: 'JetBrains Mono', monospace; font-size: 9pt;
  line-height: 1.6; margin: 1em 0; border-left: 4px solid var(--primary);
}
code {
  font-family: 'JetBrains Mono', monospace; font-size: 9pt;
  background: #f0f0f5; padding: 2px 6px; border-radius: 4px; color: var(--primary-dark);
}
pre code { background: none; padding: 0; color: inherit; }
.cover-page {
  page-break-after: always; height: 100vh; display: flex; flex-direction: column;
  justify-content: center; align-items: center; text-align: center;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 30%, #0f3460 60%, #533483 100%);
  color: white; padding: 3cm; position: relative; overflow: hidden;
}
.cover-page::before {
  content: ''; position: absolute; top: -50%; left: -50%; width: 200%; height: 200%;
  background: radial-gradient(circle at 30% 70%, rgba(108,99,255,0.15) 0%, transparent 50%),
              radial-gradient(circle at 70% 30%, rgba(0,210,255,0.1) 0%, transparent 50%);
}
.cover-title { font-size: 52pt; font-weight: 900; margin-bottom: 0.2em; position: relative;
  background: linear-gradient(135deg, #fff, #00D2FF); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.cover-subtitle { font-size: 18pt; font-weight: 300; opacity: 0.9; margin-bottom: 1em; position: relative; }
.cover-edition { font-size: 13pt; opacity: 0.7; position: relative; margin-top: 2em; }
.cover-author { font-size: 14pt; opacity: 0.8; position: relative; margin-top: 0.5em; }
.cover-logo { font-size: 80pt; margin-bottom: 0.3em; position: relative; }
.toc { page-break-after: always; padding: 1cm 0; }
.toc h1 { text-align: center; color: var(--primary-dark); margin-bottom: 1em; }
.toc-part { font-size: 13pt; font-weight: 700; color: var(--primary); margin: 1.2em 0 0.3em; padding: 6px 0; border-bottom: 2px solid var(--primary); }
.toc-entry { display: flex; justify-content: space-between; padding: 4px 0 4px 1.5em; border-bottom: 1px dotted #ddd; font-size: 10pt; }
.toc-entry:hover { background: #f8f9ff; }
.toc-appendix { font-style: italic; }
.chapter { page-break-before: always; }
.chapter-header {
  padding: 40px 30px; margin: -2.5cm -2cm 2em -2.5cm; /* bleed */
  padding-left: 2.5cm; padding-right: 2cm;
  color: white; position: relative;
}
.ch-blue { background: linear-gradient(135deg, #2c3e50, #3498db); }
.ch-purple { background: linear-gradient(135deg, #2c3e50, #6C63FF); }
.ch-green { background: linear-gradient(135deg, #1a3a2a, #2ECC71); }
.ch-orange { background: linear-gradient(135deg, #3a2a1a, #F39C12); }
.ch-red { background: linear-gradient(135deg, #3a1a1a, #e74c3c); }
.ch-teal { background: linear-gradient(135deg, #1a2a3a, #1abc9c); }
.ch-pink { background: linear-gradient(135deg, #3a1a2a, #e91e63); }
.ch-indigo { background: linear-gradient(135deg, #1a1a3a, #5C6BC0); }
.chapter-header .ch-num { font-size: 14pt; font-weight: 300; opacity: 0.8; display: block; margin-bottom: 0.3em; }
.chapter-header h1 { color: white; font-size: 30pt; margin: 0; }
.chapter-header .ch-desc { font-size: 11pt; font-weight: 300; opacity: 0.85; margin-top: 0.5em; }
.part-divider {
  page-break-before: always; height: 100vh; display: flex; flex-direction: column;
  justify-content: center; align-items: center; text-align: center;
  background: linear-gradient(135deg, var(--dark), var(--primary-dark));
  color: white; margin: -2.5cm -2cm -2.5cm -2.5cm; padding: 3cm;
}
.part-divider h1 { font-size: 42pt; color: white; border: none; }
.part-divider p { font-size: 14pt; opacity: 0.8; max-width: 500px; }
.info-box, .warning-box, .tip-box, .prompt-box, .danger-box {
  padding: 16px 20px; border-radius: 8px; margin: 1.2em 0; border-left: 5px solid;
  page-break-inside: avoid;
}
.info-box { background: #eef6ff; border-color: var(--info); }
.info-box::before { content: 'ℹ️ INFO'; display: block; font-weight: 700; color: var(--info); margin-bottom: 6px; font-size: 9pt; }
.warning-box { background: #fff8ee; border-color: var(--warning); }
.warning-box::before { content: '⚠️ WARNING'; display: block; font-weight: 700; color: var(--warning); margin-bottom: 6px; font-size: 9pt; }
.tip-box { background: #eefff4; border-color: var(--success); }
.tip-box::before { content: '💡 TIP'; display: block; font-weight: 700; color: var(--success); margin-bottom: 6px; font-size: 9pt; }
.prompt-box { background: #f5f0ff; border-color: var(--primary); }
.prompt-box::before { content: '🤖 EXAMPLE PROMPT'; display: block; font-weight: 700; color: var(--primary); margin-bottom: 6px; font-size: 9pt; }
.danger-box { background: #fff0f0; border-color: var(--accent); }
.danger-box::before { content: '🚨 DANGER'; display: block; font-weight: 700; color: var(--accent); margin-bottom: 6px; font-size: 9pt; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5em; margin: 1em 0; }
.card { background: var(--bg-alt); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
.card h4 { margin-top: 0; color: var(--primary); }
.badge { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 8pt; font-weight: 600; }
.badge-dev { background: #6C63FF; color: white; }
.badge-new { background: #2ECC71; color: white; }
.badge-beta { background: #F39C12; color: white; }
.arch-diagram { background: var(--bg-alt); border: 2px solid var(--border); border-radius: 12px; padding: 20px; margin: 1.5em 0; text-align: center; font-family: 'JetBrains Mono', monospace; font-size: 9pt; white-space: pre; line-height: 1.4; }
.figure { text-align: center; margin: 1.5em 0; }
.figure-caption { font-size: 9pt; color: var(--text-light); font-style: italic; margin-top: 0.5em; }
.page-break { page-break-after: always; }
.api-endpoint { background: var(--code-bg); color: var(--code-text); padding: 12px 16px; border-radius: 6px; margin: 0.8em 0; font-family: 'JetBrains Mono', monospace; font-size: 9.5pt; }
.api-method { font-weight: 700; padding: 2px 8px; border-radius: 4px; margin-right: 8px; }
.api-get { background: #2ECC71; color: white; }
.api-post { background: #3498DB; color: white; }
.api-put { background: #F39C12; color: white; }
.api-delete { background: #e74c3c; color: white; }
.param-table td:first-child { font-family: 'JetBrains Mono', monospace; font-size: 9pt; color: var(--primary-dark); font-weight: 500; white-space: nowrap; }
hr { border: none; border-top: 1px solid var(--border); margin: 2em 0; }
blockquote { border-left: 4px solid var(--primary); margin: 1em 0; padding: 0.5em 1em; background: var(--bg-alt); border-radius: 0 8px 8px 0; }
.footnote { font-size: 8.5pt; color: var(--text-light); }
@media print {
  .cover-page { margin: -2.5cm -2cm; padding: 0; width: calc(100% + 4.5cm); }
  .chapter-header { margin-left: -2.5cm; margin-right: -2cm; margin-top: -2.5cm; }
  body { font-size: 10pt; }
  pre { font-size: 8.5pt; }
  .no-print { display: none; }
}
</style>
</head>
<body>
`);

// ============ COVER PAGE ============
w(`
<div class="cover-page">
  <div class="cover-logo">🤖</div>
  <div class="cover-title">Niv AI</div>
  <div class="cover-subtitle">The Complete Documentation Book</div>
  <p style="font-size:12pt; opacity:0.7; max-width:500px; position:relative; line-height:1.6;">
    A comprehensive guide to building, deploying, and mastering<br>
    the AI-powered assistant for ERPNext &amp; Frappe Framework
  </p>
  <div class="cover-edition">Second Edition — Version 0.5.1 — February 2026</div>
  <div class="cover-author">By the Niv AI Team</div>
  <p style="font-size:9pt; opacity:0.5; position:relative; margin-top:3em;">
    Covers: Chat Interface • 29 MCP Tools • Voice Mode • Developer Mode (94 Features)<br>
    Telegram &amp; WhatsApp Bots • NBFC/Lending • Auto-Pilot Triggers • Production Deployment
  </p>
</div>
`);

// ============ COPYRIGHT PAGE ============
w(`
<div style="page-break-after:always; padding-top:60vh;">
  <h3 style="border:none;">Niv AI — The Complete Documentation Book</h3>
  <p>Second Edition, February 2026</p>
  <p>Copyright © 2024–2026 Niv AI Team. All rights reserved.</p>
  <p style="margin-top:2em;">No part of this publication may be reproduced, distributed, or transmitted in any form or by any means without prior written permission.</p>
  <p style="margin-top:2em;"><strong>Software Version:</strong> Niv AI v0.5.1 (frappe_assistant_core + niv_tools)</p>
  <p><strong>Frappe Framework:</strong> v14 / v15</p>
  <p><strong>ERPNext:</strong> v14 / v15</p>
  <p style="margin-top:2em; font-size:9pt; color:var(--text-light);">
    ERPNext and Frappe are registered trademarks of Frappe Technologies Pvt. Ltd.<br>
    Telegram is a trademark of Telegram FZ-LLC.<br>
    WhatsApp is a trademark of Meta Platforms, Inc.<br>
    All other trademarks are property of their respective owners.
  </p>
</div>
`);

// ============ TABLE OF CONTENTS ============
w(`<div class="toc">`);
w(`<h1>Table of Contents</h1>`);

const tocData = [
  { part: 'Part 1: Getting Started', chapters: [
    ['Chapter 1: Introduction to Niv AI', '1'], ['Chapter 2: Installation & Setup', '35'], ['Chapter 3: Quick Start Guide', '80']
  ]},
  { part: 'Part 2: User Guide', chapters: [
    ['Chapter 4: Chat Interface Deep Dive', '105'], ['Chapter 5: Working with Tools', '160'], ['Chapter 6: Voice Mode Complete Guide', '225'], ['Chapter 7: Conversation Prompts & Best Practices', '258']
  ]},
  { part: 'Part 3: Developer Guide', chapters: [
    ['Chapter 8: Developer Mode Complete Reference', '302'], ['Chapter 9: Auto-Pilot Triggers Deep Dive', '388'], ['Chapter 10: Building Custom Tools', '432']
  ]},
  { part: 'Part 4: Channels', chapters: [
    ['Chapter 11: Telegram Bot Complete Guide', '465'], ['Chapter 12: WhatsApp Bot Complete Guide', '510'], ['Chapter 13: Multi-Channel Architecture', '555']
  ]},
  { part: 'Part 5: NBFC / Lending Complete Guide', chapters: [
    ['Chapter 14: NBFC Overview & Setup', '578'], ['Chapter 15: NBFC Operations via Chat', '622'], ['Chapter 16: NBFC Compliance & Reporting', '688']
  ]},
  { part: 'Part 6: Administration', chapters: [
    ['Chapter 17: Billing & Token Management', '732'], ['Chapter 18: Security & Permissions', '765'], ['Chapter 19: Monitoring & Maintenance', '798']
  ]},
  { part: 'Part 7: Deployment', chapters: [
    ['Chapter 20: Production Deployment', '832']
  ]},
  { part: 'Part 8: Reference', chapters: [
    ['Chapter 21: Complete API Reference', '886'], ['Chapter 22: Configuration Reference', '950'],
    ['Appendix A: Prompt Library', '984'], ['Appendix B: Troubleshooting Encyclopedia', '1028'], ['Appendix C: Roadmap & Changelog', '1062']
  ]}
];

tocData.forEach(p => {
  w(`<div class="toc-part">${p.part}</div>`);
  p.chapters.forEach(([name, page]) => {
    const cls = name.startsWith('Appendix') ? ' toc-appendix' : '';
    w(`<div class="toc-entry${cls}"><span>${name}</span><span>${page}</span></div>`);
  });
});
w(`</div>`);

// ============ HELPER FUNCTIONS ============
const chColors = ['ch-blue','ch-purple','ch-green','ch-orange','ch-red','ch-teal','ch-pink','ch-indigo'];
let chIdx = 0;

function partDivider(num, title, desc) {
  w(`<div class="part-divider"><p style="font-size:16pt; opacity:0.6;">Part ${num}</p><h1>${title}</h1><p>${desc}</p></div>`);
}

function chapterHeader(num, title, desc) {
  const color = chColors[chIdx % chColors.length]; chIdx++;
  w(`<div class="chapter"><div class="chapter-header ${color}"><span class="ch-num">Chapter ${num}</span><h1>${title}</h1><p class="ch-desc">${desc}</p></div>`);
}

function endChapter() { w(`</div>`); }

function infoBox(text) { w(`<div class="info-box">${text}</div>`); }
function warnBox(text) { w(`<div class="warning-box">${text}</div>`); }
function tipBox(text) { w(`<div class="tip-box">${text}</div>`); }
function promptBox(text) { w(`<div class="prompt-box">${text}</div>`); }
function dangerBox(text) { w(`<div class="danger-box">${text}</div>`); }

function codeBlock(lang, code) {
  w(`<pre><code>// ${lang}\n${code}</code></pre>`);
}

function table(headers, rows) {
  w(`<table><thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>`);
  rows.forEach(r => { w(`<tr>${r.map(c=>`<td>${c}</td>`).join('')}</tr>`); });
  w(`</tbody></table>`);
}

function apiEndpoint(method, url) {
  const cls = method === 'GET' ? 'api-get' : method === 'POST' ? 'api-post' : method === 'PUT' ? 'api-put' : 'api-delete';
  w(`<div class="api-endpoint"><span class="api-method ${cls}">${method}</span> ${url}</div>`);
}

// ================================
// PART 1: GETTING STARTED
// ================================
partDivider('1', 'Getting Started', 'Introduction, Installation, and your first conversations with Niv AI');

// ============ CHAPTER 1 ============
chapterHeader('1', 'Introduction to Niv AI', 'Understanding the AI-powered assistant that transforms how you interact with ERPNext');

w(`
<h2>1.1 What is Niv AI?</h2>

<p>Niv AI is a comprehensive artificial intelligence assistant designed specifically for the ERPNext and Frappe Framework ecosystem. Unlike general-purpose AI chatbots that provide generic responses, Niv AI is deeply integrated with your ERPNext instance, capable of reading, creating, updating, and managing your business data through natural language conversations.</p>

<p>At its core, Niv AI bridges the gap between the powerful but complex ERPNext ERP system and the intuitive simplicity of conversational AI. Instead of navigating through dozens of menus, filling out forms, and running reports manually, users can simply ask Niv AI to perform these tasks in plain English (or Hindi, or any supported language).</p>

<h3>1.1.1 The Problem Niv AI Solves</h3>

<p>ERPNext is one of the most comprehensive open-source ERP systems available, covering modules from Accounting and Sales to Manufacturing and Human Resources. However, this comprehensiveness comes with complexity:</p>

<ul>
  <li><strong>Steep Learning Curve:</strong> New users often take weeks or months to become proficient with ERPNext. The system has over 700 DocTypes (document types), thousands of fields, and complex workflows. A new accountant joining a company might struggle to find where to create a Journal Entry, how to reconcile payments, or how to generate a specific report.</li>
  <li><strong>Navigation Overhead:</strong> Even experienced users spend significant time navigating between modules. To check a customer's outstanding balance, you might need to navigate to Accounts → Accounts Receivable → set filters → run report. With Niv AI, you simply ask: "What is the outstanding balance for Customer ABC?"</li>
  <li><strong>Report Complexity:</strong> ERPNext has powerful reporting capabilities, but creating custom reports requires knowledge of Report Builder, Script Reports, or even direct SQL queries. Niv AI can generate reports on the fly from natural language descriptions.</li>
  <li><strong>Training Costs:</strong> Organizations spend thousands of dollars training employees on ERPNext. Niv AI acts as an always-available assistant that guides users through processes and performs tasks on their behalf.</li>
  <li><strong>Mobile Limitations:</strong> While ERPNext has a mobile interface, complex operations are cumbersome on small screens. Niv AI's chat interface works beautifully on mobile, and its Telegram/WhatsApp integration means users can manage their ERP from any messaging app.</li>
  <li><strong>After-Hours Access:</strong> When a sales manager needs to check inventory levels at 10 PM while meeting a client, pulling out a laptop and logging into ERPNext is impractical. A quick Telegram message to Niv AI gets the answer in seconds.</li>
</ul>

<h3>1.1.2 How Niv AI is Different from General AI Assistants</h3>

<p>You might wonder: "Why not just use ChatGPT or GitHub Copilot?" The answer lies in deep ERP integration. Here's a detailed comparison:</p>
`);

table(['Feature', 'ChatGPT / Copilot', 'Niv AI'],
[
  ['ERP Data Access', 'No direct access to your ERPNext data', 'Full read/write access to all DocTypes, fields, and reports'],
  ['Document Creation', 'Can only suggest how to create documents', 'Actually creates Sales Orders, Invoices, Journal Entries, etc.'],
  ['Real-time Reports', 'Cannot query your database', 'Runs live SQL queries and generates reports from your data'],
  ['Workflow Execution', 'No workflow integration', 'Submits, cancels, amends documents; triggers workflows'],
  ['User Permissions', 'No concept of ERPNext roles', 'Respects Frappe permission model; user sees only their allowed data'],
  ['Custom Fields', 'No awareness of customizations', 'Discovers and works with your Custom Fields and Custom DocTypes'],
  ['Voice Mode', 'Limited voice in ChatGPT', 'Full STT (Voxtral) + TTS (Piper) optimized for ERP conversations'],
  ['Telegram/WhatsApp', 'Not available', 'Native bot integration with progressive updates and table formatting'],
  ['Auto-Pilot Triggers', 'Not available', 'Event-driven AI that validates documents, audits data, and alerts on anomalies'],
  ['Developer Mode', 'Can suggest code snippets', 'Actually creates Custom Fields, Server Scripts, Workflows, DocTypes in your instance'],
  ['Cost Control', 'Per-user subscription ($20+/mo)', 'Token-based billing with shared pool or per-user wallets; use any AI provider'],
  ['Self-Hosted', 'Cloud only (data leaves your server)', 'Fully self-hosted; your data never leaves your infrastructure'],
  ['NBFC/Lending', 'No domain knowledge', 'Specialized tools and prompts for loan origination, management, collections, and compliance'],
]);

w(`
<h3>1.1.3 The Vision Behind Niv AI</h3>

<p>Niv AI was born from a simple observation: the most powerful ERP system in the world is useless if people can't use it efficiently. The vision is to make every ERPNext user — from the CEO checking quarterly revenue to the warehouse staff updating stock entries — equally productive, regardless of their technical skill level.</p>

<p>The name "Niv" (निव) comes from Hindi, meaning "foundation" — reflecting the tool's role as the foundational layer between humans and their ERP system. Just as a strong foundation supports an entire building, Niv AI supports an organization's entire interaction with their business data.</p>

<h2>1.2 Complete Feature List</h2>

<p>Niv AI is packed with features across multiple categories. This section provides an exhaustive list with descriptions of every capability.</p>

<h3>1.2.1 Conversational AI Engine</h3>

<table>
<thead><tr><th>Feature</th><th>Description</th><th>Status</th></tr></thead>
<tbody>
<tr><td>Natural Language Understanding</td><td>Processes user queries in plain English, Hindi, and other languages. Understands context, intent, and entities specific to ERPNext terminology (DocTypes, fields, workflows).</td><td><span class="badge badge-new">Stable</span></td></tr>
<tr><td>Multi-Turn Conversations</td><td>Maintains context across multiple messages. If you ask "Show me Sales Orders for this month" and then "Now filter by Customer ABC", Niv AI understands "this" refers to the previous query.</td><td><span class="badge badge-new">Stable</span></td></tr>
<tr><td>LangGraph Agent Framework</td><td>Uses LangGraph (from LangChain) for structured agent execution. Supports tool calling, state management, and complex multi-step reasoning.</td><td><span class="badge badge-new">Stable</span></td></tr>
<tr><td>Streaming Responses</td><td>Responses stream in real-time via Server-Sent Events (SSE). Users see the response being generated word by word, similar to ChatGPT.</td><td><span class="badge badge-new">Stable</span></td></tr>
<tr><td>Multiple AI Providers</td><td>Supports Mistral AI (recommended), OpenAI (GPT-4), Groq (Llama), Together AI, and Ollama (local models). Switch providers without changing any code.</td><td><span class="badge badge-new">Stable</span></td></tr>
<tr><td>System Prompts</td><td>Customizable system prompts that define Niv AI's personality, knowledge base, and behavior. Create different prompts for different roles (accountant, sales manager, HR).</td><td><span class="badge badge-new">Stable</span></td></tr>
<tr><td>Token Usage Tracking</td><td>Every conversation tracks input tokens, output tokens, and total cost. Administrators can monitor usage per user and set budgets.</td><td><span class="badge badge-new">Stable</span></td></tr>
</tbody></table>

<h3>1.2.2 MCP Tool System (29 Tools)</h3>

<p>The Model Context Protocol (MCP) tool system is the backbone of Niv AI's ability to interact with ERPNext. Each tool is a carefully designed function that the AI can call to perform specific operations.</p>
`);

table(['Tool Name', 'Category', 'Description'],
[
  ['create_document', 'CRUD', 'Creates any document in ERPNext — Sales Order, Purchase Invoice, Journal Entry, Employee, etc. Handles child tables, validations, and naming series.'],
  ['get_document', 'CRUD', 'Retrieves a specific document by DocType and name. Returns all fields including child table data.'],
  ['update_document', 'CRUD', 'Updates fields on an existing document. Supports partial updates — only modified fields need to be specified.'],
  ['delete_document', 'CRUD', 'Permanently deletes a document. Respects Frappe permissions and linked document constraints.'],
  ['submit_document', 'Workflow', 'Submits a submittable document (e.g., Sales Invoice, Journal Entry). Changes docstatus from 0 (Draft) to 1 (Submitted).'],
  ['list_documents', 'Query', 'Lists documents with filters, sorting, pagination, and field selection. Supports complex filter operators: =, !=, >, <, >=, <=, like, not like, in, not in, between.'],
  ['search_documents', 'Query', 'Full-text search across documents. More flexible than list_documents for free-form queries.'],
  ['search_doctype', 'Discovery', 'Searches for DocType names matching a pattern. Helps the AI discover the correct DocType when the user uses informal names.'],
  ['search_link', 'Discovery', 'Searches link field values. Used when the AI needs to find valid values for a Link field (e.g., finding a Customer name).'],
  ['search', 'Discovery', 'General search across the ERPNext instance. Similar to the Awesome Bar search.'],
  ['fetch', 'Query', 'Fetches specific field values from a document. Lighter than get_document when only a few fields are needed.'],
  ['get_doctype_info', 'Discovery', 'Returns the complete schema of a DocType: all fields, their types, options, and properties. Essential for the AI to understand document structure.'],
  ['generate_report', 'Reporting', 'Generates reports using ERPNext\'s built-in Report Builder. Supports standard reports like General Ledger, Accounts Receivable, Stock Balance, etc.'],
  ['report_list', 'Reporting', 'Lists all available reports in the system, filterable by module.'],
  ['report_requirements', 'Reporting', 'Returns the required filters and columns for a specific report. Helps the AI provide correct parameters.'],
  ['run_database_query', 'Advanced', 'Executes raw SQL SELECT queries against the database. Extremely powerful for complex analytical queries.'],
  ['run_python_code', 'Advanced', 'Executes Python code in the Frappe context. Access to frappe.db, frappe.get_doc, and all Frappe APIs.'],
  ['analyze_business_data', 'Analytics', 'Performs structured business data analysis with charts and summaries.'],
  ['extract_file_content', 'Utility', 'Extracts text content from uploaded files (PDF, XLSX, CSV, images with OCR).'],
  ['run_workflow', 'Workflow', 'Triggers a workflow action on a document (Approve, Reject, etc.).'],
  ['create_dashboard', 'Visualization', 'Creates a new Dashboard with specified charts and layout.'],
  ['create_dashboard_chart', 'Visualization', 'Creates individual dashboard charts (line, bar, pie, etc.) from report data.'],
  ['list_user_dashboards', 'Visualization', 'Lists all dashboards accessible to the current user.'],
  ['universal_search', 'Discovery', 'Searches across multiple DocTypes simultaneously. Supports wildcards and fuzzy matching.'],
  ['explore_fields', 'Discovery', 'Explores and describes fields of a DocType in human-readable format. Better than raw get_doctype_info for understanding.'],
  ['test_created_item', 'Validation', 'Tests a recently created document by verifying it exists and checking its field values.'],
  ['monitor_errors', 'Admin', 'Monitors the Error Log for recent errors. Useful for debugging failed operations.'],
  ['rollback_changes', 'Undo', 'Rolls back recent changes made by Niv AI. Uses the Redis-backed undo system with 30-minute expiry.'],
  ['introspect_system', 'Admin', 'Returns system information: installed apps, Frappe version, active users, and system health metrics.'],
]);

w(`
<h3>1.2.3 Communication Channels</h3>

<div class="two-col">
  <div class="card">
    <h4>🌐 Web Chat Interface</h4>
    <p>Full-featured chat interface at <code>/app/niv-chat</code> with dark theme, conversation management, tool call visualization, code highlighting, and voice mode. Supports both full-page and floating widget modes.</p>
  </div>
  <div class="card">
    <h4>📱 Telegram Bot</h4>
    <p>Complete Telegram bot integration with webhook support, progressive message updates (streaming effect), table formatting, user mapping, and all 29 MCP tools available.</p>
  </div>
  <div class="card">
    <h4>💬 WhatsApp Bot</h4>
    <p>WhatsApp Business API integration with webhook verification, QR code onboarding, message formatting optimized for WhatsApp (no tables), and mark-as-read (blue ticks).</p>
  </div>
  <div class="card">
    <h4>🎙️ Voice Mode</h4>
    <p>Hands-free operation with Mistral Voxtral STT, Piper TTS (English + Hindi voices), browser Speech Recognition fallback, and continuous conversation mode.</p>
  </div>
</div>

<h3>1.2.4 Developer Mode (94 Features)</h3>

<p>Developer Mode transforms Niv AI from a read/query assistant into a full-featured ERPNext development tool. With Developer Mode enabled, Niv AI can create and modify the very structure of your ERPNext instance:</p>

<ul>
  <li><strong>Phase A — Custom Fields (12 features):</strong> Add any field type (Data, Int, Currency, Link, Table, Select, Date, DateTime, Check, Text Editor, Attach, etc.) to any existing DocType. Set properties like required, default value, depends_on visibility, and read_only.</li>
  <li><strong>Phase B — Server Scripts (10 features):</strong> Create Before Save, After Save, Before Submit, After Submit, Before Cancel, After Cancel event scripts. Also create API endpoints and Permission Query scripts.</li>
  <li><strong>Phase C — Client Scripts (8 features):</strong> Create scripts that run in the browser — form refresh handlers, field change handlers, validation scripts, and list view customizations.</li>
  <li><strong>Phase D — Property Setters (6 features):</strong> Modify existing field properties without altering the source code — change labels, set default values, hide fields, make fields mandatory.</li>
  <li><strong>Phase E — Custom DocTypes (14 features):</strong> Create entirely new DocTypes from scratch, complete with fields, permissions, naming rules, child tables, and workflow integration.</li>
  <li><strong>Phase F — Workflows (8 features):</strong> Design multi-state workflows with role-based transitions, condition-based routing, and automatic actions.</li>
  <li><strong>Phase G — Notifications (6 features):</strong> Create email notifications, system notifications, and SMS alerts triggered by document events.</li>
  <li><strong>Phase H — Print Formats (6 features):</strong> Design custom print formats using Jinja templates for invoices, reports, and other printable documents.</li>
  <li><strong>Phase I — Script Reports (8 features):</strong> Create custom reports with Python data functions, dynamic columns, filters, and chart integration.</li>
  <li><strong>Phase J — Web Pages (6 features):</strong> Create portal pages, web forms, and custom web views.</li>
  <li><strong>Phase K — Integrations (5 features):</strong> Set up webhook receivers, outgoing webhooks, and third-party API integrations.</li>
  <li><strong>Phase L — Debugging (5 features):</strong> Monitor Error Logs, trace script execution, inspect database queries, and profile performance.</li>
</ul>

<h3>1.2.5 Auto-Pilot Triggers</h3>

<p>Auto-Pilot Triggers enable event-driven AI processing. Instead of waiting for a user to ask a question, Niv AI can automatically respond to document events:</p>

<ul>
  <li><strong>Document Event Triggers:</strong> Fire on Before Save, After Save, Before Submit, After Submit, Before Cancel, After Cancel, On Change, or on a daily/weekly/monthly schedule.</li>
  <li><strong>Condition Expressions:</strong> Python expressions that determine whether the trigger should fire (e.g., <code>doc.grand_total > 100000</code>).</li>
  <li><strong>Prompt Templates:</strong> Customizable prompts with template variables (<code>{{doc.name}}</code>, <code>{{doc.customer}}</code>) that are rendered with the document's data.</li>
  <li><strong>Linked System Prompts:</strong> Each trigger can use a specialized system prompt that gives the AI domain-specific knowledge.</li>
  <li><strong>Multi-Step Processing:</strong> Triggers can invoke tools, create other documents, send notifications, and perform complex validation logic.</li>
</ul>

<h3>1.2.6 Billing & Token Management</h3>

<ul>
  <li><strong>Shared Pool Mode:</strong> Organization-wide token pool. All users share a common balance. Best for small teams.</li>
  <li><strong>Per User Mode:</strong> Individual wallets per user. Each user manages their own token balance. Best for larger organizations or SaaS deployments.</li>
  <li><strong>Razorpay Integration:</strong> Built-in payment gateway for purchasing tokens. Users can buy credit packs directly from the interface.</li>
  <li><strong>Usage Analytics:</strong> Detailed tracking of token usage per user, per conversation, and per tool call. Budget alerts when usage exceeds thresholds.</li>
</ul>

<h2>1.3 Architecture Overview</h2>

<p>Understanding Niv AI's architecture is essential for developers, system administrators, and anyone who wants to troubleshoot issues or extend the system. This section provides a comprehensive overview of every component and how they interact.</p>

<h3>1.3.1 High-Level Architecture Diagram</h3>

<div class="arch-diagram">
┌─────────────────────────────────────────────────────────────────────────┐
│                           CLIENT LAYER                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │  Web Chat UI  │  │ Telegram Bot │  │ WhatsApp Bot │  │  Voice UI  │ │
│  │  /app/niv-chat│  │  @BotFather  │  │  Meta API    │  │ STT + TTS  │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └─────┬──────┘ │
│         │                  │                  │                │        │
└─────────┼──────────────────┼──────────────────┼────────────────┼────────┘
          │                  │                  │                │
          ▼                  ▼                  ▼                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         API GATEWAY LAYER                               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    Frappe Web Server (Gunicorn)                   │   │
│  │  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────────┐  │   │
│  │  │ REST API  │ │  SSE     │ │ Webhooks  │ │  Authentication  │  │   │
│  │  │ Endpoints │ │ Streaming│ │ TG + WA   │ │  Session + Token │  │   │
│  │  └──────────┘ └──────────┘ └───────────┘ └──────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        AGENT ENGINE LAYER                               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                   LangGraph Agent Runtime                        │   │
│  │  ┌───────────┐ ┌──────────┐ ┌───────────┐ ┌─────────────────┐  │   │
│  │  │  State    │ │  Tool    │ │  Message  │ │   Model         │  │   │
│  │  │  Manager  │ │  Router  │ │  History  │ │   Interface     │  │   │
│  │  └───────────┘ └────┬─────┘ └───────────┘ └────────┬────────┘  │   │
│  └──────────────────────┼──────────────────────────────┼───────────┘   │
│                         │                              │               │
│  ┌──────────────────────▼──────┐  ┌────────────────────▼───────────┐   │
│  │     MCP Tool Server         │  │    AI Provider Adapter         │   │
│  │  ┌────────┐ ┌────────────┐  │  │  ┌─────────┐ ┌────────────┐  │   │
│  │  │ 23 Core│ │ 6 Custom   │  │  │  │ Mistral │ │ OpenAI     │  │   │
│  │  │ Tools  │ │ Tools      │  │  │  │   AI    │ │ GPT-4      │  │   │
│  │  │        │ │ (niv_tools)│  │  │  ├─────────┤ ├────────────┤  │   │
│  │  └────────┘ └────────────┘  │  │  │  Groq   │ │ Together   │  │   │
│  │  ┌────────────────────────┐ │  │  │  Llama  │ │   AI       │  │   │
│  │  │ Circuit Breaker +      │ │  │  ├─────────┤ ├────────────┤  │   │
│  │  │ Retry + Validation     │ │  │  │ Ollama  │ │ Custom     │  │   │
│  │  └────────────────────────┘ │  │  │ (Local) │ │ Provider   │  │   │
│  └─────────────────────────────┘  │  └─────────┘ └────────────┘  │   │
│                                    └──────────────────────────────┘   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        DATA & STORAGE LAYER                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │   MariaDB    │  │    Redis     │  │  File System │  │  ERPNext   │ │
│  │  (Frappe DB) │  │  (Cache +    │  │  (Attachments│  │  (Business │ │
│  │              │  │   Undo Store)│  │   + Logs)    │  │   Data)    │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
</div>
<p class="figure-caption">Figure 1.1: Niv AI Complete Architecture Diagram</p>

<h3>1.3.2 Component Breakdown</h3>

<h4>Client Layer</h4>
<p>The Client Layer encompasses all user-facing interfaces through which users interact with Niv AI:</p>

<p><strong>Web Chat UI (<code>/app/niv-chat</code>):</strong> A single-page application built with vanilla JavaScript and Frappe's page framework. The UI features a dark theme with a sidebar for conversation management and a main chat area with streaming message display. Key files:</p>
<ul>
  <li><code>niv_chat.py</code> — Frappe page controller that renders the initial HTML</li>
  <li><code>niv_chat.js</code> — Main JavaScript file (~2000 lines) handling UI rendering, SSE streaming, tool call visualization, and voice mode</li>
  <li><code>niv_chat.css</code> — Comprehensive CSS with dark theme variables, responsive breakpoints, and animation keyframes</li>
</ul>

<p><strong>Telegram Bot:</strong> A webhook-based bot that receives messages from Telegram's Bot API and sends responses. The bot supports progressive updates (editing messages as the AI streams), table formatting, and conversation persistence. Key file: <code>telegram.py</code></p>

<p><strong>WhatsApp Bot:</strong> Integrates with Meta's WhatsApp Business API. Supports webhook verification, message receiving, and response sending with WhatsApp-optimized formatting. Key file: <code>whatsapp.py</code></p>

<p><strong>Voice UI:</strong> Built into the Web Chat interface with three components: Browser Speech Recognition (fallback STT), Mistral Voxtral (primary STT), and Piper TTS (text-to-speech). The Voice UI features an animated orb and equalizer visualization.</p>

<h4>API Gateway Layer</h4>
<p>The Frappe web server (Gunicorn/Werkzeug) handles all HTTP requests. Key components include:</p>
<ul>
  <li><strong>REST API Endpoints:</strong> Whitelisted Python functions decorated with <code>@frappe.whitelist()</code> that handle chat, conversation, voice, billing, and admin operations.</li>
  <li><strong>SSE Streaming:</strong> Server-Sent Events implementation for real-time response streaming. Uses Frappe's response object to send chunked data.</li>
  <li><strong>Webhook Handlers:</strong> Dedicated endpoints for Telegram (<code>/api/method/frappe_assistant_core.api.telegram.webhook</code>) and WhatsApp (<code>/api/method/frappe_assistant_core.api.whatsapp.webhook</code>).</li>
  <li><strong>Authentication:</strong> Supports Frappe session auth (cookie-based) for web, API key + secret for programmatic access, and token-based auth for webhook verification.</li>
</ul>

<h4>Agent Engine Layer</h4>
<p>The heart of Niv AI — the LangGraph-based agent runtime:</p>
<ul>
  <li><strong>State Manager:</strong> Maintains conversation state across turns, including message history, tool call results, and context variables.</li>
  <li><strong>Tool Router:</strong> Determines which MCP tools to call based on the AI model's tool-calling decisions. Handles parameter validation, circuit breaking, and retry logic.</li>
  <li><strong>Message History:</strong> Manages the conversation's message list, including system prompts, user messages, assistant responses, and tool call/result pairs.</li>
  <li><strong>Model Interface:</strong> Abstract interface that supports multiple AI providers through a unified API. Each provider adapter translates between the provider's native API format and LangGraph's expected format.</li>
</ul>

<h4>MCP Tool Server</h4>
<p>The MCP (Model Context Protocol) tool server exposes 29 tools (23 core + 6 custom) that the AI can call:</p>
<ul>
  <li><strong>Core Tools (23):</strong> Defined in <code>frappe_assistant_core</code> — CRUD operations, search, reporting, database queries, Python execution, workflow, and dashboard tools.</li>
  <li><strong>Custom Tools (6):</strong> Defined in <code>niv_tools</code> — universal_search, explore_fields, test_created_item, monitor_errors, rollback_changes, introspect_system.</li>
  <li><strong>Reliability Layer:</strong> Circuit breaker (fails fast after repeated errors), retry logic (retries transient failures), and input validation (checks parameters before execution).</li>
</ul>

<h4>Data & Storage Layer</h4>
<ul>
  <li><strong>MariaDB:</strong> The primary database for all Frappe/ERPNext data, including Niv AI's conversations, messages, settings, and triggers.</li>
  <li><strong>Redis:</strong> Used for caching, real-time pub/sub, background job queuing, and the Developer Mode undo system (30-minute expiry).</li>
  <li><strong>File System:</strong> Stores file attachments, voice recordings, and log files.</li>
  <li><strong>ERPNext:</strong> The business data layer — all DocTypes, workflows, reports, and permissions managed by ERPNext.</li>
</ul>

<h2>1.4 Technology Stack</h2>

<p>Niv AI is built on a carefully chosen technology stack that balances power, flexibility, and ease of deployment:</p>
`);

table(['Technology', 'Role', 'Version', 'Why Chosen'],
[
  ['Python', 'Backend language', '3.10+', 'Frappe Framework is Python-based; rich AI/ML ecosystem'],
  ['Frappe Framework', 'Web framework', 'v14/v15', 'Full-featured framework with ORM, REST API, permissions, UI'],
  ['ERPNext', 'ERP platform', 'v14/v15', 'Target platform — the ERP system Niv AI integrates with'],
  ['LangGraph', 'Agent framework', '0.2+', 'Structured agent execution with state management, tool routing, and streaming'],
  ['LangChain', 'LLM toolchain', '0.3+', 'Foundational library for LLM interaction, prompt templates, and chain-of-thought'],
  ['MCP', 'Tool protocol', '1.0', 'Standardized protocol for tool discovery, calling, and result handling'],
  ['Mistral AI', 'Primary LLM', 'Large/Nemo', 'Best price-performance ratio; excellent tool calling; supports function calling natively'],
  ['Piper TTS', 'Text-to-Speech', '1.2+', 'High-quality offline TTS; supports English and Hindi; low latency'],
  ['Voxtral', 'Speech-to-Text', '-', 'Mistral\'s STT model; accurate transcription for ERP terminology'],
  ['MariaDB', 'Database', '10.6+', 'Frappe\'s default database; reliable, performant, well-supported'],
  ['Redis', 'Cache/Queue', '6.0+', 'Caching, background jobs, pub/sub, undo system storage'],
  ['JavaScript', 'Frontend', 'ES6+', 'Web Chat UI, SSE handling, Voice UI, Widget integration'],
  ['Nginx', 'Web server', '1.18+', 'Reverse proxy with SSE support, SSL termination, static file serving'],
  ['Docker', 'Containerization', '20.10+', 'Simplified deployment with frappe_docker; consistent environments'],
  ['Razorpay', 'Payments', 'v1', 'Indian payment gateway for token purchasing; supports UPI, cards, net banking'],
  ['Telegram Bot API', 'Messaging', '6.0+', 'Robust bot platform with webhook support, message editing, rich formatting'],
  ['WhatsApp Business API', 'Messaging', 'v17+', 'Official API for business messaging; supports templates, media, reactions'],
]);

w(`
<h2>1.5 Use Cases by Industry</h2>

<p>Niv AI's flexibility makes it valuable across a wide range of industries. This section explores detailed use cases for each major industry vertical.</p>

<h3>1.5.1 Manufacturing</h3>

<p>Manufacturing companies using ERPNext's Manufacturing module can leverage Niv AI for:</p>

<ul>
  <li><strong>Production Planning Queries:</strong> "What's the production plan for next week?" — Niv AI queries Work Orders, checks material availability, and summarizes the production schedule.</li>
  <li><strong>BOM Analysis:</strong> "Show me the Bill of Materials for Product XYZ including all sub-assemblies" — Niv AI traverses multi-level BOMs and presents a structured breakdown.</li>
  <li><strong>Quality Inspection:</strong> Using Auto-Pilot Triggers, Niv AI can automatically review Quality Inspection reports after submission and flag anomalies.</li>
  <li><strong>Inventory Alerts:</strong> "Which raw materials are below reorder level?" — Niv AI queries stock levels against reorder points and generates an alert list.</li>
  <li><strong>Work Order Status:</strong> Shop floor supervisors can check work order status via Telegram: "Status of WO-2026-001" — getting instant updates without leaving the production floor.</li>
  <li><strong>Scrap Analysis:</strong> "What was our scrap percentage for January?" — Niv AI runs SQL queries to calculate scrap rates by product, process, and shift.</li>
  <li><strong>Machine Downtime:</strong> With custom DocTypes created via Developer Mode, track machine downtime and query: "Which machines had the most downtime this month?"</li>
</ul>
`);

promptBox(`<strong>"Show me all Work Orders that are overdue by more than 3 days"</strong><br><br>
Niv AI will call <code>list_documents</code> with DocType "Work Order", filters for status = "In Process" and expected_delivery_date < today - 3 days, and present a formatted table with WO number, item, planned qty, and days overdue.`);

w(`
<h3>1.5.2 Retail & E-Commerce</h3>

<p>Retail businesses benefit from Niv AI's ability to quickly access sales data, inventory, and customer information:</p>

<ul>
  <li><strong>Sales Analytics:</strong> "What are our top 10 selling items this month by revenue?" — instant analytics without navigating to reports.</li>
  <li><strong>Customer Insights:</strong> "Show me Customer ABC's purchase history for the last 6 months" — complete order history with amounts, items, and delivery status.</li>
  <li><strong>Stock Availability:</strong> "Do we have Item XYZ in Warehouse A?" — real-time stock levels across warehouses.</li>
  <li><strong>Price Management:</strong> "What's the current price for Item ABC in Price List 'Retail'?" — instant pricing information.</li>
  <li><strong>Returns Processing:</strong> "Create a Sales Return for SI-2026-001" — guided creation of credit notes and return entries.</li>
  <li><strong>Daily Sales Summary:</strong> Via Telegram at end of day: "Give me today's sales summary" — total revenue, number of orders, top items, and comparison with yesterday.</li>
  <li><strong>Loyalty Programs:</strong> "How many loyalty points does Customer XYZ have?" — quick lookup without navigating to the customer record.</li>
</ul>

<h3>1.5.3 Healthcare</h3>

<p>Healthcare organizations using ERPNext Healthcare module can leverage Niv AI for:</p>

<ul>
  <li><strong>Patient Records:</strong> "Show me Patient John Doe's recent appointments" — quick access to patient history.</li>
  <li><strong>Appointment Management:</strong> "Schedule an appointment for Patient ABC with Dr. Smith on Monday at 10 AM" — creates the appointment document directly.</li>
  <li><strong>Lab Results:</strong> "What are the pending lab tests for today?" — lists all pending clinical procedures.</li>
  <li><strong>Pharmacy Stock:</strong> "Which medicines are expiring in the next 30 days?" — critical inventory alert for pharmaceutical stock.</li>
  <li><strong>Billing Queries:</strong> "What's the outstanding amount for Patient XYZ?" — patient billing summary.</li>
  <li><strong>Compliance Reporting:</strong> Auto-Pilot Triggers can validate that all required fields are filled before a Patient Encounter is submitted.</li>
</ul>

<h3>1.5.4 Education</h3>

<p>Educational institutions using ERPNext Education module:</p>

<ul>
  <li><strong>Student Information:</strong> "How many students are enrolled in Batch 2026-A?" — enrollment statistics.</li>
  <li><strong>Attendance Tracking:</strong> "Show me attendance for Class 10-A today" — daily attendance summary.</li>
  <li><strong>Fee Collection:</strong> "Which students have outstanding fees for the current term?" — fee defaulter list.</li>
  <li><strong>Exam Results:</strong> "Show me the results for the Mid-Term exam, sorted by rank" — academic performance reports.</li>
  <li><strong>Course Scheduling:</strong> "Create a Course Schedule for Mathematics on Monday 9-10 AM in Room 101" — schedule management.</li>
</ul>

<h3>1.5.5 NBFC / Lending (Non-Banking Financial Companies)</h3>

<p>This is one of Niv AI's most specialized and detailed integrations. NBFCs using Growth System (a lending-focused ERPNext fork) get access to 34 specialized tools for:</p>

<ul>
  <li><strong>Loan Origination:</strong> Process loan applications through natural conversation — "Create a new loan application for Applicant Rajesh Kumar, loan amount 5 lakhs, tenure 24 months"</li>
  <li><strong>KYC Verification:</strong> "Check KYC status for Application LAP-2026-001" — verifies Aadhaar, PAN, address proof, and income documents.</li>
  <li><strong>CIBIL Score Queries:</strong> "What's the CIBIL score for Applicant XYZ?" — direct access to credit bureau data.</li>
  <li><strong>EMI Calculations:</strong> "Calculate EMI for loan amount 10 lakhs at 14% for 36 months" — instant EMI calculation with amortization schedule.</li>
  <li><strong>Collection Management:</strong> "Show me all loans overdue by more than 90 days (NPA)" — critical collection data for field teams.</li>
  <li><strong>Co-Lending Operations:</strong> "What's the disbursement status with Partner Bank ABC?" — co-lending portfolio tracking.</li>
  <li><strong>Compliance Monitoring:</strong> Auto-Pilot Triggers validate loan documents against RBI guidelines before submission.</li>
  <li><strong>Portfolio Analytics:</strong> "What's our AUM (Assets Under Management) broken down by product type?" — portfolio-level analytics.</li>
</ul>

<p>Chapters 14–16 provide a 140-page deep dive into NBFC operations with Niv AI.</p>

<h3>1.5.6 Professional Services</h3>

<ul>
  <li><strong>Project Tracking:</strong> "What's the status of Project ABC? Show me all open tasks." — project dashboard via chat.</li>
  <li><strong>Timesheet Management:</strong> "Log 4 hours on Project ABC, Task: Code Review, for today" — timesheet entry via chat.</li>
  <li><strong>Invoice Generation:</strong> "Generate invoices for all completed projects this month" — batch invoice creation.</li>
  <li><strong>Resource Utilization:</strong> "Which team members have less than 20 hours logged this week?" — utilization monitoring.</li>
  <li><strong>Client Billing:</strong> "What's the total billable amount for Client XYZ this quarter?" — billing analytics.</li>
</ul>

<h2>1.6 UI Overview</h2>

<p>This section describes every UI element in Niv AI's web interface. While screenshots would typically be included, we provide detailed text descriptions that allow you to understand exactly what each element looks like and how it functions.</p>

<h3>1.6.1 Web Chat Interface (/app/niv-chat)</h3>

<p>The main web chat interface is a full-page application within the Frappe desk. It replaces the standard Frappe page layout with a custom dark-themed chat interface.</p>

<h4>Overall Layout</h4>
<p>The page is divided into two main sections:</p>
<ul>
  <li><strong>Sidebar (Left Panel, ~300px wide):</strong> Dark background (#1a1a2e), contains the conversation list, search bar, and "New Chat" button. On mobile, this collapses into a hamburger menu.</li>
  <li><strong>Main Chat Area (Right Panel, remaining width):</strong> Slightly lighter dark background (#16213e), contains the message area, input box, and voice controls.</li>
</ul>

<h4>Sidebar Elements (Top to Bottom)</h4>
<ol>
  <li><strong>App Title:</strong> "Niv AI" displayed in white with the 🤖 emoji. Below it, a subtitle "AI Assistant for ERPNext" in muted text.</li>
  <li><strong>New Chat Button:</strong> A prominent button with gradient background (primary purple to blue). Clicking creates a new conversation and clears the chat area.</li>
  <li><strong>Search Bar:</strong> An input field with search icon. Filters conversations as you type. Searches conversation titles.</li>
  <li><strong>Conversation List:</strong> Scrollable list of conversations, each showing:
    <ul>
      <li>Conversation title (auto-generated from first message or manually renamed)</li>
      <li>Last message preview (truncated to ~50 characters)</li>
      <li>Timestamp (relative: "2 min ago", "Yesterday", "Jan 15")</li>
      <li>Unread indicator (blue dot) if there are unread messages</li>
      <li>Right-click context menu: Rename, Archive, Delete</li>
    </ul>
  </li>
  <li><strong>Archive Toggle:</strong> At the bottom of the sidebar, a link to show/hide archived conversations.</li>
</ol>

<h4>Main Chat Area Elements</h4>
<ol>
  <li><strong>Chat Header:</strong> Shows current conversation title, with edit (pencil) icon and a menu (three dots) icon for conversation actions.</li>
  <li><strong>Message Area (Scrollable):</strong> The main message display area with:
    <ul>
      <li><strong>User Messages:</strong> Right-aligned bubbles with blue/purple background. Show the user's text and timestamp.</li>
      <li><strong>Assistant Messages:</strong> Left-aligned bubbles with darker background. Support Markdown rendering (headers, bold, italic, lists, tables, code blocks).</li>
      <li><strong>Tool Call Accordions:</strong> When the AI calls a tool, an accordion element appears showing:
        <ul>
          <li>Tool name with wrench icon (🔧)</li>
          <li>Collapsed by default, expandable to show parameters and result</li>
          <li>Green checkmark for successful calls, red X for failures</li>
        </ul>
      </li>
      <li><strong>Code Blocks:</strong> Syntax-highlighted code with copy button and language label</li>
      <li><strong>Tables:</strong> Formatted HTML tables with alternating row colors</li>
    </ul>
  </li>
  <li><strong>Input Area:</strong> Fixed at the bottom:
    <ul>
      <li><strong>Text Input:</strong> Auto-expanding textarea with placeholder "Ask Niv AI anything..."</li>
      <li><strong>Send Button:</strong> Purple arrow icon, activates when text is entered</li>
      <li><strong>Voice Button:</strong> Microphone icon, toggles voice input mode</li>
      <li><strong>Attachment Button:</strong> Paperclip icon for file uploads (PDF, images, spreadsheets)</li>
    </ul>
  </li>
  <li><strong>Voice Mode Overlay:</strong> When voice is active:
    <ul>
      <li>Animated orb (pulsing circle) that responds to audio levels</li>
      <li>Equalizer bars visualization</li>
      <li>Status text: "Listening...", "Processing...", "Speaking..."</li>
      <li>Stop button to end voice session</li>
    </ul>
  </li>
  <li><strong>Message Reactions:</strong> Hover over any assistant message to see:
    <ul>
      <li>👍 (Thumbs up) — rate response as helpful</li>
      <li>👎 (Thumbs down) — rate response as unhelpful</li>
      <li>📋 (Copy) — copy message text to clipboard</li>
    </ul>
  </li>
</ol>
`);

infoBox(`The Web Chat interface uses CSS custom properties (CSS variables) extensively, making it easy to customize the color scheme. All colors are defined in <code>:root</code> in the CSS file. You can create a custom theme by overriding these variables in a Custom CSS entry in Frappe.`);

w(`
<h3>1.6.2 Floating Widget</h3>

<p>The Floating Widget is a minimized version of the chat interface that can be embedded on any Frappe page. It appears as a small circular button (typically in the bottom-right corner) that expands into a compact chat window when clicked.</p>

<ul>
  <li><strong>Collapsed State:</strong> Circular button (~50px) with Niv AI logo/emoji. Badge shows unread message count.</li>
  <li><strong>Expanded State:</strong> A ~400px wide × 600px tall floating panel with the same chat functionality as the full page, but in a compact form factor.</li>
  <li><strong>Drag Support:</strong> The widget can be dragged to different screen positions.</li>
  <li><strong>Persistence:</strong> Widget state (open/closed, position) persists across page navigations within the same session.</li>
</ul>

<h3>1.6.3 Developer Mode Badge</h3>

<p>When Developer Mode is enabled, a <span class="badge badge-dev">DEV</span> badge appears in the chat header. This serves as a visual reminder that the AI has elevated permissions and can modify the system's structure (create DocTypes, add fields, write scripts).</p>
`);

warnBox(`Developer Mode should only be enabled for technical users who understand the implications of structural changes. A Custom Field added incorrectly can break forms; a Server Script with a bug can cause save failures. Always review the AI's proposed changes before confirming.`);

w(`
<h2>1.7 How Niv AI Processes a Request</h2>

<p>To fully understand Niv AI, let's trace the complete journey of a user request from input to response:</p>

<h3>Step 1: User Input</h3>
<p>The user types "Show me all unpaid Sales Invoices for Customer ABC" in the web chat interface.</p>

<h3>Step 2: API Request</h3>
<p>The frontend sends a POST request to <code>/api/method/frappe_assistant_core.api.chat.stream_chat</code> with the message text, conversation ID, and user session.</p>

<h3>Step 3: Authentication & Authorization</h3>
<p>Frappe validates the user's session, checks that the user has permission to access Niv AI (based on roles), and verifies token balance (if billing is enabled).</p>

<h3>Step 4: Message History Assembly</h3>
<p>The system loads the conversation's message history from the database, prepends the system prompt, and appends the new user message.</p>

<h3>Step 5: LangGraph Agent Invocation</h3>
<p>The assembled messages are passed to the LangGraph agent, which sends them to the configured AI provider (e.g., Mistral AI).</p>

<h3>Step 6: AI Model Decision</h3>
<p>The AI model analyzes the request and decides to call the <code>list_documents</code> tool with parameters:</p>
`);

codeBlock('JSON — Tool Call Parameters', `{
  "doctype": "Sales Invoice",
  "filters": [
    ["customer", "=", "Customer ABC"],
    ["outstanding_amount", ">", 0],
    ["docstatus", "=", 1]
  ],
  "fields": ["name", "posting_date", "grand_total", "outstanding_amount"],
  "order_by": "posting_date desc",
  "limit": 20
}`);

w(`
<h3>Step 7: Tool Execution</h3>
<p>The MCP tool server executes the <code>list_documents</code> function, which translates to a Frappe API call: <code>frappe.get_list("Sales Invoice", filters=..., fields=..., order_by=..., limit_page_length=20)</code>. This generates a SQL query against the MariaDB database and returns the matching documents.</p>

<h3>Step 8: Result Processing</h3>
<p>The tool returns a list of Sales Invoices. The LangGraph agent passes this result back to the AI model, which formats it into a human-readable response with a markdown table.</p>

<h3>Step 9: Streaming Response</h3>
<p>The response is streamed back to the frontend via SSE. Each chunk (typically a few tokens) is sent as an SSE event. The frontend renders chunks as they arrive, creating a "typing" effect.</p>

<h3>Step 10: Message Storage</h3>
<p>The complete response, including tool calls and results, is saved to the database as a Niv Message document linked to the conversation.</p>

<h3>Step 11: Token Accounting</h3>
<p>Input tokens (system prompt + history + user message) and output tokens (tool calls + response) are calculated and debited from the user's token balance.</p>

<p>This entire process typically completes in 3–8 seconds, depending on the AI provider's response time and the complexity of the tool calls.</p>

<h2>1.8 Supported Languages</h2>

<p>Niv AI's language support depends on the underlying AI model:</p>
<ul>
  <li><strong>Mistral AI:</strong> Excellent support for English, French, Spanish, German, Italian, and good support for Hindi and other languages.</li>
  <li><strong>OpenAI GPT-4:</strong> Broad multilingual support including English, Hindi, Chinese, Japanese, Korean, Arabic, and 90+ other languages.</li>
  <li><strong>Voice:</strong> STT supports English and Hindi. TTS supports English (lessac voice) and Hindi (priyamvada voice) via Piper.</li>
</ul>
`);

tipBox(`For the best experience in Hindi, set the system prompt to include instructions like: "Respond in Hindi when the user writes in Hindi. Use Devanagari script. Translate ERPNext technical terms to Hindi where natural, but keep DocType names in English for accuracy."`);

w(`
<h2>1.9 Licensing and Pricing</h2>

<p>Niv AI consists of two Frappe applications:</p>
<ul>
  <li><strong>frappe_assistant_core:</strong> The core application — open source (MIT License). Free to use, modify, and distribute.</li>
  <li><strong>niv_tools:</strong> Extended tools package — proprietary. Licensed per-instance or via subscription.</li>
</ul>

<p>The AI provider costs are separate — you pay the AI provider (Mistral, OpenAI, etc.) directly for token usage, or use a locally-hosted model (Ollama) for zero API costs.</p>

<h2>1.10 Chapter Summary</h2>

<p>In this chapter, you learned:</p>
<ul>
  <li>What Niv AI is and why it exists — bridging the gap between ERPNext complexity and conversational simplicity</li>
  <li>The complete feature set: 29 tools, voice mode, Telegram/WhatsApp bots, Developer Mode with 94 features, Auto-Pilot Triggers</li>
  <li>The architecture: Client Layer → API Gateway → Agent Engine → MCP Tools → Data Layer</li>
  <li>Technology stack: Python, Frappe, LangGraph, MCP, Mistral AI, Piper TTS, Redis</li>
  <li>Industry use cases: Manufacturing, Retail, Healthcare, Education, NBFC, Services</li>
  <li>UI elements: Web Chat, Floating Widget, Voice Mode, Developer Badge</li>
  <li>Request processing flow: from user input to streamed response</li>
</ul>

<p>In the next chapter, we'll install Niv AI and configure it for your ERPNext instance.</p>
`);
endChapter();

// ============ CHAPTER 2 ============
chapterHeader('2', 'Installation & Setup', 'Complete guide to installing Niv AI on Docker or bare-metal, configuring AI providers, and verifying your installation');

w(`
<h2>2.1 System Requirements</h2>

<p>Before installing Niv AI, ensure your system meets the following requirements. Niv AI runs as a Frappe application alongside ERPNext, so the requirements include both the base Frappe/ERPNext stack and Niv AI's additional dependencies.</p>

<h3>2.1.1 Hardware Requirements</h3>
`);

table(['Component', 'Minimum', 'Recommended', 'Notes'],
[
  ['CPU', '2 cores', '4+ cores', 'More cores improve concurrent request handling'],
  ['RAM', '4 GB', '8+ GB', 'ERPNext alone needs ~2GB; Niv AI adds ~1GB for the agent runtime'],
  ['Storage', '20 GB', '50+ GB', 'Includes OS, ERPNext, Niv AI, and database. More if storing file attachments.'],
  ['Network', '10 Mbps', '100 Mbps', 'AI API calls require stable internet; local Ollama eliminates this need'],
]);

w(`
<h3>2.1.2 Software Requirements</h3>
`);

table(['Software', 'Version', 'Purpose'],
[
  ['Operating System', 'Ubuntu 22.04 LTS (recommended), Debian 11+, CentOS 8+', 'Server OS'],
  ['Python', '3.10 or 3.11', 'Backend runtime for Frappe and Niv AI'],
  ['Node.js', '18.x LTS', 'Frappe frontend build tools'],
  ['MariaDB', '10.6+', 'Database server'],
  ['Redis', '6.0+', 'Caching, queuing, and undo system'],
  ['Nginx', '1.18+', 'Reverse proxy (production)'],
  ['Git', '2.x', 'Source code management'],
  ['wkhtmltopdf', '0.12.6+', 'PDF generation for print formats'],
  ['Docker', '20.10+ (optional)', 'Containerized deployment'],
  ['Docker Compose', '2.0+ (optional)', 'Multi-container orchestration'],
]);

w(`
<h3>2.1.3 AI Provider Requirements</h3>

<p>You need at least one AI provider configured. Here's what you need for each:</p>
`);

table(['Provider', 'What You Need', 'Cost', 'Best For'],
[
  ['Mistral AI', 'API key from console.mistral.ai', '~$0.25/M input tokens, ~$0.25/M output tokens (Nemo)', 'Best balance of cost, quality, and tool calling'],
  ['OpenAI', 'API key from platform.openai.com', '~$2.50/M input, ~$10/M output (GPT-4o)', 'Highest quality responses; most expensive'],
  ['Groq', 'API key from console.groq.com', 'Free tier available; ~$0.05/M tokens (Llama 3)', 'Fastest inference; good for high-volume, simple queries'],
  ['Together AI', 'API key from api.together.xyz', '~$0.20/M tokens (Llama 3)', 'Good open-source model hosting'],
  ['Ollama', 'Local installation of Ollama', 'Free (hardware cost only)', 'Privacy-sensitive deployments; no internet required'],
]);

w(`
<h2>2.2 Docker Installation (Recommended)</h2>

<p>Docker is the recommended installation method for Niv AI. It provides a consistent, reproducible environment that works the same way on any machine. This section covers every step in detail.</p>

<h3>2.2.1 Prerequisites: Installing Docker</h3>

<p>If Docker is not already installed on your system, follow these steps:</p>

<h4>Ubuntu 22.04</h4>
`);

codeBlock('bash — Install Docker on Ubuntu 22.04', `# Update package index
sudo apt-get update

# Install prerequisites
sudo apt-get install -y \\
    ca-certificates \\
    curl \\
    gnupg \\
    lsb-release

# Add Docker's official GPG key
sudo mkdir -m 0755 -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \\
    sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Set up the Docker repository
echo \\
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \\
  https://download.docker.com/linux/ubuntu \\
  $(lsb_release -cs) stable" | \\
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \\
    docker-buildx-plugin docker-compose-plugin

# Add your user to the docker group (avoids needing sudo)
sudo usermod -aG docker $USER

# Apply group changes (or log out and back in)
newgrp docker

# Verify installation
docker --version
# Expected output: Docker version 24.x.x, build xxxxxxx

docker compose version
# Expected output: Docker Compose version v2.x.x`);

w(`
<h4>Verify Docker is Working</h4>
`);

codeBlock('bash — Verify Docker', `# Run the hello-world test container
docker run hello-world

# Expected output:
# Hello from Docker!
# This message shows that your installation appears to be working correctly.

# Check Docker service status
sudo systemctl status docker
# Should show "active (running)"`);

w(`
<h3>2.2.2 Setting Up frappe_docker</h3>

<p>Niv AI uses the official <code>frappe_docker</code> repository as a base. This provides a Docker Compose setup for Frappe and ERPNext, to which we add Niv AI's applications.</p>
`);

codeBlock('bash — Clone and Configure frappe_docker', `# Clone the frappe_docker repository
git clone https://github.com/frappe/frappe_docker.git
cd frappe_docker

# Check out a stable version (recommended)
git checkout v15  # or v14 for older ERPNext versions

# List the directory contents
ls -la
# You should see:
# - docker-compose.yml (or compose.yaml)
# - .env.example
# - images/
# - overrides/
# - docs/`);

w(`
<h4>Understanding the Docker Compose File</h4>

<p>The <code>docker-compose.yml</code> file defines all the services that make up the ERPNext + Niv AI stack. Let's examine each service:</p>
`);

codeBlock('yaml — docker-compose.yml (annotated)', `version: "3.8"

services:
  # === BACKEND SERVICE ===
  # The main Frappe/ERPNext application server
  backend:
    image: frappe/erpnext:v15
    # Custom image with Niv AI apps (see build section below)
    # image: custom-erpnext:latest
    volumes:
      - sites:/home/frappe/frappe-bench/sites
      - logs:/home/frappe/frappe-bench/logs
    environment:
      # Database connection
      DB_HOST: db
      DB_PORT: "3306"
      # Redis connections
      REDIS_CACHE: redis-cache:6379
      REDIS_QUEUE: redis-queue:6379
      REDIS_SOCKETIO: redis-socketio:6379
      # Worker configuration
      WORKER_CLASS: gthread
      GUNICORN_WORKERS: 4
    depends_on:
      - db
      - redis-cache
      - redis-queue
      - redis-socketio

  # === DATABASE SERVICE ===
  db:
    image: mariadb:10.6
    command:
      - --character-set-server=utf8mb4
      - --collation-server=utf8mb4_unicode_ci
      - --skip-character-set-client-handshake
      - --skip-innodb-read-only-compressed
    volumes:
      - db-data:/var/lib/mysql
    environment:
      MYSQL_ROOT_PASSWORD: \${DB_PASSWORD:-admin}
      MYSQL_DATABASE: _Global

  # === REDIS SERVICES ===
  redis-cache:
    image: redis:7-alpine
    volumes:
      - redis-cache-data:/data

  redis-queue:
    image: redis:7-alpine
    volumes:
      - redis-queue-data:/data

  redis-socketio:
    image: redis:7-alpine

  # === FRONTEND/PROXY SERVICE ===
  frontend:
    image: frappe/erpnext:v15
    command: nginx-entrypoint.sh
    volumes:
      - sites:/home/frappe/frappe-bench/sites
    ports:
      - "8080:8080"
    depends_on:
      - backend
      - websocket

  # === WEBSOCKET SERVICE ===
  websocket:
    image: frappe/erpnext:v15
    command: ["node", "/home/frappe/frappe-bench/apps/frappe/socketio.js"]
    volumes:
      - sites:/home/frappe/frappe-bench/sites
      - logs:/home/frappe/frappe-bench/logs

  # === BACKGROUND WORKERS ===
  queue-short:
    image: frappe/erpnext:v15
    command: bench worker --queue short
    volumes:
      - sites:/home/frappe/frappe-bench/sites
      - logs:/home/frappe/frappe-bench/logs

  queue-default:
    image: frappe/erpnext:v15
    command: bench worker --queue default
    volumes:
      - sites:/home/frappe/frappe-bench/sites
      - logs:/home/frappe/frappe-bench/logs

  queue-long:
    image: frappe/erpnext:v15
    command: bench worker --queue long
    volumes:
      - sites:/home/frappe/frappe-bench/sites
      - logs:/home/frappe/frappe-bench/logs

  # === SCHEDULER ===
  scheduler:
    image: frappe/erpnext:v15
    command: bench schedule
    volumes:
      - sites:/home/frappe/frappe-bench/sites
      - logs:/home/frappe/frappe-bench/logs

volumes:
  db-data:
  redis-cache-data:
  redis-queue-data:
  sites:
  logs:`);

w(`
<h3>2.2.3 Building Custom Image with Niv AI</h3>

<p>To include Niv AI in the Docker setup, you need to build a custom image that includes the <code>frappe_assistant_core</code> and <code>niv_tools</code> apps.</p>
`);

codeBlock('bash — Build Custom Docker Image', `# Create an apps.json file that lists all apps to install
cat > apps.json <<'EOF'
[
  {
    "url": "https://github.com/frappe/erpnext",
    "branch": "version-15"
  },
  {
    "url": "https://github.com/your-org/frappe_assistant_core",
    "branch": "main"
  },
  {
    "url": "https://github.com/your-org/niv_tools",
    "branch": "main"
  }
]
EOF

# Build the custom image
# This uses frappe_docker's build system
export APPS_JSON_BASE64=$(base64 -w 0 apps.json)

docker build \\
  --build-arg=FRAPPE_PATH=https://github.com/frappe/frappe \\
  --build-arg=FRAPPE_BRANCH=version-15 \\
  --build-arg=PYTHON_VERSION=3.11.6 \\
  --build-arg=NODE_VERSION=18.18.2 \\
  --build-arg=APPS_JSON_BASE64=$APPS_JSON_BASE64 \\
  --tag=custom-erpnext:latest \\
  --file=images/custom/Containerfile .

# This build process takes 10-20 minutes on first run
# It will:
# 1. Set up a Frappe bench environment
# 2. Clone all apps from apps.json
# 3. Install Python dependencies for each app
# 4. Build frontend assets
# 5. Create the final production image`);

warnBox(`The build process requires internet access to download dependencies. If you're behind a corporate proxy, you may need to configure Docker's proxy settings in <code>/etc/docker/daemon.json</code> or pass <code>--build-arg HTTP_PROXY=...</code> to the build command.`);

w(`
<h3>2.2.4 Creating and Configuring the Site</h3>
`);

codeBlock('bash — Create ERPNext Site with Niv AI', `# Start the infrastructure services first
docker compose up -d db redis-cache redis-queue redis-socketio

# Wait for MariaDB to be ready (important!)
sleep 15

# Create a new site
docker compose run --rm backend \\
  bench new-site erp.example.com \\
  --mariadb-root-password=admin \\
  --admin-password=YourSecurePassword123 \\
  --install-app erpnext \\
  --install-app frappe_assistant_core \\
  --install-app niv_tools

# The site creation process:
# 1. Creates the database "erp_example_com" (dots replaced with underscores)
# 2. Runs database migrations for Frappe framework
# 3. Installs ERPNext app and runs its migrations
# 4. Installs frappe_assistant_core and creates:
#    - Niv Settings (singleton)
#    - Niv AI Provider DocType
#    - Niv System Prompt DocType
#    - Niv Conversation DocType
#    - Niv Message DocType
#    - Niv Trigger DocType
#    - Niv Telegram User DocType
#    - Niv WhatsApp User DocType
#    - Niv Token Transaction DocType
#    - Various other supporting DocTypes
# 5. Installs niv_tools and registers custom tools

# Set the site as default
docker compose run --rm backend \\
  bench --site erp.example.com set-config \\
  host_name "http://erp.example.com"

# Add site to sites/currentsite.txt
docker compose run --rm backend \\
  bench set-current-site erp.example.com`);

w(`
<h3>2.2.5 Starting All Services</h3>
`);

codeBlock('bash — Start Complete Stack', `# Start all services
docker compose up -d

# Check service status
docker compose ps

# Expected output:
# NAME                    STATUS    PORTS
# frappe_docker-backend-1       running
# frappe_docker-db-1            running   3306/tcp
# frappe_docker-frontend-1      running   0.0.0.0:8080->8080/tcp
# frappe_docker-queue-default-1 running
# frappe_docker-queue-long-1    running
# frappe_docker-queue-short-1   running
# frappe_docker-redis-cache-1   running   6379/tcp
# frappe_docker-redis-queue-1   running   6379/tcp
# frappe_docker-redis-socketio-1 running  6379/tcp
# frappe_docker-scheduler-1     running
# frappe_docker-websocket-1     running

# Check logs for any errors
docker compose logs backend --tail 50
docker compose logs frontend --tail 20

# Access the site
# Open http://localhost:8080 in your browser
# Login with: Administrator / YourSecurePassword123`);

infoBox(`After starting the services, it may take 1-2 minutes for the site to be fully accessible. Frappe needs to compile assets and warm up the cache on first load.`);

w(`
<h3>2.2.6 Docker Environment Variables</h3>

<p>Create a <code>.env</code> file in the frappe_docker directory to customize your deployment:</p>
`);

codeBlock('env — .env file', `# Database
DB_PASSWORD=your_secure_db_password

# Site
FRAPPE_SITE_NAME_HEADER=erp.example.com

# Performance
GUNICORN_WORKERS=4
WORKER_CLASS=gthread

# Ports
HTTP_PORT=8080
HTTPS_PORT=443

# Email (optional)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_LOGIN=your-email@gmail.com
MAIL_PASSWORD=your-app-password

# Niv AI specific (set via bench set-config or Niv Settings)
# These are typically configured through the UI, not environment variables`);

w(`
<h2>2.3 Manual Bench Installation</h2>

<p>If you prefer a bare-metal installation without Docker, follow this comprehensive guide. This is also the preferred method for development environments.</p>

<h3>2.3.1 Install Prerequisites (Ubuntu 22.04)</h3>
`);

codeBlock('bash — Install All Prerequisites', `# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Python 3.11
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-dev python3.11-venv python3-pip

# Install Node.js 18
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install Yarn
sudo npm install -g yarn

# Install MariaDB
sudo apt-get install -y mariadb-server mariadb-client

# Secure MariaDB
sudo mysql_secure_installation
# - Set root password: Yes (enter a strong password)
# - Remove anonymous users: Yes
# - Disallow root login remotely: Yes
# - Remove test database: Yes
# - Reload privilege tables: Yes

# Configure MariaDB for Frappe
sudo tee /etc/mysql/mariadb.conf.d/99-frappe.cnf <<'EOF'
[mysqld]
character-set-client-handshake = FALSE
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci

[mysql]
default-character-set = utf8mb4
EOF

sudo systemctl restart mariadb

# Install Redis
sudo apt-get install -y redis-server
sudo systemctl enable redis-server

# Install wkhtmltopdf
sudo apt-get install -y xvfb libfontconfig wkhtmltopdf

# Install other dependencies
sudo apt-get install -y \\
    git \\
    curl \\
    wget \\
    software-properties-common \\
    libffi-dev \\
    libssl-dev \\
    libjpeg-dev \\
    zlib1g-dev \\
    libfreetype6-dev \\
    liblcms2-dev \\
    libwebp-dev \\
    libmysqlclient-dev \\
    supervisor \\
    nginx

# Install bench CLI
sudo pip3 install frappe-bench

# Verify all installations
python3.11 --version    # Python 3.11.x
node --version          # v18.x.x
yarn --version          # 1.x.x
mysql --version         # mysql  Ver 15.1 Distrib 10.6.x-MariaDB
redis-cli --version     # redis-cli 6.x.x or 7.x.x
bench --version         # 5.x.x`);

w(`
<h3>2.3.2 Initialize Frappe Bench</h3>
`);

codeBlock('bash — Initialize Bench', `# Create bench directory
bench init frappe-bench \\
  --frappe-branch version-15 \\
  --python python3.11

# This creates:
# frappe-bench/
# ├── apps/
# │   └── frappe/           # Frappe framework
# ├── config/
# │   ├── pids/
# │   ├── redis_cache.conf
# │   ├── redis_queue.conf
# │   └── redis_socketio.conf
# ├── env/                  # Python virtual environment
# ├── logs/
# ├── sites/
# │   └── apps.txt
# ├── Procfile
# └── patches.txt

cd frappe-bench

# Get ERPNext
bench get-app erpnext --branch version-15

# Get Frappe Assistant Core (Niv AI)
bench get-app frappe_assistant_core https://github.com/your-org/frappe_assistant_core.git

# Get Niv Tools
bench get-app niv_tools https://github.com/your-org/niv_tools.git

# Verify apps are downloaded
ls apps/
# Expected: frappe  erpnext  frappe_assistant_core  niv_tools`);

w(`
<h3>2.3.3 Create Site and Install Apps</h3>
`);

codeBlock('bash — Create Site', `# Create a new site
bench new-site erp.local \\
  --mariadb-root-password YourMariaDBRootPassword \\
  --admin-password YourAdminPassword

# Install ERPNext
bench --site erp.local install-app erpnext

# Install Frappe Assistant Core
bench --site erp.local install-app frappe_assistant_core

# Install Niv Tools
bench --site erp.local install-app niv_tools

# Run database migrations (ensure all tables are created)
bench --site erp.local migrate

# Set as current site
bench use erp.local

# Build frontend assets
bench build

# Start the development server
bench start

# The bench start command starts:
# - Frappe web server on port 8000
# - Redis cache on port 13000
# - Redis queue on port 11000
# - Redis socketio on port 12000
# - Socketio server on port 9000
# - Background workers (short, default, long queues)
# - Scheduler for periodic tasks

# Access at http://localhost:8000
# Login: Administrator / YourAdminPassword`);

w(`
<h3>2.3.4 Installing Piper TTS (Voice Support)</h3>

<p>Piper TTS is required for text-to-speech functionality. It's a fast, local TTS engine that produces high-quality speech.</p>
`);

codeBlock('bash — Install Piper TTS', `# Create directory for Piper
mkdir -p ~/piper
cd ~/piper

# Download Piper binary (Linux x86_64)
wget https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_amd64.tar.gz
tar -xzf piper_amd64.tar.gz

# Download voice models
# English (lessac) - high quality US English voice
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json

# Hindi (priyamvada) - Hindi female voice
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/hi/hi_IN/priyamvada/medium/hi_IN-priyamvada-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/hi/hi_IN/priyamvada/medium/hi_IN-priyamvada-medium.onnx.json

# Test Piper
echo "Hello, I am Niv AI, your ERPNext assistant." | \\
  ./piper --model en_US-lessac-medium.onnx --output_file test.wav

# Play the test file (if you have aplay)
aplay test.wav

# Verify Piper path
echo "Piper installed at: $(pwd)/piper"
# Note this path — you'll need it for Niv Settings`);

w(`
<h2>2.4 Initial Configuration</h2>

<p>After installation, you need to configure Niv AI through the Niv Settings page. This is the central configuration hub for all Niv AI features.</p>

<h3>2.4.1 Accessing Niv Settings</h3>

<p>Navigate to <code>/app/niv-settings</code> in your browser, or search for "Niv Settings" in the Awesome Bar (the search bar at the top of every Frappe page).</p>
`);

infoBox(`Niv Settings is a "Single" DocType — there's only one instance in the entire system. It's similar to System Settings in Frappe. Only System Managers can access and modify Niv Settings.`);

w(`
<h3>2.4.2 General Settings Section</h3>

<p>The first section of Niv Settings contains general configuration options:</p>
`);

table(['Field', 'Type', 'Default', 'Description'],
[
  ['enable_niv_ai', 'Check', '0', 'Master switch. When unchecked, all Niv AI features are disabled. Chat pages show a "Niv AI is disabled" message. APIs return 403 errors.'],
  ['default_ai_provider', 'Link (Niv AI Provider)', '', 'The AI provider used for all conversations unless overridden. Must be set before using Niv AI.'],
  ['default_system_prompt', 'Link (Niv System Prompt)', '', 'The system prompt used for all conversations unless overridden. If empty, a basic default prompt is used.'],
  ['enable_developer_mode', 'Check', '0', 'Enables Developer Mode, allowing the AI to create Custom Fields, Server Scripts, DocTypes, etc. Shows the DEV badge in chat.'],
  ['enable_triggers', 'Check', '0', 'Enables Auto-Pilot Triggers. When checked, document events can trigger AI processing.'],
  ['max_tokens_per_response', 'Int', '4096', 'Maximum number of output tokens the AI can generate per response. Higher values allow longer responses but cost more.'],
  ['max_tool_calls_per_turn', 'Int', '10', 'Maximum number of tool calls the AI can make in a single turn. Prevents infinite loops.'],
  ['conversation_history_limit', 'Int', '50', 'Number of recent messages included in the context. Higher values give the AI more context but increase token usage.'],
]);

w(`
<h3>2.4.3 Billing Settings Section</h3>
`);

table(['Field', 'Type', 'Default', 'Description'],
[
  ['billing_mode', 'Select', 'Shared Pool', 'Options: "Shared Pool" (organization-wide balance) or "Per User" (individual wallets)'],
  ['shared_pool_balance', 'Currency', '0', 'Current token balance in Shared Pool mode. Visible only when billing_mode is "Shared Pool".'],
  ['enable_razorpay', 'Check', '0', 'Enable Razorpay payment integration for token purchases'],
  ['razorpay_key_id', 'Data', '', 'Razorpay API Key ID (starts with "rzp_test_" or "rzp_live_")'],
  ['razorpay_key_secret', 'Password', '', 'Razorpay API Key Secret'],
  ['razorpay_webhook_secret', 'Password', '', 'Secret for verifying Razorpay webhook signatures'],
  ['token_cost_per_1k_input', 'Float', '0.001', 'Cost in currency per 1000 input tokens. Used for billing calculations.'],
  ['token_cost_per_1k_output', 'Float', '0.003', 'Cost in currency per 1000 output tokens. Output tokens are typically 3x more expensive.'],
]);

w(`
<h3>2.4.4 Voice Settings Section</h3>
`);

table(['Field', 'Type', 'Default', 'Description'],
[
  ['enable_voice', 'Check', '0', 'Enable voice mode in the web chat interface'],
  ['tts_engine', 'Select', 'Browser', 'Options: "Piper" (recommended, high quality) or "Browser" (uses browser speechSynthesis)'],
  ['piper_binary_path', 'Data', '/usr/local/bin/piper', 'Full path to the Piper TTS binary'],
  ['piper_voice_model', 'Data', 'en_US-lessac-medium.onnx', 'Path to the default Piper voice model file'],
  ['piper_voice_hindi', 'Data', 'hi_IN-priyamvada-medium.onnx', 'Path to the Hindi Piper voice model file'],
  ['stt_engine', 'Select', 'Browser', 'Options: "Voxtral" (Mistral STT, most accurate) or "Browser" (browser Speech Recognition)'],
  ['voxtral_api_key', 'Password', '', 'Mistral AI API key for Voxtral STT (can be same as the provider key)'],
  ['enable_continuous_mode', 'Check', '0', 'Enable continuous conversation mode: after TTS finishes speaking, STT automatically resumes listening'],
]);

w(`
<h3>2.4.5 Telegram Settings Section</h3>
`);

table(['Field', 'Type', 'Default', 'Description'],
[
  ['enable_telegram', 'Check', '0', 'Enable Telegram bot integration'],
  ['telegram_bot_token', 'Password', '', 'Bot token from @BotFather (format: 123456789:ABCdef...)'],
  ['telegram_webhook_url', 'Data', '', 'Full URL for Telegram webhook (e.g., https://erp.example.com/api/method/frappe_assistant_core.api.telegram.webhook)'],
  ['telegram_webhook_secret', 'Data', '', 'Secret token for webhook verification'],
]);

w(`
<h3>2.4.6 WhatsApp Settings Section</h3>
`);

table(['Field', 'Type', 'Default', 'Description'],
[
  ['enable_whatsapp', 'Check', '0', 'Enable WhatsApp bot integration'],
  ['whatsapp_phone_number_id', 'Data', '', 'Phone Number ID from Meta Business Dashboard'],
  ['whatsapp_access_token', 'Password', '', 'Permanent access token from Meta Business Dashboard'],
  ['whatsapp_verify_token', 'Data', '', 'Custom string for webhook verification (you choose this)'],
  ['whatsapp_app_secret', 'Password', '', 'App Secret for webhook signature verification'],
]);

w(`
<h2>2.5 AI Provider Setup</h2>

<p>This section provides detailed setup instructions for each supported AI provider.</p>

<h3>2.5.1 Mistral AI Setup (Recommended)</h3>

<p>Mistral AI offers the best balance of cost, quality, and tool calling capability for Niv AI. Here's the complete setup process:</p>

<h4>Step 1: Create an Account</h4>
<ol>
  <li>Go to <a href="https://console.mistral.ai">https://console.mistral.ai</a></li>
  <li>Click "Sign Up" and create an account (email or Google/GitHub OAuth)</li>
  <li>Verify your email address</li>
  <li>Complete the onboarding form (company name, use case)</li>
</ol>

<h4>Step 2: Get an API Key</h4>
<ol>
  <li>In the Mistral console, navigate to "API Keys" in the left sidebar</li>
  <li>Click "Create New Key"</li>
  <li>Give it a name (e.g., "Niv AI Production")</li>
  <li>Copy the key immediately — it won't be shown again</li>
  <li>The key format is a long alphanumeric string</li>
</ol>

<h4>Step 3: Add Credits</h4>
<ol>
  <li>Navigate to "Billing" in the Mistral console</li>
  <li>Add a payment method (credit/debit card)</li>
  <li>Add credits (minimum $5). For testing, $5 is sufficient for thousands of conversations.</li>
</ol>

<h4>Step 4: Create Niv AI Provider in ERPNext</h4>
<ol>
  <li>Navigate to <code>/app/niv-ai-provider/new</code> in your ERPNext instance</li>
  <li>Fill in the following fields:</li>
</ol>
`);

table(['Field', 'Value', 'Explanation'],
[
  ['Provider Name', 'Mistral AI', 'Human-readable name shown in selection dropdowns'],
  ['Provider Type', 'Mistral', 'Selects the correct API adapter'],
  ['API Key', '(paste your key)', 'The API key from Step 2. Stored as a Password field (encrypted).'],
  ['API Base URL', 'https://api.mistral.ai/v1', 'The base URL for Mistral AI API. Do not change unless using a proxy.'],
  ['Model Name', 'mistral-large-latest', 'The model to use. Options: mistral-large-latest (best), open-mistral-nemo (cheapest), mistral-small-latest (balanced)'],
  ['Temperature', '0.1', 'Controls randomness. 0.0 = deterministic, 1.0 = creative. For ERP tasks, low temperature (0.1-0.3) is recommended.'],
  ['Max Tokens', '4096', 'Maximum output tokens per response'],
  ['Enabled', '✓ (checked)', 'Activate this provider'],
]);

codeBlock('json — Example Niv AI Provider document', `{
  "doctype": "Niv AI Provider",
  "provider_name": "Mistral AI",
  "provider_type": "Mistral",
  "api_key": "****",
  "api_base_url": "https://api.mistral.ai/v1",
  "model_name": "mistral-large-latest",
  "temperature": 0.1,
  "max_tokens": 4096,
  "enabled": 1
}`);

w(`
<ol start="3">
  <li>Save the document</li>
  <li>Go to Niv Settings and set "Default AI Provider" to "Mistral AI"</li>
</ol>
`);

tipBox(`<strong>Model Selection Guide:</strong><br>
• <code>mistral-large-latest</code> — Best quality, best tool calling. ~$2/M input, ~$6/M output. Recommended for production.<br>
• <code>open-mistral-nemo</code> — Good quality at 1/10th the cost. ~$0.15/M input, ~$0.15/M output. Good for development and testing.<br>
• <code>mistral-small-latest</code> — Balance between large and nemo. ~$0.2/M input, ~$0.6/M output.`);

w(`
<h3>2.5.2 OpenAI Setup</h3>

<h4>Step 1: Create an Account</h4>
<ol>
  <li>Go to <a href="https://platform.openai.com">https://platform.openai.com</a></li>
  <li>Sign up or log in</li>
  <li>Navigate to API Keys → Create New Secret Key</li>
  <li>Copy the key (starts with "sk-")</li>
</ol>

<h4>Step 2: Create Provider in ERPNext</h4>
`);

table(['Field', 'Value'],
[
  ['Provider Name', 'OpenAI GPT-4'],
  ['Provider Type', 'OpenAI'],
  ['API Key', 'sk-...'],
  ['API Base URL', 'https://api.openai.com/v1'],
  ['Model Name', 'gpt-4o'],
  ['Temperature', '0.1'],
  ['Max Tokens', '4096'],
]);

w(`
<h3>2.5.3 Groq Setup</h3>
`);

table(['Field', 'Value'],
[
  ['Provider Name', 'Groq Llama'],
  ['Provider Type', 'Groq'],
  ['API Key', 'gsk_...'],
  ['API Base URL', 'https://api.groq.com/openai/v1'],
  ['Model Name', 'llama-3.1-70b-versatile'],
  ['Temperature', '0.1'],
  ['Max Tokens', '4096'],
]);

w(`
<h3>2.5.4 Together AI Setup</h3>
`);

table(['Field', 'Value'],
[
  ['Provider Name', 'Together AI'],
  ['Provider Type', 'Together'],
  ['API Key', '(from api.together.xyz)'],
  ['API Base URL', 'https://api.together.xyz/v1'],
  ['Model Name', 'meta-llama/Llama-3-70b-chat-hf'],
  ['Temperature', '0.1'],
  ['Max Tokens', '4096'],
]);

w(`
<h3>2.5.5 Ollama Setup (Local/Self-Hosted)</h3>

<p>Ollama allows you to run AI models locally, ensuring complete data privacy and zero API costs.</p>
`);

codeBlock('bash — Install and Configure Ollama', `# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model (Llama 3 8B recommended for local use)
ollama pull llama3.1:8b

# For better quality (requires 16GB+ RAM):
ollama pull llama3.1:70b

# Start Ollama server (if not auto-started)
ollama serve

# Verify it's running
curl http://localhost:11434/api/tags
# Should return a JSON list of available models

# Test the model
curl http://localhost:11434/api/generate -d '{
  "model": "llama3.1:8b",
  "prompt": "Hello, how are you?",
  "stream": false
}'`);

table(['Field', 'Value'],
[
  ['Provider Name', 'Ollama Local'],
  ['Provider Type', 'Ollama'],
  ['API Key', '(leave empty — Ollama has no auth by default)'],
  ['API Base URL', 'http://localhost:11434/v1'],
  ['Model Name', 'llama3.1:8b'],
  ['Temperature', '0.1'],
  ['Max Tokens', '4096'],
]);

warnBox(`Ollama models running locally have significantly slower inference compared to cloud providers. A 8B model on CPU might take 10-30 seconds per response. For acceptable performance, use a GPU (NVIDIA with CUDA) or the smaller models.`);

w(`
<h2>2.6 Verification Steps</h2>

<p>After completing the installation and configuration, verify everything is working correctly:</p>

<h3>2.6.1 Verify Niv AI is Enabled</h3>
`);

codeBlock('python — Verify via bench console', `# Open bench console
# bench --site erp.local console

import frappe

# Check if Niv AI is enabled
settings = frappe.get_single("Niv Settings")
print(f"Niv AI Enabled: {settings.enable_niv_ai}")
print(f"Default Provider: {settings.default_ai_provider}")
print(f"Developer Mode: {settings.enable_developer_mode}")
print(f"Triggers Enabled: {settings.enable_triggers}")

# Check installed apps
print(f"\\nInstalled Apps: {frappe.get_installed_apps()}")
# Expected: ['frappe', 'erpnext', 'frappe_assistant_core', 'niv_tools']`);

w(`
<h3>2.6.2 Verify MCP Tools</h3>
`);

codeBlock('python — Verify Tools are Registered', `# In bench console
from frappe_assistant_core.mcp.server import get_available_tools

tools = get_available_tools()
print(f"Total tools available: {len(tools)}")
for tool in tools:
    print(f"  - {tool['name']}: {tool['description'][:60]}...")

# Expected: 29 tools (23 core + 6 custom)
# Should include: create_document, get_document, list_documents, 
# run_database_query, universal_search, etc.`);

w(`
<h3>2.6.3 Verify AI Provider Connection</h3>
`);

codeBlock('python — Test AI Provider', `# In bench console
from frappe_assistant_core.providers import get_provider

provider = get_provider()
print(f"Provider Type: {provider.provider_type}")
print(f"Model: {provider.model_name}")

# Send a test message
response = provider.chat([
    {"role": "user", "content": "Say hello in exactly 5 words"}
])
print(f"Response: {response.content}")
print(f"Tokens used: {response.usage}")
# Expected: A 5-word greeting and token count`);

w(`
<h3>2.6.4 Verify Web Chat</h3>

<ol>
  <li>Open <code>/app/niv-chat</code> in your browser</li>
  <li>You should see the dark-themed chat interface</li>
  <li>Click "New Chat" in the sidebar</li>
  <li>Type "Hello, are you working?" and press Enter</li>
  <li>You should see:
    <ul>
      <li>Your message appear as a right-aligned blue bubble</li>
      <li>A typing indicator (three dots) appear</li>
      <li>The AI's response stream in word by word</li>
      <li>The response should mention being Niv AI, an ERPNext assistant</li>
    </ul>
  </li>
</ol>

<h2>2.7 Common Installation Errors and Fixes</h2>

<p>This section covers the most common issues encountered during installation, with detailed solutions for each.</p>

<h3>Error 1: "Module 'frappe_assistant_core' not found"</h3>
`);

codeBlock('bash — Fix: Module not found', `# This usually means the app wasn't installed on the site
bench --site erp.local install-app frappe_assistant_core

# If that fails with "App not in apps.txt"
bench get-app frappe_assistant_core /path/to/repo
bench --site erp.local install-app frappe_assistant_core

# Run migrations
bench --site erp.local migrate

# Clear cache
bench --site erp.local clear-cache`);

w(`
<h3>Error 2: "langchain/langgraph not found"</h3>
`);

codeBlock('bash — Fix: Python dependencies', `# Install Python dependencies manually
cd ~/frappe-bench
./env/bin/pip install langchain langchain-core langgraph langchain-mistralai

# Or install from the app's requirements
./env/bin/pip install -r apps/frappe_assistant_core/requirements.txt

# Restart bench
bench restart  # or Ctrl+C and bench start`);

w(`
<h3>Error 3: "Redis connection refused"</h3>
`);

codeBlock('bash — Fix: Redis not running', `# Check Redis status
sudo systemctl status redis-server

# If not running, start it
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Verify Redis is accessible
redis-cli ping
# Expected: PONG

# If port conflict, check Frappe's Redis config
cat config/redis_cache.conf | grep port
# Default ports: 13000 (cache), 11000 (queue), 12000 (socketio)`);

w(`
<h3>Error 4: "SSE streaming not working — responses appear all at once"</h3>
`);

codeBlock('nginx — Fix: Nginx SSE configuration', `# Edit your Nginx site configuration
# Add these directives to the location block for API calls

location /api {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    
    # Critical for SSE:
    proxy_buffering off;          # Disable response buffering
    proxy_cache off;              # Disable caching
    proxy_set_header Connection ''; # Allow keep-alive
    
    # Timeouts for long-running SSE connections
    proxy_read_timeout 300s;
    proxy_connect_timeout 75s;
    proxy_send_timeout 300s;
    
    # Standard proxy headers
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# Reload Nginx
sudo nginx -t && sudo systemctl reload nginx`);

w(`
<h3>Error 5: "AI Provider returns 401 Unauthorized"</h3>
`);

codeBlock('text — Fix: API Key issues', `Possible causes:
1. API key is incorrect — regenerate from provider console
2. API key has expired — check provider dashboard
3. No credits/balance — add funds to provider account
4. API key stored incorrectly — check for leading/trailing spaces

To verify:
# Test the key directly with curl
curl https://api.mistral.ai/v1/chat/completions \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"open-mistral-nemo","messages":[{"role":"user","content":"hi"}]}'

# If this returns a response, the key is valid.
# If 401, regenerate the key from the provider console.`);

w(`
<h3>Error 6: "Docker container keeps restarting"</h3>
`);

codeBlock('bash — Fix: Docker restart loop', `# Check container logs
docker compose logs backend --tail 100

# Common causes:
# 1. Database not ready yet — backend starts before MariaDB
# Solution: Add healthcheck and depends_on conditions

# 2. Missing sites directory
docker compose run --rm backend ls sites/
# If empty, you need to create the site first

# 3. Permission issues
docker compose run --rm backend ls -la sites/
# Files should be owned by frappe:frappe (uid 1000)

# Force recreate containers
docker compose down
docker compose up -d --force-recreate

# Nuclear option: remove volumes and start fresh
# WARNING: This deletes all data!
docker compose down -v
docker compose up -d`);

w(`
<h3>Error 7: "Piper TTS not working"</h3>
`);

codeBlock('bash — Fix: Piper TTS issues', `# Verify Piper binary exists and is executable
ls -la /path/to/piper
# Should show -rwxr-xr-x (executable permissions)

# If not executable
chmod +x /path/to/piper

# Verify voice model exists
ls -la /path/to/en_US-lessac-medium.onnx
ls -la /path/to/en_US-lessac-medium.onnx.json
# Both files must exist in the same directory

# Test Piper directly
echo "Test speech" | /path/to/piper \\
  --model /path/to/en_US-lessac-medium.onnx \\
  --output_file /tmp/test.wav

# Check the output file
file /tmp/test.wav
# Should show: RIFF (little-endian) data, WAVE audio

# Verify path in Niv Settings matches exactly
bench --site erp.local console
>>> frappe.get_single("Niv Settings").piper_binary_path
# Must match the actual path`);

w(`
<h3>Error 8: "MariaDB character set error"</h3>