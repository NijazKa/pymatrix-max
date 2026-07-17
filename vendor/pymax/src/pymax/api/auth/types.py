from typing import Final, TypeAlias


class MissingType:
    __slots__ = ()

    def __repr__(self) -> str:
        return "MISSING"


MISSING: Final = MissingType()

Missing: TypeAlias = MissingType
