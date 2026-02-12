# order_support_orchestrator_agents
Order support Orchestrator Agents 

# High Level Flow
```

Customer (Chat UI)
        │
        ▼
Customer Support Agent (NLP) (Customer)
        │
        ▼
🧠 Host / Orchestrator Agent
        │
 ┌──────┼────────┬──────────┬───────────┬──────────┐
 ▼      ▼        ▼          ▼           ▼          ▼
Order  Shipping Returns  Knowledge  Notification  (others)
Agent  Agent    Agent    Base Agent Agent
        │
        ▼
🧠 Host Agent aggregates responses
        │
        ▼
Customer Support Agent formats reply
        │
        ▼
Customer


```

```

Presentation Layer
    - Chat UI

Conversation Layer
    - Customer Support Agent

Orchestration Layer
    - Host Agent

Service Layer
    - Order Agent
    - Shipping Agent
    - Returns Agent
    - Knowledge Agent
    - Notification Agent

Data Layer
    - Databases
    - APIs
    - External services


```
