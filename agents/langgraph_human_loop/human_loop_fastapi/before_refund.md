
# Before Refound 

This is actually normal behavior for LangGraph! Each checkpoint represents a snapshot of the graph state after each node execution in the workflow. Here's what happened with your refund request:

Checkpoint Progression:

Step -1 (Input): Initial user message received
Step 0 (START node): Graph initialization
Step 1 (support_agent): LLM generates tool call for process_refund
Step 2 (tools node): Tool executes and returns result
Step 3 (support_agent): LLM generates final response
Each checkpoint saves:

The full conversation history (messages)
Current state (order_id, amount)
Node execution branching information
Metadata (what node executed, step number)
Why this is useful:

✅ Persistence - If the server crashes, you can resume from the last checkpoint
✅ Debugging - Inspect state at any step
✅ Human-in-the-loop - Pause execution and let humans decide next steps
✅ Auditability - Full execution trace stored
✅ Replay - Run the exact same conversation path again

```

---

## 📊 **Before Refund vs After Refund Comparison**

### **Overview:**

| Aspect | Before Refund | After Refund |
|--------|---------------|--------------|
| **Total Checkpoints** | 5 | 5 |
| **Latest Step** | Step 1 | Step 3 |
| **Messages Count** | 2 messages | 4 messages |

---

### **Message Flow Comparison:**

#### ❌ **BEFORE** (Step 1 - Tool Call Generated):
```json
"messages": [
  {
    "type": "human",
    "content": "Can you refund my id12 cost is $80"
  },
  {
    "type": "ai",
    "tool_calls": [
      {
        "name": "process_refund",
        "args": {
          "order_id": "id12",
          "amount": 80
        }
      }
    ],
    "finish_reason": "tool_calls"
  }
]
```
**Status:** ⏳ Waiting for tool execution

---

#### ✅ **AFTER** (Step 3 - Complete):
```json
"messages": [
  {
    "type": "human",
    "content": "Can you refund my id12 cost is $80"
  },
  {
    "type": "ai",
    "tool_calls": [...]
  },
  {
    "type": "tool",
    "name": "process_refund",
    "content": "Refund of $80.0 for order id12 processed successfully.",
    "status": "success"
  },
  {
    "type": "ai",
    "content": "The refund of $80 for order ID **id12** has been processed successfully.",
    "finish_reason": "stop"
  }
]
```
**Status:** ✅ Execution Complete

---

### **Key Changes:**

| Step | What Changed |
|------|--------------|
| Step 1→2 | Tool node executed `process_refund()` |
| Step 2→3 | Tool result added to messages |
| Step 2→3 | LLM generated final response (no more tool calls) |
| Before | `updated_channels: ["branch:to:tools", "messages"]` |
| After | `updated_channels: ["messages"]` |
| Before | `branch_versions: {..., "branch:to:tools": 3}` |
| After | `branch_versions: {..., "branch:to:tools": 4}` |

---

### **Token Usage Progression:**

```
Step 1 (LLM decision to call tool):
  Input: 143 tokens
  Output: 21 tokens
  Total: 164 tokens ⚙️

Step 3 (LLM final response):
  Input: 186 tokens
  Output: 18 tokens
  Total: 204 tokens ✅
