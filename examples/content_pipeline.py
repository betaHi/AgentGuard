"""Example: Content Creation Pipeline.

Pipeline: coordinator → researcher → outliner → writer → editor → publisher
"""
import time, random, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
random.seed(42)

from agentguard import record_agent, record_tool, record_handoff
from agentguard.sdk.recorder import init_recorder, finish_recording

@record_tool(name="search_sources")
def search(topic):
    time.sleep(0.15)
    return [{"title": f"Source about {topic}", "url": f"https://example.com/{i}"} for i in range(5)]

@record_tool(name="llm_outline")
def make_outline(topic, sources):
    time.sleep(0.3)
    return {"sections": ["Introduction", "Key Findings", "Analysis", "Conclusion"], "estimated_words": 2000}

@record_tool(name="llm_write")
def write_section(section, context):
    time.sleep(0.4)
    return {"text": f"Content for {section}...", "words": random.randint(400, 600), "tokens": random.randint(800, 1200)}

@record_tool(name="llm_edit")
def edit(text):
    time.sleep(0.2)
    return {"edited": True, "changes": random.randint(5, 15), "quality_score": round(random.uniform(0.8, 0.95), 2)}

@record_tool(name="publish_cms")
def publish(content):
    time.sleep(0.1)
    return {"published": True, "url": "https://blog.example.com/new-post"}

@record_agent(name="researcher", version="v1.0")
def researcher(topic):
    return {"sources": search(topic), "topic": topic}

@record_agent(name="outliner", version="v1.0")
def outliner(research):
    return make_outline(research["topic"], research["sources"])

@record_agent(name="writer", version="v2.0")
def writer(outline):
    sections = []
    for s in outline["sections"]:
        sections.append(write_section(s, outline))
    return {"sections": sections, "total_words": sum(s["words"] for s in sections)}

@record_agent(name="editor", version="v1.5")
def editor(draft):
    edited = []
    for s in draft["sections"]:
        edited.append(edit(s))
    return {"edited": edited, "avg_quality": sum(e["quality_score"] for e in edited) / len(edited)}

@record_agent(name="publisher", version="v1.0")
def publisher(content):
    return publish(content)

@record_agent(name="content-coordinator", version="v2.0")
def coordinator(topic):
    research = researcher(topic)
    record_handoff("researcher", "outliner", context=research, summary=f"{len(research['sources'])} sources")
    outline = outliner(research)
    record_handoff("outliner", "writer", context=outline, summary=f"{len(outline['sections'])} sections planned")
    draft = writer(outline)
    record_handoff("writer", "editor", context=draft, summary=f"{draft['total_words']} words written")
    edited = editor(draft)
    record_handoff("editor", "publisher", context=edited, summary=f"Quality: {edited['avg_quality']:.0%}")
    result = publisher(edited)
    return {"status": "published", "url": result["url"], "words": draft["total_words"], "quality": edited["avg_quality"]}

if __name__ == "__main__":
    init_recorder(task="Blog Post: AI Agent Observability Guide", trigger="editorial_calendar")
    result = coordinator("AI Agent Observability Best Practices")
    trace = finish_recording()
    print(f"Published: {result['url']}, {result['words']} words, {result['quality']:.0%} quality")
    print(f"Trace: {len(trace.spans)} spans, {trace.duration_ms:.0f}ms")
