from django import forms


class StyledFormMixin:
    """Adds Tailwind classes to every widget so templates stay simple."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "mt-0.5 h-4 w-4 rounded border-slate-300")
            elif isinstance(widget, forms.CheckboxSelectMultiple | forms.RadioSelect):
                continue
            else:
                widget.attrs.setdefault("class", "input")


def split_csv(value):
    return [part.strip() for part in (value or "").split(",") if part.strip()]


class UpperCharField(forms.CharField):
    """Strips and upper-cases input before validators run (PAN, GSTIN, IFSC)."""

    def to_python(self, value):
        value = super().to_python(value)
        return value.strip().upper() if value else value
