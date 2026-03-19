"""
Base class for skills (pluggable tool bundles).

A Skill is a named collection of related tools that can be registered with
the agent as a unit. Think of them as "plugins" or "skill packs".

Example usage::

    class GitSkill(BaseSkill):
        name = "git"
        description = "Git operations: commit, push, pull, status, etc."

        def get_tools(self) -> list[BaseTool]:
            return [GitStatusTool(), GitCommitTool(), GitPushTool()]

    agent.register_skill(GitSkill())
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from agent.tools.base import BaseTool


class BaseSkill(ABC):
    """Abstract base class for agent skills."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique skill name."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this skill provides."""

    @abstractmethod
    def get_tools(self) -> list[BaseTool]:
        """Return the list of tools provided by this skill."""

    def __repr__(self) -> str:
        return f"<Skill '{self.name}': {len(self.get_tools())} tools>"
