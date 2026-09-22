<div align="center">

# 🧠 Document Grounded AI Tutor Guide

*A document-grounded AI tutor for learning from your own PDFs.*

</div>

### ✨ Features
- 📄 PDF-based RAG learning
- 💬 Grounded AI tutoring with memory
- 📝 Adaptive quizzes and scoring
- 📊 Performance tracking
- 📅 Personalized study plans
- 🤖 Controlled multi-agent workflow
<br>

### 🏗️ Architecture

<p align="center">
  <img src="project-docs/ai-tutor.png" alt="AI Tutor Guide Architecture" width="850">
</p>

<br>

### 🛡️ Guardrails

Input validation · Prompt-injection checks · Evidence validation · Output grounding · Citation checks · Workflow limits

<br>

### 📈 Evaluation

| Metric | Baseline RAG | Agentic RAG |
|---|---:|---:|
| Recall@4 | 0.90 | 0.90 |
| Answer Similarity | 0.847 | 0.922 |
| Groundedness | 0.486 | 0.837 |
| Faithfulness | 1.00 | 0.98 |

<br>

### 🔍 Observability
**LangSmith** traces agent decisions, retrieval, revisions, latency, and model calls.

<br>

### 🛠️ Tech Stack
`FastAPI` · `LangGraph` · `Gemini` · `ChromaDB` · `SQLite` · `LangSmith` · `React` · `Vite` · `Tailwind`
