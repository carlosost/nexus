# Carlos
Please, summarize the most relevant points so far in a way I can use the summary to ask Claude CoWork to help me build the best and complete plan to develop this application. Don't infer about things not discussed. Don't include topics not discussed so far. Be concise but add all information necessary to have a full understanding of decisions made.

---
# Perplexity

# Resume Review Application Summary

Build a resume-review and evaluation application for matching resumes to job descriptions using a hybrid scoring approach, not a single-model decision system [web:45][web:76][web:68]. The agreed direction is to combine **hard gates**, **semantic matching**, **rubric scoring**, and **human-in-the-loop review**, because LLM-only scoring is not strong enough to replace structured human judgment [web:45][web:87][web:93].

## Core decision

Do **not** use an LLM or semantic model as the sole final scorer [web:45]. The main reason is that the strongest semantic matcher is not the strongest hiring decision system: studies found only minor alignment between LLM resume ratings and human ratings, even when prompt engineering improved results [web:45]. Use the strongest semantic model where it is strongest, as one component in a broader, auditable pipeline [web:45][web:76].

## Scoring approach

Use a staged pipeline:

1. Hard gate for mandatory requirements.
2. Semantic match for relevance ranking.
3. Rubric score for transparent evaluation.
4. Human review for selected cases [web:28][web:76][web:68][web:90].

Recommended formulas:

Hard gate:
\\[\\text{HardGate}(c, j)=\\prod\_{m \\in M\_j} \\mathbf{1}[\\text{candidate } c \\text{ satisfies must-have } m]\\]
Use three states in implementation: pass, fail, unknown, so uncertain cases can go to human review instead of silent rejection [web:68][web:75].

Semantic match:
\\[\\text{Sim}\_x = \\cos(\\mathbf{v}^{R}\_x,\\mathbf{v}^{J}\_x)\\]
\\[\\text{SemanticMatch} = \\sum\_x w\_x \\cdot \\text{Sim}\_x\\]
Use section-aware embeddings for resume sections and job-description sections, then aggregate with weights [web:76][web:47][web:33].

Rubric score:
\\[\\text{RubricScore} = \\frac{\\sum\_{k=1}^{K} w\_k \\cdot r\_k}{\\sum\_{k=1}^{K} w\_k}\\]
Use 4 to 6 role-specific competencies with anchored numeric scales such as 0–5 or 1–5 [web:68][web:100][web:105].

Final score:
\\[\\text{FinalScore} = \\begin{cases} 0, & \\text{if HardGate}=0 \\\\ \\alpha \\cdot \\text{SemanticMatch} + \\beta \\cdot \\text{RubricScoreNorm} + \\gamma \\cdot \\text{EvidenceQuality}, & \\text{otherwise} \\end{cases}\\]
Normalize rubric score to 0–1 before combining it with semantic similarity [web:47][web:77]. A suggested starting blend already discussed is \\(\\alpha=0.45\\), \\(\\beta=0.45\\), \\(\\gamma=0.10\\) [conversation_history:1].

## Hard gate

Use hard gates only for true must-have requirements such as work authorization, required location policy, license, mandatory years of experience, or mandatory technologies [web:68][web:66]. Do not bury these inside the weighted score; treat them separately as explicit eligibility checks [web:63][web:68].

## Semantic match

Use a dual-tower or section-aware embedding approach for resume-job matching, based on transformer or sentence-embedding models [web:76][web:102]. Studies and implementations referenced so far use cosine similarity between embedding vectors and emphasize semantic compatibility rather than keyword-only matching [web:33][web:47][web:102]. The role of this layer is retrieval and relevance ranking, especially when equivalent phrasing is used across resumes and job descriptions [web:47][web:76].

## Rubric score

The rubric is the transparent decision layer [web:68][web:100]. Define role-specific competencies, numeric anchored scales, weights, and evidence notes [web:100][web:101][web:108]. The rubric should emphasize must-have skills more than nice-to-haves and should be calibrated and adjusted over time using hiring outcomes [web:101].

Suggested screening criteria already discussed:
- Core skills fit.
- Relevant experience depth.
- Scope and impact.
- Domain alignment.
- Education or certifications, only when genuinely relevant [conversation_history:1].

Suggested starting weights already discussed for software roles:
- Core skills fit: 0.30
- Relevant experience: 0.30
- Scope and impact: 0.20
- Domain alignment: 0.10
- Education/certifications: 0.10 [conversation_history:1]

## Human in the loop

Human oversight is required as a designed workflow, not as a symbolic approval step [web:90][web:93]. The agreed direction is that humans should review:
- Unknown or uncertain hard-gate outcomes.
- Borderline score bands.
- Low-confidence semantic matches.
- Unusual or nontraditional candidate profiles.
- Final rejection decisions [web:38][web:90][web:92].

