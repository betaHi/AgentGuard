"""Example: Multi-Agent Data Pipeline.

Pipeline: coordinator → extractor → validator → transformer → loader → reporter
"""

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
random.seed(42)

from agentguard import record_agent, record_handoff, record_tool
from agentguard.sdk.recorder import finish_recording, init_recorder


@record_tool(name="read_csv")
def read_csv(path):
    time.sleep(0.1)
    return {"rows": 10000, "columns": ["id", "name", "amount", "date"]}

@record_tool(name="validate_schema")
def validate_schema(data):
    time.sleep(0.05)
    return {"valid": True, "null_count": 23, "type_errors": 0}

@record_tool(name="clean_data")
def clean(data):
    time.sleep(0.2)
    return {"rows_cleaned": 9977, "rows_dropped": 23}

@record_tool(name="aggregate")
def aggregate(data):
    time.sleep(0.15)
    return {"total_amount": 1234567.89, "unique_customers": 4521}

@record_tool(name="write_to_db")
def write_db(data):
    time.sleep(0.1)
    return {"rows_written": 9977, "table": "transactions_clean"}

@record_tool(name="generate_report")
def gen_report(stats):
    time.sleep(0.2)
    return {"report": "Monthly Transaction Summary", "pages": 3}

@record_agent(name="extractor", version="v1.0")
def extractor(source):
    return read_csv(source)

@record_agent(name="validator", version="v2.1")
def validator(data):
    return validate_schema(data)

@record_agent(name="transformer", version="v1.5")
def transformer(data):
    cleaned = clean(data)
    aggregated = aggregate(cleaned)
    return {"cleaned": cleaned, "aggregated": aggregated}

@record_agent(name="loader", version="v1.0")
def loader(data):
    return write_db(data)

@record_agent(name="reporter", version="v1.2")
def reporter(stats):
    return gen_report(stats)

@record_agent(name="data-coordinator", version="v3.0")
def coordinator(source):
    raw = extractor(source)
    record_handoff("extractor", "validator", context=raw, summary=f"{raw['rows']} rows extracted")

    validation = validator(raw)
    record_handoff("validator", "transformer", context=validation, summary="Schema valid")

    transformed = transformer(raw)
    record_handoff("transformer", "loader", context=transformed, summary=f"{transformed['cleaned']['rows_cleaned']} rows ready")

    loaded = loader(transformed)
    record_handoff("loader", "reporter", context=loaded, summary=f"{loaded['rows_written']} rows loaded")

    report = reporter({"loaded": loaded, "transformed": transformed})
    return {"status": "complete", "report": report}

if __name__ == "__main__":
    init_recorder(task="Monthly Transaction ETL", trigger="scheduled")
    result = coordinator("/data/transactions_2026_03.csv")
    trace = finish_recording()
    print(f"ETL complete: {len(trace.spans)} spans, {trace.duration_ms:.0f}ms")
