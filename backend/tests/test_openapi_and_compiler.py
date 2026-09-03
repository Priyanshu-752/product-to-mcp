from product_to_mcp.compiler.manifest import compile_tools
from product_to_mcp.openapi.operations import discover_operations
from product_to_mcp.openapi.parser import parse_document


def test_discovers_crud_tools_and_request_body_schema() -> None:
    document = parse_document(b"""
openapi: 3.0.3
info: {title: Demo, version: '1'}
paths:
  /products/{id}:
    get:
      operationId: getProduct
      parameters:
        - {name: id, in: path, required: true, schema: {type: string}}
      responses: {'200': {description: ok}}
    delete:
      operationId: deleteProduct
      responses: {'204': {description: deleted}}
    post:
      operationId: createProduct
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [name]
              properties:
                name: {type: string}
                price: {type: number}
      responses: {'201': {description: created}}
""")
    operations = discover_operations(document)
    assert [item.tool_name for item in operations] == ["getproduct", "createproduct", "deleteproduct"]
    assert operations[0].supported is True
    assert operations[1].supported is True
    assert operations[1].input_schema["properties"]["body"]["required"] == ["name"]
    assert operations[2].supported is True
    tools = compile_tools(operations, ("getProduct", "createProduct", "deleteProduct"))
    assert tools[0].path == "/products/{id}"
    assert tools[0].input_schema["required"] == ["id"]
    assert tools[1].method == "POST"
    assert tools[1].input_schema["required"] == ["body"]


def test_invalid_document_is_rejected() -> None:
    try:
        parse_document(b"not an openapi document")
    except Exception as error:
        assert "OpenAPI" in str(error)
    else:
        raise AssertionError("invalid document was accepted")
