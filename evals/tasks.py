# evals/tasks.py
# Inspect AI Task definitions for koan evals.

from inspect_ai import Task, task

from evals.dataset import load_dataset
from evals.scorers import memory_relevance, plan_specificity, question_quality
from evals.solver import koan_solver


@task
def koan_plan_eval() -> Task:
    """Full-run koan plan workflow eval."""
    return Task(
        dataset=load_dataset(),
        solver=koan_solver(),
        scorer=[plan_specificity(), question_quality(), memory_relevance()],
    )
