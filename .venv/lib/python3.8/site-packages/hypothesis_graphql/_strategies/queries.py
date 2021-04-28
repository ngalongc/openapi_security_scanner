"""Strategies for GraphQL queries."""
from functools import partial
from typing import Callable, List, Optional, Tuple, Union

import graphql
from graphql.pyutils import FrozenList
from hypothesis import strategies as st

from ..types import Field, InputTypeNode
from . import primitives


def query(schema: Union[str, graphql.GraphQLSchema]) -> st.SearchStrategy[str]:
    """A strategy for generating valid queries for the given GraphQL schema."""
    if isinstance(schema, str):
        parsed_schema = graphql.build_schema(schema)
    else:
        parsed_schema = schema
    if parsed_schema.query_type is None:
        raise ValueError("Query type is not defined in the schema")
    return fields(parsed_schema.query_type).map(make_query).map(graphql.print_ast)


def fields(object_type: graphql.GraphQLObjectType) -> st.SearchStrategy[List[graphql.FieldNode]]:
    """Generate a subset of fields defined on the given type."""
    # minimum 1 field, an empty query is not valid
    return subset_of_fields(**object_type.fields).flatmap(lists_of_field_nodes)


make_selection_set_node = partial(graphql.SelectionSetNode, kind="selection_set")


def make_query(selections: List[graphql.FieldNode]) -> graphql.DocumentNode:
    """Create top-level node for a query AST."""
    return graphql.DocumentNode(  # type: ignore
        kind="document",
        definitions=[
            graphql.OperationDefinitionNode(
                kind="operation_definition",
                operation=graphql.OperationType.QUERY,
                selection_set=make_selection_set_node(selections=selections),
            )
        ],
    )


def field_nodes(name: str, field: graphql.GraphQLField) -> st.SearchStrategy[graphql.FieldNode]:
    """Generate a single field node with optional children."""
    return st.builds(
        partial(graphql.FieldNode, name=graphql.NameNode(value=name)),  # type: ignore
        arguments=list_of_arguments(**field.args),
        selection_set=st.builds(make_selection_set_node, selections=fields_for_type(field)),
    )


def fields_for_type(field: graphql.GraphQLField) -> st.SearchStrategy[Optional[List[graphql.FieldNode]]]:
    """Extract proper type from the field and generate field nodes for this type."""
    type_ = field.type
    while isinstance(type_, graphql.GraphQLWrappingType):
        type_ = type_.of_type
    if isinstance(type_, graphql.GraphQLObjectType):
        return fields(type_)
    # Only object has field, others don't
    return st.none()


def list_of_arguments(**kwargs: graphql.GraphQLArgument) -> st.SearchStrategy[List[graphql.ArgumentNode]]:
    """Generate a list `graphql.ArgumentNode` for a field."""
    args = []
    for name, argument in kwargs.items():
        try:
            argument_strategy = argument_values(argument)
        except TypeError as exc:
            if not isinstance(argument.type, graphql.GraphQLNonNull):
                continue
            raise TypeError("Non-nullable custom scalar types are not supported as arguments") from exc
        args.append(
            st.builds(
                partial(graphql.ArgumentNode, name=graphql.NameNode(value=name)), value=argument_strategy  # type: ignore
            )
        )
    return st.tuples(*args).map(finalize_arguments)


def finalize_arguments(nodes: Tuple[graphql.ArgumentNode, ...]) -> List[graphql.ArgumentNode]:
    """Nodes might be generated with empty values, and they should be removed from the output."""
    return [remove_empty(node) for node in nodes if not is_empty(node.value)]


def is_empty(node: graphql.ValueNode) -> bool:
    # The checked values often can't be None, but generated as such.
    # It will be better if this value won't be generated at all,
    # but in this case argument node shouldn't be generated as well - there might be some better way to handle
    # empty arguments without overriding actual node types (example - what if `None` is actually a valid value?)
    if isinstance(
        node,
        (
            graphql.IntValueNode,
            graphql.FloatValueNode,
            graphql.StringValueNode,
            graphql.BooleanValueNode,
            graphql.EnumValueNode,
        ),
    ):
        return node.value is None
    if isinstance(node, graphql.ListValueNode):
        return node.values is None
    if isinstance(node, graphql.ObjectValueNode):
        return node.fields is None
    # VariableNode or NullValueNode
    return False


