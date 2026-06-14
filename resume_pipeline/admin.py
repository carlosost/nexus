from django.contrib import admin

from resume_pipeline.models import (
    Application,
    Candidate,
    FinalScore,
    HardGateResult,
    HumanReview,
    Job,
    JobSectionEmbedding,
    RubricScore,
    SemanticMatchResult,
    SectionEmbedding,
)

admin.site.register(Job)
admin.site.register(Candidate)
admin.site.register(Application)
admin.site.register(HardGateResult)
admin.site.register(SectionEmbedding)
admin.site.register(JobSectionEmbedding)
admin.site.register(SemanticMatchResult)
admin.site.register(RubricScore)
admin.site.register(FinalScore)
admin.site.register(HumanReview)
