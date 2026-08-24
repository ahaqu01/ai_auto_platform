from platform_api.openapi_policy import forbidden_identity_inputs


def test_export_policy_recurses_into_refs_and_ignores_response_fields() -> None:
    document = {
        "paths": {
            "/example": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Input"}
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"user_id": {"type": "string"}},
                                    }
                                }
                            }
                        }
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "Input": {
                    "oneOf": [
                        {
                            "type": "object",
                            "properties": {"Owner-Id": {"type": "string"}},
                        }
                    ]
                }
            }
        },
    }

    assert forbidden_identity_inputs(document) == {
        ("post", "/example", "body", "owner_id")
    }


def test_export_policy_exceptions_are_scoped_to_exact_operation_and_location() -> None:
    document = {
        "paths": {
            "/approved": {
                "post": {
                    "parameters": [
                        {
                            "in": "header",
                            "name": "subject",
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"204": {"description": "ok"}},
                }
            },
            "/not-approved": {
                "post": {
                    "parameters": [
                        {
                            "in": "header",
                            "name": "subject",
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"204": {"description": "ok"}},
                }
            },
        }
    }
    approved = {("post", "/approved", "header", "subject")}

    assert forbidden_identity_inputs(document, approved) == {
        ("post", "/not-approved", "header", "subject")
    }