```

---

### **Execution Summary:**

🔄 **Before:** AI identified refund request → generated tool call → **STOPPED** (waiting for tool execution)

✅ **After:** Tool executed → AI processed result → **COMPLETED** with final response

The checkpoint system captured the **entire workflow execution** with full auditability!

```
{
  "thread_id": "user_136",
  "count": 5,
  "checkpoints": [
    {
      "checkpoint_id": "1f11185e-072e-6150-8003-4669bd2efd02",
      "parent_checkpoint_id": "1f11185d-f8a7-62bc-8002-a452e6fab347",
      "checkpoint": {
        "v": 4,
        "ts": "2026-02-24T13:36:51.914369+00:00",
        "id": "1f11185e-072e-6150-8003-4669bd2efd02",
        "channel_values": {
          "messages": [
            {
              "content": "Can you refund my id12 cost is $80",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "human",
              "name": null,
              "id": "20dcb597-a606-4672-b940-13cd71affa0d"
            },
            {
              "content": "",
              "additional_kwargs": {
                "refusal": null
              },
              "response_metadata": {
                "token_usage": {
                  "completion_tokens": 21,
                  "prompt_tokens": 143,
                  "total_tokens": 164,
                  "completion_tokens_details": {
                    "accepted_prediction_tokens": 0,
                    "audio_tokens": 0,
                    "reasoning_tokens": 0,
                    "rejected_prediction_tokens": 0
                  },
                  "prompt_tokens_details": {
                    "audio_tokens": 0,
                    "cached_tokens": 0
                  }
                },
                "model_provider": "openai",
                "model_name": "gpt-4o-mini-2024-07-18",
                "system_fingerprint": "fp_2d82c05f26",
                "id": "chatcmpl-DCmsjiUnvfrUawEJ1DgtfssCHUK6F",
                "service_tier": "default",
                "finish_reason": "tool_calls",
                "logprobs": null
              },
              "type": "ai",
              "name": null,
              "id": "lc_run--019c8fdd-e054-70b1-a378-65ce96441420-0",
              "tool_calls": [
                {
                  "name": "process_refund",
                  "args": {
                    "order_id": "id12",
                    "amount": 80
                  },
                  "id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
                  "type": "tool_call"
                }
              ],
              "invalid_tool_calls": [],
              "usage_metadata": {
                "input_tokens": 143,
                "output_tokens": 21,
                "total_tokens": 164,
                "input_token_details": {
                  "audio": 0,
                  "cache_read": 0
                },
                "output_token_details": {
                  "audio": 0,
                  "reasoning": 0
                }
              }
            },
            {
              "content": "Refund of $80.0 for order id12 processed successfully.",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "tool",
              "name": "process_refund",
              "id": "de3a1d18-d85b-4be1-a46e-ae78c71aaad2",
              "tool_call_id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
              "artifact": null,
              "status": "success"
            },
            {
              "content": "The refund of $80 for order ID **id12** has been processed successfully.",
              "additional_kwargs": {
                "refusal": null
              },
              "response_metadata": {
                "token_usage": {
                  "completion_tokens": 18,
                  "prompt_tokens": 186,
                  "total_tokens": 204,
                  "completion_tokens_details": {
                    "accepted_prediction_tokens": 0,
                    "audio_tokens": 0,
                    "reasoning_tokens": 0,
                    "rejected_prediction_tokens": 0
                  },
                  "prompt_tokens_details": {
                    "audio_tokens": 0,
                    "cached_tokens": 0
                  }
                },
                "model_provider": "openai",
                "model_name": "gpt-4o-mini-2024-07-18",
                "system_fingerprint": "fp_2d82c05f26",
                "id": "chatcmpl-DCmslzsmfA4Dl8g5i2JX6v27adnyL",
                "service_tier": "default",
                "finish_reason": "stop",
                "logprobs": null
              },
              "type": "ai",
              "name": null,
              "id": "lc_run--019c8fdd-e6d7-7cb2-981f-76c0e831c0b2-0",
              "tool_calls": [],
              "invalid_tool_calls": [],
              "usage_metadata": {
                "input_tokens": 186,
                "output_tokens": 18,
                "total_tokens": 204,
                "input_token_details": {
                  "audio": 0,
                  "cache_read": 0
                },
                "output_token_details": {
                  "audio": 0,
                  "reasoning": 0
                }
              }
            }
          ],
          "order_id": "123",
          "amount": 1
        },
        "channel_versions": {
          "__start__": 2,
          "messages": 5,
          "order_id": 2,
          "amount": 2,
          "branch:to:support_agent": 5,
          "branch:to:tools": 4
        },
        "versions_seen": {
          "__input__": {},
          "__start__": {
            "__start__": 1
          },
          "support_agent": {
            "branch:to:support_agent": 4
          },
          "tools": {
            "branch:to:tools": 3
          }
        },
        "updated_channels": [
          "messages"
        ]
      },
      "metadata": {
        "source": "loop",
        "step": 3,
        "parents": {}
      }
    },
    {
      "checkpoint_id": "1f11185d-f8a7-62bc-8002-a452e6fab347",
      "parent_checkpoint_id": "1f11185d-f8a2-6eba-8001-a125446c7b73",
      "checkpoint": {
        "v": 4,
        "ts": "2026-02-24T13:36:50.391104+00:00",
        "id": "1f11185d-f8a7-62bc-8002-a452e6fab347",
        "channel_values": {
          "messages": [
            {
              "content": "Can you refund my id12 cost is $80",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "human",
              "name": null,
              "id": "20dcb597-a606-4672-b940-13cd71affa0d"
            },
            {
              "content": "",
              "additional_kwargs": {
                "refusal": null
              },
              "response_metadata": {
                "token_usage": {
                  "completion_tokens": 21,
                  "prompt_tokens": 143,
                  "total_tokens": 164,
                  "completion_tokens_details": {
                    "accepted_prediction_tokens": 0,
                    "audio_tokens": 0,
                    "reasoning_tokens": 0,
                    "rejected_prediction_tokens": 0
                  },
                  "prompt_tokens_details": {
                    "audio_tokens": 0,
                    "cached_tokens": 0
                  }
                },
                "model_provider": "openai",
                "model_name": "gpt-4o-mini-2024-07-18",
                "system_fingerprint": "fp_2d82c05f26",
                "id": "chatcmpl-DCmsjiUnvfrUawEJ1DgtfssCHUK6F",
                "service_tier": "default",
                "finish_reason": "tool_calls",
                "logprobs": null
              },
              "type": "ai",
              "name": null,
              "id": "lc_run--019c8fdd-e054-70b1-a378-65ce96441420-0",
              "tool_calls": [
                {
                  "name": "process_refund",
                  "args": {
                    "order_id": "id12",
                    "amount": 80
                  },
                  "id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
                  "type": "tool_call"
                }
              ],
              "invalid_tool_calls": [],
              "usage_metadata": {
                "input_tokens": 143,
                "output_tokens": 21,
                "total_tokens": 164,
                "input_token_details": {
                  "audio": 0,
                  "cache_read": 0
                },
                "output_token_details": {
                  "audio": 0,
                  "reasoning": 0
                }
              }
            },
            {
              "content": "Refund of $80.0 for order id12 processed successfully.",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "tool",
              "name": "process_refund",
              "id": "de3a1d18-d85b-4be1-a46e-ae78c71aaad2",
              "tool_call_id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
              "artifact": null,
              "status": "success"
            }
          ],
          "order_id": "123",
          "amount": 1,
          "branch:to:support_agent": null
        },
        "channel_versions": {
          "__start__": 2,
          "messages": 4,
          "order_id": 2,
          "amount": 2,
          "branch:to:support_agent": 4,
          "branch:to:tools": 4
        },
        "versions_seen": {
          "__input__": {},
          "__start__": {
            "__start__": 1
          },
          "support_agent": {
            "branch:to:support_agent": 2
          },
          "tools": {
            "branch:to:tools": 3
          }
        },
        "updated_channels": [
          "branch:to:support_agent",
          "messages"
        ]
      },
      "metadata": {
        "source": "loop",
        "step": 2,
        "parents": {}
      }
    },
    {
      "checkpoint_id": "1f11185d-f8a2-6eba-8001-a125446c7b73",
      "parent_checkpoint_id": "1f11185d-e8c0-6f56-8000-5d5a956ae500",
      "checkpoint": {
        "v": 4,
        "ts": "2026-02-24T13:36:50.389362+00:00",
        "id": "1f11185d-f8a2-6eba-8001-a125446c7b73",
        "channel_values": {
          "messages": [
            {
              "content": "Can you refund my id12 cost is $80",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "human",
              "name": null,
              "id": "20dcb597-a606-4672-b940-13cd71affa0d"
            },
            {
              "content": "",
              "additional_kwargs": {
                "refusal": null
              },
              "response_metadata": {
                "token_usage": {
                  "completion_tokens": 21,
                  "prompt_tokens": 143,
                  "total_tokens": 164,
                  "completion_tokens_details": {
                    "accepted_prediction_tokens": 0,
                    "audio_tokens": 0,
                    "reasoning_tokens": 0,
                    "rejected_prediction_tokens": 0
                  },
                  "prompt_tokens_details": {
                    "audio_tokens": 0,
                    "cached_tokens": 0
                  }
                },
                "model_provider": "openai",
                "model_name": "gpt-4o-mini-2024-07-18",
                "system_fingerprint": "fp_2d82c05f26",
                "id": "chatcmpl-DCmsjiUnvfrUawEJ1DgtfssCHUK6F",
                "service_tier": "default",
                "finish_reason": "tool_calls",
                "logprobs": null
              },
              "type": "ai",
              "name": null,
              "id": "lc_run--019c8fdd-e054-70b1-a378-65ce96441420-0",
              "tool_calls": [
                {
                  "name": "process_refund",
                  "args": {
                    "order_id": "id12",
                    "amount": 80
                  },
                  "id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
                  "type": "tool_call"
                }
              ],
              "invalid_tool_calls": [],
              "usage_metadata": {
                "input_tokens": 143,
                "output_tokens": 21,
                "total_tokens": 164,
                "input_token_details": {
                  "audio": 0,
                  "cache_read": 0
                },
                "output_token_details": {
                  "audio": 0,
                  "reasoning": 0
                }
              }
            }
          ],
          "order_id": "123",
          "amount": 1,
          "branch:to:tools": null
        },
        "channel_versions": {
          "__start__": 2,
          "messages": 3,
          "order_id": 2,
          "amount": 2,
          "branch:to:support_agent": 3,
          "branch:to:tools": 3
        },
        "versions_seen": {
          "__input__": {},
          "__start__": {
            "__start__": 1
          },
          "support_agent": {
            "branch:to:support_agent": 2
          }
        },
        "updated_channels": [
          "branch:to:tools",
          "messages"
        ]
      },
      "metadata": {
        "source": "loop",
        "step": 1,
        "parents": {}
      }
    },
    {
      "checkpoint_id": "1f11185d-e8c0-6f56-8000-5d5a956ae500",
      "parent_checkpoint_id": "1f11185d-e8be-65ee-bfff-576127f646bd",
      "checkpoint": {
        "v": 4,
        "ts": "2026-02-24T13:36:48.723938+00:00",
        "id": "1f11185d-e8c0-6f56-8000-5d5a956ae500",
        "channel_values": {
          "messages": [
            {
              "content": "Can you refund my id12 cost is $80",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "human",
              "name": null,
              "id": "20dcb597-a606-4672-b940-13cd71affa0d"
            }
          ],
          "order_id": "123",
          "amount": 1,
          "branch:to:support_agent": null
        },
        "channel_versions": {
          "__start__": 2,
          "messages": 2,
          "order_id": 2,
          "amount": 2,
          "branch:to:support_agent": 2
        },
        "versions_seen": {
          "__input__": {},
          "__start__": {
            "__start__": 1
          }
        },
        "updated_channels": [
          "amount",
          "branch:to:support_agent",
          "messages",
          "order_id"
        ]
      },
      "metadata": {
        "source": "loop",
        "step": 0,
        "parents": {}
      }
    },
    {
      "checkpoint_id": "1f11185d-e8be-65ee-bfff-576127f646bd",
      "parent_checkpoint_id": null,
      "checkpoint": {
        "v": 4,
        "ts": "2026-02-24T13:36:48.722882+00:00",
        "id": "1f11185d-e8be-65ee-bfff-576127f646bd",
        "channel_values": {
          "__start__": {
            "messages": [
              {
                "content": "Can you refund my id12 cost is $80",
                "additional_kwargs": {},
                "response_metadata": {},
                "type": "human",
                "name": null,
                "id": "20dcb597-a606-4672-b940-13cd71affa0d"
              }
            ],
            "order_id": "123",
            "amount": 1
          }
        },
        "channel_versions": {
          "__start__": 1
        },
        "versions_seen": {
          "__input__": {}
        },
        "updated_channels": [
          "__start__"
        ]
      },
      "metadata": {
        "source": "input",
        "step": -1,
        "parents": {}
      }
    }
  ]
}

