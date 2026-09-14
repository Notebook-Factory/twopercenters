# What to ask the Kumo / NVIDIA contact

Context to give them in one line: an open dataset of 2.7 million rows across
15 annual editions of the Ioannidis "top 2% of scientists" tables, already
normalised into a relational schema with 19 foreign keys and a time column,
exported to Parquet. Public, non-commercial, intended to be written up.

## The blocking question

1. **Which access path is open to me, and how do I get credentials?**
   `kumorfm.ai` now 301-redirects to `docs.nvidia.com/sdgm/rfm/overview`,
   including `/authenticate-sdk/`, so `kumoai`'s `rfm.authenticate()` cannot
   complete: it opens that URL and waits for a token on `localhost:8765`
   that never arrives. `api.kumorfm.ai` does not resolve. Is the hosted
   KumoRFM endpoint retired, or has it moved to a new host?

2. **If it has moved, what is the value of `KUMO_API_URL`?** The SDK still
   accepts `authenticate(api_url=...)` and reads `KUMO_API_URL`, so a new
   base URL plus a key is all that is needed to make the existing client
   work unchanged.

3. **If the hosted path is gone, can I get NGC access instead?** The SDGM
   requirements page says images come from the private registry and that
   "credentials are provided by your NVIDIA or Kumo contact. There is no
   self-service sign-up path." Specifically I would need:
   - an NGC API key with access to the `1000161941370113/kumo-3` org
   - the exact 40-character git commit SHA image tag to pull
   - the hardware floor, which the requirements page does not state (GPU
     model, VRAM, host RAM, disk)

## The questions that shape what I build

4. **Is there a research or evaluation tier?** This is a public dataset and
   a non-commercial write-up, not an enterprise deployment.

5. **Can the 1000-entity cap per `predict` call be raised?** One of the
   tasks imputes a column for 955,512 rows, which is 956 calls at the
   documented cap. Is a batch or bulk path available, and what are the
   per-day rate limits?

6. **Is `evaluate` intended to be used without `indices`?** Its signature
   takes none, so it appears to draw its own in-context examples and hold
   out labelled ones. Confirming that would settle how we report accuracy.

7. **What may be published?** Specifically whether measured metrics,
   PQL queries, and `explain` output can appear in a public write-up, and
   how Kumo/NVIDIA would like to be credited.

## Useful to mention

That the same graph is being built on RelBench in the meantime, so the
comparison is like-for-like: identical tables, identical foreign keys,
identical task definitions and time splits. If they want a benchmark
datapoint on a dataset that is not in RelBench v2, this is one.
