from django.contrib import admin
from .models import Club, Station, Race, Member, Pigeon, RaceEntry
from django import forms
from django.contrib.admin.widgets import AdminSplitDateTime
from .models import RaceEntry


# ✅ Inline tipo Excel dentro de la carrera
class RaceEntryInline(admin.TabularInline):
    model = RaceEntry
    extra = 0
    fields = ("pos", "pigeon", "miles", "ypm", "to_win", "df_points", "arrival_time")
    readonly_fields = ("miles", "ypm", "df_points", "to_win", "pos")
    autocomplete_fields = ("pigeon",)
    ordering = ("pos",)


@admin.register(Club)
class ClubAdmin(admin.ModelAdmin):
    list_display = ("name", "acronym")
    search_fields = ("name", "acronym")


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ("name", "official_miles")
    search_fields = ("name",)
    list_filter = ("official_miles",)


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("name", "loft_name", "club", "active", "latitude", "longitude")
    list_filter = ("club", "active")
    search_fields = ("name", "loft_name", "club__name", "club__acronym")

    def get_readonly_fields(self, request, obj=None):
        # Si NO es superuser y el objeto ya existe -> no puede cambiar coords
        if obj is not None and not request.user.is_superuser:
            return ("latitude", "longitude")
        return ()

    def save_model(self, request, obj, form, change):
        # Obligar coords (aunque DB permita null por ahora)
        if obj.latitude is None or obj.longitude is None:
            from django.core.exceptions import ValidationError

            raise ValidationError(
                "Latitude y Longitude son obligatorios para guardar un Member."
            )
        super().save_model(request, obj, form, change)


@admin.register(Pigeon)
class PigeonAdmin(admin.ModelAdmin):
    list_display = ("band_id", "member", "color", "sex")
    list_filter = ("sex",)

    # ✅ ESTO ES OBLIGATORIO por el autocomplete_fields
    search_fields = ("band_id", "member__name", "member__loft_name")


@admin.register(Race)
class RaceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "club",
        "station",
        "season_year",
        "category",
        "miles",
        "release_date",
    )
    list_filter = ("club", "season_year", "category", "station")
    search_fields = ("club__name", "club__acronym", "station__name")
    inlines = [RaceEntryInline]
    ordering = ("-season_year", "club", "category", "station", "race_number")

    # ✅ millas oficiales se copian solas desde Station (no se editan)
    readonly_fields = ("miles", "created_at")


from django.contrib import admin

from .models import RaceEntry


@admin.register(RaceEntry)
class RaceEntryAdmin(admin.ModelAdmin):
    # Orden EXACTO que quieres en el admin
    list_display = (
        "pos",
        "owner_name",
        "band_id",
        "color",
        "sex",
        "arrival",
        "miles",
        "yd_min",
        "to_win_min",
        "points",
    )

    # Para que cargue rápido (evita queries extras)
    list_select_related = ("race", "pigeon", "pigeon__member")

    # Opcional: que sea fácil buscar
    search_fields = (
        "pigeon__band_id",
        "pigeon__member__name",
        "pigeon__member__loft_name",
        "race__name",
    )

    # Opcional: filtros útiles
    list_filter = ("race", "pigeon__sex", "pigeon__color")

    # Opcional: estos campos se calculan, mejor no editarlos a mano
    readonly_fields = ("miles", "ypm", "df_points", "to_win", "pos")

    @admin.display(description="Name", ordering="pigeon__member__name")
    def owner_name(self, obj):
        return str(obj.pigeon.member) if obj.pigeon_id and obj.pigeon.member_id else ""

    @admin.display(description="Band ID", ordering="pigeon__band_id")
    def band_id(self, obj):
        return obj.pigeon.band_id if obj.pigeon_id else ""

    @admin.display(description="Color", ordering="pigeon__color")
    def color(self, obj):
        return obj.pigeon.color if obj.pigeon_id else ""

    @admin.display(description="Sex", ordering="pigeon__sex")
    def sex(self, obj):
        return obj.pigeon.sex if obj.pigeon_id else ""

    @admin.display(description="Arrival", ordering="arrival_time")
    def arrival(self, obj):
        return obj.arrival_time

    @admin.display(description="yd/min", ordering="ypm")
    def yd_min(self, obj):
        return obj.ypm

    @admin.display(description="To win", ordering="to_win")
    def to_win_min(self, obj):
        # tu to_win ya está guardado como minutos (con decimales). Lo mostramos igual.
        return obj.to_win

    @admin.display(description="Points", ordering="df_points")
    def points(self, obj):
        return obj.df_points


class RaceEntryAdminForm(forms.ModelForm):
    class Meta:
        model = RaceEntry
        fields = "__all__"
        widgets = {
            "arrival_time": AdminSplitDateTime(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Fuerza formatos aceptados por el input (12h con AM/PM)
        self.fields["arrival_time"].input_formats = [
            "%m/%d/%Y %I:%M %p",  # 01/28/2026 07:15 PM
            "%Y-%m-%d %I:%M %p",  # 2026-01-28 07:15 PM
            "%m/%d/%Y %H:%M",  # fallback 24h
            "%Y-%m-%d %H:%M",
        ]
