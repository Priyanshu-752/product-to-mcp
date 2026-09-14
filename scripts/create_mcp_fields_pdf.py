from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "pdf" / "product-to-mcp-user-fields-checklist.pdf"


class Rule(Flowable):
    def __init__(self, color=colors.HexColor("#D7DEE8"), width=1):
        super().__init__()
        self.color = color
        self.width = width

    def wrap(self, avail_width, avail_height):
        self.avail_width = avail_width
        return avail_width, 8

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.width)
        self.canv.line(0, 4, self.avail_width, 4)


def styles():
    base = getSampleStyleSheet()
    base.add(
        ParagraphStyle(
            name="TitleCustom",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=27,
            textColor=colors.HexColor("#162033"),
            spaceAfter=8,
            alignment=TA_LEFT,
        )
    )
    base.add(
        ParagraphStyle(
            name="Subtitle",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=15,
            textColor=colors.HexColor("#42526B"),
            spaceAfter=16,
        )
    )
    base.add(
        ParagraphStyle(
            name="Section",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#1E2A3A"),
            spaceBefore=12,
            spaceAfter=7,
        )
    )
    base.add(
        ParagraphStyle(
            name="Small",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8.2,
            leading=11,
            textColor=colors.HexColor("#526173"),
        )
    )
    base.add(
        ParagraphStyle(
            name="BodyCustom",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.4,
            leading=13,
            textColor=colors.HexColor("#263445"),
            spaceAfter=5,
        )
    )
    base.add(
        ParagraphStyle(
            name="Cell",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8.2,
            leading=10.5,
            textColor=colors.HexColor("#263445"),
        )
    )
    base.add(
        ParagraphStyle(
            name="CellBold",
            parent=base["Cell"],
            fontName="Helvetica-Bold",
            textColor=colors.HexColor("#1E2A3A"),
        )
    )
    base.add(
        ParagraphStyle(
            name="CodeBlock",
            parent=base["BodyText"],
            fontName="Courier",
            fontSize=7.4,
            leading=10,
            textColor=colors.HexColor("#25364A"),
        )
    )
    return base


S = styles()


def p(text: str, style: str = "BodyCustom") -> Paragraph:
    return Paragraph(text, S[style])


def table(rows: list[list[str]], widths: list[float] | None = None) -> Table:
    data = []
    for index, row in enumerate(rows):
        style = "CellBold" if index == 0 else "Cell"
        data.append([p(cell, style) for cell in row])
    tbl = Table(data, colWidths=widths, hAlign="LEFT", repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF0F8")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1E2A3A")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D7DEE8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFBFD")]),
            ]
        )
    )
    return tbl


def bullets(items: list[str]) -> list[Paragraph]:
    return [p(f"- {item}", "BodyCustom") for item in items]


def section(title: str, body: list) -> list:
    return [p(title, "Section"), *body, Spacer(1, 5)]


def code_block(text: str) -> Table:
    lines = "<br/>".join(text.splitlines())
    tbl = Table([[p(lines, "CodeBlock")]], colWidths=[170 * mm], hAlign="LEFT")
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F7FB")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D7DEE8")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return tbl


