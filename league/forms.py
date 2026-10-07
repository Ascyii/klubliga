from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator

from accounts.models import User

from .models import Match, Season
from .scoring import ScoreError, evaluate


class PartnerSelect(forms.Select):
    """A select whose options carry the member's sex (used to preview the tournament)."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, "instance", None)
        if instance is not None:
            option["attrs"]["data-sex"] = instance.sex
        return option


class PartnerField(forms.ModelChoiceField):
    def label_from_instance(self, user):
        return f"{user.last_name}, {user.first_name}"


class EntryForm(forms.Form):
    kind = forms.ChoiceField(
        label="Format", choices=[("singles", "Singles"), ("doubles", "Doubles")],
        widget=forms.RadioSelect, initial="singles",
    )
    partner = PartnerField(
        queryset=User.objects.none(), required=False, widget=PartnerSelect,
        empty_label="– choose your partner –",
        help_text="Members appear here after their first login.",
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["partner"].queryset = (
            User.objects.filter(is_active=True, last_login__isnull=False).exclude(pk=user.pk)
        )

    def clean(self):
        data = super().clean()
        if data.get("kind") == "doubles":
            if not data.get("partner"):
                self.add_error("partner", "Please choose your partner.")
        else:
            data["partner"] = None
        return data


class ResultForm(forms.Form):
    """Set-by-set score entry; admins can also choose walkover, not played or open."""

    def __init__(self, *args, match, admin=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.match = match
        self.rules = match.season.rules
        current = match.sets() if match.status == Match.Status.PLAYED else []
        for index in range(self.rules.best_of):
            for side in (1, 2):
                name = f"s{index + 1}_{side}"
                self.fields[name] = forms.IntegerField(
                    required=False, min_value=0, max_value=99,
                    widget=forms.NumberInput(attrs={"inputmode": "numeric", "min": 0, "max": 99}),
                )
                if index < len(current):
                    self.initial[name] = current[index][side - 1]
        if admin:
            choices = [
                ("played", "Played – score below"),
                ("w1", f"Walkover – {match.entry1} wins"),
                ("w2", f"Walkover – {match.entry2} wins"),
            ]
            if not match.is_knockout:
                choices.append(("cancelled", "Not played"))
            choices.append(("pending", "Open – no result yet"))
            initial = {
                Match.Status.WALKOVER: "w1" if match.winner_id == match.entry1_id else "w2",
                Match.Status.CANCELLED: "cancelled",
                Match.Status.PENDING: "played",
            }.get(match.status, "played")
            self.fields["outcome"] = forms.ChoiceField(
                label="Result", choices=choices, initial=initial, widget=forms.RadioSelect)

    def set_rows(self):
        rows = []
        for index in range(self.rules.best_of):
            tiebreak = self.rules.is_tiebreak_set(index)
            rows.append({
                "label": "Match tie-break" if tiebreak else f"Set {index + 1}",
                "tiebreak": tiebreak,
                "side1": self[f"s{index + 1}_1"],
                "side2": self[f"s{index + 1}_2"],
            })
        return rows

    def clean(self):
        data = super().clean()
        if data.get("outcome", "played") != "played":
            return data
        sets, gap = [], False
        for index in range(self.rules.best_of):
            a, b = data.get(f"s{index + 1}_1"), data.get(f"s{index + 1}_2")
            if a is None and b is None:
                gap = True
                continue
            if a is None or b is None:
                raise forms.ValidationError(f"Set {index + 1}: please enter the score of both sides.")
            if gap:
                raise forms.ValidationError("Please fill in the sets in order.")
            sets.append((a, b))
        try:
            evaluate(sets, self.rules)
        except ScoreError as error:
            raise forms.ValidationError(str(error)) from None
        data["sets"] = sets
        return data


class SeasonForm(forms.ModelForm):
    class Meta:
        model = Season
        fields = Season.SETTING_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        limits = {"games_per_set": (1, 9), "match_tiebreak_points": (5, 21), "two_groups_from": (4, 99)}
        for name, (low, high) in limits.items():
            field = self.fields[name]
            field.validators += [MinValueValidator(low), MaxValueValidator(high)]
            field.widget.attrs.update(min=low, max=high)
