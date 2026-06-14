# Carlos
I want you to search for studies and best practices on how to add human in the loop in this context

---
# Perplexity
Yes — there is a clear body of guidance on human-in-the-loop for AI-assisted resume screening, and the consensus is that humans should review **borderline, low-confidence, and high-risk** cases rather than rubber-stamp model outputs. The strongest best practices also stress explanation-first review, override logging, bias audits, and reviewer training, because simply “adding a human” does not automatically fix bias.[1][2][3][4][5]

## Where humans intervene

The safest pattern is to use AI to prioritize and summarize, then place human checkpoints at the moments where judgment, fairness, or context matter most. Recommended intervention points are:[2][6]

- Review all hard-gate failures marked uncertain or based on incomplete evidence.[4][7]
- Review borderline score bands and low-confidence semantic matches.[3][1]
- Review unusual profiles, nontraditional backgrounds, or resumes with sparse but promising evidence.[2][4]
- Reserve final shortlist confirmation and rejection communication for humans.[6][8][4]

## Oversight design

The best implementation pattern is not “human approves every score,” but “human reviews cases selected by explicit escalation rules”. Good rules include score-band routing, confidence thresholds, fairness triggers, and mandatory review for roles with high legal or business risk.[7][1][3][2]

A practical workflow is:
1. AI scores all candidates and generates evidence summaries.[1][7]
2. Clear strong matches can be advanced to recruiter review queues, not auto-hired.[4][6]
3. Borderline and uncertain cases go to blinded human review with explanation panels.[3][2]
4. Reviewer decisions, rationale, and overrides are logged for later audit and model tuning.[9][1]

## Reviewer interface

Studies and implementation guides consistently point to explanation-centered review interfaces rather than bare scores. The reviewer should see:[10][1]

- The AI score and confidence.
- The matched evidence snippets from the resume and job description.
- Which hard gates passed, failed, or were unknown.
- The rubric breakdown by criterion.
- A required rationale field for override decisions.[9][1][3]

One especially useful practice is to prevent batch approval and require reviewers to engage with the explanation before confirming, because this reduces passive overreliance on the system. Another is to blind irrelevant signals during review, which helps recruiters focus on job-related evidence instead of demographic or prestige proxies.[2][3]

## Training and governance

Human oversight works only when reviewers are trained to challenge the system, not defer to it. Best practices include training on model limitations, explanation interpretation, fairness risks, and examples of false positives and false negatives.[5][1][4]

Governance should include:
- Regular bias audits and outcome monitoring.[11][4]
- Override-rate monitoring to detect rubber-stamping, with one source suggesting investigation if overrides fall below 5%.[3]
- Quarterly review of reviewer notes, escalation patterns, and false-rejection cases.[7][9]
- Candidate transparency on how AI and human review are used in the process.[12][4]

## Recommended design

For your architecture, the best human-in-the-loop design is:

- AI handles parsing, hard-gate prechecks, semantic ranking, and draft rubric suggestions.[1][7]
- Humans review all unknown hard-gate outcomes, all borderline bands, and all final rejection decisions.[4][2]
- The UI forces evidence review, captures override reasons, and supports blinded review for sensitive stages.[9][3]
- Monitoring tracks fairness, false rejections, override quality, and reviewer consistency over time.[5][10]

A good operating principle is: humans should intervene where the model is uncertain, where the decision is consequential, or where bias is most likely to hide.[5][2]

Sources
[1] Explainable AI in Hiring: Why Transparency Matters - ZYTHR https://zythr.com/resources/explainable-ai-in-hiring-why-transparency-matters
[2] Fair hiring in the age of AI: How to reduce bias in resume screening https://mihcm.com/resources/blog/fair-hiring-in-the-age-of-ai-how-to-reduce-bias-in-resume-screening/
[3] Human-in-the-Loop Recruitment: Why AI... | Treegarden Blog https://treegarden.io/blog/human-oversight-ai-recruitment/
[4] 7 Best Practices for Employers Using AI Resume Screeners https://www.fisherphillips.com/en/insights/insights/7-best-practices-for-employers-using-ai-resume-screeners
[5] The Human Oversight Paradox: Why People Mirror AI Bias Instead ... https://www.employers.ai/company/research/human-oversight-ai-hiring-bias
[6] Human-in-the-Loop: Keeping recruiters in control of AI-Driven ... https://www.sourcegeek.com/en/news/human-in-the-loop-keeping-recruiters-in-control-of-ai-driven-recruitment
[7] How AI Transforms Mass Candidate Screening for Faster, Fairer Hiring https://everworker.ai/blog/ai_mass_candidate_screening_faster_fairer_hiring
[8] Hiring with AI doesn't have to be so inhumane. Here's how https://www.weforum.org/stories/2025/03/ai-hiring-human-touch-recruitment/
[9] How to Advocate for Human Oversight in AI Tools https://www.resumly.ai/blog/how-to-advocate-for-human-oversight-in-ai-tools
[10] Libyan Open University Journal of Applied Sciences (LOUJAS) https://oujournals.ly/index.php/LOUJAS/article/download/42/35/67
[11] AI hiring tools may be filtering out the best job applicants https://www.bbc.com/worklife/article/20240214-ai-recruiting-hiring-software-bias-discrimination
[12] AI Bias Reduction in Resume Screening - LinkedIn https://www.linkedin.com/top-content/recruitment-hr/using-ai-in-recruitment/ai-bias-reduction-in-resume-screening/
[13] Using AI to Boost Diversity in Hiring: An HR Guide (Part 5) https://www.linkedin.com/pulse/using-ai-boost-diversity-hiring-hr-guide-part-5-rebecca-peterson-phd
[14] Driven Resume Screening and Skill Assessment https://www.ijfmr.com/papers/2025/4/52621.pdf
[15] Why Human in the Loop Improves Prediction Quality https://www.resumly.ai/blog/why-human-in-the-loop-improves-prediction-quality
---