def remove_empty(node: graphql.ArgumentNode) -> graphql.ArgumentNode:
    """Remove empty children from list nodes."""
    _remove_empty(node.value)
    return node


def _remove_empty(node: graphql.ValueNode) -> graphql.ValueNode:
    """Recursive part for removing empty child nodes."""
    if isinstance(node, graphql.ListValueNode) and node.values is not None:
        node.values = FrozenList([_remove_empty(node) for node in node.values if not is_empty(node)])
    return node


def argument_values(argument: graphql.GraphQLArgument) -> st.SearchStrategy[InputTypeNode]:
    """Value of `graphql.ArgumentNode`."""
    return value_nodes(argument.type)


def value_nodes(type_: graphql.GraphQLInputType) -> st.SearchStrategy[InputTypeNode]:
    """Generate value nodes of a type, that corresponds to the input type.

    They correspond to all `GraphQLInputType` variants:
        - GraphQLScalarType -> ScalarValueNode
        - GraphQLEnumType -> EnumValueNode
        - GraphQLInputObjectType -> ObjectValueNode

    GraphQLWrappingType[T] is unwrapped:
        - GraphQLList -> ListValueNode[T]
        - GraphQLNonNull -> T (processed with nullable=False)
    """
    type_, nullable = check_nullable(type_)
    # Types without children
    if isinstance(type_, graphql.GraphQLScalarType):
        return primitives.scalar(type_, nullable)
    if isinstance(type_, graphql.GraphQLEnumType):
        return primitives.enum(type_, nullable)
    # Types with children
    if isinstance(type_, graphql.GraphQLList):
        return lists(type_, nullable)
    if isinstance(type_, graphql.GraphQLInputObjectType):
        return objects(type_, nullable)
    raise TypeError(f"Type {type_.__class__.__name__} is not supported.")


def check_nullable(type_: graphql.GraphQLInputType) -> Tuple[graphql.GraphQLInputType, bool]:
    """Get the wrapped type and detect if it is nullable."""
    nullable = True
    if isinstance(type_, graphql.GraphQLNonNull):
        type_ = type_.of_type
        nullable = False
    return type_, nullable


def lists(type_: graphql.GraphQLList, nullable: bool = True) -> st.SearchStrategy[graphql.ListValueNode]:
    """Generate a `graphql.ListValueNode`."""
    type_ = type_.of_type
    list_value = st.lists(value_nodes(type_))
    if nullable:
        list_value |= st.none()
    return st.builds(graphql.ListValueNode, values=list_value)


def objects(type_: graphql.GraphQLInputObjectType, nullable: bool = True) -> st.SearchStrategy[graphql.ObjectValueNode]:
    """Generate a `graphql.ObjectValueNode`."""
    fields_value = subset_of_fields(**type_.fields).flatmap(list_of_object_field_nodes)
    if nullable:
        fields_value |= st.none()
    return st.builds(graphql.ObjectValueNode, fields=fields_value)


def subset_of_fields(**all_fields: Field) -> st.SearchStrategy[List[Tuple[str, Field]]]:
    """A helper to select a subset of fields."""
    field_pairs = sorted(all_fields.items())
    # pairs are unique by field name
    return st.lists(st.sampled_from(field_pairs), min_size=1, unique_by=lambda x: x[0])


def object_field_nodes(name: str, field: graphql.GraphQLInputField) -> st.SearchStrategy[graphql.ObjectFieldNode]:
    return st.builds(
        partial(graphql.ObjectFieldNode, name=graphql.NameNode(value=name)),  # type: ignore
        value=value_nodes(field.type),
    )


def list_of_nodes(
    items: List[Tuple],
    strategy: Callable[[str, Field], st.SearchStrategy],
) -> st.SearchStrategy[List]:
    return st.tuples(*(strategy(name, field) for name, field in items)).map(list)


list_of_object_field_nodes = partial(list_of_nodes, strategy=object_field_nodes)
lists_of_field_nodes = partial(list_of_nodes, strategy=field_nodes)
