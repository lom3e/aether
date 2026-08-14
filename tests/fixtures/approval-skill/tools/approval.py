from aether.core.interrupts import RequireApproval
from aether.tools.base import Tool


class ApprovalTool(Tool):
    name = "approval_tool"
    description = "Requests a human approval before continuing."

    def execute(self, input_data: str, context=None) -> str:
        raise RequireApproval("The workforce wants to perform a protected action. Approve it?")


def register(registry: object, context: dict) -> None:
    registry.register(ApprovalTool())