```

# After Checkpoint approaval completed now

# Refund Response
```
{
  "messages": [
    {
      "content": "Can you refund my id12 cost is $80",
      "additional_kwargs": {},
      "response_metadata": {},
      "type": "human",
      "name": null,
      "id": "20dcb597-a606-4672-b940-13cd71affa0d"
    },
    {
      "content": "",
      "additional_kwargs": {
        "refusal": null
      },
      "response_metadata": {
        "token_usage": {
          "completion_tokens": 21,
          "prompt_tokens": 143,
          "total_tokens": 164,
          "completion_tokens_details": {
            "accepted_prediction_tokens": 0,
            "audio_tokens": 0,
            "reasoning_tokens": 0,
            "rejected_prediction_tokens": 0
          },
          "prompt_tokens_details": {
            "audio_tokens": 0,
            "cached_tokens": 0
          }
        },
        "model_provider": "openai",
        "model_name": "gpt-4o-mini-2024-07-18",
        "system_fingerprint": "fp_2d82c05f26",
        "id": "chatcmpl-DCmsjiUnvfrUawEJ1DgtfssCHUK6F",
        "service_tier": "default",
        "finish_reason": "tool_calls",
        "logprobs": null
      },
      "type": "ai",
      "name": null,
      "id": "lc_run--019c8fdd-e054-70b1-a378-65ce96441420-0",
      "tool_calls": [
        {
          "name": "process_refund",
          "args": {
            "order_id": "id12",
            "amount": 80
          },
          "id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
          "type": "tool_call"
        }
      ],
      "invalid_tool_calls": [],
      "usage_metadata": {
        "input_tokens": 143,
        "output_tokens": 21,
        "total_tokens": 164,
        "input_token_details": {
          "audio": 0,
          "cache_read": 0
        },
        "output_token_details": {
          "audio": 0,
          "reasoning": 0
        }
      }
    },
    {
      "content": "Refund of $80.0 for order id12 processed successfully.",
      "additional_kwargs": {},
      "response_metadata": {},
      "type": "tool",
      "name": "process_refund",
      "id": "de3a1d18-d85b-4be1-a46e-ae78c71aaad2",
      "tool_call_id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
      "artifact": null,
      "status": "success"
    },
    {
      "content": "The refund of $80 for order ID **id12** has been processed successfully.",
      "additional_kwargs": {
        "refusal": null
      },
      "response_metadata": {
        "token_usage": {
          "completion_tokens": 18,
          "prompt_tokens": 186,
          "total_tokens": 204,
          "completion_tokens_details": {
            "accepted_prediction_tokens": 0,
            "audio_tokens": 0,
            "reasoning_tokens": 0,
            "rejected_prediction_tokens": 0
          },
          "prompt_tokens_details": {
            "audio_tokens": 0,
            "cached_tokens": 0
          }
        },
        "model_provider": "openai",
        "model_name": "gpt-4o-mini-2024-07-18",
        "system_fingerprint": "fp_2d82c05f26",
        "id": "chatcmpl-DCmslzsmfA4Dl8g5i2JX6v27adnyL",
        "service_tier": "default",
        "finish_reason": "stop",
        "logprobs": null
      },
      "type": "ai",
      "name": null,
      "id": "lc_run--019c8fdd-e6d7-7cb2-981f-76c0e831c0b2-0",
      "tool_calls": [],
      "invalid_tool_calls": [],
      "usage_metadata": {
        "input_tokens": 186,
        "output_tokens": 18,
        "total_tokens": 204,
        "input_token_details": {
          "audio": 0,
          "cache_read": 0
        },
        "output_token_details": {
          "audio": 0,
          "reasoning": 0
        }
      }
    }
  ],
  "order_id": "123",
  "amount": 1
}
```

## After Refund completed

```

