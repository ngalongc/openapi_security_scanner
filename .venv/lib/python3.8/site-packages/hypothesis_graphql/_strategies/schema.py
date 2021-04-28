"""Strategies are based on ANTLR4 grammar.

https://github.com/antlr/grammars-v4/blob/master/graphql/GraphQL.g4
"""
import string
from typing import Any, Optional, Tuple

from hypothesis import strategies as st


def schema(min_definitions: int = 1, max_definitions: int = 10) -> st.SearchStrategy[str]:
    # definition+;
    return st.lists(definition(), min_size=min_definitions, max_size=max_definitions).map("\n".join)


def definition() -> st.SearchStrategy[str]:
    # executableDefinition
    # 	| typeSystemDefinition
    # 	| typeSystemExtension;
    return st.one_of(
        typesystem_definition(),
    )


def typesystem_definition() -> st.SearchStrategy[str]:
    # schemaDefinition
    # 	| typeDefinition
    # 	| directiveDefinition
    # 	;
    return st.one_of(type_definition())


def type_definition() -> st.SearchStrategy[str]:
    # scalarTypeDefinition
    # 	| objectTypeDefinition
    # 	| interfaceTypeDefinition
    # 	| unionTypeDefinition
    # 	| enumTypeDefinition
    # 	| inputObjectTypeDefinition;
    return st.one_of(scalar_typedef(), object_typedef())


def scalar_typedef() -> st.SearchStrategy[str]:
    # description? 'scalar' name directives?

    def format_scalar(item: Tuple[Optional[str], str, Optional[str]]) -> str:
        return f"{item[0] or ''} scalar {item[1]} {item[2] or ''}".strip()

    return st.tuples(DESCRIPTION | st.none(), name(), directives() | st.none()).map(format_scalar)  # type: ignore


STRING = st.text(alphabet=string.ascii_letters).map('"{}"'.format)
BLOCK_STRING = st.text(alphabet=string.ascii_letters).map('"""{}"""'.format)
STRING_VALUE = STRING | BLOCK_STRING
DESCRIPTION = STRING_VALUE

FIRST_LETTER = string.ascii_letters + "_"
NON_FIRST_LETTER = FIRST_LETTER + string.digits


def name() -> st.SearchStrategy[str]:
    # [_A-Za-z] [_0-9A-Za-z]*
    return st.tuples(st.sampled_from(FIRST_LETTER), st.text(alphabet=NON_FIRST_LETTER)).map(lambda x: "{}{}".format(*x))


def directives() -> st.SearchStrategy[str]:
    # directive+;
    # Take only one directive, since in the core there are only "include" and "skip" which
    return directive()


def directive() -> st.SearchStrategy[str]:
    # '@' name arguments?;
    # TODO. restrict to "if: Boolean"

    def format_directive(item: Tuple[str, Optional[str]]) -> str:
        return f"@{item[0]} {item[1] or ''}".strip()

    return st.tuples(st.sampled_from(("include", "skip")), arguments() | st.none()).map(format_directive)  # type: ignore


def arguments() -> st.SearchStrategy[str]:
    # '(' argument+ ')';
    return st.lists(argument(), min_size=1).map(lambda x: "({})".format(", ".join(x)))


def argument() -> st.SearchStrategy[str]:
    # name ':' value;
    return st.tuples(name(), value()).map(lambda x: "{}:{}".format(*x))


def value() -> st.SearchStrategy[int]:
    # variable
    # 	| intValue
    # 	| floatValue
    # 	| stringValue
    # 	| booleanValue
    # 	| nullValue
    # 	| enumValue
    # 	| listValue
    # 	| objectValue
    #    ;
    return st.integers()


def object_typedef() -> st.SearchStrategy[str]:
    # description?   'type' name implementsInterfaces?  directives? fieldsDefinition?

    def format_object_typedef(item: Tuple[Optional[str], str, Optional[str], Optional[str], Optional[str]]) -> str:
        return f"{item[0] or ''} type {item[1]} {item[2] or ''} {item[3] or ''} {item[4] or ''}".strip().replace(
            "  ", " "
        )

    return st.tuples(
        DESCRIPTION | st.none(),
        name(),
        implements_interfaces() | st.none(),
        directives() | st.none(),
        fields_definition() | st.none(),
    ).map(
        format_object_typedef  # type: ignore
    )


@st.composite  # type: ignore
def implements_interfaces(draw: Any) -> Any:
    # 'implements' '&'? namedType | implementsInterfaces '&' namedType
    # TODO. namedType should be defined in the document
    def format_implements_interfaces(item: Tuple[Optional[str], str]) -> str:
        return f"implements {item[0] or ''} {item[1]}".replace("  ", " ")

    first = draw(st.tuples(st.just("&") | st.none(), name()).map(format_implements_interfaces))  # type: ignore
    types = " & ".join(draw(st.lists(name())))
    if types:
        types = f"& {types}"
    return f"{first} {types}".strip()


def fields_definition() -> st.SearchStrategy[str]:
    # '{' fieldDefinition+ '}';
    # TODO. names should be unique
    return st.lists(field_definition(), min_size=1).map(lambda item: "{{ {} }}".format(" ".join(item)))


def field_definition() -> st.SearchStrategy[str]:
    # description? name  argumentsDefinition? ':' type_  directives? ;

    def format_field_definition(item: Tuple[Optional[str], str, Optional[str], str, Optional[str]]) -> str:
        return f"{item[0] or ''} {item[1]} {item[2] or ''} : {item[3]} {item[4] or ''}".strip().replace("  ", " ")

    return st.tuples(
        DESCRIPTION | st.none(), name(), arguments_definition() | st.none(), TYPE, directives() | st.none()
    ).map(
        format_field_definition  # type: ignore
    )


def arguments_definition() -> st.SearchStrategy[str]:
    # '(' inputValueDefinition+ ')'
    return st.lists(input_value_definition(), min_size=1).map(lambda item: "( {} )".format(" ".join(item)))


def input_value_definition() -> st.SearchStrategy[str]:
    # description? name ':' type_ defaultValue? directives?;

    def format_input_value_definition(item: Tuple[Optional[str], str, str, Optional[str], Optional[str]]) -> str:
        return f"{item[0] or ''} {item[1]} : {item[2]} {item[3] or ''} {item[4] or ''}".strip().replace("  ", " ")

    # TODO. defaultvalue should match type
    return st.tuples(DESCRIPTION | st.none(), name(), TYPE, default_value() | st.none(), directives() | st.none(),).map(
        format_input_value_definition  # type: ignore
    )


def default_value() -> st.SearchStrategy[str]:
    # '=' value;
    return value().map("={}".format)


NAMED_TYPE = name()
# '[' type_ ']';
LIST_TYPE = st.deferred(lambda: TYPE.map("[{}]".format))
# namedType '!'?
#     | listType '!'?
#     ;
TYPE: st.SearchStrategy[str] = st.deferred(
    lambda: st.tuples(NAMED_TYPE, st.just("!") | st.none()).map(lambda item: f"{item[0]}{item[1] or ''}") | LIST_TYPE
)