def header_footer(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#6B778C"))
    canvas.drawString(18 * mm, 12 * mm, "Product-to-MCP field handoff")
    canvas.drawRightString(width - 18 * mm, 12 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_story() -> list:
    field_widths = [45 * mm, 24 * mm, 101 * mm]
    value_widths = [55 * mm, 115 * mm]
    story: list = [
        p("Product-to-MCP User Fields Checklist", "TitleCustom"),
        p(
            "Shareable step-wise intake fields for creating, testing, deploying, and publishing an MCP server from a product API.",
            "Subtitle",
        ),
        Rule(),
        Spacer(1, 7),
        p("One-line flow", "Section"),
        code_block(
            "Project details -> API auth -> OpenAPI upload -> review operations -> create actions -> "
            "validate/approve actions -> create publishing profile -> generate MCP release -> test tools -> "
            "deploy public HTTPS backend -> publish to Smithery"
        ),
        Spacer(1, 8),
    ]

    story += section(
        "Step 1: Product/API Setup",
        [
            table(
                [
                    ["Field", "Required", "Notes"],
                    ["Project name", "Yes", "Example: Demo Store"],
                    ["API base URL", "Yes", "Stable API root, not one endpoint. Example: https://api.customer.com/v1"],
                    ["Authentication type", "Yes", "Bearer token, API key header, or No authentication"],
                    ["Upstream API key/token", "If auth is not none", "Stored server-side; never shown in MCP tool schema"],
                    ["Credential header", "If auth is not none", "Example: Authorization, x-api-key"],
                ],
                field_widths,
            )
        ],
    )

    story += section(
        "Step 2: OpenAPI Import",
        [
            table(
                [
                    ["Field", "Required", "Notes"],
                    ["OpenAPI file", "Yes", "OpenAPI 3.0/3.1 JSON or YAML"],
                    ["OpenAPI paste content", "Optional", "Backend supports file upload or raw content"],
                    ["API environment/version", "Recommended", "Example: production, staging, v1"],
                    ["Operations business meaning", "Recommended", "Needed when OpenAPI descriptions are unclear"],
                ],
                field_widths,
            ),
            Spacer(1, 5),
            table(
                [
                    ["System Generated Value", "Notes"],
                    ["Operations", "Methods, paths, params, schemas"],
                    ["Operation groups", "Auto-grouped from tags/path"],
                    ["Supported/unsupported status", "Unsupported operations are shown, not guessed"],
                ],
                value_widths,
            ),
        ],
    )

    story += section(
        "Step 3: Action Studio",
        [
            p("The user selects and configures what the agent can actually use."),
            table(
                [
                    ["Field", "Required", "Notes"],
                    ["Operation group name", "Optional", "Can rename discovered groups"],
                    ["Hidden groups", "Optional", "Hide irrelevant operation groups"],
                    ["Selected operation(s)", "Yes", "One action can use one or more approved API operations"],
                    ["Tool/action name", "Yes", "Lowercase snake case, max 64 chars. Example: get_product"],
                    ["Action title", "Yes", "Human-readable name"],
                    ["Action description", "Yes", "What the tool does"],
                    ["Agent input schema", "Yes", "JSON Schema for what the agent can pass"],
                    ["Action data/output schema", "Yes", "JSON Schema for action result"],
                    ["Execution steps", "Yes", "Ordered API steps"],
                    ["Argument bindings", "Yes", "Maps agent input, previous step output, or constants to API params/body"],
                    ["Run condition", "Optional", "For multi-step actions"],
                    ["Normalized output fields", "Optional", "Select exact fields returned to agent"],
                    ["Test arguments JSON", "Recommended", "Used to validate the action before publishing"],
                ],
                field_widths,
            ),
            Spacer(1, 5),
            table(
                [
                    ["Required User Decision", "Notes"],
                    ["Which operations become actions", "OpenAPI alone does not grant permission"],
                    ["Whether writes are allowed", "Prototype supports CRUD, but writes require explicit selection"],
                    ["Which fields are exposed/redacted", "Especially for PII, finance, health, confidential data"],
                ],
                value_widths,
            ),
        ],
    )

    story.append(PageBreak())

    story += section(
        "Step 4: Publishing Profile",
        [
            p("This decides which approved actions appear in the MCP."),
            table(
                [
                    ["Field", "Required", "Notes"],
                    ["Profile name", "Yes", "Example: Customer Support"],
                    ["Profile description", "Yes", "Example: Focused tools for support agents"],
                    ["Approved actions", "Yes", "Only approved actions can be added"],
                    ["Large profile confirmation", "Conditional", "Required if profile has more than 30 tools"],
                ],
                field_widths,
            ),
            Spacer(1, 5),
            table(
                [
                    ["Generated Value", "Notes"],
                    ["Profile ID", "Internal"],
                    ["Immutable MCP release", "Created from the profile"],
                    ["Release ID", "For support/debugging"],
                    ["Deployment slug", "Used in MCP URL"],
                    ["Manifest hash", "Identifies exact immutable release"],
                    ["Public MCP URL", "Used by Smithery/MCP clients"],
                    ["Local MCP URL", "Only for local testing"],
                ],
                value_widths,
            ),
        ],
    )

    story += section(
        "Step 5: MCP Testing",
        [
            table(
                [["Field", "Required", "Notes"], ["Tool test arguments", "Recommended", "JSON arguments per generated tool"]],
                field_widths,
            ),
            Spacer(1, 5),
            table(
                [
                    ["System Shows", "Notes"],
                    ["Tool list", "What MCP clients will see"],
                    ["Tool response", "Result from upstream API"],
                    ["Errors/warnings", "Validation, timeout, upstream failure, etc."],
                ],
                value_widths,
            ),
        ],
    )

    story += section(
        "Step 6: Deploy Backend/Frontend",
        [
            p("Backend environment fields:"),
            code_block(
                "PRODUCT_TO_MCP_ENV=production\n"
                "PRODUCT_TO_MCP_DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE\n"
                "PRODUCT_TO_MCP_PUBLIC_BASE_URL=https://api.your-domain.com\n"
                "PRODUCT_TO_MCP_CORS_ORIGINS=https://app.your-domain.com\n"
                "PRODUCT_TO_MCP_ALLOWED_HOSTS=api.your-domain.com\n"
                "PRODUCT_TO_MCP_SMITHERY_API_URL=https://api.smithery.ai\n"
                "PRODUCT_TO_MCP_MAX_OPENAPI_BYTES=20971520\n"
                "PRODUCT_TO_MCP_MAX_CHAIN_STEPS=10\n"
                "PRODUCT_TO_MCP_ACTION_TIMEOUT_SECONDS=60\n"
                "PRODUCT_TO_MCP_UPSTREAM_TIMEOUT_SECONDS=20\n"
                "PRODUCT_TO_MCP_MAX_UPSTREAM_RESPONSE_BYTES=2097152\n"
                "PRODUCT_TO_MCP_ALLOW_LEGACY_RELEASES=false\n"
                "PRODUCT_TO_MCP_MCP_BEARER_TOKEN=\n"
                "PRODUCT_TO_MCP_SECRET_ENCRYPTION_KEY=long-stable-secret"
            ),
            Spacer(1, 5),
            p("Frontend environment field:"),
            code_block("VITE_PRODUCT_TO_MCP_API_BASE_URL=https://api.your-domain.com"),
            p("Important: PRODUCT_TO_MCP_PUBLIC_BASE_URL must be the backend HTTPS URL, not the frontend URL."),
        ],
    )

    story += section(
        "Step 7: Publish to Smithery",
        [
            table(
                [
                    ["Field", "Required", "Notes"],
                    ["Smithery namespace", "Yes", "Example: @acme or acme"],
                    ["Server name/slug", "Yes", "Example: demo-store-mcp"],
                    ["Smithery API key", "Yes", "Submitted once, then cleared"],
                    ["Permission to publish/update server", "Yes", "Must exist in customer's Smithery account"],
                ],
                field_widths,
            ),
            Spacer(1, 5),
            table(
                [
                    ["Publish Readiness Check", "Needed"],
                    ["Public HTTPS MCP URL", "Yes"],
                    ["Streamable HTTP MCP endpoint", "Yes"],
                    ["initialize works", "Yes"],
                    ["tools/list works", "Yes"],
                    ["Smithery API key valid", "Yes"],
                ],
                value_widths,
            ),
        ],
    )

    story += [
        Rule(),
        p("Guardrails", "Section"),
        *bullets(
            [
                "The user must explicitly select capabilities exposed by an MCP release.",
                "A source document never grants permission by itself.",
                "Secrets must not appear in tool schemas, manifests, logs, browser state, or responses.",
                "Each new source revision creates a new release; active releases are never mutated in place.",
            ]
        ),
    ]
    return story


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Product-to-MCP User Fields Checklist",
        author="Product-to-MCP",
    )
    doc.build(build_story(), onFirstPage=header_footer, onLaterPages=header_footer)
    print(OUT)


if __name__ == "__main__":
    main()