{
  "thread_id": "user_136",
  "count": 5,
  "checkpoints": [
    {
      "checkpoint_id": "1f11185e-072e-6150-8003-4669bd2efd02",
      "parent_checkpoint_id": "1f11185d-f8a7-62bc-8002-a452e6fab347",
      "checkpoint": {
        "v": 4,
        "ts": "2026-02-24T13:36:51.914369+00:00",
        "id": "1f11185e-072e-6150-8003-4669bd2efd02",
        "channel_values": {
          "messages": [
            {
              "content": "Can you refund my id12 cost is $80",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "human",
              "name": null,
              "id": "20dcb597-a606-4672-b940-13cd71affa0d"
            },
            {
              "content": "",
              "additional_kwargs": {
                "refusal": null
              },
              "response_metadata": {
                "token_usage": {
                  "completion_tokens": 21,
                  "prompt_tokens": 143,
                  "total_tokens": 164,
                  "completion_tokens_details": {
                    "accepted_prediction_tokens": 0,
                    "audio_tokens": 0,
                    "reasoning_tokens": 0,
                    "rejected_prediction_tokens": 0
                  },
                  "prompt_tokens_details": {
                    "audio_tokens": 0,
                    "cached_tokens": 0
                  }
                },
                "model_provider": "openai",
                "model_name": "gpt-4o-mini-2024-07-18",
                "system_fingerprint": "fp_2d82c05f26",
                "id": "chatcmpl-DCmsjiUnvfrUawEJ1DgtfssCHUK6F",
                "service_tier": "default",
                "finish_reason": "tool_calls",
                "logprobs": null
              },
              "type": "ai",
              "name": null,
              "id": "lc_run--019c8fdd-e054-70b1-a378-65ce96441420-0",
              "tool_calls": [
                {
                  "name": "process_refund",
                  "args": {
                    "order_id": "id12",
                    "amount": 80
                  },
                  "id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
                  "type": "tool_call"
                }
              ],
              "invalid_tool_calls": [],
              "usage_metadata": {
                "input_tokens": 143,
                "output_tokens": 21,
                "total_tokens": 164,
                "input_token_details": {
                  "audio": 0,
                  "cache_read": 0
                },
                "output_token_details": {
                  "audio": 0,
                  "reasoning": 0
                }
              }
            },
            {
              "content": "Refund of $80.0 for order id12 processed successfully.",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "tool",
              "name": "process_refund",
              "id": "de3a1d18-d85b-4be1-a46e-ae78c71aaad2",
              "tool_call_id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
              "artifact": null,
              "status": "success"
            },
            {
              "content": "The refund of $80 for order ID **id12** has been processed successfully.",
              "additional_kwargs": {
                "refusal": null
              },
              "response_metadata": {
                "token_usage": {
                  "completion_tokens": 18,
                  "prompt_tokens": 186,
                  "total_tokens": 204,
                  "completion_tokens_details": {
                    "accepted_prediction_tokens": 0,
                    "audio_tokens": 0,
                    "reasoning_tokens": 0,
                    "rejected_prediction_tokens": 0
                  },
                  "prompt_tokens_details": {
                    "audio_tokens": 0,
                    "cached_tokens": 0
                  }
                },
                "model_provider": "openai",
                "model_name": "gpt-4o-mini-2024-07-18",
                "system_fingerprint": "fp_2d82c05f26",
                "id": "chatcmpl-DCmslzsmfA4Dl8g5i2JX6v27adnyL",
                "service_tier": "default",
                "finish_reason": "stop",
                "logprobs": null
              },
              "type": "ai",
              "name": null,
              "id": "lc_run--019c8fdd-e6d7-7cb2-981f-76c0e831c0b2-0",
              "tool_calls": [],
              "invalid_tool_calls": [],
              "usage_metadata": {
                "input_tokens": 186,
                "output_tokens": 18,
                "total_tokens": 204,
                "input_token_details": {
                  "audio": 0,
                  "cache_read": 0
                },
                "output_token_details": {
                  "audio": 0,
                  "reasoning": 0
                }
              }
            }
          ],
          "order_id": "123",
          "amount": 1
        },
        "channel_versions": {
          "__start__": 2,
          "messages": 5,
          "order_id": 2,
          "amount": 2,
          "branch:to:support_agent": 5,
          "branch:to:tools": 4
        },
        "versions_seen": {
          "__input__": {},
          "__start__": {
            "__start__": 1
          },
          "support_agent": {
            "branch:to:support_agent": 4
          },
          "tools": {
            "branch:to:tools": 3
          }
        },
        "updated_channels": [
          "messages"
        ]
      },
      "metadata": {
        "source": "loop",
        "step": 3,
        "parents": {}
      }
    },
    {
      "checkpoint_id": "1f11185d-f8a7-62bc-8002-a452e6fab347",
      "parent_checkpoint_id": "1f11185d-f8a2-6eba-8001-a125446c7b73",
      "checkpoint": {
        "v": 4,
        "ts": "2026-02-24T13:36:50.391104+00:00",
        "id": "1f11185d-f8a7-62bc-8002-a452e6fab347",
        "channel_values": {
          "messages": [
            {
              "content": "Can you refund my id12 cost is $80",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "human",
              "name": null,
              "id": "20dcb597-a606-4672-b940-13cd71affa0d"
            },
            {
              "content": "",
              "additional_kwargs": {
                "refusal": null
              },
              "response_metadata": {
                "token_usage": {
                  "completion_tokens": 21,
                  "prompt_tokens": 143,
                  "total_tokens": 164,
                  "completion_tokens_details": {
                    "accepted_prediction_tokens": 0,
                    "audio_tokens": 0,
                    "reasoning_tokens": 0,
                    "rejected_prediction_tokens": 0
                  },
                  "prompt_tokens_details": {
                    "audio_tokens": 0,
                    "cached_tokens": 0
                  }
                },
                "model_provider": "openai",
                "model_name": "gpt-4o-mini-2024-07-18",
                "system_fingerprint": "fp_2d82c05f26",
                "id": "chatcmpl-DCmsjiUnvfrUawEJ1DgtfssCHUK6F",
                "service_tier": "default",
                "finish_reason": "tool_calls",
                "logprobs": null
              },
              "type": "ai",
              "name": null,
              "id": "lc_run--019c8fdd-e054-70b1-a378-65ce96441420-0",
              "tool_calls": [
                {
                  "name": "process_refund",
                  "args": {
                    "order_id": "id12",
                    "amount": 80
                  },
                  "id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
                  "type": "tool_call"
                }
              ],
              "invalid_tool_calls": [],
              "usage_metadata": {
                "input_tokens": 143,
                "output_tokens": 21,
                "total_tokens": 164,
                "input_token_details": {
                  "audio": 0,
                  "cache_read": 0
                },
                "output_token_details": {
                  "audio": 0,
                  "reasoning": 0
                }
              }
            },
            {
              "content": "Refund of $80.0 for order id12 processed successfully.",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "tool",
              "name": "process_refund",
              "id": "de3a1d18-d85b-4be1-a46e-ae78c71aaad2",
              "tool_call_id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
              "artifact": null,
              "status": "success"
            }
          ],
          "order_id": "123",
          "amount": 1,
          "branch:to:support_agent": null
        },
        "channel_versions": {
          "__start__": 2,
          "messages": 4,
          "order_id": 2,
          "amount": 2,
          "branch:to:support_agent": 4,
          "branch:to:tools": 4
        },
        "versions_seen": {
          "__input__": {},
          "__start__": {
            "__start__": 1
          },
          "support_agent": {
            "branch:to:support_agent": 2
          },
          "tools": {
            "branch:to:tools": 3
          }
        },
        "updated_channels": [
          "branch:to:support_agent",
          "messages"
        ]
      },
      "metadata": {
        "source": "loop",
        "step": 2,
        "parents": {}
      }
    },
    {
      "checkpoint_id": "1f11185d-f8a2-6eba-8001-a125446c7b73",
      "parent_checkpoint_id": "1f11185d-e8c0-6f56-8000-5d5a956ae500",
      "checkpoint": {
        "v": 4,
        "ts": "2026-02-24T13:36:50.389362+00:00",
        "id": "1f11185d-f8a2-6eba-8001-a125446c7b73",
        "channel_values": {
          "messages": [
            {
              "content": "Can you refund my id12 cost is $80",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "human",
              "name": null,
              "id": "20dcb597-a606-4672-b940-13cd71affa0d"
            },
            {
              "content": "",
              "additional_kwargs": {
                "refusal": null
              },
              "response_metadata": {
                "token_usage": {
                  "completion_tokens": 21,
                  "prompt_tokens": 143,
                  "total_tokens": 164,
                  "completion_tokens_details": {
                    "accepted_prediction_tokens": 0,
                    "audio_tokens": 0,
                    "reasoning_tokens": 0,
                    "rejected_prediction_tokens": 0
                  },
                  "prompt_tokens_details": {
                    "audio_tokens": 0,
                    "cached_tokens": 0
                  }
                },
                "model_provider": "openai",
                "model_name": "gpt-4o-mini-2024-07-18",
                "system_fingerprint": "fp_2d82c05f26",
                "id": "chatcmpl-DCmsjiUnvfrUawEJ1DgtfssCHUK6F",
                "service_tier": "default",
                "finish_reason": "tool_calls",
                "logprobs": null
              },
              "type": "ai",
              "name": null,
              "id": "lc_run--019c8fdd-e054-70b1-a378-65ce96441420-0",
              "tool_calls": [
                {
                  "name": "process_refund",
                  "args": {
                    "order_id": "id12",
                    "amount": 80
                  },
                  "id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
                  "type": "tool_call"
                }
              ],
              "invalid_tool_calls": [],
              "usage_metadata": {
                "input_tokens": 143,
                "output_tokens": 21,
                "total_tokens": 164,
                "input_token_details": {
                  "audio": 0,
                  "cache_read": 0
                },
                "output_token_details": {
                  "audio": 0,
                  "reasoning": 0
                }
              }
            }
          ],
          "order_id": "123",
          "amount": 1,
          "branch:to:tools": null
        },
        "channel_versions": {
          "__start__": 2,
          "messages": 3,
          "order_id": 2,
          "amount": 2,
          "branch:to:support_agent": 3,
          "branch:to:tools": 3
        },
        "versions_seen": {
          "__input__": {},
          "__start__": {
            "__start__": 1
          },
          "support_agent": {
            "branch:to:support_agent": 2
          }
        },
        "updated_channels": [
          "branch:to:tools",
          "messages"
        ]
      },
      "metadata": {
        "source": "loop",
        "step": 1,
        "parents": {}
      }
    },
    {
      "checkpoint_id": "1f11185d-e8c0-6f56-8000-5d5a956ae500",
      "parent_checkpoint_id": "1f11185d-e8be-65ee-bfff-576127f646bd",
      "checkpoint": {
        "v": 4,
        "ts": "2026-02-24T13:36:48.723938+00:00",
        "id": "1f11185d-e8c0-6f56-8000-5d5a956ae500",
        "channel_values": {
          "messages": [
            {
              "content": "Can you refund my id12 cost is $80",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "human",
              "name": null,
              "id": "20dcb597-a606-4672-b940-13cd71affa0d"
            }
          ],
          "order_id": "123",
          "amount": 1,
          "branch:to:support_agent": null
        },
        "channel_versions": {
          "__start__": 2,
          "messages": 2,
          "order_id": 2,
          "amount": 2,
          "branch:to:support_agent": 2
        },
        "versions_seen": {
          "__input__": {},
          "__start__": {
            "__start__": 1
          }
        },
        "updated_channels": [
          "amount",
          "branch:to:support_agent",
          "messages",
          "order_id"
        ]
      },
      "metadata": {
        "source": "loop",
        "step": 0,
        "parents": {}
      }
    },
    {
      "checkpoint_id": "1f11185d-e8be-65ee-bfff-576127f646bd",
      "parent_checkpoint_id": null,
      "checkpoint": {
        "v": 4,
        "ts": "2026-02-24T13:36:48.722882+00:00",
        "id": "1f11185d-e8be-65ee-bfff-576127f646bd",
        "channel_values": {
          "__start__": {
            "messages": [
              {
                "content": "Can you refund my id12 cost is $80",
                "additional_kwargs": {},
                "response_metadata": {},
                "type": "human",
                "name": null,
                "id": "20dcb597-a606-4672-b940-13cd71affa0d"
              }
            ],
            "order_id": "123",
            "amount": 1
          }
        },
        "channel_versions": {
          "__start__": 1
        },
        "versions_seen": {
          "__input__": {}
        },
        "updated_channels": [
          "__start__"
        ]
      },
      "metadata": {
        "source": "input",
        "step": -1,
        "parents": {}
      }
    }
  ]
}
```



# Before Refound 

This is actually normal behavior for LangGraph! Each checkpoint represents a snapshot of the graph state after each node execution in the workflow. Here's what happened with your refund request:

Checkpoint Progression:

Step -1 (Input): Initial user message received
Step 0 (START node): Graph initialization
Step 1 (support_agent): LLM generates tool call for process_refund
Step 2 (tools node): Tool executes and returns result
Step 3 (support_agent): LLM generates final response
Each checkpoint saves:

The full conversation history (messages)
Current state (order_id, amount)
Node execution branching information
Metadata (what node executed, step number)
Why this is useful:

✅ Persistence - If the server crashes, you can resume from the last checkpoint
✅ Debugging - Inspect state at any step
✅ Human-in-the-loop - Pause execution and let humans decide next steps
✅ Auditability - Full execution trace stored
✅ Replay - Run the exact same conversation path again

```
{
  "thread_id": "user_136",
  "count": 5,
  "checkpoints": [
    {
      "checkpoint_id": "1f11185e-072e-6150-8003-4669bd2efd02",
      "parent_checkpoint_id": "1f11185d-f8a7-62bc-8002-a452e6fab347",
      "checkpoint": {
        "v": 4,
        "ts": "2026-02-24T13:36:51.914369+00:00",
        "id": "1f11185e-072e-6150-8003-4669bd2efd02",
        "channel_values": {
          "messages": [
            {
              "content": "Can you refund my id12 cost is $80",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "human",
              "name": null,
              "id": "20dcb597-a606-4672-b940-13cd71affa0d"
            },
            {
              "content": "",
              "additional_kwargs": {
                "refusal": null
              },
              "response_metadata": {
                "token_usage": {
                  "completion_tokens": 21,
                  "prompt_tokens": 143,
                  "total_tokens": 164,
                  "completion_tokens_details": {
                    "accepted_prediction_tokens": 0,
                    "audio_tokens": 0,
                    "reasoning_tokens": 0,
                    "rejected_prediction_tokens": 0
                  },
                  "prompt_tokens_details": {
                    "audio_tokens": 0,
                    "cached_tokens": 0
                  }
                },
                "model_provider": "openai",
                "model_name": "gpt-4o-mini-2024-07-18",
                "system_fingerprint": "fp_2d82c05f26",
                "id": "chatcmpl-DCmsjiUnvfrUawEJ1DgtfssCHUK6F",
                "service_tier": "default",
                "finish_reason": "tool_calls",
                "logprobs": null
              },
              "type": "ai",
              "name": null,
              "id": "lc_run--019c8fdd-e054-70b1-a378-65ce96441420-0",
              "tool_calls": [
                {
                  "name": "process_refund",
                  "args": {
                    "order_id": "id12",
                    "amount": 80
                  },
                  "id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
                  "type": "tool_call"
                }
              ],
              "invalid_tool_calls": [],
              "usage_metadata": {
                "input_tokens": 143,
                "output_tokens": 21,
                "total_tokens": 164,
                "input_token_details": {
                  "audio": 0,
                  "cache_read": 0
                },
                "output_token_details": {
                  "audio": 0,
                  "reasoning": 0
                }
              }
            },
            {
              "content": "Refund of $80.0 for order id12 processed successfully.",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "tool",
              "name": "process_refund",
              "id": "de3a1d18-d85b-4be1-a46e-ae78c71aaad2",
              "tool_call_id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
              "artifact": null,
              "status": "success"
            },
            {
              "content": "The refund of $80 for order ID **id12** has been processed successfully.",
              "additional_kwargs": {
                "refusal": null
              },
              "response_metadata": {
                "token_usage": {
                  "completion_tokens": 18,
                  "prompt_tokens": 186,
                  "total_tokens": 204,
                  "completion_tokens_details": {
                    "accepted_prediction_tokens": 0,
                    "audio_tokens": 0,
                    "reasoning_tokens": 0,
                    "rejected_prediction_tokens": 0
                  },
                  "prompt_tokens_details": {
                    "audio_tokens": 0,
                    "cached_tokens": 0
                  }
                },
                "model_provider": "openai",
                "model_name": "gpt-4o-mini-2024-07-18",
                "system_fingerprint": "fp_2d82c05f26",
                "id": "chatcmpl-DCmslzsmfA4Dl8g5i2JX6v27adnyL",
                "service_tier": "default",
                "finish_reason": "stop",
                "logprobs": null
              },
              "type": "ai",
              "name": null,
              "id": "lc_run--019c8fdd-e6d7-7cb2-981f-76c0e831c0b2-0",
              "tool_calls": [],
              "invalid_tool_calls": [],
              "usage_metadata": {
                "input_tokens": 186,
                "output_tokens": 18,
                "total_tokens": 204,
                "input_token_details": {
                  "audio": 0,
                  "cache_read": 0
                },
                "output_token_details": {
                  "audio": 0,
                  "reasoning": 0
                }
              }
            }
          ],
          "order_id": "123",
          "amount": 1
        },
        "channel_versions": {
          "__start__": 2,
          "messages": 5,
          "order_id": 2,
          "amount": 2,
          "branch:to:support_agent": 5,
          "branch:to:tools": 4
        },
        "versions_seen": {
          "__input__": {},
          "__start__": {
            "__start__": 1
          },
          "support_agent": {
            "branch:to:support_agent": 4
          },
          "tools": {
            "branch:to:tools": 3
          }
        },
        "updated_channels": [
          "messages"
        ]
      },
      "metadata": {
        "source": "loop",
        "step": 3,
        "parents": {}
      }
    },
    {
      "checkpoint_id": "1f11185d-f8a7-62bc-8002-a452e6fab347",
      "parent_checkpoint_id": "1f11185d-f8a2-6eba-8001-a125446c7b73",
      "checkpoint": {
        "v": 4,
        "ts": "2026-02-24T13:36:50.391104+00:00",
        "id": "1f11185d-f8a7-62bc-8002-a452e6fab347",
        "channel_values": {
          "messages": [
            {
              "content": "Can you refund my id12 cost is $80",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "human",
              "name": null,
              "id": "20dcb597-a606-4672-b940-13cd71affa0d"
            },
            {
              "content": "",
              "additional_kwargs": {
                "refusal": null
              },
              "response_metadata": {
                "token_usage": {
                  "completion_tokens": 21,
                  "prompt_tokens": 143,
                  "total_tokens": 164,
                  "completion_tokens_details": {
                    "accepted_prediction_tokens": 0,
                    "audio_tokens": 0,
                    "reasoning_tokens": 0,
                    "rejected_prediction_tokens": 0
                  },
                  "prompt_tokens_details": {
                    "audio_tokens": 0,
                    "cached_tokens": 0
                  }
                },
                "model_provider": "openai",
                "model_name": "gpt-4o-mini-2024-07-18",
                "system_fingerprint": "fp_2d82c05f26",
                "id": "chatcmpl-DCmsjiUnvfrUawEJ1DgtfssCHUK6F",
                "service_tier": "default",
                "finish_reason": "tool_calls",
                "logprobs": null
              },
              "type": "ai",
              "name": null,
              "id": "lc_run--019c8fdd-e054-70b1-a378-65ce96441420-0",
              "tool_calls": [
                {
                  "name": "process_refund",
                  "args": {
                    "order_id": "id12",
                    "amount": 80
                  },
                  "id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
                  "type": "tool_call"
                }
              ],
              "invalid_tool_calls": [],
              "usage_metadata": {
                "input_tokens": 143,
                "output_tokens": 21,
                "total_tokens": 164,
                "input_token_details": {
                  "audio": 0,
                  "cache_read": 0
                },
                "output_token_details": {
                  "audio": 0,
                  "reasoning": 0
                }
              }
            },
            {
              "content": "Refund of $80.0 for order id12 processed successfully.",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "tool",
              "name": "process_refund",
              "id": "de3a1d18-d85b-4be1-a46e-ae78c71aaad2",
              "tool_call_id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
              "artifact": null,
              "status": "success"
            }
          ],
          "order_id": "123",
          "amount": 1,
          "branch:to:support_agent": null
        },
        "channel_versions": {
          "__start__": 2,
          "messages": 4,
          "order_id": 2,
          "amount": 2,
          "branch:to:support_agent": 4,
          "branch:to:tools": 4
        },
        "versions_seen": {
          "__input__": {},
          "__start__": {
            "__start__": 1
          },
          "support_agent": {
            "branch:to:support_agent": 2
          },
          "tools": {
            "branch:to:tools": 3
          }
        },
        "updated_channels": [
          "branch:to:support_agent",
          "messages"
        ]
      },
      "metadata": {
        "source": "loop",
        "step": 2,
        "parents": {}
      }
    },
    {
      "checkpoint_id": "1f11185d-f8a2-6eba-8001-a125446c7b73",
      "parent_checkpoint_id": "1f11185d-e8c0-6f56-8000-5d5a956ae500",
      "checkpoint": {
        "v": 4,
        "ts": "2026-02-24T13:36:50.389362+00:00",
        "id": "1f11185d-f8a2-6eba-8001-a125446c7b73",
        "channel_values": {
          "messages": [
            {
              "content": "Can you refund my id12 cost is $80",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "human",
              "name": null,
              "id": "20dcb597-a606-4672-b940-13cd71affa0d"
            },
            {
              "content": "",
              "additional_kwargs": {
                "refusal": null
              },
              "response_metadata": {
                "token_usage": {
                  "completion_tokens": 21,
                  "prompt_tokens": 143,
                  "total_tokens": 164,
                  "completion_tokens_details": {
                    "accepted_prediction_tokens": 0,
                    "audio_tokens": 0,
                    "reasoning_tokens": 0,
                    "rejected_prediction_tokens": 0
                  },
                  "prompt_tokens_details": {
                    "audio_tokens": 0,
                    "cached_tokens": 0
                  }
                },
                "model_provider": "openai",
                "model_name": "gpt-4o-mini-2024-07-18",
                "system_fingerprint": "fp_2d82c05f26",
                "id": "chatcmpl-DCmsjiUnvfrUawEJ1DgtfssCHUK6F",
                "service_tier": "default",
                "finish_reason": "tool_calls",
                "logprobs": null
              },
              "type": "ai",
              "name": null,
              "id": "lc_run--019c8fdd-e054-70b1-a378-65ce96441420-0",
              "tool_calls": [
                {
                  "name": "process_refund",
                  "args": {
                    "order_id": "id12",
                    "amount": 80
                  },
                  "id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
                  "type": "tool_call"
                }
              ],
              "invalid_tool_calls": [],
              "usage_metadata": {
                "input_tokens": 143,
                "output_tokens": 21,
                "total_tokens": 164,
                "input_token_details": {
                  "audio": 0,
                  "cache_read": 0
                },
                "output_token_details": {
                  "audio": 0,
                  "reasoning": 0
                }
              }
            }
          ],
          "order_id": "123",
          "amount": 1,
          "branch:to:tools": null
        },
        "channel_versions": {
          "__start__": 2,
          "messages": 3,
          "order_id": 2,
          "amount": 2,
          "branch:to:support_agent": 3,
          "branch:to:tools": 3
        },
        "versions_seen": {
          "__input__": {},
          "__start__": {
            "__start__": 1
          },
          "support_agent": {
            "branch:to:support_agent": 2
          }
        },
        "updated_channels": [
          "branch:to:tools",
          "messages"
        ]
      },
      "metadata": {
        "source": "loop",
        "step": 1,
        "parents": {}
      }
    },
    {
      "checkpoint_id": "1f11185d-e8c0-6f56-8000-5d5a956ae500",
      "parent_checkpoint_id": "1f11185d-e8be-65ee-bfff-576127f646bd",
      "checkpoint": {
        "v": 4,
        "ts": "2026-02-24T13:36:48.723938+00:00",
        "id": "1f11185d-e8c0-6f56-8000-5d5a956ae500",
        "channel_values": {
          "messages": [
            {
              "content": "Can you refund my id12 cost is $80",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "human",
              "name": null,
              "id": "20dcb597-a606-4672-b940-13cd71affa0d"
            }
          ],
          "order_id": "123",
          "amount": 1,
          "branch:to:support_agent": null
        },
        "channel_versions": {
          "__start__": 2,
          "messages": 2,
          "order_id": 2,
          "amount": 2,
          "branch:to:support_agent": 2
        },
        "versions_seen": {
          "__input__": {},
          "__start__": {
            "__start__": 1
          }
        },
        "updated_channels": [
          "amount",
          "branch:to:support_agent",
          "messages",
          "order_id"
        ]
      },
      "metadata": {
        "source": "loop",
        "step": 0,
        "parents": {}
      }
    },
    {
      "checkpoint_id": "1f11185d-e8be-65ee-bfff-576127f646bd",
      "parent_checkpoint_id": null,
      "checkpoint": {
        "v": 4,
        "ts": "2026-02-24T13:36:48.722882+00:00",
        "id": "1f11185d-e8be-65ee-bfff-576127f646bd",
        "channel_values": {
          "__start__": {
            "messages": [
              {
                "content": "Can you refund my id12 cost is $80",
                "additional_kwargs": {},
                "response_metadata": {},
                "type": "human",
                "name": null,
                "id": "20dcb597-a606-4672-b940-13cd71affa0d"
              }
            ],
            "order_id": "123",
            "amount": 1
          }
        },
        "channel_versions": {
          "__start__": 1
        },
        "versions_seen": {
          "__input__": {}
        },
        "updated_channels": [
          "__start__"
        ]
      },
      "metadata": {
        "source": "input",
        "step": -1,
        "parents": {}
      }
    }
  ]
}

