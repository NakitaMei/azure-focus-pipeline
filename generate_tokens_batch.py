"""
Stage 7 kick-off — generate token spend via a GLOBAL BATCH deployment.

Batch works file-in, file-out: we upload a JSONL of requests, Azure runs
them within 24h (usually far sooner) at half the interactive price, and we
read token usage back from the output file. Two commands:

    python3 generate_tokens_batch.py submit          # build, upload, start
    python3 generate_tokens_batch.py check <batch_id>  # later: status + totals

Setup (same env vars as before, plus the deployment name):
    pip install openai
    export AZURE_OPENAI_ENDPOINT="https://<resource>.openai.azure.com/"
    export AZURE_OPENAI_KEY="<api key>"
    export AZURE_OPENAI_DEPLOYMENT="gpt-4.1-nano-1"

Writes batch_input.jsonl, records batch id to batch_id.txt, and appends
completed-batch totals to token_generation_log.csv.
"""

import csv
import json
import os
import sys
import time
from datetime import datetime, timezone

from openai import AzureOpenAI

# ---- knobs -----------------------------------------------------------------
N_REQUESTS      = 800     # ~1.6M enqueued tokens; ~$0.15-0.20 at batch rates
MAX_TOKENS      = 2000    # per-request output cap (counts toward enqueued)
# gpt-4.1-nano GLOBAL BATCH = half of Global Standard (verify on pricing page):
PRICE_IN_PER_M  = 0.05
PRICE_OUT_PER_M = 0.20
# ----------------------------------------------------------------------------

DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-nano-1")
HERE = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH = os.path.join(HERE, "batch_input.jsonl")
ID_PATH = os.path.join(HERE, "batch_id.txt")
LOG_PATH = os.path.join(HERE, "token_generation_log.csv")

TOPICS = [
    "the history of double-entry bookkeeping", "how ocean currents form",
    "the economics of container shipping", "how vaccines are manufactured",
    "the design of suspension bridges", "the lifecycle of a star",
    "how municipal water treatment works", "the history of the spice trade",
]

client = AzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"], 
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version="2025-01-01-preview",
)


def submit():
    with open(INPUT_PATH, "w") as f:
        for n in range(N_REQUESTS):
            f.write(json.dumps({
                "custom_id": f"task-{n:04d}",
                "method": "POST",
                "url": "/chat/completions",
                "body": {
                    "model": DEPLOYMENT,
                    "max_completion_tokens": MAX_TOKENS,
                    "messages": [{"role": "user",
                                  "content": f"Write a detailed essay of about "
                                             f"1500 words on "
                                             f"{TOPICS[n % len(TOPICS)]}."}],
                },
            }) + "\n")
    print(f"Built {INPUT_PATH} with {N_REQUESTS} requests.")

    up = client.files.create(file=open(INPUT_PATH, "rb"), purpose="batch")
    print(f"Uploaded input file: {up.id}")

    batch = client.batches.create(input_file_id=up.id,
                                  endpoint="/chat/completions",
                                  completion_window="24h")
    open(ID_PATH, "w").write(batch.id)
    stamp = datetime.now(timezone.utc).isoformat()
    print(f"Batch submitted (UTC): {stamp}  <- record in the kick-off log")
    print(f"Batch id: {batch.id}  (saved to batch_id.txt)")

    # Poll briefly; batches often finish fast, but 24h is the contract.
    for _ in range(20):  # ~10 minutes
        time.sleep(30)
        b = client.batches.retrieve(batch.id)
        print(f"  status: {b.status}")
        if b.status in ("completed", "failed", "expired", "cancelled"):
            return check(batch.id)
    print("\nStill running — normal for Batch. Re-run later:")
    print(f"  python3 generate_tokens_batch.py check {batch.id}")


def check(batch_id):
    b = client.batches.retrieve(batch_id)
    print(f"Batch {batch_id}: {b.status}")
    if b.status != "completed":
        if getattr(b, "errors", None):
            print("Errors:", b.errors)
        print("Check again later if still in progress.")
        return
    total_in = total_out = ok = 0
    content = client.files.content(b.output_file_id).text
    for line in content.splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        body = (rec.get("response") or {}).get("body") or {}
        u = body.get("usage") or {}
        total_in += u.get("prompt_tokens", 0)
        total_out += u.get("completion_tokens", 0)
        ok += 1
    cost = (total_in * PRICE_IN_PER_M + total_out * PRICE_OUT_PER_M) / 1e6
    stamp = datetime.now(timezone.utc).isoformat()
    print(f"Completed (checked {stamp}):")
    print(f"  {ok} responses | {total_in:,} in / {total_out:,} out "
          f"| est ${cost:.4f} at batch rates")
    new_log = not os.path.exists(LOG_PATH)
    with open(LOG_PATH, "a", newline="") as f:
        w = csv.writer(f)
        if new_log:
            w.writerow(["utc_timestamp", "call_n", "deployment",
                        "prompt_tokens", "completion_tokens", "total_tokens",
                        "est_cost_usd_cumulative"])
        w.writerow([stamp, f"batch:{batch_id}({ok} reqs)", DEPLOYMENT,
                    total_in, total_out, total_in + total_out,
                    round(cost, 6)])
    print(f"Logged to {LOG_PATH}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        bid = sys.argv[2] if len(sys.argv) > 2 else open(ID_PATH).read().strip()
        check(bid)
    else:
        submit()