Best practices already discussed:
- Use explicit escalation rules rather than asking humans to review everything [web:87][web:90].
- Show explanation-first review screens with AI score, confidence, hard-gate results, rubric breakdown, and matched evidence snippets [web:87][web:96].
- Require override reasons and log all overrides for audit and model tuning [web:87][web:96].
- Train reviewers to challenge the system rather than defer to it, because human oversight does not automatically remove bias [web:93][web:92].
- Monitor override behavior and fairness over time [web:90][web:96].

## Data and database direction

The current proposed schema includes these core entities:
- `jobs`
- `candidates`
- `applications`
- `gate_results`
- `section_embeddings`
- `rubric_scores`
- `final_scores`
- `reviews` [conversation_history:1]

Important stored fields include:
- Job must-haves and nice-to-haves as structured JSON.
- Parsed resume data as structured JSON.
- Gate result with result, confidence, reason, and evidence span.
- Section-level similarity scores.
- Criterion-level rubric score, weight, evidence, and scorer type.
- Final score components and recommendation.
- Human reviewer decision, notes, and override reason [conversation_history:1]

Use **PostgreSQL as the primary database and source of truth** [web:109][web:114][web:116]. The reason is that this application needs relational consistency, structured entities, audit trails, and transactional integrity for scoring and human overrides [web:109][web:119]. Use **pgvector** for embedding storage and similarity search, and use **native PostgreSQL full-text search** or a Postgres search extension for lexical matching [web:111][web:114][web:120].

The recommended database pattern is:
- PostgreSQL as the system of record.
- `pgvector` for vector similarity.
- Full-text search in Postgres for lexical search.
- Optional Elasticsearch only later, as a secondary search index if scale or search complexity requires it [web:124][web:127][web:132][web:135].

Do **not** use Elasticsearch as the primary database [web:127][web:135]. SQLite is suitable only for a local prototype, and TinyDB is not a fit for the decided architecture [conversation_history:1][web:121].

## Search strategy inside the database

For retrieval, prefer **hybrid search** that combines lexical and semantic retrieval instead of choosing one alone [web:124][web:128][web:136]. The discussed best practice is to run both retrieval methods in parallel and fuse the rankings, commonly with **Reciprocal Rank Fusion (RRF)** [web:111][web:114][web:136].

This means:
- Lexical search contributes exact-term precision.
- Semantic search contributes phrasing and intent recall.
- Fusion rewards documents endorsed by both signals [web:124][web:136].

Implementation details already supported by the sources:
- Store `tsvector` columns for indexed full-text search [web:111][web:114].
- Store embeddings in `pgvector` columns with ANN indexing such as HNSW [web:128][web:133].
- Start with a candidate pool around 20 per retrieval side and tune upward based on recall [web:111].
- Apply metadata filters consistently to both lexical and semantic subqueries [web:111].

## Evaluation plan

Evaluate each layer separately, then evaluate the full system [conversation_history:1].

Hard gate evaluation:
- Precision of exclusion decisions.
- False rejection rate.
- Unknown-to-review rate [conversation_history:1]

Semantic ranking evaluation:
- Recall@k.
- MRR.
- nDCG@k.
- Top-k shortlist agreement with recruiters [conversation_history:1][web:85]

Rubric evaluation:
- Inter-rater reliability between humans.
- Mean absolute error between automated and human rubric scores.
- Override rate by recruiters [conversation_history:1]

Fairness evaluation:
- Selection-rate ratios.
- False rejection rate by group.
- Pass-through rate after hard gate by group.
- Top-k representation drift relative to qualified pool [conversation_history:1][web:77]

Online evaluation:
- Start in shadow mode.
- Compare system outputs to recruiter decisions and later outcomes.
- Roll out with full override capability and reason capture [conversation_history:1]

## Implementation direction

The architecture already discussed is a split pipeline with:
- Parser service.
- Eligibility service.
- Embedding service.
- Scoring service.
- Review API/UI [conversation_history:1]

The implementation stack now suggested is:
- Python for parsing and extraction.
- PostgreSQL as the primary database.
- `pgvector` for embeddings.
- PostgreSQL full-text search for lexical retrieval.
- JSON-driven rules engine for hard gates.
- Review UI with side-by-side job and resume view plus evidence, scores, and overrides [conversation_history:1][web:111][web:114].

Elasticsearch is optional later as a secondary search engine, not a starting requirement [web:116][web:132][web:135].

## Key principle

The central decision made so far is: use the strongest semantic model as a component for semantic understanding and ranking, but keep final decision-making constrained by structured scoring, hard eligibility checks, targeted human review, and a PostgreSQL-centered architecture that preserves consistency and auditability [web:45][web:76][web:90][web:114].