```

# After Checkpoint approaval completed now

# Refund Response
```
{
  "messages": [
    {
      "content": "Can you refund my id12 cost is $80",
      "additional_kwargs": {},
      "response_metadata": {},
      "type": "human",
      "name": null,
      "id": "20dcb597-a606-4672-b940-13cd71affa0d"
    },
    {
      "content": "",
      "additional_kwargs": {
        "refusal": null
      },
      "response_metadata": {
        "token_usage": {
          "completion_tokens": 21,
          "prompt_tokens": 143,
          "total_tokens": 164,
          "completion_tokens_details": {
            "accepted_prediction_tokens": 0,
            "audio_tokens": 0,
            "reasoning_tokens": 0,
            "rejected_prediction_tokens": 0
          },
          "prompt_tokens_details": {
            "audio_tokens": 0,
            "cached_tokens": 0
          }
        },
        "model_provider": "openai",
        "model_name": "gpt-4o-mini-2024-07-18",
        "system_fingerprint": "fp_2d82c05f26",
        "id": "chatcmpl-DCmsjiUnvfrUawEJ1DgtfssCHUK6F",
        "service_tier": "default",
        "finish_reason": "tool_calls",
        "logprobs": null
      },
      "type": "ai",
      "name": null,
      "id": "lc_run--019c8fdd-e054-70b1-a378-65ce96441420-0",
      "tool_calls": [
        {
          "name": "process_refund",
          "args": {
            "order_id": "id12",
            "amount": 80
          },
          "id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
          "type": "tool_call"
        }
      ],
      "invalid_tool_calls": [],
      "usage_metadata": {
        "input_tokens": 143,
        "output_tokens": 21,
        "total_tokens": 164,
        "input_token_details": {
          "audio": 0,
          "cache_read": 0
        },
        "output_token_details": {
          "audio": 0,
          "reasoning": 0
        }
      }
    },
    {
      "content": "Refund of $80.0 for order id12 processed successfully.",
      "additional_kwargs": {},
      "response_metadata": {},
      "type": "tool",
      "name": "process_refund",
      "id": "de3a1d18-d85b-4be1-a46e-ae78c71aaad2",
      "tool_call_id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
      "artifact": null,
      "status": "success"
    },
    {
      "content": "The refund of $80 for order ID **id12** has been processed successfully.",
      "additional_kwargs": {
        "refusal": null
      },
      "response_metadata": {
        "token_usage": {
          "completion_tokens": 18,
          "prompt_tokens": 186,
          "total_tokens": 204,
          "completion_tokens_details": {
            "accepted_prediction_tokens": 0,
            "audio_tokens": 0,
            "reasoning_tokens": 0,
            "rejected_prediction_tokens": 0
          },
          "prompt_tokens_details": {
            "audio_tokens": 0,
            "cached_tokens": 0
          }
        },
        "model_provider": "openai",
        "model_name": "gpt-4o-mini-2024-07-18",
        "system_fingerprint": "fp_2d82c05f26",
        "id": "chatcmpl-DCmslzsmfA4Dl8g5i2JX6v27adnyL",
        "service_tier": "default",
        "finish_reason": "stop",
        "logprobs": null
      },
      "type": "ai",
      "name": null,
      "id": "lc_run--019c8fdd-e6d7-7cb2-981f-76c0e831c0b2-0",
      "tool_calls": [],
      "invalid_tool_calls": [],
      "usage_metadata": {
        "input_tokens": 186,
        "output_tokens": 18,
        "total_tokens": 204,
        "input_token_details": {
          "audio": 0,
          "cache_read": 0
        },
        "output_token_details": {
          "audio": 0,
          "reasoning": 0
        }
      }
    }
  ],
  "order_id": "123",
  "amount": 1
}
```

## After Refund completed

```

