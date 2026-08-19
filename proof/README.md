# Proof of concept — one real pass

This proves the core works: one real protocol + one known-answer dataset →
correct test → correct numbers → a Results section that invents nothing → a
`.docx`. It calls the pipeline services **directly** (no auth, no payment, no
database), which is exactly the "prove the concept" slice.

## Files

- `bp_study.csv` — a small, made-up dataset (two independent groups, one clear
  difference) whose answer you can verify by hand. **No real patient data.**
- `protocol.txt` — a matching study protocol (independent two-group comparison of
  a continuous outcome → the correct test is an independent-samples t-test).
- `run_proof.py` — runs the whole core pipeline with the real LLM and prints the
  ground-truth answer next to the pipeline's output.

## Run it

1. Get a free key at https://aistudio.google.com/apikey and put it in `.env` at the
   project root:

   ```
   LLM_API_KEY=<your key>
   LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
   LLM_MODEL=gemini-2.5-flash
   ```

2. Install the app deps plus the packages the generated script needs to run
   locally:

   ```
   pip install -r requirements.txt scipy matplotlib statsmodels
   ```

3. Run:

   ```
   python proof/run_proof.py
   ```

It prints each step, the generated script, the execution output, the Results
section, the exported document paths, and a **ground-truth** t-test computed
independently — followed by a 4-point checklist. If all four check out, the
concept is proven.

> The script runs locally (no Docker needed) via the dev subprocess path. That's
> fine for this proof; production uses the isolated Docker sandbox.
