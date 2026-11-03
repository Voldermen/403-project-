from datetime import date

from django import forms

MODE_CHOICES = [
    #("car", "Car"),
    ("planes", "Planes"),
    ("trains", "Trains"),
    ("public_buses", "Public Buses"),
    ("greyhound", "Greyhound"),
]
ALL_MODES = [mode for mode, _ in MODE_CHOICES]


class SearchForm(forms.Form):
    origin = forms.CharField(max_length=180, label="Address A", strip=True)
    destination = forms.CharField(max_length=180, label="Address B", strip=True)
    travel_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
        initial=date.today,
    )
    adults = forms.IntegerField(min_value=1, max_value=9, initial=1, label="Travelers")
    objective = forms.ChoiceField(choices=[("cost", "Lowest cost"), ("time", "Fastest")], initial="cost")
    modes = forms.MultipleChoiceField(choices=MODE_CHOICES, required=False, initial=ALL_MODES)
    origin_lat = forms.FloatField(required=False, widget=forms.HiddenInput())
    origin_lon = forms.FloatField(required=False, widget=forms.HiddenInput())
    destination_lat = forms.FloatField(required=False, widget=forms.HiddenInput())
    destination_lon = forms.FloatField(required=False, widget=forms.HiddenInput())

    def clean_travel_date(self):
        value = self.cleaned_data["travel_date"]
        if value < date.today():
            raise forms.ValidationError("Please select today or a future departure date.")
        return value

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("origin", "").casefold() == cleaned.get("destination", "").casefold():
            self.add_error("destination", "Please choose a different destination.")
        if not cleaned.get("modes"):
            self.add_error("modes", "Select at least one transportation type.")
        for label in ("origin", "destination"):
            lat, lon = cleaned.get(label + "_lat"), cleaned.get(label + "_lon")
            if (lat is None) != (lon is None):
                self.add_error(label, "Please select an address suggestion or reenter the address.")
            # These coordinates only locate U.S. routes. Hide foreign suggestions.
            if lat is not None and not (18 <= lat <= 72 and -180 <= lon <= -60):
                self.add_error(label, "Please enter a location within the United States.")
        return cleaned
