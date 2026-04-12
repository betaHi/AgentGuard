"""Example: Multi-Agent Customer Support Pipeline.

Pipeline:
  coordinator → classifier → router → responder → escalator → followup
"""

import time, random, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
random.seed(42)

from agentguard import record_agent, record_tool, record_handoff
from agentguard.sdk.recorder import init_recorder, finish_recording

@record_tool(name="classify_intent")
def classify(text):
    time.sleep(0.1)
    return {"intent": "billing_dispute", "confidence": 0.92, "language": "en"}

@record_tool(name="search_knowledge_base")
def search_kb(query):
    time.sleep(0.15)
    return [{"title": "Billing Dispute Policy", "id": "KB-1042"}]

@record_tool(name="generate_response")
def gen_response(context):
    time.sleep(0.3)
    return {"message": "I understand your billing concern. Let me look into this...", "tokens": 150}

@record_tool(name="check_escalation_rules")
def check_escalation(ticket):
    time.sleep(0.05)
    return {"should_escalate": ticket.get("sentiment") == "angry", "reason": "negative sentiment"}

@record_tool(name="send_email")
def send_email(to, subject, body):
    time.sleep(0.08)
    return {"sent": True}

@record_agent(name="classifier", version="v2.1")
def classifier(message):
    return classify(message)

@record_agent(name="knowledge-retriever", version="v1.3")
def retriever(intent):
    return {"articles": search_kb(intent["intent"]), "intent": intent}

@record_agent(name="responder", version="v3.0")
def responder(context):
    response = gen_response(context)
    return {"response": response, "context": context}

@record_agent(name="escalation-checker", version="v1.0")
def escalator(ticket):
    result = check_escalation(ticket)
    if result["should_escalate"]:
        send_email("manager@company.com", "Escalation", f"Ticket needs attention: {result['reason']}")
    return result

@record_agent(name="support-coordinator", version="v2.0")
def coordinator(customer_message):
    intent = classifier(customer_message)
    record_handoff("classifier", "knowledge-retriever", context=intent, summary=f"Intent: {intent['intent']}")
    
    knowledge = retriever(intent)
    record_handoff("knowledge-retriever", "responder", context=knowledge, summary=f"{len(knowledge['articles'])} articles found")
    
    response = responder(knowledge)
    record_handoff("responder", "escalation-checker", context={"response": response, "sentiment": "neutral"})
    
    escalation = escalator({"response": response, "sentiment": "neutral"})
    return {"response": response["response"]["message"], "escalated": escalation["should_escalate"]}

if __name__ == "__main__":
    print("=" * 60)
    print("  AgentGuard Example: Customer Support Pipeline")
    print("=" * 60)
    
    init_recorder(task="Customer Support: Billing Dispute", trigger="incoming_message")
    result = coordinator("I was charged twice for my subscription last month and I want a refund!")
    trace = finish_recording()
    
    print(f"\n  Response: {result['response'][:60]}...")
    print(f"  Escalated: {result['escalated']}")
    print(f"  Trace: {len(trace.spans)} spans, {trace.duration_ms:.0f}ms")
    
    from agentguard.evolve import EvolutionEngine
    engine = EvolutionEngine()
    r = engine.learn(trace)
    print(f"  Lessons: {len(r.lessons)}")
    print("=" * 60)
