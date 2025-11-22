
# LLM-based Multi-Agent System

This project implements a sophisticated multi-agent system powered by Large Language Models (LLMs). The system consists of three specialized agents and an orchestrator agent that coordinates their activities.

## Project Structure

```
llm-project/
├── src/
│   ├── agents/         # Individual agent implementations
│   └── orchestrator/   # Orchestrator agent implementation
├── tests/             # Unit tests
├── config/            # Configuration files
└── requirements.txt   # Project dependencies
```

## Agents

1. Research Agent: Responsible for gathering and analyzing information
2. Code Analysis Agent: Analyzes and understands code structure and patterns
3. Code Generation Agent: Generates and modifies code based on requirements
4. Orchestrator Agent: Coordinates the activities of other agents

## Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment variables:
Create a `.env` file in the project root with necessary API keys and configurations.

## Development

More details will be added as the project progresses.