{
  "thread_id": "user_136",
  "count": 5,
  "checkpoints": [
    {
      "checkpoint_id": "1f11185e-072e-6150-8003-4669bd2efd02",
      "parent_checkpoint_id": "1f11185d-f8a7-62bc-8002-a452e6fab347",
      "checkpoint": {
        "v": 4,
        "ts": "2026-02-24T13:36:51.914369+00:00",
        "id": "1f11185e-072e-6150-8003-4669bd2efd02",
        "channel_values": {
          "messages": [
            {
              "content": "Can you refund my id12 cost is $80",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "human",
              "name": null,
              "id": "20dcb597-a606-4672-b940-13cd71affa0d"
            },
            {
              "content": "",
              "additional_kwargs": {
                "refusal": null
              },
              "response_metadata": {
                "token_usage": {
                  "completion_tokens": 21,
                  "prompt_tokens": 143,
                  "total_tokens": 164,
                  "completion_tokens_details": {
                    "accepted_prediction_tokens": 0,
                    "audio_tokens": 0,
                    "reasoning_tokens": 0,
                    "rejected_prediction_tokens": 0
                  },
                  "prompt_tokens_details": {
                    "audio_tokens": 0,
                    "cached_tokens": 0
                  }
                },
                "model_provider": "openai",
                "model_name": "gpt-4o-mini-2024-07-18",
                "system_fingerprint": "fp_2d82c05f26",
                "id": "chatcmpl-DCmsjiUnvfrUawEJ1DgtfssCHUK6F",
                "service_tier": "default",
                "finish_reason": "tool_calls",
                "logprobs": null
              },
              "type": "ai",
              "name": null,
              "id": "lc_run--019c8fdd-e054-70b1-a378-65ce96441420-0",
              "tool_calls": [
                {
                  "name": "process_refund",
                  "args": {
                    "order_id": "id12",
                    "amount": 80
                  },
                  "id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
                  "type": "tool_call"
                }
              ],
              "invalid_tool_calls": [],
              "usage_metadata": {
                "input_tokens": 143,
                "output_tokens": 21,
                "total_tokens": 164,
                "input_token_details": {
                  "audio": 0,
                  "cache_read": 0
                },
                "output_token_details": {
                  "audio": 0,
                  "reasoning": 0
                }
              }
            },
            {
              "content": "Refund of $80.0 for order id12 processed successfully.",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "tool",
              "name": "process_refund",
              "id": "de3a1d18-d85b-4be1-a46e-ae78c71aaad2",
              "tool_call_id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
              "artifact": null,
              "status": "success"
            },
            {
              "content": "The refund of $80 for order ID **id12** has been processed successfully.",
              "additional_kwargs": {
                "refusal": null
              },
              "response_metadata": {
                "token_usage": {
                  "completion_tokens": 18,
                  "prompt_tokens": 186,
                  "total_tokens": 204,
                  "completion_tokens_details": {
                    "accepted_prediction_tokens": 0,
                    "audio_tokens": 0,
                    "reasoning_tokens": 0,
                    "rejected_prediction_tokens": 0
                  },
                  "prompt_tokens_details": {
                    "audio_tokens": 0,
                    "cached_tokens": 0
                  }
                },
                "model_provider": "openai",
                "model_name": "gpt-4o-mini-2024-07-18",
                "system_fingerprint": "fp_2d82c05f26",
                "id": "chatcmpl-DCmslzsmfA4Dl8g5i2JX6v27adnyL",
                "service_tier": "default",
                "finish_reason": "stop",
                "logprobs": null
              },
              "type": "ai",
              "name": null,
              "id": "lc_run--019c8fdd-e6d7-7cb2-981f-76c0e831c0b2-0",
              "tool_calls": [],
              "invalid_tool_calls": [],
              "usage_metadata": {
                "input_tokens": 186,
                "output_tokens": 18,
                "total_tokens": 204,
                "input_token_details": {
                  "audio": 0,
                  "cache_read": 0
                },
                "output_token_details": {
                  "audio": 0,
                  "reasoning": 0
                }
              }
            }
          ],
          "order_id": "123",
          "amount": 1
        },
        "channel_versions": {
          "__start__": 2,
          "messages": 5,
          "order_id": 2,
          "amount": 2,
          "branch:to:support_agent": 5,
          "branch:to:tools": 4
        },
        "versions_seen": {
          "__input__": {},
          "__start__": {
            "__start__": 1
          },
          "support_agent": {
            "branch:to:support_agent": 4
          },
          "tools": {
            "branch:to:tools": 3
          }
        },
        "updated_channels": [
          "messages"
        ]
      },
      "metadata": {
        "source": "loop",
        "step": 3,
        "parents": {}
      }
    },
    {
      "checkpoint_id": "1f11185d-f8a7-62bc-8002-a452e6fab347",
      "parent_checkpoint_id": "1f11185d-f8a2-6eba-8001-a125446c7b73",
      "checkpoint": {
        "v": 4,
        "ts": "2026-02-24T13:36:50.391104+00:00",
        "id": "1f11185d-f8a7-62bc-8002-a452e6fab347",
        "channel_values": {
          "messages": [
            {
              "content": "Can you refund my id12 cost is $80",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "human",
              "name": null,
              "id": "20dcb597-a606-4672-b940-13cd71affa0d"
            },
            {
              "content": "",
              "additional_kwargs": {
                "refusal": null
              },
              "response_metadata": {
                "token_usage": {
                  "completion_tokens": 21,
                  "prompt_tokens": 143,
                  "total_tokens": 164,
                  "completion_tokens_details": {
                    "accepted_prediction_tokens": 0,
                    "audio_tokens": 0,
                    "reasoning_tokens": 0,
                    "rejected_prediction_tokens": 0
                  },
                  "prompt_tokens_details": {
                    "audio_tokens": 0,
                    "cached_tokens": 0
                  }
                },
                "model_provider": "openai",
                "model_name": "gpt-4o-mini-2024-07-18",
                "system_fingerprint": "fp_2d82c05f26",
                "id": "chatcmpl-DCmsjiUnvfrUawEJ1DgtfssCHUK6F",
                "service_tier": "default",
                "finish_reason": "tool_calls",
                "logprobs": null
              },
              "type": "ai",
              "name": null,
              "id": "lc_run--019c8fdd-e054-70b1-a378-65ce96441420-0",
              "tool_calls": [
                {
                  "name": "process_refund",
                  "args": {
                    "order_id": "id12",
                    "amount": 80
                  },
                  "id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
                  "type": "tool_call"
                }
              ],
              "invalid_tool_calls": [],
              "usage_metadata": {
                "input_tokens": 143,
                "output_tokens": 21,
                "total_tokens": 164,
                "input_token_details": {
                  "audio": 0,
                  "cache_read": 0
                },
                "output_token_details": {
                  "audio": 0,
                  "reasoning": 0
                }
              }
            },
            {
              "content": "Refund of $80.0 for order id12 processed successfully.",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "tool",
              "name": "process_refund",
              "id": "de3a1d18-d85b-4be1-a46e-ae78c71aaad2",
              "tool_call_id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
              "artifact": null,
              "status": "success"
            }
          ],
          "order_id": "123",
          "amount": 1,
          "branch:to:support_agent": null
        },
        "channel_versions": {
          "__start__": 2,
          "messages": 4,
          "order_id": 2,
          "amount": 2,
          "branch:to:support_agent": 4,
          "branch:to:tools": 4
        },
        "versions_seen": {
          "__input__": {},
          "__start__": {
            "__start__": 1
          },
          "support_agent": {
            "branch:to:support_agent": 2
          },
          "tools": {
            "branch:to:tools": 3
          }
        },
        "updated_channels": [
          "branch:to:support_agent",
          "messages"
        ]
      },
      "metadata": {
        "source": "loop",
        "step": 2,
        "parents": {}
      }
    },
    {
      "checkpoint_id": "1f11185d-f8a2-6eba-8001-a125446c7b73",
      "parent_checkpoint_id": "1f11185d-e8c0-6f56-8000-5d5a956ae500",
      "checkpoint": {
        "v": 4,
        "ts": "2026-02-24T13:36:50.389362+00:00",
        "id": "1f11185d-f8a2-6eba-8001-a125446c7b73",
        "channel_values": {
          "messages": [
            {
              "content": "Can you refund my id12 cost is $80",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "human",
              "name": null,
              "id": "20dcb597-a606-4672-b940-13cd71affa0d"
            },
            {
              "content": "",
              "additional_kwargs": {
                "refusal": null
              },
              "response_metadata": {
                "token_usage": {
                  "completion_tokens": 21,
                  "prompt_tokens": 143,
                  "total_tokens": 164,
                  "completion_tokens_details": {
                    "accepted_prediction_tokens": 0,
                    "audio_tokens": 0,
                    "reasoning_tokens": 0,
                    "rejected_prediction_tokens": 0
                  },
                  "prompt_tokens_details": {
                    "audio_tokens": 0,
                    "cached_tokens": 0
                  }
                },
                "model_provider": "openai",
                "model_name": "gpt-4o-mini-2024-07-18",
                "system_fingerprint": "fp_2d82c05f26",
                "id": "chatcmpl-DCmsjiUnvfrUawEJ1DgtfssCHUK6F",
                "service_tier": "default",
                "finish_reason": "tool_calls",
                "logprobs": null
              },
              "type": "ai",
              "name": null,
              "id": "lc_run--019c8fdd-e054-70b1-a378-65ce96441420-0",
              "tool_calls": [
                {
                  "name": "process_refund",
                  "args": {
                    "order_id": "id12",
                    "amount": 80
                  },
                  "id": "call_mE2vKuuNuY8YjucSLfeU0B8D",
                  "type": "tool_call"
                }
              ],
              "invalid_tool_calls": [],
              "usage_metadata": {
                "input_tokens": 143,
                "output_tokens": 21,
                "total_tokens": 164,
                "input_token_details": {
                  "audio": 0,
                  "cache_read": 0
                },
                "output_token_details": {
                  "audio": 0,
                  "reasoning": 0
                }
              }
            }
          ],
          "order_id": "123",
          "amount": 1,
          "branch:to:tools": null
        },
        "channel_versions": {
          "__start__": 2,
          "messages": 3,
          "order_id": 2,
          "amount": 2,
          "branch:to:support_agent": 3,
          "branch:to:tools": 3
        },
        "versions_seen": {
          "__input__": {},
          "__start__": {
            "__start__": 1
          },
          "support_agent": {
            "branch:to:support_agent": 2
          }
        },
        "updated_channels": [
          "branch:to:tools",
          "messages"
        ]
      },
      "metadata": {
        "source": "loop",
        "step": 1,
        "parents": {}
      }
    },
    {
      "checkpoint_id": "1f11185d-e8c0-6f56-8000-5d5a956ae500",
      "parent_checkpoint_id": "1f11185d-e8be-65ee-bfff-576127f646bd",
      "checkpoint": {
        "v": 4,
        "ts": "2026-02-24T13:36:48.723938+00:00",
        "id": "1f11185d-e8c0-6f56-8000-5d5a956ae500",
        "channel_values": {
          "messages": [
            {
              "content": "Can you refund my id12 cost is $80",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "human",
              "name": null,
              "id": "20dcb597-a606-4672-b940-13cd71affa0d"
            }
          ],
          "order_id": "123",
          "amount": 1,
          "branch:to:support_agent": null
        },
        "channel_versions": {
          "__start__": 2,
          "messages": 2,
          "order_id": 2,
          "amount": 2,
          "branch:to:support_agent": 2
        },
        "versions_seen": {
          "__input__": {},
          "__start__": {
            "__start__": 1
          }
        },
        "updated_channels": [
          "amount",
          "branch:to:support_agent",
          "messages",
          "order_id"
        ]
      },
      "metadata": {
        "source": "loop",
        "step": 0,
        "parents": {}
      }
    },
    {
      "checkpoint_id": "1f11185d-e8be-65ee-bfff-576127f646bd",
      "parent_checkpoint_id": null,
      "checkpoint": {
        "v": 4,
        "ts": "2026-02-24T13:36:48.722882+00:00",
        "id": "1f11185d-e8be-65ee-bfff-576127f646bd",
        "channel_values": {
          "__start__": {
            "messages": [
              {
                "content": "Can you refund my id12 cost is $80",
                "additional_kwargs": {},
                "response_metadata": {},
                "type": "human",
                "name": null,
                "id": "20dcb597-a606-4672-b940-13cd71affa0d"
              }
            ],
            "order_id": "123",
            "amount": 1
          }
        },
        "channel_versions": {
          "__start__": 1
        },
        "versions_seen": {
          "__input__": {}
        },
        "updated_channels": [
          "__start__"
        ]
      },
      "metadata": {
        "source": "input",
        "step": -1,
        "parents": {}
      }
    }
  ]
}
```