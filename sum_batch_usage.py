"""sum_batch_usage.py — retrieve an Azure OpenAI batch job, sum its token usage,
and (optionally) append a row to token_generation_log.csv.

Usage:
    python3 sum_batch_usage.py batch_<id>                  # print only
    python3 sum_batch_usage.py batch_<id> --append PATH    # print + append CSV row

Config comes from environment variables (same names as generate_tokens_batch.py):
    AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY
No credentials in this file — safe for the public repo.

Timestamps: written in real UTC (timezone-aware), fixing the batch-1 hygiene bug
where local SAST was logged under a utc_ column name.
"""

import csv
import json
import os
import sys
from datetime import datetime, timezone

from openai import AzureOpenAI

# gpt-4.1-nano GLOBAL BATCH rates, USD per 1M tokens, as billed 31 Aug 2026
# (verified against the FOCUS export: $0.05 input / $0.20 output).
# If the deployment or pricing changes, update here and note it in the log.
RATE_IN_PER_1M = 0.05
RATE_OUT_PER_1M = 0.20
DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-nano-1")


def iso_utc(epoch):
    if not epoch:
        return ""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].startswith("batch_"):
        sys.exit("usage: python3 sum_batch_usage.py batch_<id> [--append token_generation_log.csv]")
    batch_id = sys.argv[1]
    append_path = None
    if "--append" in sys.argv:
        i = sys.argv.index("--append")
        if i + 1 >= len(sys.argv):
            sys.exit("--append needs a CSV path")
        append_path = sys.argv[i + 1]

    client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version="2025-01-01-preview",
    )

    job = client.batches.retrieve(batch_id)
    print(f"id:        {job.id}")
    print(f"status:    {job.status}")
    print(f"created:   {iso_utc(job.created_at)} (UTC)")
    print(f"completed: {iso_utc(getattr(job, 'completed_at', None))} (UTC)")
    rc = getattr(job, "request_counts", None)
    if rc:
        print(f"requests:  total={rc.total} completed={rc.completed} failed={rc.failed}")

    if job.status != "completed":
        sys.exit("job not completed — no output file to sum yet")
    if not job.output_file_id:
        sys.exit("no output_file_id on the job")

    content = client.files.content(job.output_file_id)
    prompt = completion = lines = 0
    for line in content.text.strip().splitlines():
        usage = json.loads(line)["response"]["body"]["usage"]
        prompt += usage["prompt_tokens"]
        completion += usage["completion_tokens"]
        lines += 1

    total = prompt + completion
    est_cost = prompt / 1_000_000 * RATE_IN_PER_1M + completion / 1_000_000 * RATE_OUT_PER_1M
    print(f"\nlines:             {lines}")
    print(f"prompt_tokens:     {prompt}")
    print(f"completion_tokens: {completion}")
    print(f"total_tokens:      {total}")
    print(f"est_cost_usd:      {est_cost:.6f}  (batch rates {RATE_IN_PER_1M}/{RATE_OUT_PER_1M} per 1M)")

    if append_path:
        # Match the existing CSV schema: read its header and fill known fields.
        with open(append_path, newline="") as f:
            header = next(csv.reader(f))
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
        values = {
            "utc_timestamp": now_utc,
            "call_n": f"batch:{job.id}",
            "deployment": DEPLOYMENT,
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
        }
        row = []
        for col in header:
            if col in values:
                row.append(values[col])
            elif col.startswith("est_cost_usd"):
                row.append(f"{est_cost:.6f}")
            else:
                row.append("")
        with open(append_path, "a", newline="") as f:
            csv.writer(f).writerow(row)
        print(f"\nappended to {append_path}:")
        print(",".join(str(v) for v in row))


if __name__ == "__main__":
    main()
