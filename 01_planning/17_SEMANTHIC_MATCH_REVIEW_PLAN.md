 When open application review I see Semantic Match equals 1% for the user that generated this logs app-1  | {"ts": "2026-06-16T17:30:38.301089+00:00", "event": "pipeline_started", "application_id": "fe33853a-d0f2-4607-8764-b332bf4de1d0", "job_id": "99fa4c92-efcc-4bf0-9d84-a9724ace82f4", "candidate_id": "84ac2186-c5e4-46d6-9009-80f7d072dc89"}
  app-1  | {"ts": "2026-06-16T17:30:38.301221+00:00", "event": "pipeline_input_prepared", "application_id": "fe33853a-d0f2-4607-8764-b332bf4de1d0", "job_title": "Senior Backend Engineer", "resume_sections": {"summary": 650, "experience": 2986, "total_experience_years": 4}, "resume_section_count": 3, "job_requirement_keys": {"required_skills": 47, "preferred_skills": 33, "minimum_experience_years": 1}, "must_haves_count": 3}
  app-1  | {"ts": "2026-06-16T17:30:38.306976+00:00", "event": "pipeline_embeddings_built", "application_id": "fe33853a-d0f2-4607-8764-b332bf4de1d0", "candidate_sections": ["summary", "experience"], "job_sections": ["summary", "experience", "skills", "education", "certifications", "projects"], "candidate_section_count": 2, "job_section_count": 6, "embedding_dim": 1536}
  app-1  | {"ts": "2026-06-16T17:30:38.307647+00:00", "event": "pipeline_embedding_stats", "application_id": "fe33853a-d0f2-4607-8764-b332bf4de1d0", "candidate_section_norms": {"summary": 1.0, "experience": 1.0}, "job_section_norms": {"summary": 1.0, "experience": 1.0, "skills": 1.0, "education": 1.0, "certifications": 1.0, "projects": 1.0}, "first_vec_dim": 1536, "first_vec_norm": 1.0, "first_vec_sample": [0.004874, 0.005531, 0.020114, 0.026708, -0.001558]}
  app-1  | {"ts": "2026-06-16T17:30:38.307934+00:00", "event": "gate_transition", "application_id": "fe33853a-d0f2-4607-8764-b332bf4de1d0", "criterion": "min_experience", "previous_outcome": null, "new_outcome": "pass", "evidence": "Candidate has 15.0 years; required 5"}
  app-1  | {"ts": "2026-06-16T17:30:38.307982+00:00", "event": "gate_transition", "application_id": "fe33853a-d0f2-4607-8764-b332bf4de1d0", "criterion": "django_required", "previous_outcome": null, "new_outcome": "pass", "evidence": "Found all required keywords: ['Django']"}
  app-1  | {"ts": "2026-06-16T17:30:38.308002+00:00", "event": "gate_transition", "application_id": "fe33853a-d0f2-4607-8764-b332bf4de1d0", "criterion": "python_required", "previous_outcome": null, "new_outcome": "pass", "evidence": "Found all required keywords: ['Python']"}
  app-1  | {"ts": "2026-06-16T17:30:38.308667+00:00", "event": "rubric_llm_call_started", "model_name": "gpt-4o-mini", "system_prompt_len": 1574, "user_prompt_len": 4138, "resume_sections": ["summary", "experience", "total_experience_years"], "job_requirement_keys": ["required_skills", "preferred_skills", "minimum_experience_years"]}
  app-1  | Not Found: /api/applications/fe33853a-d0f2-4607-8764-b332bf4de1d0/score/
  app-1  | 192.168.65.1 - - [16/Jun/2026:17:30:41 +0000] "GET /api/applications/fe33853a-d0f2-4607-8764-b332bf4de1d0/score/ HTTP/1.1" 404 51 "http://localhost:3000/" "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
  app-1  | 127.0.0.1 - - [16/Jun/2026:17:30:41 +0000] "GET /api/health/ HTTP/1.1" 200 16 "-" "curl/8.14.1"
  app-1  | {"ts": "2026-06-16T17:30:41.946349+00:00", "event": "rubric_llm_call_finished", "model_name": "gpt-4o-mini", "response_type": "structured", "response_len": null, "latency_ms": 3637.577, "used_fallback": false}
  app-1  | {"ts": "2026-06-16T17:30:41.946457+00:00", "event": "rubric_response_parsed", "parse_path": "structured_object", "had_markdown_fence": false, "criteria_found": ["core_skills", "relevant_experience", "scope_impact", "domain_alignment", "education_certs"], "criteria_count": 5, "is_fallback": false}
  app-1  | {"ts": "2026-06-16T17:30:41.946515+00:00", "event": "rubric_scored", "raw_scores": {"core_skills": 4.0, "relevant_experience": 5.0, "scope_impact": 4.0, "domain_alignment": 4.0, "education_certs": 5.0}, "clamped_scores": {"core_skills": 4.0, "relevant_experience": 5.0, "scope_impact": 4.0, "domain_alignment": 4.0, "education_certs": 5.0}, "weighted_sum": 4.4, "normalized_score": 0.88, "evidence_per_criterion": {"core_skills": 19, "relevant_experience": 18, "scope_impact": 19, "domain_alignment": 19, "education_certs": 19}, "evidence_quality": 1.0}
  app-1  | {"ts": "2026-06-16T17:30:41.946624+00:00", "event": "score_computed", "application_id": "fe33853a-d0f2-4607-8764-b332bf4de1d0", "final_score": 0.5003694291408757, "gate_passed": true, "component_scores": {"semantic_match": 0.009709842535279182, "rubric_score_norm": 0.8800000000000001, "evidence_quality": 1.0}, "confidence": 1.0, "model_name": "gpt-4o-mini", "retry_count": null, "is_evaluated_via_fallback": false}
  app-1  | {"ts": "2026-06-16T17:30:41.946691+00:00", "event": "pipeline_gate_result", "application_id": "fe33853a-d0f2-4607-8764-b332bf4de1d0", "gate_outcome": "pass", "gate_passed": true, "criteria": [{"name": "min_experience", "outcome": "pass", "evidence": "Candidate has 15.0 years; required 5"}, {"name":: "pass", "evidence": "Found all required keywords: ['Django']"}, {"name": "python_required","outcome": "pass", "evidence": "Found all required keywords: ['Python']"}]}
  app-1  | {"ts": "2026-06-16T17:30:41.946746+00:00", "event": "pipeline_semantic_result", "application_id": "fe33853a-d0f2-4607-8764-b332bf4de1d0", "semantic_score": 0.009709842535279182, "section_scores": {"summary": 0.04294230950266497, "experience": -0.0027523325774904883}, "sections_scored": 2}
  app-1  | {"ts": "2026-06-16T17:30:41.946779+00:00", "event": "pipeline_rubric_result", "application_id": "fe33853a-d0f2-4607-8764-b332bf4de1d0", "rubric_score": 0.8800000000000001, "criterion_scores": {"core_skills": 4.0, "relevant_experience": 5.0, "scope_impact": 4.0, "domain_alignment": 4.0, "education_certs": 5.0}, "evidence_quality": 1.0}
  app-1  | {"ts": "2026-06-16T17:30:41.946812+00:00", "event": "score_computed", "application_id": "fe33853a-d0f2-4607-8764-b332bf4de1d0", "final_score": 0.5003694291408757, "gate_passed": true, "component_scores": {"semantic_match": 0.009709842535279182, "rubric_score_norm": 0.8800000000000001, "evidence_quality": 1.0}, "confidence": 1.0, "model_name": "openai", "retry_count": null, "is_evaluated_via_fallback": false}
  app-1  | {"ts": "2026-06-16T17:30:41.957344+00:00", "event": "pipeline_persisted", "application_id332bf4de1d0", "gate_outcome": "pass", "gate_passed": true, "stages_persisted": ["hard_gate","semantic_match", "rubric"], "new_status": "scored"}
  app-1  | {"ts": "2026-06-16T17:30:41.957421+00:00", "event": "pipeline_completed", "application_id332bf4de1d0", "gate_outcome": "pass", "gate_passed": true, "final_score": 0.5003694291408757,"stages_executed": ["hard_gate", "semantic_match", "rubric"], "latency_ms": 3638.878}
  app-1  | 192.168.65.1 - - [16/Jun/2026:17:30:41 +0000] "POST /api/applications/fe33853a-d0f2-4607-.1" 200 655 "http://localhost:3000/" "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36". Does it make sense? Explain me again the semanthic match

