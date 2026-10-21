"""Find the fields of an application form in a page's HTML (FR-35).

Pure and offline: it parses markup with the standard library and nothing else. The page is
untrusted data (NFR-07): it is read for structure, never obeyed, and no script in it runs here.
Every fillable control becomes a `FormField` with a label, an inferred type and a required flag;
a control with no discoverable label is kept with a placeholder label, never dropped. Hidden
inputs and buttons are not fields. A page with no form yields an empty list.
"""

from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Final

_SKIPPED_TYPES: Final = frozenset({"hidden", "submit", "button", "reset", "image"})
_KNOWN_TYPES: Final = frozenset(
    {"text", "email", "tel", "number", "url", "date", "password", "checkbox", "radio", "file"}
)
_CONTROLS: Final = frozenset({"input", "textarea", "select"})


@dataclass(frozen=True)
class FormField:
    """One fillable control, or one radio group.

    Attributes:
        key: A stable identifier within the form (`f1`, `f2`...).
        label: What the page calls it, or `Field N` when the page names it nowhere.
        labelled: False if the label is a placeholder because the page gave none.
        type: `text`, `email`, `tel`, `number`, `url`, `date`, `password`, `textarea`, `select`,
            `checkbox`, `radio` or `file`.
        required: Whether the page marks it required.
        name: The control's `name` attribute, if any.
        options: The choices of a select or radio group.
        selector: A Playwright selector that finds exactly this control (or its first radio).
        sensitive: True for a password field: it is listed but never suggested or filled.
    """

    key: str
    label: str
    labelled: bool
    type: str
    required: bool
    name: str | None
    options: tuple[str, ...]
    selector: str
    sensitive: bool


@dataclass
class _Control:
    ordinal: int
    tag: str
    attrs: dict[str, str | None]
    wrapping_label: list[str] = field(default_factory=list)
    options: list[str] = field(default_factory=list)


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class _FormParser(HTMLParser):
    """Collects controls, `label for` texts and wrapping labels in document order."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.controls: list[_Control] = []
        self.label_for: dict[str, str] = {}
        self.forms = 0
        self._label_stack: list[tuple[str | None, list[str]]] = []
        self._select: _Control | None = None
        self._in_option = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "form":
            self.forms += 1
        elif tag == "label":
            self._label_stack.append((a.get("for"), []))
        elif tag in _CONTROLS:
            control = _Control(len(self.controls), tag, a)
            if self._label_stack and self._label_stack[-1][0] is None:
                control.wrapping_label = self._label_stack[-1][1]
            self.controls.append(control)
            self._select = control if tag == "select" else self._select
        elif tag == "option" and self._select is not None:
            self._in_option = True
            self._select.options.append(a.get("value") or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "label" and self._label_stack:
            target, parts = self._label_stack.pop()
            if target:
                self.label_for[target] = " ".join("".join(parts).split())
        elif tag == "select":
            self._select = None
        elif tag == "option":
            self._in_option = False

    def handle_data(self, data: str) -> None:
        if self._label_stack:
            self._label_stack[-1][1].append(data)
        if self._in_option and self._select is not None and not self._select.options[-1]:
            self._select.options[-1] = data.strip()


def _type_of(control: _Control) -> str:
    if control.tag != "input":
        return control.tag
    declared = (control.attrs.get("type") or "text").lower()
    return declared if declared in _KNOWN_TYPES | _SKIPPED_TYPES else "text"


def _label_of(control: _Control, label_for: dict[str, str]) -> str:
    a = control.attrs
    control_id = a.get("id")
    candidates = [
        label_for.get(control_id or ""),
        " ".join("".join(control.wrapping_label).split()),
        a.get("aria-label"),
        a.get("placeholder"),
        a.get("name"),
    ]
    return next((c.strip() for c in candidates if c and c.strip()), "")


def _selector(control: _Control) -> str:
    control_id = control.attrs.get("id")
    if control_id:
        return f"[id={_quote(control_id)}]"
    return f"input, select, textarea >> nth={control.ordinal}"


def analyze_form(html: str) -> list[FormField]:
    """List the fillable fields of the form(s) in `html`.

    Args:
        html: The page's HTML (static, or the DOM after scripts ran).

    Returns:
        The fields in document order; empty if the page has no form or no fillable control.
    """
    parser = _FormParser()
    parser.feed(html)
    parser.close()
    if parser.forms == 0:
        return []
    fields: list[FormField] = []
    seen_radios: dict[str, int] = {}
    for control in parser.controls:
        kind = _type_of(control)
        if kind in _SKIPPED_TYPES or "disabled" in control.attrs:
            continue
        name = control.attrs.get("name")
        if kind == "radio" and name in seen_radios:
            previous = fields[seen_radios[name]]
            value = control.attrs.get("value") or ""
            fields[seen_radios[name]] = FormField(
                **{**previous.__dict__, "options": (*previous.options, value)}
            )
            continue
        label = _label_of(control, parser.label_for)
        number = len(fields) + 1
        options = tuple(control.options)
        if kind == "radio":
            options = (control.attrs.get("value") or "",)
            seen_radios[name or f"_{number}"] = len(fields)
        fields.append(
            FormField(
                key=f"f{number}",
                label=label or f"Field {number}",
                labelled=bool(label),
                type=kind,
                required="required" in control.attrs
                or (control.attrs.get("aria-required") or "").lower() == "true",
                name=name,
                options=options,
                selector=_selector(control),
                sensitive=kind == "password",
            )
        )
    return fields
