"""Recipe contracts that shape grounded editorial outputs."""

from vidsnap.recipes.render import InterviewRecipeArtifacts, render_interview_recipe
from vidsnap.recipes.runner import InterviewRecipeRunner, InterviewRecipeRunResult
from vidsnap.recipes.task import InterviewRecipeTaskAdapter

__all__ = [
    "InterviewRecipeArtifacts",
    "InterviewRecipeRunner",
    "InterviewRecipeRunResult",
    "InterviewRecipeTaskAdapter",
    "render_interview_recipe",
]