Sources

[1] Human and LLM-Based Resume Matching: An Observational Study https://aclanthology.org/2025.findings-naacl.270/
[2] Transformer-Based Semantic Embedding Model for Resume-Job ... https://ideas.repec.org/a/axf/aidtaa/v3y2026i1p82-91.html
[3] HHS Office of Human Resources Guidance, Hiring Assessment ... https://www.hhs.gov/about/agencies/asa/ohr/hr-library/hiring-assessment-strategies.html
[4] Explainable AI in Hiring: Why Transparency Matters - ZYTHR https://zythr.com/resources/explainable-ai-in-hiring-why-transparency-matters
[5] The Human Oversight Paradox: Why People Mirror AI Bias Instead ... https://www.employers.ai/company/research/human-oversight-ai-hiring-bias
[6] Red Flags Vs Context: What... https://treegarden.io/blog/how-to-screen-resumes/
[7] Human-in-the-Loop Recruitment: Why AI... | Treegarden Blog https://treegarden.io/blog/human-oversight-ai-recruitment/
[8] Resume Screening Rubric Template: How to Score ... - HireSort https://hiresort.ai/blog/resume-screening-rubric-template
[9] Smart-Hiring: An Explainable end-to-end Pipeline for CV Information ... https://arxiv.org/html/2511.02537v1
[10] [PDF] Automated Resume Screening and Candidate Ranking Using ... https://liberteresearch.org/wp-content/uploads/3-LBRJ2941.pdf
[11] [PDF] Candidate Evaluation Rubric and Scorecard Overview - imgix https://kuow-prod.imgix.net/store/2204db3f96d6ec49eba7f87e8bbcbea2.pdf
[12] [PDF] How to Effectively Measure Competencies for Selection - OPM https://www.opm.gov/policy-data-oversight/assessment-and-selection/assessment-strategy/leveraging-assessments.pdf
[13] Libyan Open University Journal of Applied Sciences (LOUJAS) https://oujournals.ly/index.php/LOUJAS/article/download/42/35/67
[14] Resume to Job Description Match: Practical Guide - CVScouting https://cvscouting.com/resume-job-description-match
[15] Resume screening: a checklist to get it right - Hubert https://www.hubert.ai/insights/resume-screening-a-checklist-to-get-it-right
[16] Resume Screening API: Score Every Resume ... - TalentSprout https://www.talentsprout.ai/resume-screening-api
[17] [PDF] Machine Learning Techniques for Matching Candidates' Profiles ... https://openreview.net/pdf/e5dcf82cf16f348ed2f5bc097e8d287c4e8e9fe9.pdf
[18] elements to include in an... https://www.aihr.com/blog/interview-rubric/
[19] Remove bias from your interview rubric - VidCruiter https://vidcruiter.com/interview/structured/interview-rubric/
[20] Fair hiring in the age of AI: How to reduce bias in resume screening https://mihcm.com/resources/blog/fair-hiring-in-the-age-of-ai-how-to-reduce-bias-in-resume-screening/
[21] 7 Best Practices for Employers Using AI Resume Screeners https://www.fisherphillips.com/en/insights/insights/7-best-practices-for-employers-using-ai-resume-screeners
[22] How to Advocate for Human Oversight in AI Tools https://www.resumly.ai/blog/how-to-advocate-for-human-oversight-in-ai-tools
[23] NLP-Powered Resume Screening and Ranking System - UPDF AI https://ai.updf.com/hk/paper-detail/nlp-powered-resume-screening-and-ranking-system-dharmendra-meenakshi-9fddd7234dd0f0d2e707152b35fe6135113b7f63
[24] Do LLM-Generated Resumes Make Me More Qualified? An ... https://conf.researchr.org/details/vlhcc-2025/vlhcc-2025-workshops-and-tutorials/20/Do-LLM-Generated-Resumes-Make-Me-More-Qualified-An-Observational-Study-of-LLMs-For-R
[25] [PDF] Human and LLM-Based Resume Matching: An Observational Study https://yoseph.et/assets/pdf/NAACL_2025.pdf
[26] Guide To Scoring Rubrics & Fair Hiring In MENA - Evalufy https://www.evalufy.com/blog/candidate-assessment-selection/structured-interviews-scoring-rubrics-consistency-checks-mena/
[27] Measuring Validity in LLM-based Resume Screening - arXiv https://arxiv.org/html/2602.18550v1
[28] On Using LLM's for Matching Resumes - LinkedIn https://www.linkedin.com/pulse/using-llms-matching-resumes-glen-cathey-xrxje
[29] ADVANCED AI BASED RESUME SCREENING https://www.lingayasvidyapeeth.edu.in/IJISIE/papers/vol1_1/5.pdf


