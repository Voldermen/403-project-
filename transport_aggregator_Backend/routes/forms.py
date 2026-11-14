"""Validate provider-specific location identifiers and travel details."""
from datetime import date
from uuid import UUID
from django import forms
from greyhound_search import DALLAS, HOUSTON


class SearchForm(forms.Form):
    origin = forms.CharField(max_length=3, min_length=3, label="From (airport code)")
    destination = forms.CharField(max_length=3, min_length=3, label="To (airport code)")
    travel_date = forms.DateField(label="Departure date", input_formats=["%Y-%m-%d"],
                                  widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    adults = forms.IntegerField(label="Travelers", min_value=1, max_value=9, initial=1)
    include_train = forms.BooleanField(required=False, label="Also search Amtrak")
    train_origin = forms.CharField(max_length=6, required=False, label="From station code")
    train_destination = forms.CharField(max_length=6, required=False, label="To station code")
    include_bus = forms.BooleanField(required=False, label="Also search Greyhound")
    # The Greyhound teammate's module uses city UUIDs (not IATA station codes).
    bus_origin = forms.CharField(max_length=36, required=False, initial=DALLAS, label="Greyhound from-city UUID")
    bus_destination = forms.CharField(max_length=36, required=False, initial=HOUSTON, label="Greyhound to-city UUID")

    def clean_origin(self):
        value = self.cleaned_data["origin"].strip().upper()
        if not value.isalpha() or len(value) != 3:
            raise forms.ValidationError("Enter a three-letter airport code such as MSY.")
        return value

    def clean_destination(self):
        value = self.cleaned_data["destination"].strip().upper()
        if not value.isalpha() or len(value) != 3:
            raise forms.ValidationError("Enter a three-letter airport code such as ORD.")
        return value

    def clean_travel_date(self):
        value = self.cleaned_data["travel_date"]
        if value < date.today():
            raise forms.ValidationError("Choose today or a future date.")
        return value

    def clean(self):
        values = super().clean()
        if values.get("origin") and values.get("origin") == values.get("destination"):
            self.add_error("destination", "Choose a different destination airport.")
        if values.get("include_train"):
            for name in ("train_origin", "train_destination"):
                if not values.get(name):
                    self.add_error(name, "Required when searching Amtrak.")
                elif len(values[name].strip()) != 3 or not values[name].strip().isalpha():
                    self.add_error(name, "Use a three-letter station code, e.g. NOL.")
                else:
                    values[name] = values[name].strip().upper()
            if values.get("train_origin") == values.get("train_destination"):
                self.add_error("train_destination", "Choose different stations.")
        if values.get("include_bus"):
            for name in ("bus_origin", "bus_destination"):
                try:
                    values[name] = str(UUID(values.get(name, "")))
                except (ValueError, TypeError, AttributeError):
                    self.add_error(name, "Enter a valid Greyhound city UUID.")
            if values.get("bus_origin") == values.get("bus_destination"):
                self.add_error("bus_destination", "Choose different cities.")
        return values