Two separate problems compound here, plus a minor side-effect from our change.

---
How Semantic Match works (recap)

SemanticMatchEvaluator compares the candidate's pre-stored section embeddings against the job's section embeddings using cosine similarity, then fuses the per-section scores with RRF. The final semantic score feeds the formula as 0.45 × semantic + 0.45 × rubric_norm + 0.10 × evidence_quality.

---
Why 1%?

Problem 1 — Missing sections (structural)

The candidate has only 2 embeddable sections:
candidate_sections: ["summary", "experience"]   ← 2 sections
job_sections:       ["summary", "experience", "skills", "education", "certifications", "projects"]  ← 6 sections
The job's skills, education, certifications, and projects sections have nothing to compare against. Only summary and experience contribute any signal.

Problem 2 — The section scores themselves are near-zero (root cause)

summary:    0.043
experience: -0.003

For real embeddings between professionally similar content ("senior backend engineer summary" vs "escription") you'd expect cosine similarity in the 0.7–0.9 range. Values this close to zero — and a negative score for experience — are the signature of mock/random embeddings. Random unit vectors in 1536 dimensions have expected cosine similarity ≈ 0.

The rubric stage clearly uses real OpenAI (gpt-4o-mini, 88% score, meaningful criterion scores). Bontrolled separately from LLM_BACKEND. If the embeddings were stored at ingestion time using themock backend, they're random unit vectors and cosine similarity against any other vector is near-zero regardless of content. The RRF fusion then averages those near-zero values into the 0.97% final semantic score.

The impact on final score:

0.45 × 0.0097 + 0.45 × 0.88 + 0.10 × 1.0 = 0.004 + 0.396 + 0.100 = 0.50

That's why a candidate the LLM rates at 88% ends up with a 50% overall score — the semantic component is dragging it down from a potential ~89%.

---
Side-effect from our ExperienceExtractor change

Notice this in pipeline_input_prepared:
"resume_sections": {"summary": 650, "experience": 2986, "total_experience_years": 4}
And in rubric_llm_call_started:
"resume_sections": ["summary", "experience", "total_experience_years"]

total_experience_years is a float stored directly in the sections dict, so the pipeline iterates oection. The embedding stage skips it (it's not a string), but the rubric LLM receives it as asection name. It's benign for now — the LLM can interpret it — but it's semantically wrong. The cleaner fix is to store it under a separate key that the pipeline won't treat as a section, or filter it out before passing sections downstream. Worth addressing separately.

---
Summary

┌───────────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                 Issue                 │                                      Cause                                       │                               Fix                               │
├───────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 1% semantic match                     │ Mock embeddings stored at ingestion; candidate missing skills/education sections │ Enable real embedding backend; re-upload or backfill embeddings │
├───────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────┤
│ total_experience_years as a "section" │ We stored the float directly in sections dict           ore it separately or filter before pipeline iteration         │
└───────────────────────────────────────┴──────────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────┘