from fastapi import APIRouter

from simulation.models import Design, Evaluation

from backend.app.deps import ContainerDep

router = APIRouter(tags=["design"])


@router.post("/evaluate", response_model=Evaluation)
def evaluate(design: Design, container: ContainerDep) -> Evaluation:
    """Check a design. Stateless; accepts partial designs; no login needed.

    An infeasible design is a normal 200 result with failed constraints.
    """
    return container.runs.evaluate(design)
