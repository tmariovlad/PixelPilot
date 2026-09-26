"""Run one SQL query on a Perfetto trace and print the rows.
Usage: python3 trace_query.py trace.pftrace "select name, count(*) n from slice group by name order by n desc limit 20"
Needs: pip install perfetto"""
import sys
from perfetto.trace_processor import TraceProcessor
tp = TraceProcessor(trace=sys.argv[1])
q = sys.argv[2]
for r in tp.query(q):
    print(r.__dict__ if hasattr(r, "__dict__") else r)
