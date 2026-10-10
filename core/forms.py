from django import forms

INPUT_CLASS = "input"
CHECKBOX_CLASS = "h-4 w-4 rounded border-white/20 bg-white/5 text-accent focus:ring-accent"
FILE_CLASS = (
    "block w-full text-sm text-zinc-400 file:mr-4 file:rounded-full file:border-0 file:bg-white/10 "
    "file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white hover:file:bg-white/15"
)


class StyledFormMixin:
    """Apply design-system classes and accessible error attributes to every widget."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", CHECKBOX_CLASS)
            elif isinstance(widget, forms.FileInput):
                widget.attrs.setdefault("class", FILE_CLASS)
            else:
                widget.attrs.setdefault("class", INPUT_CLASS)

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                bound = self[name]
                attrs = self.fields[name].widget.attrs
                attrs["aria-invalid"] = "true"
                attrs["aria-describedby"] = f"{bound.auto_id}-error"
                if INPUT_CLASS in attrs.get("class", "").split():
                    attrs["class"] = f"{INPUT_CLASS} input-invalid"
