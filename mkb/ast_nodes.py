# mkb/ast_nodes.py

from dataclasses import dataclass, field
from typing import List

@dataclass
class ASTNode:
    line: int = 0
    col: int = 0

@dataclass
class ProgramNode(ASTNode):
    statements: List[ASTNode] = field(default_factory=list)

@dataclass
class ImportNode(ASTNode):
    module_name: str = ""

@dataclass
class FunctionDefNode(ASTNode):
    name: str = ""
    params: List[str] = field(default_factory=list)
    body: List[ASTNode] = field(default_factory=list)

@dataclass
class FunctionCallNode(ASTNode):
    name: str = ""
    args: List[str] = field(default_factory=list)

@dataclass
class StatementNode(ASTNode):
    text: str = ""

@dataclass
class CommentNode(ASTNode):
    text: str = ""
